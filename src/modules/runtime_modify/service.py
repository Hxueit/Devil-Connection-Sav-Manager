"""启动游戏，并通过 Chrome DevTools Protocol (CDP) 在游戏里执行 JS

游戏是 NW.js 程序，带 --remote-debugging-port 启动后，从 http://127.0.0.1:<port>/json/list
拿到页面的 webSocketDebuggerUrl，连上后发 Runtime.evaluate 就能读写 TYRANO 的变量。
这里的函数都是阻塞的，界面代码要放到后台线程里调用。
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
from typing import Any

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
_WS_CONNECT_OPTIONS: dict[str, Any] = (
    {"proxy": None} if "proxy" in inspect.signature(connect).parameters else {}
)

# 游戏里保存变量的 JS 对象
SF_JS_PATH = "TYRANO.kag.variable.sf"       # 系统变量（对应 DevilConnection_sf.sav）
KAG_STAT_JS_PATH = "TYRANO.kag.stat"        # 当前游戏状态（不会自动保存）

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


class CdpError(Exception):
    """与游戏通信失败，或在游戏里执行的 JS 出错"""


class GameNotConnectedError(CdpError):
    """连不上游戏页面（游戏没运行，或调试端口还没就绪）"""


class MarkReadRefusedError(CdpError):

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class LaunchError(Exception):
    """info 是已经拿到的启动详情；still_starting 表示超时了但进程还在（Steam 启动较慢）"""

    def __init__(self, message: str, info: dict[str, Any], still_starting: bool = False) -> None:
        super().__init__(message)
        self.info = info
        self.still_starting = still_starting


def check_port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            # connect_ex 返回 0 表示连上了，即端口已被占用
            return sock.connect_ex(("127.0.0.1", port)) != 0
    except OSError:
        return False


def get_game_exe_path(storage_dir: str) -> Path | None:
    exe_path = Path(storage_dir).parent / GAME_EXE_NAME
    return exe_path if exe_path.is_file() else None


def _target_score(target: dict[str, Any]) -> int:
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


def fetch_target(port: int, timeout: float = 5.0) -> dict[str, Any] | None:
    try:
        with _http_opener.open(f"http://127.0.0.1:{port}/json/list", timeout=timeout) as response:
            targets = json.load(response)
    except (OSError, ValueError):
        return None
    # 端口上也可能是别的程序，回复不一定是 CDP 的页面列表
    if not isinstance(targets, list):
        return None
    pages = [t for t in targets if t.get("type") in ("page", "webview") and t.get("webSocketDebuggerUrl")]
    return max(pages, key=_target_score, default=None)


def fetch_ws_url(port: int, timeout: float = 5.0) -> str | None:
    target = fetch_target(port, timeout)
    return target["webSocketDebuggerUrl"] if target else None


def evaluate(ws_url: str, expression: str, timeout: float = EVAL_TIMEOUT) -> Any:
    """在游戏页面执行 JS 并返回结果；连不上、超时或 JS 抛异常时抛出 CdpError"""
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
        raise CdpError("Timed out waiting for the game to respond") from None
    except (OSError, WebSocketException, ValueError) as e:
        raise CdpError(f"WebSocket connection failed: {e}") from e

    if "error" in message:
        raise CdpError(message["error"].get("message", str(message["error"])))
    result = message.get("result", {})
    if "exceptionDetails" in result:
        details = result["exceptionDetails"]
        raise CdpError(details.get("exception", {}).get("description") or details.get("text") or "JavaScript error")
    return result.get("result", {}).get("value")


def read_json_variable(ws_url: str, js_path: str) -> dict[str, Any]:
    # 先在游戏里 JSON.stringify，避免 CDP 按值返回时丢掉复杂结构
    text = evaluate(ws_url, f"JSON.stringify({js_path})")
    if text is None:   # 变量是 undefined
        raise CdpError("Read data is empty")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise CdpError(f"Parsed data is not a dictionary type: {type(data).__name__}")
    return data


def assign_json_variable(ws_url: str, js_path: str, data: dict[str, Any], save_system_variable: bool = False) -> None:
    if not data:
        raise CdpError("Cannot inject empty data")
    # JSON 本身就是合法的 JS 字面量，直接嵌入即可，不需要再转义
    save = "TYRANO.kag.saveSystemVariable();" if save_system_variable else ""
    expression = (
        f"(function() {{ try {{ Object.assign({js_path}, {json.dumps(data)}); {save} return true; }}"
        " catch (e) { return e.toString(); } })()"
    )
    result = evaluate(ws_url, expression)
    if result is not True:
        raise CdpError(result)   # JS 的错误描述


def inject_and_save_sf(ws_url: str, edited_data: dict[str, Any]) -> None:
    """把编辑后的 sf 深度合并到游戏当前的 sf 上，再调用 saveSystemVariable 写入存档"""
    if not edited_data:
        raise CdpError("Cannot inject empty data")
    current = read_json_variable(ws_url, SF_JS_PATH)
    assign_json_variable(ws_url, SF_JS_PATH, deep_merge(current, edited_data), save_system_variable=True)


def mark_current_label_read(ws_url: str) -> None:
    result = evaluate(ws_url, _JS_MARK_CURRENT_LABEL_READ)
    if not result["success"]:
        raise MarkReadRefusedError(result["message"])
    logger.info(f"Label marked as read: {result['label']}")


def deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """递归合并字典：两边都是 dict 的键继续合并，其余（包括数组）用 source 的值替换"""
    merged = copy.deepcopy(target)
    for key, value in source.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def describe_changes(original: dict[str, Any], current: dict[str, Any]) -> list[str]:
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


def _steam_launch_commands(exe_path: Path, port: int) -> list[list[str]]:
    """Steam 版必须经由 Steam 启动（直接运行 exe 会被 Steam 重新拉起而丢失参数）；不是 Steam 版时返回空列表"""
    parts = exe_path.resolve().parts
    lower_parts = [p.lower() for p in parts]
    if "steamapps" not in lower_parts or "common" not in lower_parts:
        return []

    args = ["-applaunch", GAME_STEAM_APP_ID, f"--remote-debugging-port={port}"]
    commands = []
    # Steam 根目录 = steamapps 的上一级
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


def _mark_window_title(ws_url: str) -> None:
    suffix = json.dumps(" - DCSM Injected")
    try:
        evaluate(ws_url, f"if (!document.title.includes({suffix})) {{ document.title += {suffix}; }} true")
    except CdpError:
        pass


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

    def __init__(self, game_exe_path: Path | None) -> None:
        self.game_exe_path = game_exe_path
        self.game_process: subprocess.Popen[bytes] | None = None
        self.launch_mode = "unknown"   # "steam" 或 "direct"

    def launch_game(self, exe_path: Path, port: int) -> None:
        self.game_exe_path = exe_path
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

    def launch_and_test(self, exe_path: Path, port: int) -> dict[str, Any]:
        """启动游戏并等待 TYRANO 就绪，返回启动详情；失败或超时抛出 LaunchError"""
        info: dict[str, Any] = {}
        try:
            self.launch_game(exe_path, port)
        except OSError as e:
            raise LaunchError(f"Failed to start game: {e}", info) from e
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
                try:
                    tyrano_type = evaluate(ws_url, "typeof TYRANO")
                except CdpError as e:
                    last_error = str(e)
                else:
                    info["tyrano_type"] = tyrano_type
                    if tyrano_type == "object":
                        _mark_window_title(ws_url)
                        info["ws_url"] = ws_url
                        ws_path = ws_url[len("ws://"):] if ws_url.startswith("ws://") else ws_url
                        info["inspector_url"] = f"http://127.0.0.1:{port}/devtools/inspector.html?ws={ws_path}"
                        return info
                    # 页面还在加载时 TYRANO 可能还未定义，继续等
                    last_error = f"typeof TYRANO = {tyrano_type} (expected 'object')"
            time.sleep(CDP_RETRY_DELAY)

        logger.warning(f"CDP/TYRANO not ready within {max_wait:.0f}s (mode={self.launch_mode}, error={last_error})")
        if self.is_process_running():
            raise LaunchError("Game may not be fully started yet, retrying...", info, still_starting=True)
        raise LaunchError(last_error or "Cannot connect to CDP debug port", info)

    def is_process_running(self) -> bool:
        if self.game_process is not None:
            if self.game_process.poll() is None:
                return True
            self.game_process = None   # 已退出（Steam 启动器会很快退出）
        return self.game_exe_path is not None and _is_exe_running(self.game_exe_path.name)

    def poll_status(self, port: int | None) -> tuple[bool, str | None]:
        """检查一次状态，返回 (游戏是否在运行, ws_url)；ws_url 不为 None 表示可以注入"""
        ws_url = fetch_ws_url(port, timeout=0.8) if port else None
        if ws_url:
            return True, ws_url
        return self.is_process_running(), None

    def stop_game(self, port: int | None) -> None:
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
            try:
                evaluate(ws_url, "window.close(); true", timeout=2)
            except CdpError:
                pass   # 窗口关闭时连接常常来不及回复
