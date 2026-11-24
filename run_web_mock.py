"""開發用：網頁預覽，但 NotebookLM 改用模擬伺服器（不開 Chrome、不連 Google）。http://127.0.0.1:8681"""
import os
import runpy

os.environ["NB_MCP_MOCK"] = "1"
os.environ.setdefault("NB_WEB_PORT", "8681")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_web.py"), run_name="__main__")
