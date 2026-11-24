"""成品庫：左邊清單；右邊預覽、修改、來源與指令、匯出整組檔案。"""
import os

import flet as ft

from .. import artifacts as A
from .. import render as R
from . import theme as T

I = ft.Icons


class Works(ft.Row):
    def __init__(self, ctx, job=None, kind="", **kw):
        self.ctx = ctx
        self.b = ctx.books
        self.kind_filter = kind or ""
        self.cur = None
        self.q = T.field("搜尋名稱或主題", "", expand=True, prefix_icon=I.SEARCH, on_submit=lambda e: self.reload())
        self.kind_dd = T.dropdown("類型", [(k, A.KINDS[k][0]) for k in A.KIND_ORDER], self.kind_filter, width=130,
                                  blank="全部", filterable=False, on_select=lambda e: self.reload())
        self.list = ft.ListView(spacing=6, expand=True)
        left = T.card(ft.Column([ft.Row([self.q, self.kind_dd], spacing=8), self.list], spacing=10, expand=True),
                      width=360, padding=14)
        self.detail = ft.Container(expand=True)
        super().__init__([left, self.detail], spacing=16, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        self.reload(False)
        if job:
            self.open(int(job), False)
        elif self.rows:
            self.open(self.rows[0]["id"], False)
        else:
            self.detail.content = T.empty_state(I.INVENTORY_2, "還沒有成品", "到「產生工具」做第一份簡報吧！")

    # ================================================================ 清單
    def reload(self, refresh=True):
        self.rows = self.b.jobs(kind=self.kind_dd.value or "", q=(self.q.value or "").strip())
        items = []
        for r in self.rows:
            name, icon, tone = A.KINDS.get(r["kind"], ("?", "HELP", "slate"))
            sel = self.cur and self.cur["id"] == r["id"]
            items.append(ft.Container(ft.Row([
                T.icon_tile(getattr(I, icon), tone, 38),
                ft.Column([ft.Text(r["title"], size=14, weight=ft.FontWeight.W_700, max_lines=2,
                                   overflow=ft.TextOverflow.ELLIPSIS),
                           ft.Row([T.chip(name, tone, size=11),
                                   T.chip("NotebookLM" if r["engine"] == "NOTEBOOKLM" else "範本",
                                          "blue" if r["engine"] == "NOTEBOOKLM" else "slate", size=11)], spacing=4),
                           T.muted("%s　%s" % (T.show(r["updated_at"])[:16], r["summary"]), 11)], spacing=3,
                          expand=True)], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START),
                padding=10, border_radius=12, bgcolor="#EEF3FB" if sel else None, ink=True,
                border=ft.Border.all(1, T.PRIMARY if sel else T.LINE), on_click=lambda e, i=r["id"]: self.open(i)))
        self.list.controls = items or [T.muted("沒有符合的成品")]
        if refresh:
            T.safe_update(self.list)

    # ================================================================ 明細
    def open(self, jid, refresh=True):
        try:
            self.cur = self.b.job(jid)
        except Exception as e:
            self.ctx.toast(str(e), True)
            return
        self.content = self.cur["content"]
        self.dirty = False
        j = self.cur
        name, icon, tone = A.KINDS[j["kind"]]
        self.title = T.field("名稱", j["title"], expand=True, on_change=lambda e: self.mark())
        self.style_dd = T.dropdown("視覺風格", [(s["id"], s["name"]) for s in A.STYLES], j["style"], width=170,
                                   filterable=False, on_select=lambda e: self.mark(redraw=True))
        self.save_btn = T.btn("儲存", I.SAVE, lambda e: self.save(), disabled=True)
        head = ft.Row([T.icon_tile(getattr(I, icon), tone, 46, radius=14), self.title, self.style_dd, self.save_btn,
                       ft.PopupMenuButton(icon=I.MORE_VERT, items=[
                           ft.PopupMenuItem("複製 NotebookLM 指令", icon=I.CONTENT_COPY, on_click=lambda e: self.copy_prompt()),
                           ft.PopupMenuItem("刪除這份成品", icon=I.DELETE_OUTLINE, on_click=lambda e: self.delete())])],
                      spacing=10)
        meta = ft.Row([T.chip(name, tone), T.chip("依 NotebookLM 筆記本" if j["engine"] == "NOTEBOOKLM" else "內建範本",
                                                   "blue" if j["engine"] == "NOTEBOOKLM" else "slate"),
                       T.muted("主題：%s　建立：%s %s　%s" % (j["topic_name"], j["owner"], T.show(j["created_at"])[:16],
                                                       ("耗時 %d 秒" % j["seconds"]) if j["seconds"] else ""), 12)],
                      spacing=8, wrap=True)
        self.preview = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        self.editor = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        self.export_box = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        src = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        if j["engine"] == "NOTEBOOKLM":
            src.controls = [
                ft.Text("引用的來源", size=15, weight=ft.FontWeight.W_700),
                *([ft.Text("[%s] %s　%s" % (s.get("index", ""), s.get("title", ""), (s.get("excerpt") or "")[:160]),
                           size=13, selectable=True) for s in j["sources"]] or [T.muted("（NotebookLM 沒有回傳引用）")]),
                ft.Text("送出的指令", size=15, weight=ft.FontWeight.W_700),
                ft.Container(ft.Text(j["prompt"] or "", size=12, selectable=True), bgcolor="#F7F9FC", padding=12,
                             border_radius=10),
                ft.Text("NotebookLM 原始回答", size=15, weight=ft.FontWeight.W_700),
                ft.Container(ft.Text(j["answer"] or "", size=12, selectable=True), bgcolor="#F7F9FC", padding=12,
                             border_radius=10)]
        else:
            src.controls = [T.muted("這份成品是用內建範本產生的；如果要依文案產生，請到產生工具選 NotebookLM。"),
                            ft.Text("可以貼到 NotebookLM 官方網頁的指令：", size=14, weight=ft.FontWeight.W_700),
                            ft.Container(ft.Text(self.prompt_text(), size=12, selectable=True), bgcolor="#F7F9FC",
                                         padding=12, border_radius=10)]
        tabs = ft.Tabs(selected_index=0, length=4, expand=True, content=ft.Column([
            ft.TabBar(tabs=[ft.Tab(label="預覽", icon=I.VISIBILITY), ft.Tab(label="修改", icon=I.EDIT),
                            ft.Tab(label="匯出", icon=I.DOWNLOAD), ft.Tab(label="來源與指令", icon=I.SOURCE)]),
            ft.TabBarView(controls=[self.preview, self.editor, self.export_box, src], expand=True)], expand=True))
        self.detail.content = T.card(ft.Column([head, meta, tabs], spacing=10, expand=True), padding=16, expand=True)
        self.build_editor()
        self.build_export()
        self.draw_preview()
        self.reload(False)
        if refresh:
            self.ctx.page.update()

    def mark(self, redraw=False):
        self.dirty = True
        self.save_btn.disabled = False
        T.safe_update(self.save_btn)
        if redraw:
            self.draw_preview()

    # ================================================================ 預覽
    def draw_preview(self):
        kind, c, style = self.cur["kind"], self.content, self.style_dd.value or "pastel"
        self.preview.controls = [ft.Row([ft.ProgressRing(width=20, height=20), T.muted("正在畫預覽…")])]
        T.safe_update(self.preview)

        def work():
            ctrls = []
            try:
                if kind == "SLIDES":
                    pngs = R.preview_pngs(kind, c, style, 0.5)
                    slides = c.get("slides", [])
                    for i, png in enumerate(pngs):
                        s = slides[i]
                        ctrls.append(ft.Row([
                            ft.Image(src=png, width=560, border_radius=10),
                            ft.Column([ft.Text("第 %d 頁｜%s" % (i + 1, s.get("label", "")), size=13,
                                               weight=ft.FontWeight.W_700),
                                       ft.Text("講者備註：" + (s.get("notes") or "（無）"), size=12, color=T.MUTED,
                                               selectable=True),
                                       T.btn("朗讀備註", I.VOLUME_UP, lambda e, t=s.get("notes", ""): self.ctx.say_text(t),
                                             kind="ghost") if s.get("notes") and not self.ctx.web else ft.Container()],
                                      spacing=6, expand=True)], spacing=14, vertical_alignment=ft.CrossAxisAlignment.START))
                    if c.get("qa"):
                        ctrls.append(ft.Markdown("### Q&A\n" + "\n".join(
                            "%d. **%s**  \n　答：%s" % (i, x["q"], x["a"]) for i, x in enumerate(c["qa"], 1))))
                elif kind in ("MINDMAP", "INFOGRAPHIC"):
                    png = R.preview_pngs(kind, c, style)[0]
                    ctrls.append(ft.Image(src=png, border_radius=10, fit=ft.BoxFit.CONTAIN,
                                          width=860 if kind == "MINDMAP" else 560))
                elif kind == "REPORT":
                    ctrls.append(ft.Markdown(R.report_markdown(c), selectable=True))
                elif kind == "WEBPAGE":
                    ctrls.append(ft.Row([T.btn("在瀏覽器開啟互動網頁", I.OPEN_IN_BROWSER, lambda e: self.open_web(),
                                               bgcolor=T.ACCENT)]))
                    md = ["# " + c.get("title", ""), "*%s*" % c.get("subtitle", ""), c.get("intro", "")]
                    for i, s in enumerate(c.get("sections", []), 1):
                        md += ["### %d. %s" % (i, s["heading"]), "> " + s.get("summary", "")]
                        md += ["- " + p for p in s.get("points", [])]
                    if c.get("cards"):
                        md.append("### 翻牌卡\n" + "　".join("**%s**：%s" % (x["front"], x["back"]) for x in c["cards"]))
                    if c.get("quiz"):
                        md.append("### 小測驗 %d 題" % len(c["quiz"]))
                    ctrls.append(ft.Markdown("\n\n".join(md), selectable=True))
                elif kind == "QUIZ":
                    md = ["## " + c.get("title", "")]
                    for i, q in enumerate(c.get("questions", []), 1):
                        md.append("**%d. %s**" % (i, q["q"]))
                        if q["type"] == "single":
                            md += ["- (%s) %s" % ("ABCD"[j], o) for j, o in enumerate(q["options"][:4])]
                        md.append("> 答案：%s　%s\n" % (q["answer"], q.get("explain", "")))
                    ctrls.append(ft.Markdown("\n\n".join(md), selectable=True))
            except Exception as e:
                ctrls = [T.muted("預覽失敗：%s" % e)]
            self.preview.controls = ctrls
            T.safe_update(self.preview)
        self.ctx.page.run_thread(work)

    # ================================================================ 修改
    def build_editor(self):
        kind = self.cur["kind"]
        if kind != "SLIDES":
            self.text = T.field("內容（照格式修改：# 標題、## 小節、- 條列）", A.to_text(kind, self.content), multiline=True,
                                min_lines=24, on_change=lambda e: self.mark())
            hint = {"MINDMAP": "第一行 # 是中心主題；每個分支一行「- 文字」，往下一層多空兩格。",
                    "REPORT": "# 標題、摘要：、## 小節標題、一般文字是段落、- 開頭是條列、結論：、參考來源：（用；分隔）。",
                    "QUIZ": "每題第一行「1.（單選）題目」，接著 A.～D. 選項、答案：B、解析：…；是非題寫（是非），答案 ○ 或 ✕。",
                    "INFOGRAPHIC": "# 標題、副標：、數字：值｜說明（最多 4 個）、## 區塊與 - 重點、提醒：、頁尾：",
                    "WEBPAGE": "# 標題、副標：、介紹：；每章「## 章名」、摘要：、- 重點、補充：；卡片：正面｜背面；"
                               "問：／答：；題目：接選項（正確答案前面用 *，其他用 -）、解析：；帶走：一句話。"}[kind]
            self.editor.controls = [T.muted(hint, 12), self.text,
                                    ft.Row([T.btn("套用並重畫預覽", I.REFRESH, lambda e: self.apply_text(), kind="outline")])]
            return
        self.slide_list = ft.Column(spacing=10)
        self.qa_list = ft.Column(spacing=8)
        self.render_slide_editors()
        self.editor.controls = [
            ft.Row([ft.Text("投影片", size=16, weight=ft.FontWeight.W_700, expand=True),
                    T.btn("新增一頁", I.ADD, lambda e: self.add_slide(), kind="outline")]),
            T.muted("每個重點一行；封面依專案範本的固定格式。改完按右上「儲存」。", 12),
            self.slide_list,
            ft.Row([ft.Text("Q&A", size=16, weight=ft.FontWeight.W_700, expand=True),
                    T.btn("新增一題", I.ADD, lambda e: self.add_qa(), kind="outline")]),
            self.qa_list]

    def render_slide_editors(self, refresh=False):
        slides = self.content.setdefault("slides", [])
        eds = []
        for i, s in enumerate(slides):
            def upd(e, i=i, k=None):
                v = e.control.value
                slides[i][k] = [x.strip() for x in v.splitlines() if x.strip()] if k == "points" else v
                self.mark()
            cover = i == 0 and s.get("kind") == "cover"
            eds.append(T.card(ft.Column([
                ft.Row([ft.Text("第 %d 頁" % (i + 1), size=14, weight=ft.FontWeight.W_700),
                        T.field("頁型", s.get("label", ""), width=200, on_change=lambda e, i=i: upd(e, i, "label")),
                        ft.Container(expand=True),
                        ft.IconButton(I.ARROW_UPWARD, tooltip="往上移", disabled=i <= 1 or cover,
                                      on_click=lambda e, i=i: self.move_slide(i, -1)),
                        ft.IconButton(I.ARROW_DOWNWARD, tooltip="往下移", disabled=cover or i >= len(slides) - 1,
                                      on_click=lambda e, i=i: self.move_slide(i, 1)),
                        ft.IconButton(I.DELETE_OUTLINE, tooltip="刪除這頁", icon_color=T.DANGER, disabled=cover,
                                      on_click=lambda e, i=i: self.del_slide(i))], spacing=8),
                T.field("標題", s.get("title", ""), on_change=lambda e, i=i: upd(e, i, "title")),
                T.field("重點（一行一點）" if not cover else "次標題／小標題（一行一個）", "\n".join(s.get("points", [])),
                        multiline=True, min_lines=3, on_change=lambda e, i=i: upd(e, i, "points")),
                T.field("講者備註", s.get("notes", ""), multiline=True, min_lines=2,
                        on_change=lambda e, i=i: upd(e, i, "notes"))], spacing=8), padding=12))
        self.slide_list.controls = eds
        qa = self.content.setdefault("qa", [])
        qeds = []
        for i, x in enumerate(qa):
            def uq(e, i=i, k=None):
                qa[i][k] = e.control.value
                self.mark()
            qeds.append(ft.Row([ft.Text("%d." % (i + 1), width=24),
                                T.field("題目", x.get("q", ""), expand=True, on_change=lambda e, i=i: uq(e, i, "q")),
                                T.field("參考答案", x.get("a", ""), expand=True, on_change=lambda e, i=i: uq(e, i, "a")),
                                ft.IconButton(I.DELETE_OUTLINE, icon_color=T.DANGER,
                                              on_click=lambda e, i=i: self.del_qa(i))], spacing=8))
        self.qa_list.controls = qeds
        if refresh:
            T.safe_update(self.editor)

    def add_slide(self):
        s = self.content["slides"]
        s.insert(max(len(s) - 1, 1), dict(label="補充重點", title="新的投影片", points=["重點"], notes=""))
        self.render_slide_editors(True)
        self.mark(redraw=True)

    def move_slide(self, i, d):
        s = self.content["slides"]
        j = i + d
        if 1 <= j < len(s):
            s[i], s[j] = s[j], s[i]
            self.render_slide_editors(True)
            self.mark(redraw=True)

    def del_slide(self, i):
        del self.content["slides"][i]
        self.render_slide_editors(True)
        self.mark(redraw=True)

    def add_qa(self):
        self.content.setdefault("qa", []).append(dict(q="新的題目", a=""))
        self.render_slide_editors(True)
        self.mark()

    def del_qa(self, i):
        del self.content["qa"][i]
        self.render_slide_editors(True)
        self.mark()

    def apply_text(self):
        try:
            self.content = A.from_text(self.cur["kind"], self.text.value, self.content)
        except Exception as e:
            self.ctx.toast("格式有誤：%s" % e, True)
            return False
        self.mark(redraw=True)
        return True

    def save(self):
        if self.cur["kind"] != "SLIDES" and not self.apply_text():
            return
        if self.ctx.guard(self.b.save_job_content, self.cur["id"], self.content, self.title.value.strip(),
                          self.style_dd.value, ok="已儲存"):
            self.dirty = False
            self.save_btn.disabled = True
            self.draw_preview()
            self.reload()
            T.safe_update(self.save_btn)

    def delete(self):
        def go():
            if self.ctx.guard(self.b.delete_job, self.cur["id"], ok="已刪除"):
                self.ctx.app.go("works")
        self.ctx.confirm("刪除成品", "確定要刪除「%s」嗎？刪除後無法復原。" % self.cur["title"], go, "刪除")

    def prompt_text(self):
        j = self.cur
        br = self.b.make_brief(j["project_id"], j["topic_id"], **{k: v for k, v in j["brief"].items()
                                                                   if k not in ("topic", "project")})
        return A.build_prompt(j["kind"], br)

    def copy_prompt(self):
        self.ctx.copy_text(self.cur["prompt"] or self.prompt_text(), "已複製指令，可以貼到 NotebookLM 官方網頁使用")

    # ================================================================ 匯出
    def build_export(self):
        kind = self.cur["kind"]
        files = {"SLIDES": ["PowerPoint 簡報（含講者備註）", "簡報大綱 Word", "Q&A 作答卷 Word（題目＋空白作答）",
                            "Q&A 解答 Word", "網頁版（可分享）", "純文字大綱（貼到 LINE、郵件）"],
                 "MINDMAP": ["心智圖圖片 PNG", "可收合的網頁", "Markdown 大綱", "FreeMind .mm（XMind 可匯入）"],
                 "REPORT": ["Word 報告", "Markdown", "網頁版"],
                 "QUIZ": ["作答卷 Word", "解答 Word", "線上作答網頁（自動計分）"],
                 "INFOGRAPHIC": ["直式海報 PNG", "網頁版"],
                 "WEBPAGE": ["互動式網頁 HTML（章節展開、翻牌卡、問答、計分小測驗；單一檔案可直接分享）",
                             "內容 JSON（給其他程式使用）"]}[kind]
        c = self.ctx
        btns = []
        if not c.web:
            btns.append(T.btn("匯出到資料夾並開啟", I.FOLDER_OPEN, lambda e: self.export_folder(), bgcolor=T.ACCENT))
            if kind == "SLIDES":
                btns.append(T.btn("直接開啟 PowerPoint", I.SLIDESHOW, lambda e: self.open_main(), kind="outline"))
        btns.append(T.btn("下載 ZIP 壓縮檔", I.ARCHIVE, lambda e: c.page.run_task(self.export_zip), kind="outline"))
        if kind == "SLIDES":
            btns.append(T.btn("複製純文字大綱", I.CONTENT_COPY,
                              lambda e: c.copy_text(A.outline_text(self.content)), kind="ghost"))
        self.export_box.controls = [
            ft.Text("會產生這些檔案：", size=15, weight=ft.FontWeight.W_700),
            *[ft.Row([ft.Icon(I.INSERT_DRIVE_FILE_OUTLINED, size=18, color=T.PRIMARY), ft.Text(f, size=14)]) for f in files],
            ft.Row(btns, spacing=10, wrap=True),
            T.muted("匯出的是目前畫面上的內容（有修改請先儲存）。範本內容為通用版，正式使用前請由指導員確認。", 12)]

    def bundle(self):
        return R.export_bundle(self.cur["kind"], self.content, self.title.value.strip() or self.cur["title"],
                               self.style_dd.value or "pastel")

    def export_dir(self):
        d = self.b.company().get("export_dir") or os.path.join(os.path.expanduser("~"), "Documents", "NotebookLM MCP簡報")
        import re
        sub = re.sub(r'[\\/:*?"<>|]+', "_", self.title.value.strip() or self.cur["title"])[:60]
        path = os.path.join(d, sub)
        os.makedirs(path, exist_ok=True)
        return path

    def export_folder(self):
        self.ctx.toast("正在產生檔案…")

        def work():
            try:
                d = self.export_dir()
                for name, data in self.bundle():
                    with open(os.path.join(d, name), "wb") as f:
                        f.write(data)
                self.b.log("export", self.cur["id"], d)
                T.open_file(d)
                self.ctx.toast("已匯出到 %s" % d)
            except Exception as e:
                self.ctx.toast("匯出失敗：%s" % e, True)
        self.ctx.page.run_thread(work)

    def open_main(self):
        def work():
            try:
                d = self.export_dir()
                files = self.bundle()
                for name, data in files:
                    with open(os.path.join(d, name), "wb") as f:
                        f.write(data)
                T.open_file(os.path.join(d, files[0][0]))
            except Exception as e:
                self.ctx.toast("開啟失敗：%s（PowerPoint 是否正開著同名檔案？）" % e, True)
        self.ctx.page.run_thread(work)

    def open_web(self):
        if self.ctx.web:
            self.ctx.page.run_task(self.export_zip)
            return
        import tempfile
        import webbrowser
        p = os.path.join(tempfile.gettempdir(), "nb_web_%d.html" % self.cur["id"])
        with open(p, "w", encoding="utf-8") as f:
            f.write(R.webpage_html(self.content, self.style_dd.value or "pastel"))
        webbrowser.open("file:///" + p.replace("\\", "/"))

    async def export_zip(self):
        import re
        data = R.bundle_zip(self.bundle())
        name = re.sub(r'[\\/:*?"<>|\s]+', "_", self.title.value.strip() or "成品")[:60] + ".zip"
        path = await self.ctx.save_download(name, data)
        if path:
            self.b.log("export_zip", self.cur["id"], name)
            self.ctx.toast("已儲存：%s" % os.path.basename(str(path)))

