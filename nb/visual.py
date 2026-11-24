"""NotebookLM 官方「資訊圖表／簡報」視覺指令產生器。

想法參考 Meiko 微課頻道「NotebookLM 資訊圖表 Prompt 生成器 2.0」（需求類型 × 風格 × 佈局）；
以下說明文字為本系統自行撰寫。產生的指令可以貼到 NotebookLM 的 Studio（資訊圖表、簡報）自訂提示，
讓 NotebookLM 依來源畫出有 AI 插圖的版本；本系統自己的 PowerPoint 則用「柔和插畫」版型。
"""

NEEDS = [
    ("edu", "教育知識科普", "把專業知識轉成一般人看得懂的教材"),
    ("flow", "流程邏輯說明", "說明操作步驟與先後順序"),
    ("market", "行銷懶人包", "吸睛、重點一眼看懂"),
    ("data", "數據分析報告", "以數字與圖表呈現結果"),
    ("research", "專業研究報告", "嚴謹、條理分明"),
    ("history", "歷史演進時間", "依時間呈現發展過程"),
    ("idea", "創意發想筆記", "發散聯想、點子整理"),
    ("social", "社群媒體分享", "適合手機瀏覽與分享"),
]

STYLES = [
    ("pastel", "可愛粉嫩風格", "柔和粉嫩配色，搭配可愛的卡通小圖案"),
    ("clay3d", "3D 黏土風格", "圓潤可愛的 3D 黏土角色，柔和棚拍光線，薄荷綠與奶油橘等粉嫩色，溫馨親切"),
    ("japan", "日系清新風格", "平面向量插畫，溫柔粉彩色調、柔和線條、極簡背景，清新又讓人安心"),
    ("chalk", "黑板粉筆風格", "教室深綠黑板，帶粉筆灰質感的手寫字與插圖"),
    ("doodle", "手繪塗鴉風格", "鉛筆素描線條與筆記本紙張紋理，像隨手塗鴉的筆記"),
    ("memphis", "企業曼非斯風格", "無輪廓線的柔和色塊插圖，科技新創的極簡感"),
    ("whiteboard", "白板馬克筆風格", "亮白板背景，粗獷多彩的馬克筆字跡，像腦力激盪"),
    ("dashboard", "數據儀表板風", "現代儀表板介面，乾淨的圖表與曲線元件"),
    ("retro", "復古報紙風格", "1950 年代復古海報，微黃舊紙與摺痕質感"),
    ("blindbox", "盲盒公仔風", "Q 版 3D 公仔角色，光滑霧面材質"),
    ("handwrite", "手寫筆跡", "寬螢幕手繪圖表，文字是流暢的手寫筆觸"),
    ("manga", "漫畫可愛風格", "漫畫風衛教圖，統一用一個可愛吉祥物角色貫穿全圖"),
    ("isometric", "等距視角微縮風格", "等角視角的微縮立體場景，像小模型世界"),
    ("notes", "手繪筆記風格", "手繪筆記排版，重點用框線與箭頭串起來"),
    ("cute", "可愛風格", "圓潤可愛的造型與明亮配色"),
    ("pro", "專業風格", "穩重配色與清楚的資訊層級，正式場合使用"),
    ("science", "科學風格", "科學圖解質感，精準的示意圖與標註"),
    ("anime", "動漫風格", "日系動漫人物與鮮明色彩"),
    ("clay", "黏土風格", "手捏黏土質感的造型與場景"),
    ("editorial", "社論風格", "雜誌社論版面，大標題與留白"),
    ("teaching", "教學風格", "課堂講義感，條列清楚、重點標示"),
    ("bento", "便當盒排版法", "大小不一的方格拼成一頁，像便當盒分格"),
    ("blocks", "積木風格", "以積木堆疊呈現概念之間的組合關係"),
]

LAYOUTS = [
    ("auto", "不指定佈局", "由 NotebookLM 自行安排"),
    ("center", "中心對焦", "核心概念放中央，分支向外展開"),
    ("snake", "蛇形流程", "步驟沿 S 形路線前進，適合操作步驟（推薦）"),
    ("compare", "左右對比", "左右兩欄對照，適合正確／錯誤、優缺點"),
    ("grid", "網格矩陣", "整齊的方格模組，並列多個重點"),
    ("pyramid", "層級金字塔", "由廣到深的層級架構"),
    ("timeline", "垂直時間軸", "由上而下呈現時間順序或發展"),
    ("radial", "環形輻射", "以圓環呈現循環或彼此關聯"),
    ("stairs", "階梯進展", "一階一階往上，呈現階段性的進步"),
]

NEED_BY = {x[0]: x for x in NEEDS}
STYLE_BY = {x[0]: x for x in STYLES}
LAYOUT_BY = {x[0]: x for x in LAYOUTS}

KIND_WORD = {"INFOGRAPHIC": "資訊圖表", "SLIDES": "簡報", "MINDMAP": "心智圖", "REPORT": "報告", "QUIZ": "測驗",
             "WEBPAGE": "資訊圖表"}


def build(kind, brief, need="edu", style="pastel", layout="snake", extra=""):
    """組出貼到 NotebookLM Studio 自訂提示的視覺指令（繁體中文）。"""
    what = KIND_WORD.get(kind, "資訊圖表")
    n, s, lay = NEED_BY.get(need, NEEDS[0]), STYLE_BY.get(style, STYLES[0]), LAYOUT_BY.get(layout, LAYOUTS[0])
    L = ["%s設計：「%s」。" % (what, brief.topic_name)]
    if brief.org_text:
        L.append("機構名稱一律使用「%s」。" % brief.org_text)
    L.append("需求類型：%s（%s）。" % (n[1], n[2]))
    if lay[0] != "auto":
        L.append("佈局採「%s」：%s。" % (lay[1], lay[2]))
    L.append("風格要求「%s」：%s。" % (s[1], s[2]))
    L.append("對象：%s；語言程度：%s。" % (brief.audience, {"basic": "基礎，用短句與常用字", "mid": "日常會話",
                                                        "pro": "專業人員"}.get(brief.level, brief.level)))
    L.append("內容以筆記本中的來源為唯一依據%s；全部使用台灣繁體中文。" %
             ("（%s）" % brief.source_title if brief.source_title else ""))
    if kind == "SLIDES":
        L.append("簡報約 %d 張；第一張封面：%s／%s／%s。最後一張是 Q&A %d 題。" % (
            brief.slide_count, brief.cover_title, brief.subtitle, brief.byline, brief.qa_count))
    else:
        L.append("寬螢幕版面，專業又親切，每個重點搭配小圖示。")
    if brief.notes:
        L.append("本次重點：" + brief.notes)
    if extra:
        L.append(extra)
    return "".join(L)
