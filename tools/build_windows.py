"""一鍵建置 Windows 安裝檔：
1. 確認內附的 MariaDB（packaging/mariadb）
2. 準備 NotebookLM MCP 伺服器：編譯 vendor/notebooklm-mcp（TypeScript）→ packaging/mcp（只含執行需要的套件），
   並複製 Node.js 執行檔到 packaging/node
3. 產生資料表說明、圖示、語音說明（已存在且沒變則略過）
4. flet pack（PyInstaller）打包到 dist/ZMSNotebookLM
5. Inno Setup 產生 dist-installer/ZMSNotebookLM-Setup-<版本>.exe

用法：.venv\\Scripts\\python tools\\build_windows.py
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from nb import APP_ID, APP_NAME, APP_VERSION, AUTHOR  # noqa: E402
from nb.mcp import find_node  # noqa: E402

ISCC = [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"]
PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
MCP_SRC = os.path.join(HERE, "vendor", "notebooklm-mcp")


def node_env(node):
    env = dict(ENV)
    env["PATH"] = os.path.dirname(node) + os.pathsep + env.get("PATH", "")
    return env


def prepare_mcp():
    node = find_node()
    if not node:
        raise SystemExit("找不到 Node.js 18 以上（建置需要）")
    npm = os.path.join(os.path.dirname(node), "npm.cmd")
    env = node_env(node)
    if not os.path.isdir(os.path.join(MCP_SRC, "node_modules")):
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=MCP_SRC, check=True, env=env, shell=False)
    subprocess.run([os.path.join(MCP_SRC, "node_modules", ".bin", "tsc.cmd")], cwd=MCP_SRC, check=True, env=env)
    out = os.path.join(HERE, "packaging", "mcp")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for f in ("package.json", "package-lock.json", "LICENSE", "README.md"):
        shutil.copy2(os.path.join(MCP_SRC, f), out)
    shutil.copytree(os.path.join(MCP_SRC, "dist"), os.path.join(out, "dist"),
                    ignore=shutil.ignore_patterns("*.map", "*.d.ts"))
    # 只裝執行需要的套件；--ignore-scripts：不要再跑 prepare（會呼叫 tsc）
    subprocess.run([npm, "ci", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=out, check=True,
                   env=env)
    nd = os.path.join(HERE, "packaging", "node")
    os.makedirs(nd, exist_ok=True)
    shutil.copy2(node, os.path.join(nd, "node.exe"))
    print("NotebookLM MCP：", out, "Node：", node)


def prepare():
    if not os.path.isfile(os.path.join(HERE, "packaging", "mariadb", "bin", "mariadbd.exe")):
        raise SystemExit("缺少 packaging/mariadb（請複製 MariaDB 10.11 的 bin 與 share 最小檔案）")
    prepare_mcp()
    subprocess.run([PY, "tools/gen_schema_doc.py"], cwd=HERE, check=True, env=ENV)
    if not os.path.isfile(os.path.join(HERE, "assets", "icon.png")):
        subprocess.run([PY, "tools/make_icon.py"], cwd=HERE, check=True, env=ENV)
    subprocess.run([PY, "tools/make_voice.py"], cwd=HERE, check=False, env=ENV)


def pack():
    flet = os.path.join(HERE, ".venv", "Scripts", "flet.exe")
    shutil.rmtree(os.path.join(HERE, "dist"), ignore_errors=True)
    cmd = [flet, "pack", "main.py", "-D", "-y", "-n", APP_ID, "-i", "packaging/icon.ico", "--distpath", "dist",
           "--add-data", "assets:assets", "--add-data", "nb/samples:nb/samples",
           "--hidden-import", "edge_tts", "--hidden-import", "pymysql", "--hidden-import", "certifi",
           "--hidden-import", "qrcode", "--hidden-import", "pptx", "--hidden-import", "docx",
           "--pyinstaller-build-args=--collect-all=pptx", "--pyinstaller-build-args=--collect-all=docx",
           "--pyinstaller-build-args=--collect-all=flet_web",
           "--pyinstaller-build-args=--collect-all=flet_audio", "--pyinstaller-build-args=--collect-submodules=uvicorn",
           "--product-name", APP_NAME, "--file-description", APP_NAME, "--product-version", APP_VERSION,
           "--file-version", APP_VERSION + ".0", "--company-name", AUTHOR, "--copyright", "© 2026 " + AUTHOR]
    subprocess.run(cmd, cwd=HERE, check=True, env=ENV)


def installer():
    iscc = next((p for p in ISCC if os.path.isfile(p)), None)
    if not iscc:
        raise SystemExit("找不到 Inno Setup 6（ISCC.exe）")
    # 先編譯到暫存資料夾再搬回 dist-installer：直接寫 dist-installer 時常被防毒鎖檔（EndUpdateResource failed 110）
    tmp = tempfile.mkdtemp(prefix="zmsnotebooklm-iss-")
    subprocess.run([iscc, "/DAppVer=" + APP_VERSION, "/O" + tmp, os.path.join(HERE, "packaging", "installer.iss")],
                   check=True)
    name = "%s-Setup-%s.exe" % (APP_ID, APP_VERSION)
    out = os.path.join(HERE, "dist-installer", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    shutil.move(os.path.join(tmp, name), out)
    shutil.rmtree(tmp, ignore_errors=True)
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print("完成：%s（%.1f MB）\nSHA256 %s" % (out, os.path.getsize(out) / 1e6, sha))


if __name__ == "__main__":
    prepare()
    pack()
    installer()

