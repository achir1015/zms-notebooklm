"""第一次使用的預設資料：權限功能、角色，以及內定範例專案「病房助理技術教育外傭實務訓練」。

內定範例的規格來自原專案的 CLAUDE.md（nb/samples/ward_template.md）與主題庫（nb/samples/ward_topics.json），
預設筆記本是使用者分享的 NotebookLM 筆記本。範本只是「起點」：換掉機構、封面格式與主題庫，就能做其他專案。
"""
import json
import os

# 權限功能：(代號, 名稱, 說明)；等級 0 無、1 查詢、2 維護
FUNCS = [
    ("GEN", "產生工具", "選筆記本產生簡報、心智圖、報告、測驗、資訊圖表；等級 2 可以產生與修改自己的成品"),
    ("NOTE", "NotebookLM 連線", "查看筆記本、測試提問；等級 2 可以登入 Google、新增筆記本、加入來源"),
    ("PROJ", "專案範本與主題庫", "封面格式、指令上下文、主題庫、年度主題表；等級 2 可以修改"),
    ("PEOPLE", "人員名單", "簡報人與指導員名單；等級 2 可以新增修改"),
    ("ALL", "全部成品", "看、修改、刪除別人產生的成品"),
    ("SYS", "系統管理", "使用者與權限、單位設定、備份還原、版本更新、操作紀錄"),
]
FUNC_NAMES = {f[0]: f[1] for f in FUNCS}
LEVEL_NAMES = {0: "無", 1: "查詢", 2: "維護"}


def _r(**kw):
    return {f[0]: kw.get(f[0], 0) for f in FUNCS}


ROLES = {
    "系統管理員": {f[0]: 2 for f in FUNCS},
    "教育訓練主管": _r(GEN=2, NOTE=2, PROJ=2, PEOPLE=2, ALL=2),
    "講師": _r(GEN=2, NOTE=1, PROJ=1, PEOPLE=1),
    "訪客": _r(GEN=1, NOTE=1, PROJ=1),
}

SAMPLE_NOTEBOOK = "https://notebook.google.com/notebook/097207c0-8984-4a58-b041-30ed62c4c23b"
SAMPLE_NAME = "病房助理技術教育外傭實務訓練"

SAMPLE_PROJECT = dict(
    name=SAMPLE_NAME, org="臺北市立聯合醫院忠孝院區", unit="RCW", unit_full="呼吸照護病房",
    cover_title_tpl="{org} {unit} {topic}教學護理實務",
    cover_subtitle="提升 RCW 照護品質，落實感染管制",
    byline_tpl="簡報人：{presenter_role} {presenter} ｜ {instructor_role}：護理師{instructor}",
    presenter_role="病房助理員", instructor_role="護理指導員",
    role_text="病房助理員（資深前輩）",
    background_text="針對 {unit}（{unit_full}）的{audience}進行實務教育訓練，提升照護品質並落實感染管制。",
    purpose_text="將生硬的醫療衛教單張轉化為生動、圖文並茂的教學簡報，方便第一線照護人員快速吸收。",
    audience_text="印尼籍、越南籍、泰國籍看護（外傭）",
    term_langs=json.dumps([["印尼", "印尼文"], ["越南", "越南文"], ["泰國", "泰文"]], ensure_ascii=False),
    font_title=45, font_sub=40, font_small=32, min_slides=10, qa_count=5, style="pastel",
    extra_rules="課程內容須注重實務操作，語氣親切且易懂；必須包含主題的「目的與步驟」、「使用目的與注意事項」關鍵實務點；"
                "內容須落實感染管制與照護品質。範本護理內容為通用版，正式授課前需護理指導員確認。",
)

# 示範人員（虛構，正式使用請改成自己的名單）
SAMPLE_PEOPLE = [("PRESENTER", "WA001", "示範病房助理甲", "病房助理員"),
                 ("PRESENTER", "WA002", "示範病房助理乙", "病房助理員"),
                 ("INSTRUCTOR", "RN001", "示範護理師甲", "護理師"),
                 ("INSTRUCTOR", "RN002", "示範護理師乙", "護理師")]


def _sample_file(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", name)


def seed_all(db, first=False):
    """每次開啟都會補上缺的參考資料（不覆蓋使用者修改過的內容）。"""
    db.exec("INSERT IGNORE INTO sys_company (id, name) VALUES (1, '')")
    if db.value("SELECT v FROM sys_meta WHERE k='sample_seeded'"):
        return
    seed_sample(db)
    db.exec("REPLACE INTO sys_meta (k, v) VALUES ('sample_seeded', '1')")


def seed_sample(db):
    """建立內定範例專案：預設筆記本、專案範本（含 CLAUDE.md 規格）、9 個月份主題、示範人員。"""
    from .mcp import normalize_url
    url, uid = normalize_url(SAMPLE_NOTEBOOK)
    db.exec("INSERT IGNORE INTO nb_notebook (uuid, url, title, description, tags, is_default, owner) "
            "VALUES (%s, %s, %s, %s, %s, 1, 'system')",
            (uid, url, "護理教學簡報使用文件", "內定範本：病房助理技術教育外傭實務訓練的照護文件與衛教單張（21 份來源）",
             "範例,外傭,技術教育"))
    nb_id = db.value("SELECT id FROM nb_notebook WHERE uuid=%s", (uid,))
    with open(_sample_file("ward_template.md"), encoding="utf-8") as f:
        spec = f.read()
    p = dict(SAMPLE_PROJECT, spec_md=spec, notebook_id=nb_id, is_sample=1, created_by="system")
    cols = list(p)
    db.exec("INSERT INTO nb_project (%s) VALUES (%s)" % (", ".join(cols), ", ".join(["%s"] * len(cols))),
            tuple(p[c] for c in cols))
    pid = db.value("SELECT MAX(id) FROM nb_project WHERE is_sample=1")
    with open(_sample_file("ward_topics.json"), encoding="utf-8") as f:
        topics = json.load(f)
    for i, t in enumerate(topics):
        data = {k: v for k, v in t.items() if k not in ("id", "month", "name", "sourceHint")}
        db.exec("INSERT INTO nb_topic (project_id, code, month, name, source_hint, data, sort) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (pid, t["id"], t.get("month"), t["name"], t.get("sourceHint", ""), json.dumps(data, ensure_ascii=False),
                 i))
    for kind, no, name, title in SAMPLE_PEOPLE:
        db.exec("INSERT INTO nb_person (project_id, kind, emp_no, name, title, note) VALUES (%s, %s, %s, %s, %s, %s)",
                (pid, kind, no, name, title, "示範資料"))
    db.exec("UPDATE sys_company SET default_project=%s WHERE id=1 AND default_project IS NULL", (pid,))
