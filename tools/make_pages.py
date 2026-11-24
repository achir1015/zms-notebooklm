"""產生線上版（GitHub Pages：docs/）需要的資料與檔案。

* docs/app/data.js：內定範例專案與主題庫、產出類型、風格、語言、JSON 格式、頁型架構、官方視覺指令選項、
  小圖示關鍵字規則、語音教學課程與各頁說明 —— 全部從 Python 程式產生，兩個版本共用同一份定義
  （引擎邏輯在 docs/app/engine.js，要和 nb/artifacts.py 一起改；tests/test_web_parity.py 會比對兩邊輸出）。
* docs/voice/：語音教學 MP3（從 assets/voice 複製）。
* docs/app/icons/：Fluent Emoji 3D 小圖示（從 assets/icons 複製）。
* docs/icon.png、docs/app/icon.png。
* docs/app/lib/：PptxGenJS、JSZip（用 --libs 從 npm 下載，需要 Node 22）。

用法：python tools/make_pages.py [--libs]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from nb import APP_NAME, APP_VERSION, GITHUB_REPO  # noqa: E402
from nb import artifacts as A  # noqa: E402
from nb import deck, visual  # noqa: E402
from nb.help_text import LESSONS, PAGES  # noqa: E402
from nb.seed import SAMPLE_NOTEBOOK, SAMPLE_PEOPLE, SAMPLE_PROJECT  # noqa: E402

DOCS = os.path.join(HERE, "docs")
APP = os.path.join(DOCS, "app")
NODE = os.path.expandvars(r"%LOCALAPPDATA%\nvm\v22.22.3")
LIBS = {"pptxgenjs": "4.0.1", "jszip": "3.10.1"}
WEB_PAGES = ("home", "studio", "works", "notebooks", "projects", "help")


def data():
    with open(os.path.join(HERE, "nb", "samples", "ward_topics.json"), encoding="utf-8") as f:
        topics = json.load(f)
    with open(os.path.join(HERE, "nb", "samples", "ward_template.md"), encoding="utf-8") as f:
        spec = f.read()
    proj = dict(SAMPLE_PROJECT, term_langs=json.loads(SAMPLE_PROJECT["term_langs"]), spec_md=spec)
    lessons = [{"key": x["key"], "title": x["title"], "voice": x["voice"],
                "steps": [{"icon": s[0], "tone": s[1], "text": s[2], "page": s[3]} for s in x["steps"]]}
               for x in LESSONS]
    pages = {k: {"title": v[0], "voice": v[1]} for k, v in PAGES.items() if k in WEB_PAGES}
    return {
        "app": APP_NAME, "version": APP_VERSION, "repo": GITHUB_REPO,
        "kinds": {k: list(v) for k, v in A.KINDS.items()}, "kindOrder": A.KIND_ORDER,
        "styles": A.STYLES, "langs": A.LANGS, "levels": A.LEVELS, "contentRule": A.CONTENT_RULE,
        "defaultProject": A.DEFAULT_PROJECT, "schemas": A.SCHEMAS,
        "frameGuide": [list(x) for x in A.FRAME_GUIDE], "frameExtra": [list(x) for x in A.FRAME_EXTRA],
        "sample": {"project": proj, "topics": topics, "notebook": {"url": SAMPLE_NOTEBOOK, "title": "護理教學簡報使用文件"},
                   "people": [list(p) for p in SAMPLE_PEOPLE]},
        "visual": {"needs": [list(x) for x in visual.NEEDS], "styles": [list(x) for x in visual.STYLES],
                   "layouts": [list(x) for x in visual.LAYOUTS], "kindWord": visual.KIND_WORD},
        "iconRules": [list(x) for x in deck.ICON_RULES], "generic": deck.GENERIC,
        "subDefaults": [list(x) for x in deck.SUB_DEFAULTS],
        "icons": sorted(f[:-4] for f in os.listdir(os.path.join(HERE, "assets", "icons")) if f.endswith(".png")),
        "lessons": lessons, "pages": pages,
    }


def write_data():
    os.makedirs(APP, exist_ok=True)
    js = ("// 由 tools/make_pages.py 自動產生，請不要手動修改（改 Python 程式後重新產生）\n"
          "export const DATA = %s;\n" % json.dumps(data(), ensure_ascii=False, indent=1))
    with open(os.path.join(APP, "data.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(js)
    print("data.js", len(js))


def write_webpage_template():
    """互動式網頁範本：直接用 Python 版的 CSS 與程式（兩個版本產生的網頁一模一樣）。"""
    from nb import render as R
    html = ("<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>%TITLE%</title><style>"
            ":root{%VARS%}" + R.WEBPAGE_CSS + "</style></head><body>"
            "<header><div class='in'><h1 id='t'></h1><p id='st'></p><div class='by' id='by'></div></div></header>"
            "<nav id='nav'></nav><main id='m'></main>"
            "<footer>由 資料助秘NotebookLM MCP簡報 產生　<span id='ft'></span></footer>"
            "<script>const C=%DATA%;" + R.WEBPAGE_JS + "</script></body></html>")
    with open(os.path.join(APP, "webpage.tpl.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)


def copy_assets():
    for d, src in (("voice", os.path.join(HERE, "assets", "voice")),
                   (os.path.join("app", "icons"), os.path.join(HERE, "assets", "icons"))):
        dst = os.path.join(DOCS, d)
        os.makedirs(dst, exist_ok=True)
        for fn in os.listdir(src):
            if fn.endswith((".mp3", ".png")):
                shutil.copy2(os.path.join(src, fn), os.path.join(dst, fn))
    for d in (DOCS, APP):
        shutil.copy2(os.path.join(HERE, "assets", "icon.png"), os.path.join(d, "icon.png"))
    print("assets ok")


def libs():
    lib = os.path.join(APP, "lib")
    os.makedirs(lib, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="nbweb_")
    npm = os.path.join(NODE, "npm.cmd")
    env = dict(os.environ, PATH=NODE + os.pathsep + os.environ.get("PATH", ""))
    subprocess.run([npm, "init", "-y"], cwd=tmp, check=True, env=env, capture_output=True)
    subprocess.run([npm, "install", "--no-audit", "--no-fund"] + ["%s@%s" % kv for kv in LIBS.items()],
                   cwd=tmp, check=True, env=env)
    nm = os.path.join(tmp, "node_modules")
    shutil.copy2(os.path.join(nm, "pptxgenjs", "dist", "pptxgen.bundle.js"), os.path.join(lib, "pptxgen.bundle.js"))
    shutil.copy2(os.path.join(nm, "jszip", "dist", "jszip.min.js"), os.path.join(lib, "jszip.min.js"))
    for name in ("pptxgenjs", "jszip"):
        for lic in ("LICENSE", "LICENSE.markdown", "LICENSE.md"):
            p = os.path.join(nm, name, lic)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(lib, name + "-LICENSE.txt"))
                break
    shutil.rmtree(tmp, ignore_errors=True)
    print("libs ok", os.listdir(lib))


if __name__ == "__main__":
    write_data()
    write_webpage_template()
    copy_assets()
    if "--libs" in sys.argv:
        libs()
