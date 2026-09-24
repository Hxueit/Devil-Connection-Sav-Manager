"""运行时修改：启动游戏，并通过 Chrome DevTools Protocol (CDP) 在游戏里执行 JS

游戏是 NW.js 程序。带 --remote-debugging-port=<port> 启动后：
    1. GET http://127.0.0.1:<port>/json/list 得到页面列表，每个页面有 webSocketDebuggerUrl
    2. 连上这个 WebSocket，发送 Runtime.evaluate 就能在游戏页面里执行 JS，
       从而读写 TyranoScript 的变量（TYRANO.kag.variable.sf、TYRANO.kag.stat 等）

本模块的函数都是同步阻塞的（网络请求、等待进程），界面代码要放到后台线程里调用。
"""
import copy
import inspect
import json
import logging
import platform
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

logger = logging.getLogger(__name__)

DEFAULT_PORT = 1145
MIN_PORT = 1
MAX_PORT = 65535

GAME_EXE_NAME = "DevilConnection.exe"
GAME_STEAM_APP_ID = "3054820"

GAME_STARTUP_DELAY = 3.0        # 启动后先等一会儿再连 CDP
CDP_RETRY_DELAY = 1.0
DIRECT_CDP_MAX_WAIT = 10.0      # 直接启动 exe 时等待 CDP 就绪的最长时间
STEAM_CDP_MAX_WAIT = 60.0       # 通过 Steam 启动要慢得多
EVAL_TIMEOUT = 15.0             # 单条 JS 最长等待时间（awaitPromise 可能一直不返回）
_MAX_MESSAGE_SIZE = 10 * 1024 * 1024

# 访问本机调试端口时不能走系统代理（Clash 等代理软件会设置系统代理）
_http_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# websockets 15+ 默认也会使用系统代理；旧版本没有这个参数
_WS_CONNECT_OPTIONS: Dict[str, Any] = (
    {"proxy": None} if "proxy" in inspect.signature(connect).parameters else {}
)

_INJECTED_TITLE_SUFFIX = " - DCSM Injected"

# 把当前 label 标记为已读，这样游戏会允许快进（模仿 TyranoScript 自动记录已读的逻辑）
_JS_MARK_CURRENT_LABEL_READ = """(function() {
    if (typeof TYRANO === 'undefined' || !TYRANO.kag) {
        return { success: false, message: 'tyrano_not_ready' };
    }
    try {
        if (TYRANO.kag.config.autoRecordLabel != 'true') {
            return { success: false, message: 'game_not_using_read_record' };
        }
        const currentLabel = TYRANO.kag.stat.buff_label_name;
        if (!currentLabel) {
            return { success: false, message: 'not_in_any_label' };
        }
        if (!TYRANO.kag.tmp.record) {
            TYRANO.kag.tmp.record = new Map(TYRANO.kag.variable.sf.record || []);
        }
        const record = TYRANO.kag.tmp.record;
        record.set(currentLabel, (record.get(currentLabel) || 0) + 1);
        TYRANO.kag.variable.sf.record = Array.from(record);
        TYRANO.kag.saveSystemVariable();
        TYRANO.kag.stat.already_read = true;
        $('.skip_button.event-setting-element').removeClass('unread');
        return { success: true, message: 'marked_as_read', label: currentLabel };
    } catch (e) {
        return { success: false, message: 'error: ' + e.message };
    }
})()"""


# ---------------------------------------------------------------- 端口 / 路径

def check_port_available(port: int) -> bool:
    """端口没有被占用时返回 True"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            # connect_ex 返回 0 表示连上了，即端口已被占用
            return sock.connect_ex(("127.0.0.1", port)) != 0
    except OSError as e:
        logger.debug(f"Port check error: {e}")
        return False


def get_game_exe_path(storage_dir: Optional[str]) -> Optional[Path]:
    """游戏 exe 位于 _storage 目录的上一级；找不到时返回 None"""
    if not storage_dir:
        return None
    exe_path = Path(storage_dir).parent / GAME_EXE_NAME
    return exe_path if exe_path.is_file() else None


# ---------------------------------------------------------------- CDP

def _target_score(target: Dict[str, Any]) -> int:
    """给 CDP 页面打分，分数越高越可能是游戏主页面"""
    title = (target.get("title") or "").lower()
    url = (target.get("url") or "").lower()

    if any(word in title for word in ("devtools", "steam", "about:blank")):
        return -100
    if url.startswith(("devtools://", "chrome://", "edge://", "about:blank", "chrome-extension://", "steam://")):
        return -100

    score = 0
    if any(word in title for word in ("恶魔", "devil", "でびる")):
        score += 10
    if "app.asar" in url or "index.html" in url:
        score += 5
    if url.startswith("file://"):
        score += 3
    if "tyrano" in url or "kag" in url:
        score += 8
    return score


def fetch_target(port: int, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """从调试端口取得游戏页面信息（含 webSocketDebuggerUrl）；连不上时返回 None"""
    try:
        with _http_opener.open(f"http://127.0.0.1:{port}/json/list", timeout=timeout) as response:
            targets = json.load(response)
    except (OSError, ValueError) as e:
        logger.debug(f"CDP list request failed on port {port}: {e}")
        return None

    if not isinstance(targets, list):
        return None
    pages = [
        t for t in targets
        if isinstance(t, dict) and t.get("type") in ("page", "webview") and t.get("webSocketDebuggerUrl")
    ]
    return max(pages, key=_target_score, default=None)


def fetch_ws_url(port: int, timeout: float = 5.0) -> Optional[str]:
    target = fetch_target(port, timeout)
    return target["webSocketDebuggerUrl"] if target else None


def evaluate(ws_url: str, expression: str, timeout: float = EVAL_TIMEOUT) -> Tuple[Any, Optional[str]]:
    """在游戏页面执行 JS 表达式，返回 (结果值, 错误信息)

    结果按值返回（对象会变成 dict/list），JS 抛出的异常也作为错误信息返回。
    """
    request = {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {"expression": expression, "returnByValue": True, "awaitPromise": True},
    }
    try:
        with connect(ws_url, max_size=_MAX_MESSAGE_SIZE, open_timeout=5, close_timeout=2,
                     **_WS_CONNECT_OPTIONS) as ws:
            ws.send(json.dumps(request))
            deadline = time.monotonic() + timeout
            while True:
                # 页面可能同时推送其它事件，只取我们这条请求的回复
                message = json.loads(ws.recv(timeout=max(0.0, deadline - time.monotonic())))
                if message.get("id") == 1:
                    break
    except TimeoutError:
        return None, "Timed out waiting for the game to respond"
    except (OSError, WebSocketException, ValueError) as e:
        logger.debug(f"CDP evaluate failed: {e}")
        return None, f"WebSocket connection failed: {e}"

    if "error" in message:
        return None, message["error"].get("message", str(message["error"]))
    result = message.get("result", {})
    if "exceptionDetails" in result:
        details = result["exceptionDetails"]
        return None, details.get("exception", {}).get("description") or details.get("text") or "JavaScript error"
    return result.get("result", {}).get("value"), None


def read_json_variable(ws_url: str, js_path: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """读取游戏里的一个对象变量（如 TYRANO.kag.variable.sf），返回 (dict, 错误信息)"""
    # 先在游戏里 JSON.stringify，避免 CDP 按值返回时丢掉复杂结构
    text, error = evaluate(ws_url, f"JSON.stringify({js_path})")
    if error is not None:
        return None, error
    if not isinstance(text, str):
        return None, "Read data is empty"
    try:
        data = json.loads(text)
    except ValueError as e:
        return None, f"JSON parsing failed: {e}"
    if not isinstance(data, dict):
        return None, f"Parsed data is not a dictionary type: {type(data).__name__}"
    return data, None


def assign_json_variable(
    ws_url: str, js_path: str, data: Dict[str, Any], save_system_variable: bool = False
) -> Tuple[bool, Optional[str]]:
    """用 Object.assign 把 data 写入游戏里的对象变量，返回 (是否成功, 错误信息)"""
    if not data:
        return False, "Cannot inject empty data"
    # JSON 本身就是合法的 JS 字面量，直接嵌入即可，不需要再转义
    save = "TYRANO.kag.saveSystemVariable();" if save_system_variable else ""
    expression = (
        f"(function() {{ try {{ Object.assign({js_path}, {json.dumps(data)}); {save} return true; }}"
        " catch (e) { return e.toString(); } })()"
    )
    result, error = evaluate(ws_url, expression)
    if error is not None:
        return False, error
    if result is True:
        return True, None
    return False, result if isinstance(result, str) else f"Unknown return result: {result}"


def deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典：两边都是 dict 的键继续合并，其余（包括数组）用 source 的值替换"""
    merged = copy.deepcopy(target)
    for key, value in source.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def describe_changes(original: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
    """逐个顶层键列出两份数据的差异"""
    lines = []
    for key in sorted(set(original) | set(current)):
        old, new = original.get(key), current.get(key)
        if old == new:
            continue
        if isinstance(old, dict) or isinstance(new, dict):
            lines.append(f"  {key}: Object changed")
        elif isinstance(old, list) or isinstance(new, list):
            old_len = len(old) if isinstance(old, list) else "N/A"
            new_len = len(new) if isinstance(new, list) else "N/A"
            lines.append(f"  {key}: Array changed (length: {old_len} -> {new_len})")
        else:
            lines.append(f"  {key}: {old} -> {new}")
    return lines


# ---------------------------------------------------------------- 游戏进程

def _steam_launch_commands(exe_path: Path, port: int) -> List[List[str]]:
    """Steam 版必须经由 Steam 启动（直接运行 exe 会被 Steam 重新拉起而丢失参数）"""
    args = ["-applaunch", GAME_STEAM_APP_ID, f"--remote-debugging-port={port}"]
    commands: List[List[str]] = []

    # Steam 根目录 = steamapps 的上一级
    parts = exe_path.resolve().parts
    lower_parts = [p.lower() for p in parts]
    if "steamapps" in lower_parts:
        steam_root = Path(*parts[:lower_parts.index("steamapps")])
        names = ["steam.exe"] if platform.system() == "Windows" else ["steam.sh", "steam"]
        for name in names:
            if (steam_root / name).is_file():
                commands.append([str(steam_root / name), *args])
                break

    if shutil.which("steam"):
        commands.append(["steam", *args])
    if platform.system() != "Windows" and shutil.which("flatpak"):
        commands.append(["flatpak", "run", "com.valvesoftware.Steam", *args])
    return commands


def _is_steam_install(exe_path: Path) -> bool:
    try:
        lower_parts = [p.lower() for p in exe_path.resolve().parts]
    except OSError:
        return False
    return "steamapps" in lower_parts and "common" in lower_parts


def _is_exe_running(exe_name: str) -> bool:
    """用 tasklist 按进程名检测游戏（可以发现不是由本工具启动的游戏），仅 Windows"""
    if platform.system() != "Windows":
        return False
    try:
        output = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return exe_name.lower() in output.lower()


class RuntimeModifyService:
    """管理由本工具启动的游戏进程，并提供游戏内变量的读写

    sf 查看器（save_analysis/sf）通过 ViewerConfig.service 拿到这个对象，
    调用下面几个 async 方法。
    """

    def __init__(self, game_exe_path: Optional[Path] = None) -> None:
        self.game_exe_path = game_exe_path
        self.game_process: Optional["subprocess.Popen[bytes]"] = None
        self.launch_mode = "unknown"   # "steam" 或 "direct"

    def launch_game(self, exe_path: Path, port: int) -> None:
        """依次尝试 Steam 启动命令和直接启动 exe，第一个能启动的即成功

        Raises:
            OSError: 所有方式都启动失败
        """
        self.game_exe_path = exe_path
        attempts = []
        if _is_steam_install(exe_path):
            attempts = [("steam", cmd) for cmd in _steam_launch_commands(exe_path, port)]
        attempts.append(("direct", [str(exe_path), f"--remote-debugging-port={port}"]))

        errors = []
        for mode, cmd in attempts:
            logger.info(f"Launching game ({mode}): {' '.join(cmd)}")
            try:
                self.game_process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as e:
                logger.warning(f"{mode} launch failed: {e}")
                errors.append(f"{mode} launch failed: {e}")
                continue
            self.launch_mode = mode
            return
        raise OSError(" | ".join(errors))

    def launch_and_test(self, exe_path: Path, port: int) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """启动游戏并等待 TYRANO 就绪，返回 (是否成功, 错误信息, 详情)

        详情可能包含 launch_mode、target_title、target_url、tyrano_type、ws_url、inspector_url；
        超时但游戏进程还在时 pending_cdp 为 True（游戏还没完全启动）。
        """
        info: Dict[str, Any] = {}
        try:
            self.launch_game(exe_path, port)
        except OSError as e:
            return False, f"Failed to start game: {e}", info
        info["launch_mode"] = self.launch_mode

        time.sleep(GAME_STARTUP_DELAY)
        max_wait = STEAM_CDP_MAX_WAIT if self.launch_mode == "steam" else DIRECT_CDP_MAX_WAIT
        deadline = time.monotonic() + max_wait
        last_error = None
        while time.monotonic() < deadline:
            target = fetch_target(port)
            if target:
                ws_url = target["webSocketDebuggerUrl"]
                info["target_title"] = target.get("title", "")
                info["target_url"] = target.get("url", "")
                tyrano_type, error = evaluate(ws_url, "typeof TYRANO")
                if error is None:
                    info["tyrano_type"] = tyrano_type
                if tyrano_type == "object":
                    self._mark_window_title(ws_url)
                    info["ws_url"] = ws_url
                    ws_path = ws_url[len("ws://"):] if ws_url.startswith("ws://") else ws_url
                    info["inspector_url"] = f"http://127.0.0.1:{port}/devtools/inspector.html?ws={ws_path}"
                    return True, None, info
                # 页面还在加载时 TYRANO 可能还未定义，继续等
                last_error = error or f"typeof TYRANO = {tyrano_type} (expected 'object')"
            time.sleep(CDP_RETRY_DELAY)

        logger.warning(f"CDP/TYRANO not ready within {max_wait:.0f}s (mode={self.launch_mode}, error={last_error})")
        if self.is_process_running():
            info["pending_cdp"] = True
            return False, "Game may not be fully started yet, retrying...", info
        return False, last_error or "Cannot connect to CDP debug port", info

    def _mark_window_title(self, ws_url: str) -> None:
        """在游戏窗口标题后加上标记，方便用户确认已被注入"""
        suffix = json.dumps(_INJECTED_TITLE_SUFFIX)
        evaluate(ws_url, f"if (!document.title.includes({suffix})) {{ document.title += {suffix}; }} true")

    def is_process_running(self) -> bool:
        """本工具启动的进程还活着，或（Windows）系统里有游戏进程"""
        if self.game_process is not None:
            if self.game_process.poll() is None:
                return True
            self.game_process = None   # 已退出（Steam 启动器会很快退出）
        return self.game_exe_path is not None and _is_exe_running(self.game_exe_path.name)

    def poll_status(self, port: Optional[int]) -> Tuple[bool, Optional[str]]:
        """检查一次状态，返回 (游戏是否在运行, ws_url)；ws_url 不为 None 表示可以注入"""
        ws_url = fetch_ws_url(port, timeout=0.8) if port else None
        if ws_url:
            return True, ws_url
        return self.is_process_running(), None

    def stop_game(self, port: Optional[int]) -> None:
        """结束本工具启动的进程，再通过 CDP 关闭游戏窗口（Steam 启动的游戏不是我们的子进程）"""
        process, self.game_process = self.game_process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning("Process termination timeout, forcing kill")
                process.kill()
                process.wait()

        ws_url = fetch_ws_url(port, timeout=0.8) if port else None
        if ws_url:
            evaluate(ws_url, "window.close(); true", timeout=2)

    def mark_current_label_read(self, ws_url: str) -> Tuple[bool, Optional[str]]:
        """强制快进：把当前 label 标记为已读"""
        result, error = evaluate(ws_url, _JS_MARK_CURRENT_LABEL_READ)
        if error is not None:
            return False, error
        if not isinstance(result, dict):
            return False, f"Unexpected result type: {type(result).__name__}"
        if result.get("success"):
            logger.info(f"Label marked as read: {result.get('label', '')}")
            return True, None
        return False, result.get("message", "")

    # 以下方法由 sf 查看器在它自己的事件循环里以协程方式调用，所以保留 async；
    # 方法体是同步阻塞的，调用方本来就在后台线程里运行它们。

    async def read_tyrano_variable_sf(self, ws_url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        return read_json_variable(ws_url, "TYRANO.kag.variable.sf")

    async def read_tyrano_kag_stat(self, ws_url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        return read_json_variable(ws_url, "TYRANO.kag.stat")

    async def inject_kag_stat(self, ws_url: str, edited_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """写入 kag.stat（只改内存，不保存）"""
        return assign_json_variable(ws_url, "TYRANO.kag.stat", edited_data)

    async def inject_and_save_sf(self, ws_url: str, edited_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """把编辑后的 sf 深度合并到游戏当前的 sf 上，再调用 saveSystemVariable 保存"""
        if not edited_data:
            return False, "Cannot inject empty data"
        current, error = read_json_variable(ws_url, "TYRANO.kag.variable.sf")
        if error is not None:
            return False, f"Failed to read current data: {error}"
        merged = deep_merge(current, edited_data)
        return assign_json_variable(ws_url, "TYRANO.kag.variable.sf", merged, save_system_variable=True)

    async def check_sf_changes(self, ws_url: str, original_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """游戏内存里的 sf 与 original_data 不同时返回 (True, {"changes_text": 差异说明})"""
        current, error = read_json_variable(ws_url, "TYRANO.kag.variable.sf")
        if error is not None:
            logger.warning(f"Failed to read current sf data for change detection: {error}")
            return False, {"changes_text": "", "error": error}
        if current == original_data:
            return False, {"changes_text": ""}
        changes = describe_changes(original_data, current)
        return True, {"changes_text": "\n".join(changes) or "Unknown changes detected", "changes": changes}
