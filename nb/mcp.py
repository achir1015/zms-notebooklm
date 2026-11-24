"""NotebookLM MCP 用戶端：啟動內附的 notebooklm-mcp（Node.js），用 MCP stdio（一行一個 JSON-RPC）呼叫工具。

比喻：MCP 伺服器是一位「代跑腿的助理」，它開著一個看不見的 Chrome 幫我們到 NotebookLM 問問題；
本模組就是我們跟這位助理講話的電話線。

* 伺服器程式：vendor/notebooklm-mcp/dist/index.js（MIT，已加上 list_account_notebooks 工具）
* Node.js：NB_NODE → 程式旁 node/node.exe → nvm v22 → PATH 上的 node
* Google 登入（setup_auth）會開一個看得見的 Chrome，由使用者自己登入；Cookie 存在使用者電腦的 Chrome 設定檔。
* 測試用：NB_MCP_MOCK=1 改用假的伺服器（不連網路）。
"""
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

from .settings import program_dir, resource_dir

log = logging.getLogger("nb")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
NOTEBOOK_RE = re.compile(r"https?://(notebook(?:lm)?\.google\.com)/notebook/([0-9a-fA-F-]{36})")


class McpError(Exception):
    """可以直接顯示給使用者看的 NotebookLM 錯誤。"""


def normalize_url(url):
    """把分享網址整理成標準格式（新網域 notebook.google.com、舊網域 notebooklm.google.com 都接受）。
    回傳 (網址, UUID) 或 ("", "")。"""
    m = NOTEBOOK_RE.search((url or "").strip())
    if not m:
        return "", ""
    uid = m.group(2).lower()
    return "https://%s/notebook/%s" % (m.group(1).lower(), uid), uid


def server_script():
    # Windows 安裝版在程式旁；macOS .app 在 Contents/Resources；開發時在專案的 vendor/
    for base in (resource_dir(), program_dir(), os.path.normpath(os.path.join(program_dir(), "..", "Resources"))):
        p = os.path.join(base, "vendor", "notebooklm-mcp", "dist", "index.js")
        if os.path.isfile(p):
            return p
    return ""


def find_node():
    exe = "node.exe" if os.name == "nt" else "node"
    cands = [os.environ.get("NB_NODE", ""),
             os.path.join(program_dir(), "node", exe), os.path.join(resource_dir(), "node", exe),
             os.path.normpath(os.path.join(program_dir(), "..", "Resources", "node", "bin", "node"))]
    if os.name == "nt":
        nvm = os.path.join(os.environ.get("LOCALAPPDATA", ""), "nvm")
        if os.path.isdir(nvm):
            for n in sorted(os.listdir(nvm), reverse=True):
                if n.startswith("v2"):
                    cands.append(os.path.join(nvm, n, exe))
    cands.append(shutil.which("node") or "")
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return ""


def node_version(node):
    try:
        out = subprocess.run([node, "-v"], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        return out.stdout.strip()
    except Exception:
        return ""


class McpClient:
    """一條到 notebooklm-mcp 的連線（執行緒安全：同一時間只送一個請求）。"""

    def __init__(self, headless=True):
        self.headless = headless
        self.proc = None
        self.lock = threading.Lock()
        self.seq = 0
        self.q = queue.Queue()
        self.stderr_tail = []
        self.server_info = {}

    # ------------------------------------------------------------ 啟動與關閉
    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        node, script = find_node(), server_script()
        if not node:
            raise McpError("找不到 Node.js（安裝版內附；開發環境請安裝 Node.js 18 以上）")
        if not script:
            raise McpError("找不到 NotebookLM MCP 伺服器程式（vendor/notebooklm-mcp/dist）")
        env = dict(os.environ)
        env.update({"NOTEBOOKLM_AI_MARKER": "false", "HEADLESS": "true" if self.headless else "false",
                    "NOTEBOOKLM_PROFILE": "full", "NOTEBOOKLM_FOLLOW_UP_REMINDER": "false",
                    "ANSWER_TIMEOUT_MS": env.get("ANSWER_TIMEOUT_MS", "600000")})
        log.info("mcp start %s %s", node, script)
        self.proc = subprocess.Popen([node, script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=env, cwd=os.path.dirname(os.path.dirname(script)),
                                     creationflags=NO_WINDOW)
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()
        r = self._request("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                         "clientInfo": {"name": "zms-notebooklm", "version": "1.0"}}, timeout=60)
        self.server_info = r.get("serverInfo", {})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def stop(self):
        p, self.proc = self.proc, None
        if not p:
            return
        try:
            p.stdin.close()
        except Exception:
            pass
        try:
            p.wait(8)
        except Exception:
            p.kill()

    def alive(self):
        return bool(self.proc and self.proc.poll() is None)

    # ------------------------------------------------------------ 傳輸
    def _read_out(self):
        p = self.proc
        for raw in iter(p.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("{"):
                continue
            try:
                self.q.put(json.loads(line))
            except ValueError:
                pass
        self.q.put(None)

    def _read_err(self):
        p = self.proc
        for raw in iter(p.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            self.stderr_tail = (self.stderr_tail + [line])[-60:]

    def _send(self, obj):
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def _request(self, method, params, timeout=120, progress=None):
        self.seq += 1
        rid = self.seq
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                raise McpError("NotebookLM 回應逾時（%d 秒）" % timeout)
            try:
                msg = self.q.get(timeout=min(left, 1.0))
            except queue.Empty:
                if not self.alive():
                    raise McpError("NotebookLM 伺服器已結束：%s" % " ".join(self.stderr_tail[-3:]))
                continue
            if msg is None:
                raise McpError("NotebookLM 伺服器已結束：%s" % " ".join(self.stderr_tail[-3:]))
            if msg.get("id") == rid:
                if "error" in msg:
                    raise McpError(msg["error"].get("message", "MCP 錯誤"))
                return msg.get("result", {})
            if progress and msg.get("method") == "notifications/progress":
                prm = msg.get("params", {})
                progress(prm.get("message") or "", prm.get("progress"), prm.get("total"))

    def call(self, tool, args=None, timeout=660, progress=None):
        """呼叫工具，回傳 data（伺服器回 success=false 時丟出 McpError）。"""
        with self.lock:
            self.start()
            params = {"name": tool, "arguments": args or {}}
            if progress:
                params["_meta"] = {"progressToken": "p%d" % (self.seq + 1)}
            r = self._request("tools/call", params, timeout=timeout, progress=progress)
        text = "".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        try:
            obj = json.loads(text)
        except ValueError:
            if r.get("isError"):
                raise McpError(text or "NotebookLM 工具失敗")
            return {"text": text}
        if isinstance(obj, dict) and obj.get("success") is False:
            raise McpError(translate_error(obj.get("error") or "NotebookLM 工具失敗"))
        return obj.get("data", obj) if isinstance(obj, dict) else obj

    def tools(self):
        with self.lock:
            self.start()
            return [t["name"] for t in self._request("tools/list", {}).get("tools", [])]

    # ------------------------------------------------------------ 常用工具
    def health(self):
        return self.call("get_health", timeout=60)

    def setup_auth(self):
        return self.call("setup_auth", {"show_browser": True}, timeout=120)

    def re_auth(self):
        return self.call("re_auth", {"show_browser": True}, timeout=120)

    def account_notebooks(self):
        return self.call("list_account_notebooks", {}, timeout=120).get("notebooks", [])

    def ask(self, url, question, session_id=None, progress=None, show_browser=None):
        """對筆記本提問（資料助秘版 ask_notebook：每次開新分頁，適用 2026 新版 notebook.google.com）。
        回傳 {answer, sources:[{index,title}], seconds}；session_id 保留相容（新版不需要）。"""
        args = {"question": question, "notebook_url": url}
        if show_browser is not None:
            args["show_browser"] = bool(show_browser)
        return self.call("ask_notebook", args, progress=progress)

    def add_source(self, url, kind, content, title=""):
        args = {"type": kind, "content": content, "notebook_url": url}
        if title:
            args["title"] = title
        return self.call("add_source", args, timeout=300)

    def close_session(self, sid):
        try:
            return self.call("close_session", {"session_id": sid}, timeout=60)
        except McpError:
            return None


def translate_error(msg):
    m = str(msg)
    low = m.lower()
    if "auth" in low and ("not" in low or "fail" in low or "required" in low):
        return "尚未登入 Google 或登入已過期，請到「NotebookLM 連線」按「登入 Google」。（%s）" % m[:160]
    if "timeout" in low:
        return "NotebookLM 回應逾時，請稍後再試。（%s）" % m[:160]
    if "rate" in low and "limit" in low:
        return "NotebookLM 今天的提問次數已達上限，請明天再試或換帳號。（%s）" % m[:160]
    return m


class MockClient(McpClient):
    """測試用假伺服器：不開瀏覽器、不連網路，回傳固定格式的答案。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.asked = []

    def start(self):
        pass

    def alive(self):
        return True

    def stop(self):
        pass

    def tools(self):
        return ["ask_question", "get_health", "setup_auth", "list_account_notebooks", "add_source"]

    def call(self, tool, args=None, timeout=0, progress=None):
        args = args or {}
        if tool == "get_health":
            return {"status": "ok", "authenticated": True, "version": "2.0.0-mock"}
        if tool in ("setup_auth", "re_auth"):
            return {"status": "opened"}
        if tool == "list_account_notebooks":
            return {"notebooks": [{"title": "病房助理技術教育外傭實務訓練",
                                   "url": "https://notebook.google.com/notebook/097207c0-8984-4a58-b041-30ed62c4c23b"}]}
        if tool == "add_source":
            return {"result": {"success": True, "added": True}}
        if tool in ("ask_question", "ask_notebook"):
            self.asked.append(args.get("question", ""))
            from .mockdata import mock_answer
            return {"status": "success", "answer": mock_answer(args.get("question", "")), "session_id": "mock_1",
                    "sources": [{"index": 1, "title": "範例來源.pdf", "excerpt": "（測試用摘錄）"}]}
        return {}


def make_client(headless=True):
    if os.environ.get("NB_MCP_MOCK"):
        return MockClient(headless)
    return McpClient(headless)


if __name__ == "__main__":       # 手動測試：python -m nb.mcp
    c = make_client()
    print(c.tools())
    print(json.dumps(c.health(), ensure_ascii=False, indent=1))
    c.stop()
    sys.exit(0)
