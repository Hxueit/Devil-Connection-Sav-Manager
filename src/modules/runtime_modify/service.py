"""运行时修改服务层

负责进程启动、CDP连接管理和JS注入执行。
"""
import asyncio
import json
import logging
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional, Tuple, Dict, Any, List, Set

import requests
import websockets
from websockets.exceptions import WebSocketException

from src.modules.runtime_modify.config import RuntimeModifyConfig

logger = logging.getLogger(__name__)

# CDP目标类型
_TARGET_TYPES = ("page", "webview")
# 评分关键词
_SCORE_KEYWORDS_TITLE = ("恶魔", "devil", "でびるコネクショん", "でびる")
_SCORE_KEYWORDS_URL = ("app.asar", "index.html")
_EXCLUDE_KEYWORDS_TITLE = ("devtools", "steam", "about:blank")
_EXCLUDE_KEYWORDS_URL = (
    "devtools://",
    "chrome://",
    "edge://",
    "about:blank",
    "chrome-extension://",
    "steam://",
)
# 评分权重
_SCORE_WEIGHT_TITLE = 10
_SCORE_WEIGHT_URL = 5
# TYRANO类型期望值
_EXPECTED_TYRANO_TYPE = "object"
# WebSocket最大消息大小（10MB）
_WEBSOCKET_MAX_SIZE = 10 * 1024 * 1024

# JS表达式常量
_JS_READ_SF_EXPRESSION = "JSON.stringify(TYRANO.kag.variable.sf)"
_JS_INJECT_TEMPLATE = """(function() {{
    try {{
        const data = JSON.parse('{json_data}');
        Object.assign(TYRANO.kag.variable.sf, data);
        TYRANO.kag.saveSystemVariable();
        return true;
    }} catch (e) {{
        return e.toString();
    }}
}})()"""
_JS_READ_KAG_STAT_EXPRESSION = "JSON.stringify(TYRANO.kag.stat)"
_JS_INJECT_KAG_STAT_TEMPLATE = """(function() {{
    try {{
        const data = JSON.parse('{json_data}');
        Object.assign(TYRANO.kag.stat, data);
        return true;
    }} catch (e) {{
        return e.toString();
    }}
}})()"""

_JS_FORCE_FAST_FORWARD_INJECT = """(function() {
    if (typeof TYRANO === 'undefined' || !TYRANO.kag) {
        return { success: false, message: 'tyrano_not_ready' };
    }
    
    try {
        if (TYRANO.kag.config.autoRecordLabel != 'true') {
            return { success: false, message: 'game_not_using_read_record' };
        }
        
        const currentLabel = TYRANO.kag.stat.buff_label_name;
        if (!currentLabel || currentLabel === '') {
            return { success: false, message: 'not_in_any_label' };
        }
        
        if (!TYRANO.kag.tmp.record) {
            if (TYRANO.kag.variable.sf.record) {
                TYRANO.kag.tmp.record = new Map(TYRANO.kag.variable.sf.record);
            } else {
                TYRANO.kag.tmp.record = new Map();
            }
        }
        
        TYRANO.kag.tmp.record.set(currentLabel, (TYRANO.kag.tmp.record.get(currentLabel) || 0) + 1);
        TYRANO.kag.variable.sf.record = Array.from(TYRANO.kag.tmp.record);
        TYRANO.kag.saveSystemVariable();
        TYRANO.kag.stat.already_read = true;
        $('.skip_button.event-setting-element').removeClass('unread');
        
        return { success: true, message: 'marked_as_read', label: currentLabel };
    } catch (e) {
        return { success: false, message: 'error: ' + e.message };
    }
})()"""

_JS_FORCE_FAST_FORWARD_REMOVE = """(function() {
    return { success: true, message: 'no_cleanup_needed' };
})()"""
_INJECTED_TITLE_SUFFIX = " - DCSM Injected"

# JSON转义字符映射
_JSON_ESCAPE_MAP = {
    "\\": "\\\\",
    "'": "\\'",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t"
}

def _escape_json_for_js(json_str: str) -> str:
    """转义JSON字符串以便在JavaScript中使用
    
    Args:
        json_str: 原始JSON字符串
        
    Returns:
        转义后的JSON字符串
    """
    escaped = json_str
    for char, escaped_char in _JSON_ESCAPE_MAP.items():
        escaped = escaped.replace(char, escaped_char)
    return escaped


class RuntimeModifyService:
    """运行时修改服务类
    
    负责管理游戏进程生命周期、CDP连接和JS注入。
    """
    
    def __init__(self) -> None:
        """初始化服务"""
        self.game_process: Optional[subprocess.Popen[bytes]] = None
        self.game_exe_path: Optional[Path] = None  # 保存exe路径，用于检测外部启动的游戏
        self.last_cdp_port: Optional[int] = None
        self.last_launch_mode: str = "unknown"
    
    def _build_exe_launch_cmd(self, exe_path: Path, port: int) -> List[str]:
        """构建直接启动游戏exe的命令"""
        return [
            str(exe_path),
            f"--remote-debugging-port={port}"
        ]
    
    def _is_steam_install_path(self, exe_path: Path) -> bool:
        """根据路径判断是否为Steam库中的安装"""
        try:
            resolved_path = exe_path.resolve()
            lower_parts = [part.lower() for part in resolved_path.parts]
            return "steamapps" in lower_parts and "common" in lower_parts
        except (OSError, RuntimeError):
            return False
    
    def _guess_steam_binary_from_game_path(self, exe_path: Path) -> Optional[str]:
        """根据游戏路径推断Steam可执行文件"""
        try:
            resolved = exe_path.resolve()
            lower_parts = [part.lower() for part in resolved.parts]
            if "steamapps" not in lower_parts:
                return None
            
            steamapps_index = lower_parts.index("steamapps")
            steam_root = Path(*resolved.parts[:steamapps_index])
            
            if platform.system() == "Windows":
                steam_exe = steam_root / "steam.exe"
                if steam_exe.exists() and steam_exe.is_file():
                    return str(steam_exe)
            else:
                steam_sh = steam_root / "steam.sh"
                if steam_sh.exists() and steam_sh.is_file():
                    return str(steam_sh)
                steam_bin = steam_root / "steam"
                if steam_bin.exists() and steam_bin.is_file():
                    return str(steam_bin)
        except (OSError, RuntimeError, ValueError):
            return None
        
        return None
    
    def _build_steam_launch_candidates(self, exe_path: Path, port: int) -> List[List[str]]:
        """构建可能可用的Steam启动命令候选列表"""
        launch_args = [
            "-applaunch",
            RuntimeModifyConfig.GAME_APP_ID,
            f"--remote-debugging-port={port}"
        ]
        
        candidates: List[List[str]] = []
        seen: Set[Tuple[str, ...]] = set()
        
        guessed_steam_binary = self._guess_steam_binary_from_game_path(exe_path)
        if guessed_steam_binary:
            cmd = [guessed_steam_binary, *launch_args]
            candidates.append(cmd)
            seen.add(tuple(cmd))
        
        if shutil.which("steam"):
            cmd = ["steam", *launch_args]
            cmd_key = tuple(cmd)
            if cmd_key not in seen:
                candidates.append(cmd)
                seen.add(cmd_key)
        
        if platform.system() != "Windows" and shutil.which("flatpak"):
            cmd = ["flatpak", "run", "com.valvesoftware.Steam", *launch_args]
            cmd_key = tuple(cmd)
            if cmd_key not in seen:
                candidates.append(cmd)
        
        return candidates
    
    def _start_process(self, cmd: List[str]) -> subprocess.Popen[bytes]:
        """统一的子进程启动封装"""
        creation_flags = (
            subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0
        )
        
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags
        )
    
    def _is_cdp_alive(self, port: Optional[int]) -> bool:
        """通过CDP端口探测判断游戏是否仍在运行"""
        if not isinstance(port, int):
            return False
        
        if not (RuntimeModifyConfig.MIN_PORT <= port <= RuntimeModifyConfig.MAX_PORT):
            return False
        
        url = RuntimeModifyConfig.CDP_LIST_URL_TEMPLATE.format(port=port)
        url += f"?{RuntimeModifyConfig.CDP_TIMEOUT_PARAM}={int(time.time() * 1000)}"
        
        try:
            response = requests.get(url, timeout=RuntimeModifyConfig.CDP_PING_TIMEOUT)
            response.raise_for_status()
            target_list = response.json()
            if not isinstance(target_list, list):
                return False
            return self.pick_target(target_list) is not None
        except (requests.RequestException, ValueError, TypeError):
            return False
    
    async def _close_game_via_cdp(self, port: int) -> bool:
        """尝试通过CDP执行window.close关闭游戏窗口"""
        ws_url, _ = await self.fetch_ws_url(port)
        if not ws_url:
            return False
        
        _, error = await self.eval_expr(ws_url, "window.close(); true")
        return error is None
    
    def launch_game(self, exe_path: Path, port: int) -> subprocess.Popen[bytes]:
        """启动游戏进程
        
        Args:
            exe_path: 游戏可执行文件路径
            port: CDP调试端口
            
        Returns:
            启动的进程对象
            
        Raises:
            FileNotFoundError: 如果游戏可执行文件不存在
            subprocess.SubprocessError: 如果启动进程失败
            ValueError: 如果端口号无效
        """
        if not isinstance(exe_path, Path):
            raise TypeError(f"exe_path must be Path, got {type(exe_path)}")
        
        if not exe_path.exists():
            raise FileNotFoundError(
                f"Game executable not found: {exe_path}"
            )
        
        if not exe_path.is_file():
            raise ValueError(f"Path is not a file: {exe_path}")
        
        if not (RuntimeModifyConfig.MIN_PORT <= port <= RuntimeModifyConfig.MAX_PORT):
            raise ValueError(
                f"Port {port} out of range [{RuntimeModifyConfig.MIN_PORT}, "
                f"{RuntimeModifyConfig.MAX_PORT}]"
            )
        
        # 保存exe路径，用于后续检测外部启动的游戏
        self.game_exe_path = exe_path
        self.last_cdp_port = port
        
        launch_attempts: List[Tuple[str, List[str]]] = []
        
        if self._is_steam_install_path(exe_path):
            for steam_cmd in self._build_steam_launch_candidates(exe_path, port):
                launch_attempts.append(("steam", steam_cmd))
        
        launch_attempts.append(("direct", self._build_exe_launch_cmd(exe_path, port)))
        
        errors: List[str] = []
        
        for launch_type, cmd in launch_attempts:
            logger.info(f"Launching game ({launch_type}): {' '.join(cmd)}")
            try:
                self.game_process = self._start_process(cmd)
                self.last_launch_mode = launch_type
                return self.game_process
            except OSError as e:
                error_msg = f"{launch_type} launch failed: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)
        
        raise subprocess.SubprocessError("Failed to start process: " + " | ".join(errors))
    
    def is_game_running(self) -> bool:
        """检查游戏进程是否仍在运行
        
        优先检查自己启动的进程，如果不存在则通过exe路径检测系统进程。
        这样可以检测到从其他途径启动的游戏。
        
        Returns:
            如果进程正在运行返回True，否则返回False
        """
        # 快速路径：检查自己启动的进程
        if self.game_process is not None:
            if self.game_process.poll() is None:
                return True
            # 进程已结束，清除引用
            self.game_process = None
        
        # 回退路径：通过exe路径检测系统进程（可以检测外部启动的游戏）
        if self.game_exe_path:
            from src.modules.runtime_modify.utils import is_game_running_by_path
            if is_game_running_by_path(self.game_exe_path):
                return True
        
        return self._is_cdp_alive(self.last_cdp_port)
    
    def stop_game(self) -> None:
        """关闭游戏进程
        
        先尝试优雅终止（terminate），如果超时则强制杀死（kill）。
        """
        process = self.game_process
        self.game_process = None
        
        if process is not None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=RuntimeModifyConfig.GAME_STARTUP_DELAY)
                except subprocess.TimeoutExpired:
                    logger.warning("Process termination timeout, forcing kill")
                    process.kill()
                    process.wait()
            except ProcessLookupError:
                # 进程已经不存在
                logger.debug("Process already terminated")
            except OSError as e:
                logger.error(f"Error stopping game process: {e}", exc_info=True)
                raise
        
        if not self._is_cdp_alive(self.last_cdp_port):
            return
        
        if self.last_cdp_port is None:
            return
        
        try:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._close_game_via_cdp(self.last_cdp_port))
            finally:
                loop.close()
        except Exception as e:
            logger.debug(f"Failed to close game via CDP: {e}")
    
    def _score_target(self, target: Dict[str, Any]) -> int:
        """计算目标页面的相关性分数
        
        Args:
            target: CDP目标页面信息
            
        Returns:
            相关性分数，分数越高越相关
        """
        title = (target.get("title") or "").lower()
        url = (target.get("url") or "").lower()
        ws_url = (target.get("webSocketDebuggerUrl") or "").lower()
        
        if not ws_url:
            return -1000
        
        if any(keyword in title for keyword in _EXCLUDE_KEYWORDS_TITLE):
            return -100
        if any(keyword in url for keyword in _EXCLUDE_KEYWORDS_URL):
            return -100
        
        score = 0
        if any(keyword in title for keyword in _SCORE_KEYWORDS_TITLE):
            score += _SCORE_WEIGHT_TITLE
        if any(keyword in url for keyword in _SCORE_KEYWORDS_URL):
            score += _SCORE_WEIGHT_URL
        
        # file://通常是游戏主页面，更倾向选择
        if url.startswith("file://"):
            score += 3
        
        # TYRANO相关路径优先级更高
        if "tyrano" in url or "kag" in url:
            score += 8
        
        return score
    
    def pick_target(self, target_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """从CDP目标列表中选择最相关的页面
        
        Args:
            target_list: CDP目标列表
            
        Returns:
            选中的目标页面，如果没有找到则返回None
        """
        if not target_list:
            return None
        
        pages = [
            target for target in target_list
            if target.get("type") in _TARGET_TYPES and target.get("webSocketDebuggerUrl")
        ]
        
        if not pages:
            return None
        
        pages.sort(key=self._score_target, reverse=True)
        return pages[0]
    
    async def fetch_ws_url(self, port: int) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """获取WebSocket调试URL
        
        Args:
            port: CDP端口
            
        Returns:
            (WebSocket URL, 目标页面信息)，如果失败则返回(None, None)
        """
        url = RuntimeModifyConfig.CDP_LIST_URL_TEMPLATE.format(port=port)
        url += f"?{RuntimeModifyConfig.CDP_TIMEOUT_PARAM}={int(time.time() * 1000)}"
        
        try:
            response = requests.get(
                url,
                timeout=RuntimeModifyConfig.CDP_CONNECT_TIMEOUT
            )
            response.raise_for_status()
            target_list = response.json()
            
            if not isinstance(target_list, list):
                logger.warning(f"Invalid CDP response format: {type(target_list)}")
                return None, None
            
            target = self.pick_target(target_list)
            if target is None:
                return None, None
            
            ws_url = target.get("webSocketDebuggerUrl")
            return ws_url, target
            
        except requests.Timeout:
            logger.debug(f"CDP list request timeout for port {port}")
            return None, None
        except requests.RequestException as e:
            logger.debug(f"CDP list request failed: {e}")
            return None, None
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Failed to parse CDP list: {e}")
            return None, None
    
    async def eval_expr(
        self,
        ws_url: str,
        expr: str
    ) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """通过CDP执行JS表达式
        
        Args:
            ws_url: WebSocket调试URL
            expr: 要执行的JS表达式
            
        Returns:
            (执行结果值, 错误信息)，如果成功则错误信息为None
        """
        if not ws_url:
            return None, {"message": "WebSocket URL is empty"}
        
        if not expr:
            return None, {"message": "Expression is empty"}
        
        try:
            async with websockets.connect(
                ws_url,
                max_size=_WEBSOCKET_MAX_SIZE,
                open_timeout=RuntimeModifyConfig.WEBSOCKET_OPEN_TIMEOUT,
                close_timeout=RuntimeModifyConfig.WEBSOCKET_CLOSE_TIMEOUT
            ) as websocket:
                msg_id = 1
                
                async def send_cdp_message(
                    method: str,
                    params: Optional[Dict[str, Any]] = None
                ) -> int:
                    """发送CDP消息"""
                    nonlocal msg_id
                    payload: Dict[str, Any] = {"id": msg_id, "method": method}
                    if params is not None:
                        payload["params"] = params
                    
                    await websocket.send(json.dumps(payload))
                    current_id = msg_id
                    msg_id += 1
                    return current_id
                
                await send_cdp_message("Runtime.enable")
                
                request_id = await send_cdp_message(
                    "Runtime.evaluate",
                    {
                        "expression": expr,
                        "returnByValue": True,
                        "awaitPromise": True
                    }
                )
                
                while True:
                    raw_message = await websocket.recv()
                    message = json.loads(raw_message)
                    
                    if message.get("id") == request_id:
                        if "error" in message:
                            return None, message["error"]
                        
                        result = message.get("result", {})
                        value = result.get("result", {}).get("value")
                        return value, None
                        
        except WebSocketException as e:
            logger.debug(f"WebSocket connection error: {e}")
            return None, {"message": f"WebSocket connection failed: {e}"}
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse WebSocket message: {e}")
            return None, {"message": f"Failed to parse message: {e}"}
        except Exception as e:
            logger.exception("Unexpected error in eval_expr")
            return None, {"message": f"Execution failed: {e}"}
    
    async def test_injection(
        self,
        ws_url: str
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """测试JS注入功能
        
        执行 typeof TYRANO 来测试目标页面是否已就绪
        
        Args:
            ws_url: WebSocket调试URL
            
        Returns:
            (是否成功, 错误信息, 额外信息)
        """
        tyrano_type, error = await self.eval_expr(ws_url, "typeof TYRANO")
        
        if error is not None:
            error_message = error.get("message", str(error))
            return False, error_message, None
        
        if tyrano_type == _EXPECTED_TYRANO_TYPE:
            return True, None, {"tyrano_type": tyrano_type}
        else:
            return (
                False,
                f"typeof TYRANO = {tyrano_type} (expected '{_EXPECTED_TYRANO_TYPE}')",
                {"tyrano_type": tyrano_type}
            )
    
    async def mark_window_title(self, ws_url: str) -> bool:
        """安全地为游戏窗口标题添加注入标记"""
        suffix_json = json.dumps(_INJECTED_TITLE_SUFFIX)
        expression = (
            "(function(){"
            "try {"
            "if (typeof document === 'undefined' || !document || typeof document.title !== 'string') {"
            "return {ok:false,reason:'document_unavailable'};"
            "}"
            f"if (document.title.includes({suffix_json})) {{"
            "return {ok:true,already:true};"
            "}"
            f"document.title = document.title + {suffix_json};"
            "return {ok:true,already:false};"
            "} catch (e) {"
            "return {ok:false,reason:String(e)};"
            "}"
            "})()"
        )
        
        value, error = await self.eval_expr(ws_url, expression)
        if error is not None:
            logger.debug(
                "Failed to mark window title via CDP: %s",
                error.get("message", str(error))
            )
            return False
        
        if isinstance(value, dict):
            return bool(value.get("ok"))
        
        return False
    
    def _is_tyrano_not_ready_failure(
        self,
        error_message: Optional[str],
        extra_info: Optional[Dict[str, Any]]
    ) -> bool:
        """判断失败是否属于可重试的“游戏尚未就绪”场景"""
        if extra_info and extra_info.get("tyrano_type") == "undefined":
            return True
        
        if not error_message:
            return False
        
        normalized = error_message.lower()
        return (
            "websocket" in normalized or
            "cannot find context" in normalized or
            "execution context" in normalized
        )
    
    async def _connect_cdp_with_retry(
        self,
        port: int,
        max_wait_seconds: float
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """带重试的CDP连接
        
        Args:
            port: CDP端口
            max_wait_seconds: 最大等待时间（秒）
            
        Returns:
            (WebSocket URL, 目标页面信息)
        """
        if max_wait_seconds <= 0:
            return None, None
        
        deadline = time.monotonic() + max_wait_seconds
        
        while True:
            ws_url, target = await self.fetch_ws_url(port)
            if ws_url:
                return ws_url, target
            
            if time.monotonic() >= deadline:
                break
            
            await asyncio.sleep(RuntimeModifyConfig.CDP_RETRY_DELAY)
        
        return None, None
    
    async def launch_and_test(
        self,
        exe_path: Path,
        port: int
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """启动游戏并测试CDP连接
        
        Args:
            exe_path: 游戏可执行文件路径
            port: CDP端口
            
        Returns:
            (是否成功, 错误信息, 额外信息)
        """
        result_info: Dict[str, Any] = {"launch_mode": self.last_launch_mode}
        
        try:
            self.launch_game(exe_path, port)
        except FileNotFoundError as e:
            return False, str(e), result_info
        except (subprocess.SubprocessError, ValueError) as e:
            return False, f"Failed to start game: {e}", result_info
        
        result_info["launch_mode"] = self.last_launch_mode
        
        await asyncio.sleep(RuntimeModifyConfig.GAME_STARTUP_DELAY)
        connect_wait = (
            RuntimeModifyConfig.STEAM_CDP_MAX_WAIT
            if self.last_launch_mode == "steam"
            else RuntimeModifyConfig.DIRECT_CDP_MAX_WAIT
        )
        logger.info(
            "Waiting up to %.1fs for CDP endpoint (launch_mode=%s, port=%s)",
            connect_wait,
            self.last_launch_mode,
            port
        )
        
        deadline = time.monotonic() + connect_wait
        last_error: Optional[str] = None
        last_extra: Dict[str, Any] = {}
        last_target: Optional[Dict[str, Any]] = None
        
        while time.monotonic() < deadline:
            ws_url, target = await self.fetch_ws_url(port)
            if ws_url is None:
                await asyncio.sleep(RuntimeModifyConfig.CDP_RETRY_DELAY)
                continue
            
            if target:
                last_target = target
            
            success, error_message, extra_info = await self.test_injection(ws_url)
            if success:
                result_info.update(extra_info or {})
                title_marked = await self.mark_window_title(ws_url)
                result_info["title_marked"] = title_marked
                result_info["ws_url"] = ws_url
                ws_path = ws_url.replace("ws://", "") if ws_url.startswith("ws://") else ws_url
                result_info["inspector_url"] = f"http://127.0.0.1:{port}/devtools/inspector.html?ws={ws_path}"
                if target:
                    result_info["target_title"] = target.get("title", "")
                    result_info["target_url"] = target.get("url", "")
                return True, None, result_info
            
            last_error = error_message
            if extra_info:
                last_extra = extra_info
            
            if target:
                logger.debug(
                    "Target not ready yet (title=%s, url=%s, error=%s)",
                    target.get("title", ""),
                    target.get("url", ""),
                    error_message
                )
            
            if self._is_tyrano_not_ready_failure(error_message, extra_info):
                await asyncio.sleep(RuntimeModifyConfig.CDP_RETRY_DELAY)
                continue
            
            # 目标可能在启动过程中切换，非TYRANO错误也继续重试直到超时
            await asyncio.sleep(RuntimeModifyConfig.CDP_RETRY_DELAY)
        
        logger.warning(
            "CDP/TYRANO not ready within %.1fs (launch_mode=%s, port=%s, last_error=%s)",
            connect_wait,
            self.last_launch_mode,
            port,
            last_error
        )
        
        if last_target:
            result_info["target_title"] = last_target.get("title", "")
            result_info["target_url"] = last_target.get("url", "")
        if last_extra:
            result_info.update(last_extra)
        
        if self.is_game_running():
            result_info["pending_cdp"] = True
            return False, "Game may not be fully started yet, retrying...", result_info
        
        if last_error:
            return False, last_error, result_info
        
        return False, "Cannot connect to CDP debug port", result_info
    
    async def _read_tyrano_json_variable(
        self,
        ws_url: str,
        js_expression: str,
        variable_name: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """通过JS注入读取TYRANO变量的通用方法
        
        Args:
            ws_url: WebSocket调试URL
            js_expression: JavaScript表达式
            variable_name: 变量名称（用于日志）
            
        Returns:
            (数据字典, 错误信息)，如果成功则错误信息为None
        """
        if not ws_url:
            return None, "WebSocket URL is empty"
        
        if not js_expression:
            return None, "JavaScript expression is empty"
        
        json_str, error = await self.eval_expr(ws_url, js_expression)
        
        if error is not None:
            error_message = error.get("message", str(error))
            logger.debug(f"Failed to evaluate JS expression for {variable_name}: {error_message}")
            return None, error_message
        
        if json_str is None:
            logger.warning(f"JS expression for {variable_name} returned None")
            return None, "Read data is empty"
        
        if not isinstance(json_str, str):
            actual_type = type(json_str).__name__
            logger.error(f"Expected string for {variable_name}, got {actual_type}")
            return None, f"Read data is not a string type: {actual_type}"
        
        try:
            parsed_data = json.loads(json_str)
            if not isinstance(parsed_data, dict):
                actual_type = type(parsed_data).__name__
                logger.error(f"Expected dict for {variable_name}, got {actual_type}")
                return None, f"Parsed data is not a dictionary type: {actual_type}"
            return parsed_data, None
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse {variable_name} JSON: {json_err}")
            return None, f"JSON parsing failed: {json_err}"
        except (TypeError, ValueError) as parse_err:
            logger.exception(f"Unexpected error parsing {variable_name} JSON data")
            return None, f"Parse error: {parse_err}"
        except Exception as unexpected_err:
            logger.exception(f"Unexpected error reading {variable_name}")
            return None, f"Read failed: {unexpected_err}"
    
    async def read_tyrano_variable_sf(
        self,
        ws_url: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """通过JS注入读取TYRANO.kag.variable.sf
        
        Args:
            ws_url: WebSocket调试URL
            
        Returns:
            (数据字典, 错误信息)，如果成功则错误信息为None
        """
        return await self._read_tyrano_json_variable(
            ws_url,
            _JS_READ_SF_EXPRESSION,
            "TYRANO.kag.variable.sf"
        )
    
    @staticmethod
    def _deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并两个字典
        
        递归合并嵌套字典，对于非字典类型直接替换。
        
        Args:
            target: 目标字典（原始数据）
            source: 源字典（用户修改的数据）
            
        Returns:
            合并后的字典（深拷贝）
        """
        merged = json.loads(json.dumps(target))  # 深拷贝目标字典
        
        for key, source_value in source.items():
            target_value = merged.get(key)
            
            # 只有当两个值都是字典时才递归合并
            if isinstance(target_value, dict) and isinstance(source_value, dict):
                merged[key] = RuntimeModifyService._deep_merge(target_value, source_value)
            else:
                # 直接替换（包括数组和基本类型），深拷贝避免引用问题
                merged[key] = json.loads(json.dumps(source_value))
        
        return merged
    
    async def inject_and_save_sf(
        self,
        ws_url: str,
        edited_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """将编辑后的数据注入到游戏内存并保存
        
        先读取当前游戏内存中的TYRANO.kag.variable.sf，然后合并用户修改的数据，
        最后调用saveSystemVariable保存。
        
        Args:
            ws_url: WebSocket调试URL
            edited_data: 编辑后的数据字典（用户修改的部分）
            
        Returns:
            (是否成功, 错误信息)
        """
        if not ws_url:
            return False, "WebSocket URL is empty"
        
        if not isinstance(edited_data, dict):
            return False, "edited_data must be a dictionary"
        
        if not edited_data:
            logger.warning("Attempted to inject empty data")
            return False, "Cannot inject empty data"
        
        try:
            # 先读取当前游戏内存中的数据
            current_data, read_error = await self.read_tyrano_variable_sf(ws_url)
            if read_error:
                logger.error(f"Failed to read current data before injection: {read_error}")
                return False, f"Failed to read current data: {read_error}"
            
            if current_data is None:
                logger.warning("Current data is None, cannot merge")
                return False, "Current data is empty"
            
            # 合并用户修改到当前数据
            merged_data = self._deep_merge(current_data, edited_data)
            
            # 将合并后的数据序列化为JSON字符串并转义
            json_str = json.dumps(merged_data, ensure_ascii=False)
            escaped_json = _escape_json_for_js(json_str)
            
            # 构建JS注入代码
            js_expr = _JS_INJECT_TEMPLATE.format(json_data=escaped_json)
            
            result, error = await self.eval_expr(ws_url, js_expr)
            
            if error is not None:
                error_message = error.get("message", str(error))
                logger.error(f"JS evaluation error during injection: {error_message}")
                return False, error_message
            
            if result is True:
                logger.info("Successfully injected and saved sf data")
                return True, None
            elif isinstance(result, str):
                # 返回的是JS执行错误字符串
                logger.error(f"JS execution returned error: {result}")
                return False, result
            else:
                result_type = type(result).__name__
                logger.error(f"Unexpected result type: {result_type}, value: {result}")
                return False, f"Unknown return result: {result}"
                
        except (TypeError, ValueError) as validation_err:
            logger.exception("Data validation error during injection")
            return False, f"Injection failed: {validation_err}"
        except Exception as unexpected_err:
            logger.exception("Unexpected error injecting and saving sf")
            return False, f"Injection failed: {unexpected_err}"
    
    async def check_sf_changes(
        self,
        ws_url: str,
        original_data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """检查游戏内存中的sf数据是否有变更
        
        Args:
            ws_url: WebSocket调试URL
            original_data: 原始数据快照
            
        Returns:
            (是否有变更, 变更信息字典)
        """
        if not ws_url:
            return False, {"changes_text": ""}
        
        # 读取当前游戏内存中的数据
        current_data, error = await self.read_tyrano_variable_sf(ws_url)
        
        if error is not None:
            # 读取失败，不进行变更检测
            logger.warning(f"Failed to read current sf data for change detection: {error}")
            return False, {"changes_text": "", "error": error}
        
        if current_data is None:
            return False, {"changes_text": ""}
        
        # 比较数据
        try:
            # 使用排序后的JSON字符串进行快速比较
            original_json = json.dumps(original_data, sort_keys=True, ensure_ascii=False)
            current_json = json.dumps(current_data, sort_keys=True, ensure_ascii=False)
            
            if original_json == current_json:
                return False, {"changes_text": ""}
            
            # 有变更，生成变更信息
            change_descriptions = []
            all_keys = set(original_data.keys()) | set(current_data.keys())
            
            for key in sorted(all_keys):  # 排序以保证输出一致性
                original_value = original_data.get(key)
                current_value = current_data.get(key)
                
                if original_value == current_value:
                    continue
                
                # 根据值类型生成不同的变更描述
                if isinstance(original_value, dict) or isinstance(current_value, dict):
                    change_descriptions.append(f"  {key}: Object changed")
                elif isinstance(original_value, list) or isinstance(current_value, list):
                    orig_len = len(original_value) if isinstance(original_value, list) else "N/A"
                    curr_len = len(current_value) if isinstance(current_value, list) else "N/A"
                    change_descriptions.append(f"  {key}: Array changed (length: {orig_len} -> {curr_len})")
                else:
                    change_descriptions.append(f"  {key}: {original_value} -> {current_value}")
            
            changes_text = "\n".join(change_descriptions) if change_descriptions else "Unknown changes detected"
            return True, {"changes_text": changes_text, "changes": change_descriptions}
            
        except (TypeError, ValueError) as comparison_err:
            logger.exception("Error comparing sf data")
            return False, {"changes_text": f"Error comparing data: {comparison_err}"}
        except Exception as unexpected_err:
            logger.exception("Unexpected error during comparison")
            return False, {"changes_text": f"Error comparing data: {unexpected_err}"}
    
    async def read_tyrano_kag_stat(
        self,
        ws_url: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """通过JS注入读取TYRANO.kag.stat
        
        Args:
            ws_url: WebSocket调试URL
            
        Returns:
            (数据字典, 错误信息)，如果成功则错误信息为None
        """
        return await self._read_tyrano_json_variable(
            ws_url,
            _JS_READ_KAG_STAT_EXPRESSION,
            "TYRANO.kag.stat"
        )
    
    async def _inject_tyrano_variable(
        self,
        ws_url: str,
        edited_data: Dict[str, Any],
        js_template: str,
        variable_name: str
    ) -> Tuple[bool, Optional[str]]:
        """注入数据到TYRANO变量的通用方法
        
        Args:
            ws_url: WebSocket调试URL
            edited_data: 编辑后的数据字典
            js_template: JavaScript注入模板
            variable_name: 变量名称（用于日志）
            
        Returns:
            (是否成功, 错误信息)
        """
        if not ws_url:
            return False, "WebSocket URL is empty"
        
        if not isinstance(edited_data, dict):
            return False, "edited_data must be a dictionary"
        
        if not edited_data:
            logger.warning(f"Attempted to inject empty {variable_name} data")
            return False, "Cannot inject empty data"
        
        try:
            # 将数据序列化为JSON字符串并转义
            json_str = json.dumps(edited_data, ensure_ascii=False)
            escaped_json = _escape_json_for_js(json_str)
            
            # 构建JS注入代码
            js_expr = js_template.format(json_data=escaped_json)
            
            result, error = await self.eval_expr(ws_url, js_expr)
            
            if error is not None:
                error_message = error.get("message", str(error))
                logger.error(f"JS evaluation error during {variable_name} injection: {error_message}")
                return False, error_message
            
            if result is True:
                logger.info(f"Successfully injected {variable_name} data")
                return True, None
            elif isinstance(result, str):
                logger.error(f"JS execution returned error for {variable_name}: {result}")
                return False, result
            else:
                result_type = type(result).__name__
                logger.error(f"Unexpected result type for {variable_name}: {result_type}, value: {result}")
                return False, f"Unknown return result: {result}"
                
        except (TypeError, ValueError) as validation_err:
            logger.exception(f"Data validation error during {variable_name} injection")
            return False, f"Injection failed: {validation_err}"
        except Exception as unexpected_err:
            logger.exception(f"Unexpected error injecting {variable_name}")
            return False, f"Injection failed: {unexpected_err}"
    
    async def inject_kag_stat(
        self,
        ws_url: str,
        edited_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """将编辑后的数据注入到游戏内存中的 kag.stat
        
        直接使用 Object.assign 覆盖 kag.stat，不调用保存方法。
        
        Args:
            ws_url: WebSocket调试URL
            edited_data: 编辑后的数据字典
            
        Returns:
            (是否成功, 错误信息)
        """
        return await self._inject_tyrano_variable(
            ws_url,
            edited_data,
            _JS_INJECT_KAG_STAT_TEMPLATE,
            "kag.stat"
        )
    
    async def inject_fast_forward_script(
        self,
        ws_url: str
    ) -> Tuple[bool, Optional[str]]:
        """标记当前label为已读
        
        Args:
            ws_url: WebSocket调试URL
            
        Returns:
            (是否成功, 错误信息)
        """
        if not ws_url:
            return False, "WebSocket URL is empty"
        
        try:
            result, error = await self.eval_expr(ws_url, _JS_FORCE_FAST_FORWARD_INJECT)
            
            if error is not None:
                error_message = error.get("message", str(error))
                logger.error(f"JS evaluation error during fast forward injection: {error_message}")
                return False, error_message
            
            if not isinstance(result, dict):
                logger.error(f"Unexpected result type: {type(result).__name__}")
                return False, f"Unexpected result type: {type(result).__name__}"
            
            success = result.get("success", False)
            message = result.get("message", "")
            
            if success:
                label = result.get("label", "")
                logger.info(f"Label marked as read: {label}")
                return True, None
            else:
                logger.error(f"Failed to mark as read: {message}")
                return False, message
                    
        except Exception as unexpected_err:
            logger.exception("Unexpected error injecting fast forward script")
            return False, f"Injection failed: {unexpected_err}"
    
    async def remove_fast_forward_script(
        self,
        ws_url: str
    ) -> Tuple[bool, Optional[str]]:
        """移除强制快进脚本（占位方法，当前无需清理）
        
        Args:
            ws_url: WebSocket调试URL
            
        Returns:
            (是否成功, 错误信息)
        """
        return True, None
