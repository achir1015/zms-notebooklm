"""語音動態教學與各畫面說明。

LESSONS：每一課有步驟 [(圖示, 色調, 步驟文字, 對應畫面代號)] 與旁白；播放時依旁白長度依序點亮步驟（聚光框），
         每一步都可以按「跟著做」直接開啟對應畫面。
         旁白由 tools/make_voice.py 用微軟臺灣華語自然語音（曉臻）預先產生 MP3（assets/voice/<key>.mp3）。
PAGES：各畫面「本頁說明」的旁白（assets/voice/page_<畫面代號>.mp3）。
"""

LESSONS = [
    dict(key="intro", title="認識資料助秘NotebookLM MCP簡報", steps=[
        ("LINK", "blue", "連上 NotebookLM，選一本筆記本", "notebooks"),
        ("SLIDESHOW", "violet", "選簡報、心智圖、報告、測驗、資訊圖表或互動式網頁", "studio"),
        ("AUTO_AWESOME", "amber", "依筆記本來源自動產生內容", "studio"),
        ("EDIT_NOTE", "teal", "逐頁預覽、直接修改", "works"),
        ("DOWNLOAD", "green", "匯出 PowerPoint、Word、圖片與網頁", "works"),
    ], voice=(
        "歡迎使用資料助秘NotebookLM MCP簡報。這套系統透過 NotebookLM MCP 伺服器，"
        "直接讀取你在 Google NotebookLM 建立的筆記本，依照筆記本裡的文件來源，"
        "在這個工具裡產生簡報、心智圖、報告、測驗、資訊圖表和互動式網頁，不必再到 NotebookLM 官方網頁裡製作。"
        "使用方式只有三步：第一，在 NotebookLM 連線登入 Google，選一本筆記本；"
        "第二，在產生工具選擇產出類型、專案範本和主題，按開始產生；"
        "第三，在成品庫預覽、修改，再匯出成 PowerPoint、Word、圖片或網頁。"
        "系統內建病房助理技術教育外傭實務訓練當作範例，稍做修改就能變成其他專案的簡報產生工具。")),
    dict(key="notebooks", title="NotebookLM 連線與筆記本", steps=[
        ("LOGIN", "blue", "按登入 Google，在跳出的 Chrome 自己登入", "notebooks"),
        ("TRAVEL_EXPLORE", "violet", "讀取帳號裡的筆記本清單", "notebooks"),
        ("ADD_LINK", "amber", "或貼上筆記本分享網址", "notebooks"),
        ("QUESTION_ANSWER", "teal", "測試提問，看看引用來源", "notebooks"),
        ("POST_ADD", "green", "把文案貼成新的來源", "notebooks"),
    ], voice=(
        "第一次使用要先登入 Google。按登入 Google，會開啟一個 Chrome 視窗，請你自己輸入帳號密碼，"
        "登入完成後視窗會自動關閉，狀態會變成已登入。登入資料只存在這台電腦的 Chrome 設定檔裡，不會進資料庫。"
        "接著按讀取我的筆記本，系統會列出你帳號裡的筆記本，勾選要用的加入清單；也可以直接貼上分享網址。"
        "選一本筆記本後，可以在下面測試提問，看 NotebookLM 依來源回答的內容和引用的文件。"
        "如果有新的文案，可以貼上文字或網址，加到筆記本當成新的來源。")),
    dict(key="studio", title="產生工具：七個步驟做出簡報", steps=[
        ("CALENDAR_MONTH", "blue", "選專案與主題（或年度主題表的月份）", "studio"),
        ("BADGE", "violet", "確認簡報人與指導員", "studio"),
        ("GROUPS", "amber", "學員對象與語言程度", "studio"),
        ("DESCRIPTION", "teal", "依據文件、頁數與文案重點", "studio"),
        ("TUNE", "pink", "張數、語言、視覺風格", "studio"),
        ("AUTO_AWESOME", "green", "選 NotebookLM 或內建範本，開始產生", "studio"),
    ], voice=(
        "產生工具上方先選產出類型：簡報、心智圖、報告、測驗、資訊圖表或互動式網頁。"
        "第一步選專案範本與主題，也可以直接點年度主題表的某個月份，主題和講師會自動帶入。"
        "第二步確認簡報人和指導員，名單外的人可以直接輸入。第三步選學員對象和華語程度。"
        "第四步填依據的文件名稱、頁數和這次的文案重點，同一個主題、不同文案，產生的內容就不同。"
        "第五步設定張數、語言和視覺風格；簡報不少於十張，最後一定有 Q 和 A 五題。"
        "最後選產生方式：依 NotebookLM 筆記本，或用內建範本。NotebookLM 大約要等半分鐘到三分鐘，"
        "產生完成會自動打開成品，讓你預覽和修改。")),
    dict(key="works", title="成品庫：預覽、修改、匯出", steps=[
        ("VIEW_CAROUSEL", "blue", "逐頁預覽投影片", "works"),
        ("EDIT", "amber", "直接改標題、重點、講者備註", "works"),
        ("PALETTE", "violet", "換視覺風格", "works"),
        ("DOWNLOAD", "green", "匯出整組檔案", "works"),
        ("CONTENT_COPY", "teal", "複製 NotebookLM 指令", "works"),
    ], voice=(
        "成品庫列出所有產生過的成品，點一份就能預覽。簡報會一頁一頁顯示，每頁都可以修改標題、重點和講者備註，"
        "也可以新增或刪除投影片、修改 Q 和 A。修改後按儲存，預覽圖會重新畫。"
        "匯出時，簡報會產生 PowerPoint、簡報大綱 Word、Q 和 A 作答卷與解答兩份 Word、網頁和純文字大綱；"
        "心智圖可匯出圖片、可收合的網頁和 XMind 可以開的檔案；報告是 Word 和網頁；"
        "測驗有作答卷、解答和可以直接作答的網頁；資訊圖表是直式海報圖片；"
        "互動式網頁是一個單獨的網頁檔，有可展開的章節、翻牌卡、常見問答和會計分的小測驗，傳給學員用手機就能打開。"
        "如果想在 NotebookLM 官方網頁自己做，也可以複製系統寫好的指令。")),
    dict(key="projects", title="專案範本：換成其他專案", steps=[
        ("FOLDER_COPY", "blue", "複製內定範例成新專案", "projects"),
        ("TITLE", "violet", "改機構、封面標題與字級", "projects"),
        ("PSYCHOLOGY", "amber", "改指令的角色、背景與目的", "projects"),
        ("LIST_ALT", "teal", "建立自己的主題庫", "projects"),
        ("PEOPLE", "green", "人員名單與年度主題表", "people"),
    ], voice=(
        "專案範本決定簡報的封面格式和交給 NotebookLM 的指令。內定範例是病房助理技術教育外傭實務訓練："
        "封面標題四十五點、次標題四十點、小標題三十二點，大綱階段只產生文字內容。"
        "要做其他專案時，按複製成新專案，改機構名稱、封面標題範本、簡報人和指導員的職稱，"
        "以及指令裡的角色、任務背景和目的，再設定預設筆記本。"
        "主題庫是每個主題的教案骨架，沒有網路時可以用內建範本產生；有 NotebookLM 時，內容會跟著筆記本的來源走。"
        "人員名單可以一次貼上多筆，年度主題表可以排好一整年每個月的主題與講師。")),
    dict(key="admin", title="使用者權限與系統管理", steps=[
        ("ADMIN_PANEL_SETTINGS", "rose", "使用者與權限", "users"),
        ("BACKUP", "teal", "備份與還原", "backup"),
        ("SYSTEM_UPDATE", "blue", "版本更新與捷徑", "update"),
        ("HISTORY", "slate", "操作紀錄", "audit"),
    ], voice=(
        "使用者與權限有六項功能：產生工具、NotebookLM 連線、專案範本與主題庫、人員名單、全部成品和系統管理，"
        "每項分成無、查詢、維護三種等級，也可以套用系統管理員、教育訓練主管、講師和訪客的角色範本。"
        "一般使用者只看得到自己的成品。所有資料都在內建的 MariaDB 資料庫，請定期備份；"
        "Google 登入資料只存在這台電腦的 Chrome 設定檔，不會進備份。"
        "程式開啟時會自動檢查新版本，有新版本時上方會出現提示，按下去就能下載並安裝。")),
]

BY_KEY = {lesson["key"]: lesson for lesson in LESSONS}

PAGES = {
    "home": ("首頁", "上方是 NotebookLM 連線狀態和預設筆記本；中間五個按鈕可以直接開始產生簡報、心智圖、報告、測驗或資訊圖表；"
                   "下面是最近的成品。"),
    "studio": ("產生工具", "上方選產出類型，左邊依序完成七個步驟，右邊是需求摘要；最後選 NotebookLM 或內建範本，按開始產生。"),
    "works": ("成品庫", "左邊是所有成品，點一份在右邊預覽與修改，改完按儲存，再按匯出整組檔案。"),
    "notebooks": ("NotebookLM 連線", "先確認上方已登入 Google；左邊是筆記本清單，可以讀取帳號裡的筆記本或貼上網址；"
                              "右邊可以測試提問和加入來源。"),
    "projects": ("專案範本與主題庫", "左邊選專案，右邊上半部是封面格式與指令設定，下半部是主題庫；可以複製成新專案。"),
    "plan": ("年度主題表", "選年度，一到十二月逐月選主題、簡報人和指導員；按套用範例可以依主題的建議月份自動填入。"),
    "people": ("人員名單", "管理簡報人與指導員；可以一次貼上多筆名單，每行寫身分、員編、姓名、職稱。"),
    "users": ("使用者與權限", "左邊是使用者清單，右邊設定姓名、密碼、角色範本和六項功能的權限。"),
    "backup": ("備份與還原", "按立即備份把資料存成壓縮檔，包含所有成品；還原會用備份檔覆蓋目前所有資料，請小心使用。"),
    "update": ("版本更新與捷徑", "按檢查更新查詢新版本，有新版本時按下載並安裝；也可以重建桌面捷徑。"),
    "audit": ("操作紀錄", "列出最近一千筆操作，可以依使用者或對象篩選，並匯出 Excel。"),
    "help": ("語音動態教學", "左邊選課程，按播放語音教學，步驟會隨著講解依序亮起來；每一步都可以按跟著做開啟對應畫面。"),
}


def text_for(sid):
    if sid in PAGES:
        return PAGES[sid]
    return ("本頁說明", "完整的操作教學請到說明的語音動態教學。")


def page_voice_key(sid):
    return "page_" + sid if sid in PAGES else "page_default"
