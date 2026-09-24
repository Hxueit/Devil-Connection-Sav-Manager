"""运行时修改：用一个假的 CDP 服务器（HTTP /json/list + WebSocket Runtime.evaluate）测试服务层"""
import http.server
import json
import socket
import threading

import pytest
from websockets.sync.server import serve

from src.modules.runtime_modify import service
from src.modules.runtime_modify.cache_clean_dialog import (
    CannotCleanNowError,
    CleanupItemResult,
    CleanupJob,
    run_cleanup,
)
from src.modules.runtime_modify.cache_clean_scripts import JS_CHECK_PHOTO_OPEN, JS_CHECK_STATE, generate_cleanup_script
from src.modules.runtime_modify.console import describe_quick_save, format_result


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeGame:
    """模拟游戏页面：保存 sf / stat，按表达式返回结果"""

    ASSIGN_PREFIX = "(function() { try { Object.assign("

    def __init__(self) -> None:
        self.sf = {"a": 1, "nested": {"x": 1, "y": 2}, "list": [1, 2]}
        self.stat = {"f": {"day": 3}}
        self.saved = 0
        self.expressions = []
        self.overrides = {}   # 表达式 -> 返回值

    def evaluate(self, expr: str) -> dict:
        """返回 CDP Runtime.evaluate 的 result 字段"""
        self.expressions.append(expr)
        if expr in self.overrides:
            return {"result": {"type": "object", "value": self.overrides[expr]}}
        if expr == "hang":
            return None
        if expr.startswith("throw"):
            return {
                "result": {"type": "object", "subtype": "error", "description": "Error: boom"},
                "exceptionDetails": {"text": "Uncaught", "exception": {"description": "Error: boom"}},
            }
        if expr == "typeof TYRANO":
            return {"result": {"type": "string", "value": "object"}}
        if expr == "JSON.stringify(TYRANO.kag.variable.sf)":
            return {"result": {"type": "string", "value": json.dumps(self.sf)}}
        if expr == "JSON.stringify(TYRANO.kag.stat)":
            return {"result": {"type": "string", "value": json.dumps(self.stat)}}
        if expr.startswith(self.ASSIGN_PREFIX):
            rest = expr[len(self.ASSIGN_PREFIX):]
            target, rest = rest.split(", ", 1)
            data, _end = json.JSONDecoder().raw_decode(rest)
            (self.sf if target == "TYRANO.kag.variable.sf" else self.stat).update(data)
            if "saveSystemVariable" in rest:
                self.saved += 1
            return {"result": {"type": "boolean", "value": True}}
        if "buff_label_name" in expr:
            return {"result": {"type": "object", "value": {"success": True, "label": "*start"}}}
        return {"result": {"type": "undefined"}}


class FakeCdpServer:
    def __init__(self, game: FakeGame) -> None:
        self.game = game
        self.port = _free_port()
        ws_port = _free_port()
        self.ws_url = f"ws://127.0.0.1:{ws_port}/devtools/page/GAME"
        targets = [
            {"type": "page", "title": "DevTools", "url": "devtools://devtools/x",
             "webSocketDebuggerUrl": f"ws://127.0.0.1:{ws_port}/devtools/page/DEVTOOLS"},
            {"type": "page", "title": "でびるコネクショん", "url": "file:///app/index.html",
             "webSocketDebuggerUrl": self.ws_url},
            {"type": "service_worker", "title": "sw", "url": "", "webSocketDebuggerUrl": "ws://ignored"},
        ]

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = json.dumps(targets).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.ws = serve(self._handle_ws, "127.0.0.1", ws_port)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        threading.Thread(target=self.ws.serve_forever, daemon=True).start()

    def _handle_ws(self, connection) -> None:
        for raw in connection:
            request = json.loads(raw)
            # 真实页面会穿插推送事件，客户端必须按 id 找回复
            connection.send(json.dumps({"method": "Runtime.consoleAPICalled", "params": {}}))
            result = self.game.evaluate(request["params"]["expression"])
            if result is not None:
                connection.send(json.dumps({"id": request["id"], "result": result}))

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()
        self.ws.shutdown()


@pytest.fixture
def game():
    return FakeGame()


@pytest.fixture
def cdp(game):
    server = FakeCdpServer(game)
    yield server
    server.close()


def test_fetch_target_picks_game_page(cdp):
    target = service.fetch_target(cdp.port)
    assert target["webSocketDebuggerUrl"] == cdp.ws_url
    assert service.fetch_ws_url(_free_port(), timeout=0.5) is None


def test_evaluate_value_exception_and_timeout(cdp):
    assert service.evaluate(cdp.ws_url, "typeof TYRANO") == "object"
    assert service.evaluate(cdp.ws_url, "1 + undefinedThing") is None
    with pytest.raises(service.CdpError, match="Error: boom"):
        service.evaluate(cdp.ws_url, "throw new Error('boom')")
    with pytest.raises(service.CdpError, match="Timed out"):
        service.evaluate(cdp.ws_url, "hang", timeout=0.3)
    with pytest.raises(service.CdpError):
        service.evaluate(f"ws://127.0.0.1:{_free_port()}/x", "1")


def test_read_and_inject_sf(cdp, game):
    assert service.read_json_variable(cdp.ws_url, service.SF_JS_PATH) == game.sf

    service.inject_and_save_sf(cdp.ws_url, {"nested": {"y": 5}, "text": "it's \"quoted\"\n"})
    assert game.sf["nested"] == {"x": 1, "y": 5}
    assert game.sf["text"] == "it's \"quoted\"\n"
    assert game.saved == 1

    service.assign_json_variable(cdp.ws_url, service.KAG_STAT_JS_PATH, {"f": {"day": 4}})
    assert game.stat == {"f": {"day": 4}} and game.saved == 1
    with pytest.raises(service.CdpError, match="empty"):
        service.assign_json_variable(cdp.ws_url, service.KAG_STAT_JS_PATH, {})


def test_read_json_variable_rejects_non_objects(cdp, game):
    game.overrides["JSON.stringify(TYRANO.kag.stat)"] = "[1, 2]"
    with pytest.raises(service.CdpError, match="not a dictionary"):
        service.read_json_variable(cdp.ws_url, service.KAG_STAT_JS_PATH)
    game.overrides["JSON.stringify(TYRANO.kag.stat)"] = None
    with pytest.raises(service.CdpError, match="empty"):
        service.read_json_variable(cdp.ws_url, service.KAG_STAT_JS_PATH)


def test_describe_changes(cdp, game):
    original = dict(game.sf)
    assert service.describe_changes(original, service.read_json_variable(cdp.ws_url, service.SF_JS_PATH)) == []
    game.sf["a"] = 2
    game.sf["list"] = [1]
    changes = service.describe_changes(original, service.read_json_variable(cdp.ws_url, service.SF_JS_PATH))
    assert changes == ["  a: 1 -> 2", "  list: Array changed (length: 2 -> 1)"]


def test_poll_status_and_mark_read(cdp, game):
    s = service.RuntimeModifyService()
    assert s.poll_status(cdp.port) == (True, cdp.ws_url)
    assert s.poll_status(_free_port()) == (False, None)
    assert s.poll_status(None) == (False, None)
    service.mark_current_label_read(cdp.ws_url)

    game.overrides[service._JS_MARK_CURRENT_LABEL_READ] = {"success": False, "message": "not_in_any_label"}
    with pytest.raises(service.MarkReadRefusedError) as info:
        service.mark_current_label_read(cdp.ws_url)
    assert info.value.code == "not_in_any_label"


def test_launch_and_test(cdp, game, monkeypatch, tmp_path):
    launched = []

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            launched.append(cmd)

        def poll(self):
            return None

    monkeypatch.setattr(service.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(service, "GAME_STARTUP_DELAY", 0)
    exe = tmp_path / "DevilConnection.exe"
    exe.write_text("")

    s = service.RuntimeModifyService()
    info = s.launch_and_test(exe, cdp.port)
    assert launched == [[str(exe), f"--remote-debugging-port={cdp.port}"]]
    assert info["ws_url"] == cdp.ws_url and info["launch_mode"] == "direct"
    assert info["tyrano_type"] == "object"
    assert any("DCSM Injected" in e for e in game.expressions)


def test_launch_and_test_reports_still_starting(monkeypatch, tmp_path):
    class FakePopen:
        def __init__(self, cmd, **kwargs):
            pass

        def poll(self):
            return None

    monkeypatch.setattr(service.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(service, "GAME_STARTUP_DELAY", 0)
    monkeypatch.setattr(service, "DIRECT_CDP_MAX_WAIT", 0.2)
    exe = tmp_path / "DevilConnection.exe"
    exe.write_text("")

    with pytest.raises(service.LaunchError) as info:
        service.RuntimeModifyService().launch_and_test(exe, _free_port())
    assert info.value.still_starting and info.value.info == {"launch_mode": "direct"}


def test_deep_merge_does_not_modify_inputs():
    target = {"a": {"b": 1, "c": [1]}, "d": 1}
    source = {"a": {"c": [2]}, "e": {"f": 1}}
    merged = service.deep_merge(target, source)
    assert merged == {"a": {"b": 1, "c": [2]}, "d": 1, "e": {"f": 1}}
    assert target == {"a": {"b": 1, "c": [1]}, "d": 1}


def test_run_cleanup_skips_photo_items_when_photo_open(cdp, game):
    game.overrides[JS_CHECK_STATE] = {"canClean": True}
    game.overrides[JS_CHECK_PHOTO_OPEN] = {"isOpen": True}
    game.overrides["ok-script"] = {"success": True, "count": 3}
    jobs = [CleanupJob("photo", "photo-script", requires_photo_closed=True), CleanupJob("ok", "ok-script"),
            CleanupJob("bad", "throw bad"), CleanupJob("odd", "odd-script")]
    result = run_cleanup(cdp.ws_url, jobs)
    assert result.skipped == ["photo"]
    assert result.items == [
        CleanupItemResult("ok", 3),
        CleanupItemResult("bad", None, "Error: boom", script_failed=True),
        CleanupItemResult("odd", None, script_failed=True),
    ]
    assert "photo-script" not in game.expressions

    game.overrides[JS_CHECK_STATE] = {"canClean": False, "reason": "is_trans"}
    with pytest.raises(CannotCleanNowError) as info:
        run_cleanup(cdp.ws_url, jobs)
    assert info.value.reason == "is_trans"


def test_generate_cleanup_script_escapes_values():
    script = generate_cleanup_script({"type": "selector", "selector": "a[title='x']"})
    assert "querySelectorAll(\"a[title='x']\")" in script
    script = generate_cleanup_script({"type": "function", "func": "TYRANO.kag.layer.getLayer", "args": ["base", 1]})
    assert '"TYRANO.kag.layer.getLayer".split' in script and 'fn(...["base", 1])' in script
    assert generate_cleanup_script({"type": "property", "path": "TYRANO"}) == ""
    assert generate_cleanup_script({"type": "unknown"}) == ""


def _t(key, **kwargs):
    return {
        "tyrano_day_label": "Day {day}",
        "tyrano_epilogue_day_label": "Epilogue {day}",
        "runtime_modify_console_no_quick_save": "none",
    }.get(key, key).format(**kwargs)


def test_describe_quick_save():
    assert describe_quick_save(None, _t) == "none"
    slot = {
        "stat": {"f": {"day": 1, "day_epilogue": 0, "finished": [0, 0, 0, 1, 1]}},
        "save_date": "2024/1/1",
        "subtitle": True,
        "subtitleText": "hello",
    }
    assert describe_quick_save(slot, _t) == "Day 1 · ●●○ · 2024/1/1 · hello"
    slot = {"stat": {"f": {"day": 5, "day_epilogue": "2"}}, "subtitle": False, "subtitleText": "x"}
    assert describe_quick_save(slot, _t) == "Epilogue 2"
    assert describe_quick_save({"stat": {}}, _t) == "none"


def test_format_result():
    assert format_result(None) == "undefined"
    assert format_result("a") == '"a"'
    assert format_result({"k": "値"}) == '{\n  "k": "値"\n}'
    assert format_result(3) == "3"
