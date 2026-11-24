"""NotebookLM 連線：登入狀態、筆記本清單（讀帳號／貼網址）、測試提問、加入來源。"""

import flet as ft

from . import theme as T

I = ft.Icons


class Notebooks(ft.Column):
    def __init__(self, ctx, **kw):
        self.ctx = ctx
        self.b = ctx.books
        self.can_edit = self.b.can("NOTE", 2)
        self.sel = None
        self.state_icon = ft.Icon(I.SYNC, color=T.MUTED)
        self.state_text = ft.Text("正在檢查連線…", size=15, weight=ft.FontWeight.W_700)
        self.state_sub = T.muted("第一次啟動 NotebookLM MCP 伺服器約需 5～10 秒", 12)
        self.login_btn = T.btn("登入 Google", I.LOGIN, lambda e: self.login(False), visible=False)
        self.switch_btn = T.btn("換帳號", I.SWITCH_ACCOUNT, lambda e: self.login(True), kind="ghost", visible=False)
        status = T.card(ft.Row([T.icon_tile(I.LINK, "blue", 48, radius=14), ft.Column([
            ft.Row([self.state_icon, self.state_text], spacing=6), self.state_sub], spacing=2, expand=True),
            self.login_btn, self.switch_btn,
            T.btn("重新檢查", I.REFRESH, lambda e: self.check(), kind="outline")], spacing=14), padding=16)

        self.list = ft.ListView(spacing=6, expand=True)
        left = T.card(ft.Column([
            ft.Row([ft.Text("我的筆記本", size=16, weight=ft.FontWeight.W_700, expand=True),
                    T.btn("讀取帳號筆記本", I.TRAVEL_EXPLORE, lambda e: self.discover(), kind="outline",
                          visible=self.can_edit),
                    ft.IconButton(I.ADD_LINK, tooltip="貼上分享網址新增", on_click=lambda e: self.edit(None),
                                  visible=self.can_edit)]),
            self.list], spacing=10, expand=True), width=420, padding=14)
        self.pane = ft.Container(expand=True)
        super().__init__([status, ft.Row([left, self.pane], spacing=16, expand=True,
                                         vertical_alignment=ft.CrossAxisAlignment.STRETCH)], spacing=14, expand=True)
        self.reload(False)
        rows = self.rows
        if rows:
            self.pick(rows[0]["id"], False)
        self.check()

    # ================================================================ 連線狀態
    def check(self):
        self.state_icon.icon, self.state_icon.color = I.SYNC, T.MUTED
        self.state_text.value = "正在檢查連線…"
        T.safe_update(self)

        def work():
            try:
                s = self.b.nlm_status()
                if s["authenticated"]:
                    self.state_icon.icon, self.state_icon.color = I.CHECK_CIRCLE, T.SUCCESS
                    self.state_text.value = "已登入 Google，可以使用 NotebookLM"
                    self.state_sub.value = "NotebookLM MCP 伺服器 v%s 執行中；登入資料只存在這台電腦的 Chrome 設定檔" % (
                        s["version"] or "2")
                    self.login_btn.visible, self.switch_btn.visible = False, self.can_edit
                else:
                    self.state_icon.icon, self.state_icon.color = I.ERROR_OUTLINE, T.WARN
                    self.state_text.value = "尚未登入 Google"
                    self.state_sub.value = "按「登入 Google」會開一個 Chrome 視窗，請自己輸入帳號密碼；進到 NotebookLM 畫面後會自動完成"
                    self.login_btn.visible, self.switch_btn.visible = self.can_edit, False
            except Exception as e:
                self.state_icon.icon, self.state_icon.color = I.ERROR, T.DANGER
                self.state_text.value = "NotebookLM 伺服器無法啟動"
                self.state_sub.value = str(e)[:200]
            T.safe_update(self)
        self.ctx.page.run_thread(work)

    def login(self, switch):
        self.login_btn.disabled = True
        self.state_icon.icon, self.state_icon.color = I.OPEN_IN_BROWSER, T.PRIMARY
        self.state_text.value = "請在跳出的 Chrome 視窗登入 Google（最多 10 分鐘）"
        self.state_sub.value = "登入後進到 NotebookLM 首頁，視窗會自動關閉；這裡會自動更新狀態"
        T.safe_update(self)

        def work():
            try:
                self.b.nlm_login(switch)
                self.ctx.toast("登入完成！")
            except Exception as e:
                self.ctx.toast("登入沒有完成：%s" % e, True)
            self.login_btn.disabled = False
            self.check()
        self.ctx.page.run_thread(work)

    # ================================================================ 筆記本清單
    def reload(self, refresh=True):
        self.rows = self.b.notebooks()
        items = []
        for r in self.rows:
            sel = self.sel and self.sel["id"] == r["id"]
            items.append(ft.Container(ft.Row([
                T.icon_tile(I.MENU_BOOK, "teal" if r["is_default"] else "blue", 36),
                ft.Column([ft.Row([ft.Text(r["title"], size=14, weight=ft.FontWeight.W_700, max_lines=1,
                                           overflow=ft.TextOverflow.ELLIPSIS, expand=True)] +
                                  ([T.chip("預設", "teal", size=11)] if r["is_default"] else [])),
                           T.muted((r["description"] or r["url"])[:60], 11),
                           T.muted("使用 %d 次%s" % (r["use_count"], "　最近 " + T.show(r["last_used"])[:10]
                                                    if r["last_used"] else ""), 11)], spacing=2, expand=True)],
                spacing=10), padding=10, border_radius=12, ink=True, bgcolor="#EEF3FB" if sel else None,
                border=ft.Border.all(1, T.PRIMARY if sel else T.LINE), on_click=lambda e, i=r["id"]: self.pick(i)))
        self.list.controls = items or [T.muted("還沒有筆記本。按「讀取帳號筆記本」或右上角貼上分享網址。")]
        if refresh:
            T.safe_update(self.list)

    def pick(self, nid, refresh=True):
        self.sel = self.b.notebook(nid)
        r = self.sel
        self.question = T.field("問 NotebookLM 一個問題（依這本筆記本的來源回答）", "", multiline=True, min_lines=2,
                                hint_text="例：請用五點整理會陰沖洗的注意事項")
        self.answer = ft.Column(spacing=8)
        self.ask_btn = T.btn("提問", I.SEND, lambda e: self.ask())
        self.src_kind = ft.RadioGroup(value="text", content=ft.Row([ft.Radio(value="text", label="貼上文字"),
                                                                     ft.Radio(value="url", label="網址")]))
        self.src_title = T.field("來源名稱（可空白）", "", width=260)
        self.src_body = T.field("文字內容或網址", "", multiline=True, min_lines=3, expand=True)
        actions = [T.btn("在瀏覽器開啟", I.OPEN_IN_NEW, lambda e: self.ctx.open_url(r["url"]), kind="outline")]
        if self.can_edit:
            actions += [T.btn("修改", I.EDIT, lambda e: self.edit(r), kind="outline"),
                        T.btn("刪除", I.DELETE_OUTLINE, lambda e: self.delete(), kind="danger")]
        self.pane.content = T.card(ft.Column([
            ft.Row([T.icon_tile(I.MENU_BOOK, "teal", 46, radius=14), ft.Column([
                ft.Text(r["title"], size=18, weight=ft.FontWeight.W_800), T.muted(r["url"], 12, selectable=True)],
                spacing=0, expand=True)] + actions, spacing=10),
            T.muted(r["description"] or "", 13),
            ft.Divider(height=1, color=T.LINE),
            ft.Text("測試提問", size=16, weight=ft.FontWeight.W_700),
            ft.Row([ft.Container(self.question, expand=True), self.ask_btn],
                   vertical_alignment=ft.CrossAxisAlignment.START),
            self.answer,
            ft.Divider(height=1, color=T.LINE),
            ft.Text("加入來源到這本筆記本", size=16, weight=ft.FontWeight.W_700),
            T.muted("把新的文案或網頁加進筆記本，NotebookLM 之後產生內容就會參考它（不支援上傳檔案，PDF 請到 NotebookLM 網頁上傳）。", 12),
            ft.Row([self.src_kind, self.src_title], wrap=True), ft.Row([self.src_body]),
            ft.Row([T.btn("加入來源", I.POST_ADD, lambda e: self.add_source(), disabled=not self.can_edit)]),
        ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True), padding=18, expand=True)
        self.reload(False)
        if refresh:
            self.ctx.page.update()

    def ask(self):
        q = (self.question.value or "").strip()
        if not q:
            self.ctx.toast("請輸入問題", True)
            return
        self.ask_btn.disabled = True
        self.answer.controls = [ft.Row([ft.ProgressRing(width=20, height=20), T.muted("NotebookLM 回答中（約 10～60 秒）…")])]
        T.safe_update(self.pane)

        def work():
            try:
                r = self.b.nlm_ask(self.sel["id"], q)
                src = r.get("sources") or []
                self.answer.controls = [
                    ft.Container(ft.Markdown(r.get("answer", ""), selectable=True), bgcolor="#F7F9FC", padding=14,
                                 border_radius=12),
                    *[T.muted("[%s] %s：%s" % (s.get("index"), s.get("title", ""), (s.get("excerpt") or "")[:140]), 12)
                      for s in src]]
            except Exception as e:
                self.answer.controls = [ft.Text("提問失敗：%s" % e, color=T.DANGER)]
            self.ask_btn.disabled = False
            T.safe_update(self.pane)
        self.ctx.page.run_thread(work)

    def add_source(self):
        body = (self.src_body.value or "").strip()
        if not body:
            self.ctx.toast("請貼上文字或網址", True)
            return
        self.ctx.toast("正在加入來源（約 20～90 秒）…")

        def work():
            if self.ctx.guard(self.b.nlm_add_source, self.sel["id"], self.src_kind.value, body,
                              self.src_title.value.strip(), ok="已加入來源"):
                self.src_body.value = ""
                T.safe_update(self.src_body)
        self.ctx.page.run_thread(work)

    # ================================================================ 新增、修改、讀取帳號
    def edit(self, r):
        c = self.ctx
        r = r or {}
        url = T.field("分享網址", r.get("url", ""), hint_text="https://notebook.google.com/notebook/…")
        title = T.field("名稱", r.get("title", ""))
        desc = T.field("內容說明", r.get("description", "") or "", multiline=True, min_lines=2)
        tags = T.field("標籤（逗號分隔）", r.get("tags", ""))
        default = T.switch("設為預設筆記本", r.get("is_default"))

        def save(e):
            nid = c.guard(self.b.save_notebook, r.get("id"), url.value, title.value, desc.value, tags.value,
                          default.value, ok="已儲存")
            if nid:
                c.close()
                self.reload()
                self.pick(nid)
        c.dialog("修改筆記本" if r else "新增筆記本", ft.Column([url, title, desc, tags, default], tight=True, spacing=12),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close()), T.btn("儲存", I.SAVE, save)],
                 icon=I.MENU_BOOK, width=560)

    def delete(self):
        r = self.sel

        def go():
            if self.ctx.guard(self.b.delete_notebook, r["id"], ok="已從清單移除（NotebookLM 上的筆記本不會被刪除）"):
                self.sel = None
                self.reload()
                self.pane.content = None
                self.ctx.page.update()
        self.ctx.confirm("移除筆記本", "只會從本系統的清單移除「%s」，不會刪除 Google NotebookLM 上的筆記本。" % r["title"],
                         go, "移除")

    def discover(self):
        c = self.ctx
        c.toast("正在讀取帳號裡的筆記本（約 10～30 秒）…")

        def work():
            try:
                items = self.b.nlm_account_notebooks()
            except Exception as e:
                c.toast("讀取失敗：%s" % e, True)
                return
            if not items:
                c.toast("沒有讀到筆記本；請確認已登入，或改用貼上分享網址", True)
                return
            checks = [ft.Checkbox(label=it["title"] + ("（已在清單）" if it["added"] else ""), value=False,
                                  disabled=it["added"], data=it) for it in items]

            def add(e):
                n = 0
                for cb in checks:
                    if cb.value and not cb.disabled:
                        it = cb.data
                        if c.guard(self.b.save_notebook, None, it["url"], it["title"]):
                            n += 1
                c.close()
                c.toast("已加入 %d 本筆記本" % n)
                self.reload()
            c.dialog("帳號裡的筆記本（%d 本）" % len(items), ft.Column(checks, scroll=ft.ScrollMode.AUTO, height=420),
                     [T.btn("取消", kind="ghost", on_click=lambda e: c.close()), T.btn("加入勾選的", I.ADD, add)],
                     icon=I.TRAVEL_EXPLORE, width=600)
        self.ctx.page.run_thread(work)
