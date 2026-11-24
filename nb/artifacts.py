"""產出物領域模型：簡報、心智圖、報告、測驗、資訊圖表。

比喻：NotebookLM 是「圖書館員」，只負責依照筆記本裡的來源回答；
本模組是「編輯」——先寫好給圖書館員的指令（Brief → prompt），拿回答案後整理成固定格式（content JSON），
再交給 render.py 這位「美編」排成 PowerPoint、Word、圖片與網頁。

同一個 content JSON 有兩種來源：
* NOTEBOOKLM：依選定的 NotebookLM 筆記本來源產生（內容不寫死，跟著文案走）
* TEMPLATE  ：依專案範本的主題庫產生（離線也能用，當作起點，再自己修改）
"""
import copy
import json
import re

KINDS = {
    "SLIDES": ("簡報", "SLIDESHOW", "blue"),
    "MINDMAP": ("心智圖", "ACCOUNT_TREE", "violet"),
    "REPORT": ("報告", "ARTICLE", "teal"),
    "QUIZ": ("測驗", "QUIZ", "amber"),
    "INFOGRAPHIC": ("資訊圖表", "INSIGHTS", "pink"),
    "WEBPAGE": ("互動式網頁", "WEB", "green"),
}
KIND_ORDER = list(KINDS)

STYLES = [
    dict(id="pastel", name="柔和插畫（活潑）", desc="奶油底、粉藍配色、3D 小圖示、多種版型",
         colors=("#5C3A32", "#BE6260", "#94C4EC", "#F8F1EA", "#3A3432"),
         prompt="柔和 3D 插畫風格，奶油色背景、粉紅與淺藍配色，搭配親切的醫護人物與立體小圖示，重點用圓角膠囊與編號呈現，活潑不枯燥。"),
    dict(id="business", name="專業企業商務", desc="深藍、深灰沉穩配色，結構化版面",
         colors=("#14325C", "#1E4D8C", "#E0A526", "#F4F6FA", "#1F2937"),
         prompt="請以專業企業商務風格設計簡報，採用深粉紅藍、深灰等沉穩配色，搭配清晰的資料圖表、結構化版面與正式排版，展現權威感與可信度。"),
    dict(id="tech", name="科技潮流", desc="深色網格、電能粉紅、霓虹光暈",
         colors=("#0B1020", "#E1306C", "#22D3EE", "#111827", "#F3F4F6"),
         prompt="科技潮流配色（如：電能粉紅、深色網格、霓虹光暈）、精密醫療防護感、硬朗直角排版。"),
    dict(id="clay", name="3D 立體插畫", desc="柔和粉藍、親切立體感",
         colors=("#5B7DB1", "#F48FB1", "#81D4FA", "#FDF7FB", "#334155"),
         prompt="3D 等角立體插畫風格，柔和的粉紅與淺藍配色，搭配親切的人物角色與立體場景，資訊以標籤與箭頭清楚標示。"),
    dict(id="warm", name="溫馨照護手繪", desc="暖色調、圖卡式步驟",
         colors=("#8D5524", "#E07A5F", "#F2CC8F", "#FFF8EE", "#3D2C1E"),
         prompt="溫馨手繪插畫風格，暖色調，步驟以圖卡與編號呈現，文字少、圖像多，適合語言程度不同的學員。"),
]
STYLE_BY_ID = {s["id"]: s for s in STYLES}

LANGS = [
    dict(id="zh", name="繁體中文", note="台灣繁體中文通用語"),
    dict(id="zh-en", name="中文＋英文對照", note="標題中英對照，內文以繁體中文為主"),
    dict(id="en", name="English", note="English, simple vocabulary"),
]
LANG_BY_ID = {x["id"]: x for x in LANGS}

LEVELS = {"basic": "基礎（短句、常用字，一句只講一件事）", "mid": "日常會話（可用一般專業用語）",
          "pro": "專業人員（可用專有名詞）"}

# 內容限定規則（取自範例專案 CLAUDE.md）：大綱階段只產生文字內容
CONTENT_RULE = ("【內容限定規則】本階段僅生成文字內容。禁止提供或加入任何視覺風格、配色、背景、圖片、插圖、圖示、"
                "圖表外觀、人物、角色、Logo、版面配置、排版或畫面描述建議。")


# ================================================================ 專案範本（可換成其他專案）
DEFAULT_PROJECT = dict(
    name="新專案", org="", unit="", unit_full="",
    cover_title_tpl="{org} {unit} {topic}",
    cover_subtitle="",
    byline_tpl="簡報人：{presenter_role} {presenter} ｜ {instructor_role}：{instructor}",
    presenter_role="講師", instructor_role="指導老師",
    role_text="資深講師", background_text="", purpose_text="將來源文件轉化為生動、易懂的教學內容。",
    audience_text="學員", term_langs=[], font_title=45, font_sub=40, font_small=32,
    min_slides=10, qa_count=5, extra_rules="",
)


def fill(tpl, **kw):
    """範本字串套值：{org}{unit}{topic}… 不存在的鍵保留原樣。"""
    return re.sub(r"\{(\w+)\}", lambda m: str(kw.get(m.group(1), m.group(0))), tpl or "")


class Brief:
    """一次產生的需求單（相當於範例專案的 TrainingSession）。"""

    def __init__(self, project=None, topic=None, **kw):
        self.project = dict(DEFAULT_PROJECT, **(project or {}))
        self.topic = topic or {}
        self.topic_name = kw.get("topic_name") or self.topic.get("name") or "自訂主題"
        self.presenter = kw.get("presenter", "")          # 「員編 姓名」
        self.instructor = kw.get("instructor", "")
        self.date = kw.get("date", "")
        self.audience = kw.get("audience") or self.project["audience_text"]
        self.term_langs = kw.get("term_langs")
        if self.term_langs is None:
            self.term_langs = [x[0] for x in self.project.get("term_langs") or []]
        self.level = kw.get("level", "basic")
        self.source_title = kw.get("source_title") or self.topic.get("sourceHint", "")
        self.source_pages = kw.get("source_pages", "")
        self.notes = kw.get("notes", "")
        self.slide_count = max(int(kw.get("slide_count") or 11), int(self.project.get("min_slides") or 1))
        self.qa_count = int(kw.get("qa_count") or self.project.get("qa_count") or 5)
        self.quiz_count = int(kw.get("quiz_count") or 10)
        self.lang = kw.get("lang", "zh")
        self.style = kw.get("style", "pastel")
        self.subtitle = kw.get("subtitle") or self.project.get("cover_subtitle", "")

    # ---------------------------------------------------------- 封面
    @property
    def cover_title(self):
        p = self.project
        return re.sub(r"\s+", " ", fill(p["cover_title_tpl"], org=p["org"], unit=p["unit"], unit_full=p["unit_full"],
                                        topic=self.topic_name)).strip()

    @property
    def byline(self):
        p = self.project
        return fill(p["byline_tpl"], presenter_role=p["presenter_role"], instructor_role=p["instructor_role"],
                    presenter=self.presenter or "[員工編號 員工姓名]", instructor=self.instructor or "[員工姓名]")

    @property
    def org_text(self):
        p = self.project
        return " ".join(x for x in (p["org"], p["unit"]) if x).strip()

    def to_json(self):
        d = {k: v for k, v in self.__dict__.items() if k not in ("project", "topic")}
        return d

    # ---------------------------------------------------------- 指令共用段落（CSIF：上下文／具體信息／目標／格式）
    def context_block(self, what):
        p = self.project
        L = ["製作%s「%s」%s。" % (self.org_text + " " if self.org_text else "", self.topic_name, what), "",
             "上下文（Context）"]
        if p.get("role_text"):
            L.append("角色／身分：%s%s。" % (p["org"], p["role_text"]))
        if p.get("background_text"):
            L.append("任務背景：" + fill(p["background_text"], unit=p["unit"], unit_full=p["unit_full"],
                                        audience=self.audience))
        if p.get("purpose_text"):
            L.append("任務目的：" + p["purpose_text"])
        L += ["", "具體信息（Specific Information）"]
        src = self.source_title or "筆記本中的來源文件"
        L.append("依據：「%s」%s。" % (src, "（來源第 %s 頁）" % self.source_pages if self.source_pages else ""))
        L.append("內容以筆記本中的來源文件為唯一依據；下方架構只是建議，如與來源不同，一律以來源為準。來源沒有提到的內容不要自行編造。")
        if self.notes:
            L.append("本次文案重點與特別要求：" + self.notes)
        L.append("對象：%s；語言程度：%s。" % (self.audience, LEVELS.get(self.level, self.level)))
        L.append("語言：%s。" % LANG_BY_ID.get(self.lang, LANGS[0])["note"])
        if self.org_text:
            L.append("機構名稱一律使用「%s」。" % self.org_text)
        if p.get("extra_rules"):
            L.append(p["extra_rules"])
        return L


# ================================================================ JSON 格式說明（要 NotebookLM 照著回答）
SCHEMAS = {
    "SLIDES": '{"slides":[{"label":"頁型（例：目的與重要性）","title":"投影片標題","subtitle":"一句吸引人的副標（15 字內）",'
              '"points":["重點一（20 字內）","重點二"],"notes":"講者備註（口語、短句）"}],"qa":[{"q":"題目","a":"參考答案"}]}',
    "MINDMAP": '{"root":{"text":"中心主題","children":[{"text":"分支","children":[{"text":"子項"}]}]}}',
    "REPORT": '{"title":"報告標題","summary":"摘要（3～5 句）","sections":[{"heading":"小節標題",'
              '"paragraphs":["段落"],"bullets":["條列重點"]}],"conclusion":"結論","references":["引用的來源名稱"]}',
    "QUIZ": '{"title":"測驗名稱","questions":[{"type":"single","q":"題目","options":["A 選項","B 選項","C 選項","D 選項"],'
            '"answer":"A","explain":"解析（說明依據）"},{"type":"tf","q":"是非題","options":["○","✕"],"answer":"○",'
            '"explain":"解析"}]}',
    "INFOGRAPHIC": '{"title":"大標題","subtitle":"一句話說明","stats":[{"value":"數字或關鍵字","label":"說明"}],'
                   '"sections":[{"heading":"區塊標題","points":["重點"]}],"tip":"一句最重要的提醒","footer":"資料來源"}',
    "WEBPAGE": '{"title":"網頁標題","subtitle":"一句話介紹","intro":"開場段落（2～4 句）",'
               '"sections":[{"heading":"章節標題","summary":"一句摘要","points":["重點"],"detail":"展開後的補充說明"}],'
               '"cards":[{"front":"關鍵詞","back":"解釋"}],"faq":[{"q":"常見問題","a":"回答"}],'
               '"quiz":[{"q":"題目","options":["選項一","選項二","選項三"],"answer":0,"explain":"解析"}],'
               '"takeaway":"一句話帶走的重點"}',
}


def build_prompt(kind, brief, frame=None):
    """組出交給 NotebookLM 的完整指令（也可以複製到 NotebookLM 官方網頁使用）。"""
    b = brief
    if kind == "SLIDES":
        L = b.context_block("教育訓練簡報內容")
        frame = frame or slide_frame(b)
        L += ["", "目標（Intent）", "規劃每一頁簡報的文字標題、重點與講者備註；把複雜的步驟簡化為容易執行的實務清單。",
              "限制：簡報共 %d 張（含封面與最後的感謝頁，不少於 %d 張）；最後要有 Q&A %d 題作為驗收。"
              % (b.slide_count, b.project.get("min_slides") or 1, b.qa_count),
              "第一頁封面固定為：",
              "[標題 %spt] %s" % (b.project["font_title"], b.cover_title),
              "[次標題 %spt] %s" % (b.project["font_sub"], b.subtitle),
              "[小標題 %spt] %s" % (b.project["font_small"], b.byline),
              "", "建議架構（各頁頁型）："]
        L += ["%d. %s：%s" % (i + 1, f["label"], f.get("guide", "")) for i, f in enumerate(frame)]
        L += ["", CONTENT_RULE]
    elif kind == "MINDMAP":
        L = b.context_block("心智圖")
        L += ["", "目標（Intent）", "把來源整理成一張心智圖：中心主題是「%s」，第一層 4～7 個分支，"
              "每個分支 2～6 個子項，子項可以再往下一層；每個節點不超過 18 個字。" % b.topic_name, "", CONTENT_RULE]
    elif kind == "REPORT":
        L = b.context_block("書面報告")
        L += ["", "目標（Intent）", "寫一份結構完整的報告：摘要、4～6 個小節（每節有段落與條列重點）、結論；"
              "引用的來源名稱列在 references。全文約 1500～2500 字。", "", CONTENT_RULE]
    elif kind == "QUIZ":
        L = b.context_block("測驗卷")
        L += ["", "目標（Intent）", "出 %d 題測驗：大約七成單選題（4 個選項、只有一個正確答案）、三成是非題；"
              "題目要能從來源找到依據，每題附解析。答案用選項字母（A～D）或 ○／✕。" % b.quiz_count, "", CONTENT_RULE]
    elif kind == "INFOGRAPHIC":
        L = b.context_block("一頁式資訊圖表")
        L += ["", "目標（Intent）", "把最重要的內容濃縮成一張資訊圖表：大標題、一句副標、3～4 個關鍵數字或關鍵字（stats）、"
              "4～6 個區塊（每區塊 2～4 點、每點不超過 22 字）、一句最重要的提醒。", "", CONTENT_RULE]
    elif kind == "WEBPAGE":
        L = b.context_block("互動式學習網頁")
        L += ["", "目標（Intent）", "把來源整理成一個互動式學習網頁的內容：開場段落、4～7 個章節（每章一句摘要、3～5 個重點、"
              "一段展開補充）、6～10 張關鍵詞翻牌卡、4～6 題常見問答、5 題選擇題（answer 是正確選項的序號，從 0 開始）"
              "與一句帶走的重點。", "", CONTENT_RULE]
    else:
        raise ValueError(kind)
    L += ["", "格式要求（Response Format）",
          "只回覆一段 JSON（不要任何說明文字、不要 Markdown 標記、不要引用編號），格式如下：", SCHEMAS[kind]]
    return "\n".join(L)


# ================================================================ 簡報頁型架構（依文案架構）
FRAME_GUIDE = [
    ("破題與議程", "用一個問題或情境引起注意，列出今天 4～5 個學習重點"),
    ("目的與重要性", "這項主題的目的 3～4 點，做不好會有什麼風險"),
    ("用物準備", "需要準備的用物與規格"),
    ("操作步驟（一）", "前半段步驟，依順序 4～5 點，標出關鍵數字（溫度、角度、時間、次數）"),
    ("操作步驟（二）", "後半段步驟，依順序 4～5 點，包含結束後的整理與紀錄"),
    ("注意事項與安全", "安全與感染管制重點 3～4 點"),
    ("常見錯誤與正確做法", "3～4 組「錯誤 → 正確」對照，以及需要立即報告的情形"),
    ("關鍵詞母語對照", "重要詞彙的母語對照（依學員語言）"),
    ("總結與行動呼籲", "重申 3 個最重要的動作，一句明確的行動呼籲"),
    ("感謝與問答", "Q&A 時間與聯絡方式"),
]
FRAME_EXTRA = [("實作演練", "分組實作的方式與檢核重點"), ("情境練習", "一個情境題與思考方向"),
               ("每日檢核", "每天上班的自我檢核清單")]


def slide_frame(brief):
    """依張數排出頁型（封面不算在內）。"""
    base = list(FRAME_GUIDE)
    if not brief.term_langs:
        base = [f for f in base if f[0] != "關鍵詞母語對照"]
    need = brief.slide_count - 1
    extra = list(FRAME_EXTRA)
    while len(base) < need and extra:
        base.insert(len(base) - 2, extra.pop(0))
    while len(base) < need:
        base.insert(len(base) - 2, ("補充重點 %d" % (len(base) - 8), "依來源補充的重點"))
    if len(base) > need:
        keep_tail = base[-2:]
        base = base[:max(need - 2, 1)] + keep_tail
    return [dict(label=a, guide=g) for a, g in base]


# ================================================================ 解析 NotebookLM 回答
def extract_json(text):
    """從回答裡挖出 JSON（容忍 ```json 包裝、前後說明文字、引用編號 [1]、全形引號）。"""
    t = (text or "").strip()
    t = re.sub(r"^\[AI-GENERATED[^\]]*\]\s*", "", t)
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1)
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0] or [-1])
    if start < 0:
        raise ValueError("回答裡沒有 JSON")
    t = t[start:]
    for cand in (t, _balance(t)):
        for fixer in (lambda s: s, _clean_json):
            try:
                return json.loads(fixer(cand))
            except ValueError:
                pass
    raise ValueError("JSON 格式不正確")


def _balance(t):
    depth, out, in_str, esc = 0, [], False, False
    for ch in t:
        out.append(ch)
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                break
    return "".join(out)


def _clean_json(s):
    s = s.replace("“", '"').replace("”", '"')
    s = re.sub(r"\s*\[\d+(?:[,，\-–]\s*\d+)*\]", "", s)      # 引用編號 [1] [2, 3]
    s = re.sub(r",\s*([}\]])", r"\1", s)                     # 結尾多的逗號
    return s


def strip_cites(v):
    if isinstance(v, str):
        return re.sub(r"\s*\[\d+(?:[,，\-–]\s*\d+)*\]", "", v).strip()
    if isinstance(v, list):
        return [strip_cites(x) for x in v]
    if isinstance(v, dict):
        return {k: strip_cites(x) for k, x in v.items()}
    return v


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip(" •-・\t") for x in re.split(r"[\n；;]", v) if x.strip(" •-・\t")]
    return [str(x).strip() for x in v if str(x).strip()]


def normalize(kind, data, brief):
    """把回答整理成固定格式；缺的欄位補預設值。簡報封面一律依專案格式（不交給 AI）。"""
    data = strip_cites(data)
    if kind == "SLIDES":
        if isinstance(data, list):
            data = {"slides": data}
        slides = []
        for s in data.get("slides") or []:
            if not isinstance(s, dict):
                continue
            slides.append(dict(label=str(s.get("label") or s.get("type") or "").strip(),
                               title=str(s.get("title") or "").strip(),
                               subtitle=str(s.get("subtitle") or "").strip(),
                               points=_as_list(s.get("points") or s.get("content") or s.get("bullets")),
                               notes=str(s.get("notes") or s.get("speaker_notes") or "").strip()))
        slides = [s for s in slides if s["title"] or s["points"]]
        if slides and ("封面" in slides[0]["label"] or slides[0]["title"] == brief.cover_title):
            slides = slides[1:]
        qa = [dict(q=str(x.get("q") or x.get("question") or ""), a=str(x.get("a") or x.get("answer") or ""))
              for x in data.get("qa") or [] if isinstance(x, dict)]
        return dict(cover=cover_of(brief), slides=[cover_slide(brief)] + slides, qa=qa[:max(brief.qa_count, 1)])
    if kind == "MINDMAP":
        root = data.get("root") if isinstance(data, dict) and "root" in data else data
        return dict(root=_node(root, brief.topic_name))
    if kind == "REPORT":
        secs = []
        for s in data.get("sections") or []:
            if isinstance(s, dict):
                secs.append(dict(heading=str(s.get("heading") or s.get("title") or ""),
                                 paragraphs=_as_list(s.get("paragraphs")) if isinstance(s.get("paragraphs"), list)
                                 else [x for x in [str(s.get("paragraphs") or s.get("text") or "")] if x],
                                 bullets=_as_list(s.get("bullets") or s.get("points"))))
        return dict(title=str(data.get("title") or brief.topic_name), summary=str(data.get("summary") or ""),
                    sections=secs, conclusion=str(data.get("conclusion") or ""),
                    references=_as_list(data.get("references")), byline=brief.byline, org=brief.org_text)
    if kind == "QUIZ":
        qs = []
        for q in data.get("questions") or (data if isinstance(data, list) else []):
            if not isinstance(q, dict):
                continue
            opts = _as_list(q.get("options"))
            typ = str(q.get("type") or ("tf" if len(opts) == 2 else "single" if opts else "short")).lower()
            if typ not in ("single", "tf", "short"):
                typ = "single" if opts else "short"
            if typ == "tf" and not opts:
                opts = ["○", "✕"]
            opts = [re.sub(r"^[A-DＡ-Ｄ][\.、．:：)\s]+", "", o).strip() for o in opts] if typ == "single" else opts
            qs.append(dict(type=typ, q=str(q.get("q") or q.get("question") or ""), options=opts,
                           answer=_norm_answer(q.get("answer"), typ, opts), explain=str(q.get("explain") or "")))
        return dict(title=str(data.get("title") or (brief.topic_name + " 測驗")) if isinstance(data, dict)
                    else brief.topic_name + " 測驗", questions=[q for q in qs if q["q"]])
    if kind == "INFOGRAPHIC":
        return dict(title=str(data.get("title") or brief.topic_name), subtitle=str(data.get("subtitle") or ""),
                    stats=[dict(value=str(x.get("value", "")), label=str(x.get("label", "")))
                           for x in data.get("stats") or [] if isinstance(x, dict)][:4],
                    sections=[dict(heading=str(x.get("heading", "")), points=_as_list(x.get("points")))
                              for x in data.get("sections") or [] if isinstance(x, dict)][:6],
                    tip=str(data.get("tip") or ""), footer=str(data.get("footer") or brief.org_text))
    if kind == "WEBPAGE":
        def qz(x):
            opts = _as_list(x.get("options"))
            a = x.get("answer", 0)
            if not isinstance(a, int):
                letter = _norm_answer(a, "single", opts)
                a = "ABCD".find(letter) if letter in "ABCD" else 0
            return dict(q=str(x.get("q", "")), options=opts, answer=max(0, min(int(a), max(len(opts) - 1, 0))),
                        explain=str(x.get("explain", "")))
        return dict(title=str(data.get("title") or brief.topic_name), subtitle=str(data.get("subtitle") or ""),
                    intro=str(data.get("intro") or ""),
                    sections=[dict(heading=str(x.get("heading", "")), summary=str(x.get("summary", "")),
                                   points=_as_list(x.get("points")), detail=str(x.get("detail", "")))
                              for x in data.get("sections") or [] if isinstance(x, dict)],
                    cards=[dict(front=str(x.get("front", "")), back=str(x.get("back", "")))
                           for x in data.get("cards") or [] if isinstance(x, dict)],
                    faq=[dict(q=str(x.get("q", "")), a=str(x.get("a", ""))) for x in data.get("faq") or []
                         if isinstance(x, dict)],
                    quiz=[qz(x) for x in data.get("quiz") or [] if isinstance(x, dict) and x.get("q")],
                    takeaway=str(data.get("takeaway") or ""), footer=brief.org_text, byline=brief.byline)
    raise ValueError(kind)


def _norm_answer(a, typ, opts):
    a = str(a or "").strip()
    if typ == "single":
        m = re.match(r"^[\(（]?([A-DＡ-Ｄa-d])", a)
        if m:
            return "ABCD"["ＡＢＣＤ".find(m.group(1))] if m.group(1) in "ＡＢＣＤ" else m.group(1).upper()
        for i, o in enumerate(opts):
            if a and (a == o or a in o):
                return "ABCD"[i] if i < 4 else "A"
        return "A"
    if typ == "tf":
        return "✕" if a[:1] in ("✕", "X", "x", "×", "錯", "否", "F", "f") or a.lower().startswith("false") else "○"
    return a


def _node(n, default="主題", depth=0):
    if isinstance(n, str):
        return dict(text=n, children=[])
    n = n or {}
    kids = n.get("children") or []
    return dict(text=str(n.get("text") or n.get("name") or n.get("title") or default)[:40],
                children=[_node(k, "", depth + 1) for k in kids][:10] if depth < 4 else [])


def cover_of(brief):
    return dict(title=brief.cover_title, subtitle=brief.subtitle, byline=brief.byline,
                sizes=[brief.project["font_title"], brief.project["font_sub"], brief.project["font_small"]])


def cover_slide(brief):
    return dict(label="封面頁", title=brief.cover_title, points=[brief.subtitle, brief.byline], kind="cover",
                notes="大家好，我是%s。今天要和大家一起學習「%s」。" % (brief.presenter.split(" ")[-1] or "講師",
                                                         brief.topic_name))


# ================================================================ 內建範本（離線）：依主題庫產生
def from_template(kind, brief):
    t = _topic_or_blank(brief)
    name = brief.topic_name
    if kind == "SLIDES":
        return dict(cover=cover_of(brief), slides=_template_slides(brief, t), qa=[dict(q=q, a=a) for q, a in t["qa"]])
    if kind == "MINDMAP":
        return dict(root=dict(text=name, children=[
            _branch("目的", t["purposes"]), _branch("用物準備", t["supplies"]),
            _branch(t["stepsA"]["title"], t["stepsA"]["items"]), _branch(t["stepsB"]["title"], t["stepsB"]["items"]),
            _branch("注意事項", t["cautions"]), _branch("常見錯誤", ["%s → %s" % tuple(e) for e in t["errors"]]),
            _branch("立即報告", _as_list(t["report"].replace("、", "\n")))]))
    if kind == "REPORT":
        return dict(title="%s 實務報告" % name, summary="%s。本報告整理「%s」的目的、用物、操作步驟、注意事項與常見錯誤，"
                    "作為教育訓練與日常照護的參考。" % (t["hook"], name),
                    sections=[dict(heading="一、目的與重要性", paragraphs=[], bullets=t["purposes"]),
                              dict(heading="二、用物準備", paragraphs=[], bullets=t["supplies"]),
                              dict(heading="三、" + t["stepsA"]["title"], paragraphs=[], bullets=t["stepsA"]["items"]),
                              dict(heading="四、" + t["stepsB"]["title"], paragraphs=[], bullets=t["stepsB"]["items"]),
                              dict(heading="五、注意事項", paragraphs=[], bullets=t["cautions"]),
                              dict(heading="六、常見錯誤與正確做法", paragraphs=["發現以下情形要立即報告：%s。" % t["report"]],
                                   bullets=["✗ %s → ✓ %s" % tuple(e) for e in t["errors"]])],
                    conclusion=t["action"], references=[brief.source_title or t.get("sourceHint", "")],
                    byline=brief.byline, org=brief.org_text)
    if kind == "QUIZ":
        return dict(title="%s 測驗" % name, questions=_template_quiz(t, brief.quiz_count))
    if kind == "INFOGRAPHIC":
        return dict(title=name, subtitle=t["hook"],
                    stats=[dict(value=str(len(t["purposes"])), label="個照護目的"),
                           dict(value=str(len(t["stepsA"]["items"]) + len(t["stepsB"]["items"])), label="個操作步驟"),
                           dict(value=str(len(t["cautions"])), label="項安全重點"),
                           dict(value=str(len(t["qa"])), label="題課後驗收")],
                    sections=[dict(heading="為什麼要做", points=t["purposes"][:4]),
                              dict(heading="準備用物", points=t["supplies"][:4]),
                              dict(heading="步驟重點", points=(t["stepsA"]["items"] + t["stepsB"]["items"])[:4]),
                              dict(heading="安全第一", points=t["cautions"][:4]),
                              dict(heading="常見錯誤", points=["✗ %s → ✓ %s" % tuple(e) for e in t["errors"]][:3]),
                              dict(heading="立即報告", points=_as_list(t["report"].replace("、", "\n"))[:4])],
                    tip=t["action"], footer=brief.org_text)
    if kind == "WEBPAGE":
        quiz = []
        for q in _template_quiz(t, 20):
            if q["type"] == "single":
                quiz.append(dict(q=q["q"], options=q["options"], answer="ABCD".find(q["answer"]), explain=q["explain"]))
        terms = [dict(front=row[0], back="｜".join(x for x in row[1:] if x)) for row in t.get("terms") or []]
        terms += [dict(front="✗ " + w, back="✓ " + r) for w, r in t["errors"] if w and r]
        return dict(title="%s 互動學習" % name, subtitle=t["hook"],
                    intro="這個網頁整理「%s」的目的、用物、步驟與注意事項。點章節可以展開補充說明，翻牌卡可以練習關鍵詞，"
                          "最後做小測驗檢查自己學會了沒有。" % name,
                    sections=[dict(heading="為什麼要做", summary=t["purposes"][0], points=t["purposes"],
                                   detail="做對了，病人舒服、照顧者也安全。"),
                              dict(heading="準備用物", summary="開始前先把東西準備好", points=t["supplies"],
                                   detail="東西準備齊全，做的時候就不會手忙腳亂。"),
                              dict(heading=t["stepsA"]["title"], summary=t["stepsA"]["items"][0],
                                   points=t["stepsA"]["items"], detail="一個步驟做完再做下一個。"),
                              dict(heading=t["stepsB"]["title"], summary=t["stepsB"]["items"][0],
                                   points=t["stepsB"]["items"], detail="結束後記得整理與紀錄。"),
                              dict(heading="安全第一", summary=t["cautions"][0], points=t["cautions"],
                                   detail="發現異常：%s，要立即報告。" % t["report"])],
                    cards=terms[:10], faq=[dict(q=q, a=a) for q, a in t["qa"]], quiz=quiz[:5],
                    takeaway=t["action"], footer=brief.org_text, byline=brief.byline)
    raise ValueError(kind)


def _branch(text, items):
    return dict(text=text, children=[dict(text=str(x)[:40], children=[]) for x in items])


def blank_topic(name):
    return dict(name=name, sourceHint="%s相關文件" % name, hook="今天一起學會「%s」！" % name,
                purposes=["（請填寫）目的一", "（請填寫）目的二"], supplies=["（請填寫）需要準備的用物"],
                stepsA=dict(title="操作步驟（一）", items=["（請填寫）步驟"]),
                stepsB=dict(title="操作步驟（二）", items=["（請填寫）步驟"]),
                cautions=["（請填寫）注意事項"], errors=[["（請填寫）常見錯誤", "（請填寫）正確做法"]],
                report="（請填寫）需要立即報告的情形", action="把「%s」的重點每天做到、做對。" % name,
                qa=[["（請填寫）第 %d 題" % i, "（請填寫）參考答案"] for i in range(1, 6)], terms=[])


def _topic_or_blank(brief):
    t = copy.deepcopy(brief.topic or {})
    base = blank_topic(brief.topic_name)
    for k, v in base.items():
        if not t.get(k):
            t[k] = v
    return t


def _template_slides(brief, t):
    """依範例專案（OutlineBuilder）的頁型排課。"""
    name = brief.topic_name
    pres = brief.presenter.split(" ")[-1] if brief.presenter else ""
    inst = brief.instructor.split(" ")[-1] if brief.instructor else ""
    S = [cover_slide(brief)]
    S[0]["notes"] = ("大家好，我是%s。今天由%s陪我們一起學「%s」。請大家放輕鬆，聽不懂可以隨時舉手，"
                     "我們會用簡單的中文、慢慢說，也會實際示範。" % (pres or "講師", inst or "指導老師", name))

    def add(label, title, points, notes):
        S.append(dict(label=label, title=title, points=list(points), notes=notes))

    add("破題與議程", t["hook"], ["為什麼要做（目的）", "要準備什麼（用物）", "怎麼做（步驟）", "哪裡要小心（注意事項）",
                              "課後驗收 Q&A %d 題" % brief.qa_count],
        "先問大家一個問題：%s 今天我們分五個部分，最後會有小測驗，請大家認真聽。" % t["hook"])
    add("目的與重要性", "為什麼要做好「%s」？" % name, t["purposes"],
        "這一頁講目的。重點是：%s。做對了，病人舒服、我們也安全。" % t["purposes"][0])
    add("用物準備", "開始前，先把東西準備好", t["supplies"], "我現在一樣一樣拿給大家看，請跟著我說出名稱。")
    add("操作步驟（一）", t["stepsA"]["title"], t["stepsA"]["items"], "這一頁我會一邊說一邊示範，一個步驟做完再做下一個。")
    add("操作步驟（二）", t["stepsB"]["title"], t["stepsB"]["items"], "接著第二部分。等一下請兩位同學上來練習。")
    add("注意事項與安全", "安全第一：這幾點一定要記住", t["cautions"], "這一頁是安全重點。特別提醒：%s。" % t["cautions"][0])
    add("常見錯誤與正確做法", "這樣做不對！正確應該這樣做", ["✗ %s → ✓ %s" % tuple(e) for e in t["errors"]],
        "這些都是常看到的錯誤。看到以下情形要馬上報告：%s。" % t["report"])
    langs = brief.project.get("term_langs") or []
    cols = [(i + 1, lab) for i, (lab, _l) in enumerate(langs) if lab in brief.term_langs]
    if cols and t.get("terms"):
        add("關鍵詞母語對照", "關鍵詞，用你的語言記住",
            ["%s：%s" % (row[0], "｜".join("%s %s" % (lab, row[c]) for c, lab in cols if c < len(row)))
             for row in t["terms"]], "請大家用自己的語言唸一次這些關鍵詞，再用中文唸一次。（母語翻譯請由學員或通譯協助確認。）")
    add("總結與行動呼籲", "重點回顧與下一步行動",
        [t["stepsA"]["items"][0], t["cautions"][0], "立即報告：" + t["report"], "行動呼籲：" + t["action"]],
        "最後幫大家整理重點。請記住一句話：%s" % t["action"])
    add("感謝與問答", "感謝聆聽", ["Q&A 時間：有問題請舉手", "課後驗收：Q&A %d 題（紙本作答）" % brief.qa_count,
                             "聯絡：%s／%s" % (brief.presenter or "講師", brief.instructor or "指導老師")],
        "謝謝大家今天認真學習！現在發下 Q&A，請寫完交給我。")
    extras = [("實作演練", "換你試試看：分組實作演練", ["兩人一組，一人操作、一人檢查", "依步驟清單逐項打勾", "指導老師現場回饋"],
               "請兩人一組，照著步驟清單練習。做完互相交換角色。"),
              ("情境練習", "情境題：如果是你，會怎麼做？", ["情境：照護中發現「%s」" % t["report"].split("、")[0],
                                                     "你的第一個動作是？", "要報告誰？要說什麼？"],
               "請大家想一想，再分享答案。重點是：發現異常，先保護病人、再立即報告。"),
              ("每日檢核", "每天上班的自我檢核清單", ["□ " + c for c in t["cautions"][:3]], "這張清單可以拍照存在手機裡。")]
    i = 0
    while len(S) < brief.slide_count and i < len(extras):
        lab, title, pts, notes = extras[i]
        S.insert(len(S) - 2, dict(label=lab, title=title, points=pts, notes=notes))
        i += 1
    return S


def _shuffle(a, seed):
    """可重現的洗牌（線上版 JavaScript 用同一個演算法，兩邊結果一樣）。"""
    for i in range(len(a) - 1, 0, -1):
        seed[0] = (seed[0] * 1103515245 + 12345) % 2147483648
        j = seed[0] % (i + 1)
        a[i], a[j] = a[j], a[i]


def _template_quiz(t, n):
    seed = [sum(ord(ch) for ch in t["name"]) or 1]
    qs = []
    # 常見錯誤 → 單選題（正確做法 vs 其他錯誤做法）
    errs = [e for e in t["errors"] if len(e) == 2]
    for w, r in errs:
        wrong = [x[0] for x in errs if x[0] != w][:3]
        while len(wrong) < 3:
            wrong.append(["不必在意，照平常習慣做", "等下班再處理", "請家屬自己處理"][len(wrong)])
        opts = [r] + wrong
        _shuffle(opts, seed)
        qs.append(dict(type="single", q="關於「%s」，正確的做法是？" % w, options=opts, answer="ABCD"[opts.index(r)],
                       explain="正確做法：%s。" % r))
    for c in t["cautions"]:
        qs.append(dict(type="tf", q=c, options=["○", "✕"], answer="○", explain="這是安全重點，要做到。"))
    for w, r in errs:
        qs.append(dict(type="tf", q=w + "，這樣做是對的。", options=["○", "✕"], answer="✕", explain="應該：%s。" % r))
    for q, a in t["qa"]:
        qs.append(dict(type="short", q=q, options=[], answer=a, explain=""))
    return qs[:max(n, 1)]


# ================================================================ 其他輸出用的純文字
def outline_text(content):
    """簡報純文字大綱（郵件內文、複製用）。"""
    L = []
    for i, s in enumerate(content.get("slides", []), 1):
        L.append("【投影片 %d｜%s】%s" % (i, s.get("label", ""), s.get("title", "")))
        L += ["  • " + p for p in s.get("points", [])]
        if s.get("notes"):
            L.append("  講者備註：" + s["notes"])
        L.append("")
    if content.get("qa"):
        L.append("【Q&A %d 題】" % len(content["qa"]))
        L += ["%d. %s\n   答：%s" % (i, x["q"], x["a"]) for i, x in enumerate(content["qa"], 1)]
    return "\n".join(L)


def mindmap_markdown(node, depth=0):
    L = [("#" if depth == 0 else "  " * (depth - 1) + "-") + " " + node["text"]]
    for k in node.get("children", []):
        L.append(mindmap_markdown(k, depth + 1))
    return "\n".join(L)


def summary_of(kind, content):
    """清單上顯示的一句摘要。"""
    if kind == "SLIDES":
        return "%d 張投影片、Q&A %d 題" % (len(content.get("slides", [])), len(content.get("qa", [])))
    if kind == "MINDMAP":
        def cnt(n):
            return 1 + sum(cnt(k) for k in n.get("children", []))
        return "%d 個分支、%d 個節點" % (len(content.get("root", {}).get("children", [])), cnt(content.get("root", {})))
    if kind == "REPORT":
        return "%d 個小節" % len(content.get("sections", []))
    if kind == "QUIZ":
        return "%d 題" % len(content.get("questions", []))
    if kind == "INFOGRAPHIC":
        return "%d 個數字、%d 個區塊" % (len(content.get("stats", [])), len(content.get("sections", [])))
    if kind == "WEBPAGE":
        return "%d 章、%d 張卡、%d 題" % (len(content.get("sections", [])), len(content.get("cards", [])),
                                       len(content.get("quiz", [])))
    return ""


# ================================================================ 純文字編輯格式（成品庫「修改」用；可來回轉換）
def to_text(kind, c):
    L = []
    if kind == "MINDMAP":
        def walk(n, d):
            L.append(("# " if d == 0 else "  " * (d - 1) + "- ") + n["text"])
            for k in n.get("children", []):
                walk(k, d + 1)
        walk(c.get("root") or {"text": "主題"}, 0)
    elif kind == "REPORT":
        L += ["# " + c.get("title", ""), "摘要：" + c.get("summary", ""), ""]
        for s in c.get("sections", []):
            L.append("## " + s.get("heading", ""))
            L += s.get("paragraphs", [])
            L += ["- " + b for b in s.get("bullets", [])]
            L.append("")
        L += ["結論：" + c.get("conclusion", ""), "參考來源：" + "；".join(c.get("references", []))]
    elif kind == "QUIZ":
        L += ["# " + c.get("title", ""), ""]
        for i, q in enumerate(c.get("questions", []), 1):
            L.append("%d.（%s）%s" % (i, {"single": "單選", "tf": "是非", "short": "問答"}[q["type"]], q["q"]))
            if q["type"] == "single":
                L += ["%s. %s" % ("ABCD"[j], o) for j, o in enumerate(q["options"][:4])]
            L.append("答案：" + q.get("answer", ""))
            if q.get("explain"):
                L.append("解析：" + q["explain"])
            L.append("")
    elif kind == "INFOGRAPHIC":
        L += ["# " + c.get("title", ""), "副標：" + c.get("subtitle", "")]
        L += ["數字：%s｜%s" % (s["value"], s["label"]) for s in c.get("stats", [])]
        L.append("")
        for s in c.get("sections", []):
            L.append("## " + s.get("heading", ""))
            L += ["- " + p for p in s.get("points", [])]
            L.append("")
        L += ["提醒：" + c.get("tip", ""), "頁尾：" + c.get("footer", "")]
    elif kind == "WEBPAGE":
        L += ["# " + c.get("title", ""), "副標：" + c.get("subtitle", ""), "介紹：" + c.get("intro", ""), ""]
        for s in c.get("sections", []):
            L += ["## " + s.get("heading", ""), "摘要：" + s.get("summary", "")]
            L += ["- " + p for p in s.get("points", [])]
            L += ["補充：" + s.get("detail", ""), ""]
        L += ["卡片：%s｜%s" % (x["front"], x["back"]) for x in c.get("cards", [])]
        L.append("")
        for x in c.get("faq", []):
            L += ["問：" + x["q"], "答：" + x["a"]]
        L.append("")
        for x in c.get("quiz", []):
            L.append("題目：" + x["q"])
            L += [("* " if j == x["answer"] else "- ") + o for j, o in enumerate(x["options"])]
            L.append("解析：" + x.get("explain", ""))
        L += ["", "帶走：" + c.get("takeaway", "")]
    return "\n".join(L).strip() + "\n"


def from_text(kind, text, old=None):
    old = old or {}
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    if kind == "MINDMAP":
        root, stack = None, []
        for ln in lines:
            if not ln.strip():
                continue
            if ln.startswith("# "):
                root = dict(text=ln[2:].strip(), children=[])
                stack = [(-1, root)]
                continue
            if root is None:
                root = dict(text="主題", children=[])
                stack = [(-1, root)]
            ind = (len(ln) - len(ln.lstrip(" "))) // 2
            node = dict(text=ln.strip().lstrip("-•* ").strip(), children=[])
            while stack and stack[-1][0] >= ind:
                stack.pop()
            stack[-1][1]["children"].append(node)
            stack.append((ind, node))
        return dict(root=root or dict(text="主題", children=[]))
    if kind == "REPORT":
        c = dict(old, title="", summary="", sections=[], conclusion="", references=[])
        cur = None
        for ln in lines:
            s = ln.strip()
            if s.startswith("## "):
                cur = dict(heading=s[3:].strip(), paragraphs=[], bullets=[])
                c["sections"].append(cur)
            elif s.startswith("# "):
                c["title"] = s[2:].strip()
            elif s.startswith("摘要："):
                c["summary"] = s[3:].strip()
            elif s.startswith("結論："):
                c["conclusion"], cur = s[3:].strip(), None
            elif s.startswith("參考來源："):
                c["references"] = [x.strip() for x in re.split(r"[；;]", s[5:]) if x.strip()]
            elif s and cur is not None:
                (cur["bullets"] if s[:2] in ("- ", "• ") else cur["paragraphs"]).append(s.lstrip("-• ").strip())
        return c
    if kind == "QUIZ":
        c = dict(title="", questions=[])
        q = None
        for ln in lines:
            s = ln.strip()
            m = re.match(r"^\d+[\.、．]\s*[（(](單選|是非|問答)[）)]\s*(.*)$", s)
            if s.startswith("# "):
                c["title"] = s[2:].strip()
            elif m:
                typ = {"單選": "single", "是非": "tf", "問答": "short"}[m.group(1)]
                q = dict(type=typ, q=m.group(2).strip(), options=["○", "✕"] if typ == "tf" else [], answer="", explain="")
                c["questions"].append(q)
            elif q is not None and re.match(r"^[A-D][\.、．]\s*", s) and q["type"] == "single":
                q["options"].append(re.sub(r"^[A-D][\.、．]\s*", "", s))
            elif q is not None and s.startswith("答案："):
                q["answer"] = _norm_answer(s[3:], q["type"], q["options"])
            elif q is not None and s.startswith("解析："):
                q["explain"] = s[3:].strip()
        return c
    if kind == "INFOGRAPHIC":
        c = dict(title="", subtitle="", stats=[], sections=[], tip="", footer="")
        cur = None
        for ln in lines:
            s = ln.strip()
            if s.startswith("## "):
                cur = dict(heading=s[3:].strip(), points=[])
                c["sections"].append(cur)
            elif s.startswith("# "):
                c["title"] = s[2:].strip()
            elif s.startswith("副標："):
                c["subtitle"] = s[3:].strip()
            elif s.startswith("數字："):
                v, _, lab = s[3:].partition("｜")
                c["stats"].append(dict(value=v.strip(), label=lab.strip()))
            elif s.startswith("提醒："):
                c["tip"], cur = s[3:].strip(), None
            elif s.startswith("頁尾："):
                c["footer"] = s[3:].strip()
            elif s and cur is not None:
                cur["points"].append(s.lstrip("-• ").strip())
        return c
    if kind == "WEBPAGE":
        c = dict(old, title="", subtitle="", intro="", sections=[], cards=[], faq=[], quiz=[], takeaway="")
        cur, q, faq = None, None, None
        for ln in lines:
            s = ln.strip()
            if s.startswith("## "):
                cur, q = dict(heading=s[3:].strip(), summary="", points=[], detail=""), None
                c["sections"].append(cur)
            elif s.startswith("# "):
                c["title"] = s[2:].strip()
            elif s.startswith("副標："):
                c["subtitle"] = s[3:].strip()
            elif s.startswith("介紹："):
                c["intro"] = s[3:].strip()
            elif s.startswith("摘要：") and cur:
                cur["summary"] = s[3:].strip()
            elif s.startswith("補充：") and cur:
                cur["detail"] = s[3:].strip()
            elif s.startswith("卡片："):
                a, _, b = s[3:].partition("｜")
                c["cards"].append(dict(front=a.strip(), back=b.strip()))
                cur = None
            elif s.startswith("問："):
                faq, cur = dict(q=s[2:].strip(), a=""), None
                c["faq"].append(faq)
            elif s.startswith("答：") and faq:
                faq["a"] = s[2:].strip()
            elif s.startswith("題目："):
                q, cur = dict(q=s[3:].strip(), options=[], answer=0, explain=""), None
                c["quiz"].append(q)
            elif q is not None and s[:2] in ("* ", "- "):
                if s.startswith("* "):
                    q["answer"] = len(q["options"])
                q["options"].append(s[2:].strip())
            elif s.startswith("解析：") and q is not None:
                q["explain"] = s[3:].strip()
            elif s.startswith("帶走："):
                c["takeaway"] = s[3:].strip()
            elif s and cur is not None:
                cur["points"].append(s.lstrip("-• ").strip())
        return c
    raise ValueError(kind)
