"""產生工具：選產出類型 → 七個步驟填需求單 → 依 NotebookLM 筆記本（或內建範本）產生。

版面：上方五種產出類型；左邊是七個步驟卡片（由上往下填）；右邊是需求摘要、產生方式與進度。
"""
import threading
import time

import flet as ft

from .. import artifacts as A
from .. import rocdate
from .. import visual as V
from . import theme as T

I = ft.Icons


def step_card(no, title, sub, body, tone="blue"):
    return T.card(ft.Column([
        ft.Row([ft.Container(ft.Text(str(no), color=ft.Colors.WHITE, weight=ft.FontWeight.W_800, size=15),
                             width=30, height=30, border_radius=15, bgcolor=T.TONES[tone][1],
                             alignment=ft.Alignment.CENTER),
                ft.Column([ft.Text(title, size=16, weight=ft.FontWeight.W_700), T.muted(sub, 12)], spacing=0,
                          expand=True)], spacing=12),
        body], spacing=12), padding=16)


class Studio(ft.Row):
    def __init__(self, ctx, kind="SLIDES", project=None, month=None, **kw):
        self.ctx = ctx
        b = self.b = ctx.books
        self.kind = kind if kind in A.KINDS else "SLIDES"
        self.busy = False
        self.pid = int(project) if project else b.default_project_id()
        self.proj = b.project(self.pid) if self.pid else {}
        roc = rocdate.today().year - 1911

        # ---------------------------------------------------- 產出類型
        self.kind_row = ft.Row(spacing=10)
        # ---------------------------------------------------- 1. 主題
        self.project_dd = T.dropdown("專案範本", [(p["id"], p["name"]) for p in b.projects()], self.pid, width=330,
                                     on_select=self.on_project, filterable=False)
        self.year = T.dropdown("年度", [(y, "民國 %d 年" % y) for y in range(roc - 1, roc + 3)], roc, width=150,
                               on_select=lambda e: self.load_plan(), filterable=False)
        self.month = T.dropdown("年度主題表月份", [], None, width=260, on_select=self.on_month, blank="（不用年度主題表）",
                                filterable=False)
        self.topic_dd = T.dropdown("主題", [], None, width=330, on_select=self.on_topic, blank="（自訂主題）")
        self.custom = T.field("自訂主題名稱", "", width=330, on_change=lambda e: self.refresh_summary(),
                              hint_text="主題庫沒有時直接輸入，例如：拍背與排痰")
        # ---------------------------------------------------- 2. 人員
        self.pres_dd = T.dropdown("簡報人（名單）", [], None, width=260, on_select=self.on_person, blank="（手動輸入）")
        self.pres = T.field("簡報人：員編 姓名", "", width=260, on_change=lambda e: self.refresh_summary())
        self.inst_dd = T.dropdown("指導員（名單）", [], None, width=260, on_select=self.on_person, blank="（手動輸入）")
        self.inst = T.field("指導員：員編 姓名", "", width=260, on_change=lambda e: self.refresh_summary())
        self.date = T.field("上課日期", "", width=170, hint_text="115/12/15")
        # ---------------------------------------------------- 3. 學員
        self.audience = T.field("學員對象", "", expand=True, on_change=lambda e: self.refresh_summary())
        self.langs_row = ft.Row(spacing=4, wrap=True)
        self.level = T.dropdown("語言程度", list(A.LEVELS.items()), "basic", width=330, filterable=False)
        # ---------------------------------------------------- 4. 依據文件
        self.source = T.field("依據文件名稱（衛教單張、手冊…）", "", expand=True)
        self.pages = T.field("頁數", "", width=150, hint_text="例：282-290")
        self.notes = T.field("本次文案重點與特別要求", "", multiline=True, min_lines=2, max_lines=5, expand=True,
                             hint_text="同一個主題、不同文案，產生的內容就不同。例：著重氣切病人的翻身注意事項")
        # ---------------------------------------------------- 5. 設定
        self.count = T.field("簡報張數", "12", width=120, keyboard_type=ft.KeyboardType.NUMBER,
                             on_change=lambda e: self.refresh_summary())
        self.qa = T.field("Q&A 題數", str(self.proj.get("qa_count") or 5), width=120, keyboard_type=ft.KeyboardType.NUMBER)
        self.quiz_n = T.field("測驗題數", "10", width=120, keyboard_type=ft.KeyboardType.NUMBER)
        self.lang = T.dropdown("語言", [(x["id"], x["name"]) for x in A.LANGS], "zh", width=200, filterable=False)
        self.style = self.proj.get("style") or "pastel"
        self.style_row = ft.Row(spacing=8, wrap=True)
        self.subtitle = T.field("封面次標題", self.proj.get("cover_subtitle", ""), expand=True,
                                on_change=lambda e: self.refresh_summary())
        # ---------------------------------------------------- 6. 產生方式
        self.engine = ft.RadioGroup(value="NOTEBOOKLM", on_change=lambda e: self.refresh_summary(), content=ft.Column([
            ft.Radio(value="NOTEBOOKLM", label="依 NotebookLM 筆記本來源產生（建議；內容跟著文案走）"),
            ft.Radio(value="TEMPLATE", label="用內建範本產生（離線也能用，當作起點再修改）")], spacing=0))
        nbs = b.notebooks()
        default_nb = self.proj.get("notebook_id") or next((n["id"] for n in nbs if n["is_default"]), None)
        self.nb_dd = T.dropdown("NotebookLM 筆記本", [(n["id"], n["title"]) for n in nbs], default_nb, expand=True,
                                filterable=False, on_select=lambda e: self.refresh_summary())
        # ---------------------------------------------------- 7. 官方 AI 插圖版指令
        self.v_need = T.dropdown("需求類型", [(k, n) for k, n, _ in V.NEEDS], "edu", width=200, filterable=False,
                                 on_select=lambda e: self.refresh_visual())
        self.v_style = T.dropdown("視覺風格", [(k, n) for k, n, _ in V.STYLES], "clay3d", width=220, filterable=False,
                                  on_select=lambda e: self.refresh_visual())
        self.v_layout = T.dropdown("佈局結構", [(k, n) for k, n, _ in V.LAYOUTS], "snake", width=200, filterable=False,
                                   on_select=lambda e: self.refresh_visual())
        self.v_text = ft.Text("", size=13, selectable=True)
        # ---------------------------------------------------- 右邊：摘要與產生
        self.summary = ft.Column(spacing=6)
        self.go_btn = T.btn("開始產生", I.AUTO_AWESOME, lambda e: self.start(), bgcolor=T.GOLD, height=52)
        self.ring = ft.ProgressRing(width=22, height=22, stroke_width=3, visible=False)
        self.prog = ft.Text("", size=13, color=T.MUTED)
        self.log = ft.ListView(height=150, spacing=2, auto_scroll=True)

        self.steps = ft.Column([
            step_card(1, "主題", "選專案範本與主題；也可以從年度主題表直接帶入某個月份", ft.Column([
                ft.Row([self.project_dd, self.year, self.month], wrap=True, spacing=10, run_spacing=10),
                ft.Row([self.topic_dd, self.custom], wrap=True, spacing=10, run_spacing=10)], spacing=10)),
            step_card(2, "人員", "簡報人與指導員：從名單選，名單外的人直接輸入", ft.Column([
                ft.Row([self.pres_dd, self.pres], spacing=10, wrap=True),
                ft.Row([self.inst_dd, self.inst, self.date], spacing=10, wrap=True)], spacing=10), "violet"),
            step_card(3, "學員", "對象、母語關鍵詞與語言程度", ft.Column([
                ft.Row([self.audience]), self.langs_row, self.level], spacing=10), "amber"),
            step_card(4, "依據文件", "NotebookLM 會以筆記本裡的來源為唯一依據；這裡寫要依據哪一份、哪幾頁", ft.Column([
                ft.Row([self.source, self.pages], spacing=10), ft.Row([self.notes])], spacing=10), "teal"),
            step_card(5, "設定", "張數（不少於專案規定）、題數、語言、視覺風格、封面次標題", ft.Column([
                ft.Row([self.count, self.qa, self.quiz_n, self.lang], spacing=10, wrap=True), ft.Row([self.subtitle]),
                ft.Text("視覺風格（只用在匯出的檔案；大綱只放文字）", size=13, weight=ft.FontWeight.W_600),
                self.style_row], spacing=10), "pink"),
            step_card(6, "產生方式", "選 NotebookLM 筆記本，或用內建範本", ft.Column([
                self.engine, ft.Row([self.nb_dd, T.btn("管理筆記本", I.LINK, lambda e: ctx.app.go("notebooks"),
                                                       kind="outline")], spacing=10)], spacing=8), "green"),
            step_card(7, "NotebookLM 官方 AI 插圖版（選用）",
                      "想要 NotebookLM 畫的 3D 插圖簡報或資訊圖表：選需求、風格、佈局 → 複製指令 → 在 NotebookLM 的 Studio 貼上",
                      ft.Column([ft.Row([self.v_need, self.v_style, self.v_layout], wrap=True, spacing=10, run_spacing=10),
                                 ft.Container(self.v_text, bgcolor="#F7F9FC", padding=12, border_radius=10),
                                 ft.Row([T.btn("複製視覺指令", I.CONTENT_COPY, lambda e: self.copy_visual(), kind="outline"),
                                         T.btn("開啟這本筆記本", I.OPEN_IN_NEW, lambda e: self.open_notebook(),
                                               kind="ghost")], spacing=10, wrap=True),
                                 T.muted("提示：NotebookLM 右側 Studio →「簡報」或「資訊圖表」旁的筆形圖示 → 貼上指令 → 產生。"
                                         "產生完可以下載 PDF。風格與佈局的分類參考 Meiko 微課頻道。", 11)],
                                spacing=10), "violet"),
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

        right = T.card(ft.Column([
            ft.Row([T.icon_tile(I.ASSIGNMENT, "blue", 34), ft.Text("需求摘要", size=16, weight=ft.FontWeight.W_700)]),
            ft.Container(self.summary, expand=True),
            ft.Divider(height=1, color=T.LINE),
            ft.Row([self.ring, self.prog], spacing=8),
            ft.Container(self.log, bgcolor="#F7F9FC", border_radius=10, padding=8),
            ft.Row([self.go_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([T.btn("複製 NotebookLM 指令", I.CONTENT_COPY, lambda e: self.copy_prompt(), kind="ghost"),
                    T.btn("看指令", I.ARTICLE, lambda e: self.show_prompt(), kind="ghost")],
                   alignment=ft.MainAxisAlignment.CENTER, wrap=True)], spacing=10), width=400, padding=18)
        left = ft.Column([self.kind_row, self.steps], spacing=14, expand=True)
        super().__init__([left, right], spacing=16, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        self.render_kinds(False)
        self.render_styles(False)
        self.on_project(None, refresh=False)
        if month:
            self.month.value = str(month)
            self.on_month(None, refresh=False)
        self.refresh_summary(False)

    # ================================================================ 產出類型與風格
    def render_kinds(self, refresh=True):
        items = []
        for k in A.KIND_ORDER:
            name, icon, tone = A.KINDS[k]
            sel = k == self.kind
            bg, fg = T.TONES[tone]
            items.append(ft.Container(ft.Row([ft.Icon(getattr(I, icon), color=ft.Colors.WHITE if sel else fg, size=20),
                                              ft.Text(name, size=15, weight=ft.FontWeight.W_700,
                                                      color=ft.Colors.WHITE if sel else T.TEXT)], spacing=8, tight=True),
                                      padding=ft.Padding.symmetric(horizontal=18, vertical=12), border_radius=14,
                                      bgcolor=fg if sel else T.CARD, border=ft.Border.all(1, fg if sel else T.LINE),
                                      ink=True, on_click=lambda e, k=k: self.set_kind(k)))
        self.kind_row.controls = items
        if refresh:
            T.safe_update(self.kind_row)

    def set_kind(self, k):
        self.kind = k
        self.render_kinds()
        self.refresh_summary()

    def render_styles(self, refresh=True):
        items = []
        for s in A.STYLES:
            sel = s["id"] == self.style
            items.append(ft.Container(ft.Column([
                ft.Row([ft.Container(width=22, height=22, border_radius=6, bgcolor=c) for c in s["colors"][:3]], spacing=3),
                ft.Text(s["name"], size=13, weight=ft.FontWeight.W_700), T.muted(s["desc"], 11)], spacing=4),
                width=170, padding=10, border_radius=12, bgcolor="#EEF3FB" if sel else T.CARD,
                border=ft.Border.all(2 if sel else 1, T.PRIMARY if sel else T.LINE), ink=True,
                on_click=lambda e, i=s["id"]: self.set_style(i)))
        self.style_row.controls = items
        if refresh:
            T.safe_update(self.style_row)

    def set_style(self, sid):
        self.style = sid
        self.render_styles()
        self.refresh_summary()

    # ================================================================ 專案、年度主題表、主題、人員
    def on_project(self, e, refresh=True):
        b = self.b
        if self.project_dd.value:
            self.pid = int(self.project_dd.value)
            self.proj = b.project(self.pid)
        p = self.proj
        self.topics = b.topics(self.pid) if self.pid else []
        self.topic_dd.options = [ft.DropdownOption(key="", text="（自訂主題）")] + [
            ft.DropdownOption(key=str(t["id"]), text=("%d 月｜" % t["month"] if t["month"] else "") + t["name"])
            for t in self.topics]
        self.topic_dd.value = str(self.topics[0]["id"]) if self.topics else ""
        self.people = b.people(self.pid) if self.pid else []
        self.pres_dd.options = [ft.DropdownOption(key="", text="（手動輸入）")] + [
            ft.DropdownOption(key=str(x["id"]), text="%s %s" % (x["emp_no"], x["name"]))
            for x in self.people if x["kind"] == "PRESENTER"]
        self.inst_dd.options = [ft.DropdownOption(key="", text="（手動輸入）")] + [
            ft.DropdownOption(key=str(x["id"]), text="%s %s" % (x["emp_no"], x["name"]))
            for x in self.people if x["kind"] == "INSTRUCTOR"]
        self.pres_dd.label = "%s（名單）" % (p.get("presenter_role") or "簡報人")
        self.inst_dd.label = "%s（名單）" % (p.get("instructor_role") or "指導員")
        self.audience.value = p.get("audience_text", "")
        self.subtitle.value = p.get("cover_subtitle", "")
        self.qa.value = str(p.get("qa_count") or 5)
        self.style = p.get("style") or self.style
        try:
            if int(self.count.value or 0) < int(p.get("min_slides") or 0):
                self.count.value = str(max(int(p.get("min_slides") or 10), 11))
        except ValueError:
            self.count.value = "12"
        self.langs = {lab: ft.Checkbox(label="%s（%s）" % (lab, lang), value=True,
                                       on_change=lambda e: self.refresh_summary())
                      for lab, lang in (p.get("term_langs") or [])}
        self.langs_row.controls = ([T.muted("母語關鍵詞：", 13)] + list(self.langs.values())) if self.langs else \
            [T.muted("這個專案沒有設定母語關鍵詞欄", 12)]
        if p.get("notebook_id"):
            self.nb_dd.value = str(p["notebook_id"])
        self.load_plan(refresh=False)
        self.on_topic(None, refresh=False)
        self.render_styles(False)
        if refresh:
            self.ctx.page.update()
            self.refresh_summary()

    def load_plan(self, refresh=True):
        self.plan_rows = {}
        if self.pid and self.year.value:
            for r in self.b.plan(self.pid, int(self.year.value)):
                if r.get("topic_id") or r.get("custom_topic"):
                    self.plan_rows[r["month"]] = r
        names = {t["id"]: t["name"] for t in self.topics}
        self.month.options = [ft.DropdownOption(key="", text="（不用年度主題表）")] + [
            ft.DropdownOption(key=str(m), text="%d 月｜%s" % (m, names.get(r.get("topic_id")) or r.get("custom_topic")))
            for m, r in sorted(self.plan_rows.items())]
        self.month.value = ""
        if refresh:
            T.safe_update(self.month)

    def on_month(self, e, refresh=True):
        r = self.plan_rows.get(int(self.month.value)) if self.month.value else None
        if not r:
            return
        self.topic_dd.value = str(r["topic_id"]) if r.get("topic_id") else ""
        self.custom.value = r.get("custom_topic") or ""
        ppl = {x["id"]: x for x in self.people}
        if r.get("presenter_id") in ppl:
            self.pres_dd.value = str(r["presenter_id"])
            self.pres.value = self.b.person_text(ppl[r["presenter_id"]])
        if r.get("instructor_id") in ppl:
            self.inst_dd.value = str(r["instructor_id"])
            self.inst.value = self.b.person_text(ppl[r["instructor_id"]])
        if r.get("class_date"):
            self.date.value = rocdate.show(r["class_date"])
        self.on_topic(None, refresh=False)
        if refresh:
            self.ctx.page.update()
            self.refresh_summary()

    def on_topic(self, e, refresh=True):
        t = next((x for x in self.topics if str(x["id"]) == (self.topic_dd.value or "")), None)
        self.custom.visible = t is None
        self.source.value = t["source_hint"] if t else (self.custom.value + "相關文件" if self.custom.value else "")
        if refresh:
            self.ctx.page.update()
            self.refresh_summary()

    def on_person(self, e):
        ppl = {str(x["id"]): x for x in self.people}
        if e.control is self.pres_dd and self.pres_dd.value in ppl:
            self.pres.value = self.b.person_text(ppl[self.pres_dd.value])
        if e.control is self.inst_dd and self.inst_dd.value in ppl:
            self.inst.value = self.b.person_text(ppl[self.inst_dd.value])
        self.ctx.page.update()
        self.refresh_summary()

    # ================================================================ 需求單
    def topic_id(self):
        return int(self.topic_dd.value) if self.topic_dd.value else None

    def brief(self):
        def num(f, d):
            try:
                return int(f.value)
            except (TypeError, ValueError):
                return d
        return self.b.make_brief(
            self.pid, self.topic_id(), topic_name="" if self.topic_id() else (self.custom.value or "").strip(),
            presenter=self.pres.value.strip(), instructor=self.inst.value.strip(), date=self.date.value.strip(),
            audience=self.audience.value.strip(), term_langs=[k for k, c in self.langs.items() if c.value],
            level=self.level.value or "basic", source_title=self.source.value.strip(), source_pages=self.pages.value.strip(),
            notes=self.notes.value.strip(), slide_count=num(self.count, 12), qa_count=num(self.qa, 5),
            quiz_count=num(self.quiz_n, 10), lang=self.lang.value or "zh", style=self.style,
            subtitle=self.subtitle.value.strip())

    def refresh_summary(self, refresh=True):
        try:
            br = self.brief()
        except Exception as ex:
            self.summary.controls = [T.muted("需求單還不完整：%s" % ex)]
            if refresh:
                T.safe_update(self.summary)
            return
        name, icon, tone = A.KINDS[self.kind]
        nb = next((o.text for o in self.nb_dd.options if o.key == self.nb_dd.value), "（未選）")

        def line(k, v):
            return ft.Row([ft.Text(k, size=12, color=T.MUTED, width=70),
                           ft.Text(v or "—", size=13, expand=True, selectable=True)],
                          vertical_alignment=ft.CrossAxisAlignment.START)
        rows = [ft.Row([T.icon_tile(getattr(I, icon), tone, 30), ft.Text(name, size=15, weight=ft.FontWeight.W_700),
                        T.chip("NotebookLM" if self.engine.value == "NOTEBOOKLM" else "內建範本",
                               "blue" if self.engine.value == "NOTEBOOKLM" else "slate")], spacing=8),
                line("主題", br.topic_name)]
        if self.kind == "SLIDES":
            rows += [line("封面標題", br.cover_title), line("次標題", br.subtitle), line("小標題", br.byline),
                     line("張數", "%d 張（含封面）＋ Q&A %d 題" % (br.slide_count, br.qa_count))]
        elif self.kind == "QUIZ":
            rows.append(line("題數", "%d 題" % br.quiz_count))
        rows += [line("對象", br.audience), line("依據", br.source_title + ("（%s 頁）" % br.source_pages
                                                                         if br.source_pages else "")),
                 line("風格", A.STYLE_BY_ID[self.style]["name"])]
        if self.engine.value == "NOTEBOOKLM":
            rows.append(line("筆記本", nb))
        if self.kind == "SLIDES" and (self.count.value or "").isdigit() and br.slide_count > int(self.count.value):
            rows.append(T.muted("張數已調整為專案最少 %d 張" % br.slide_count, 12))
        self.summary.controls = rows
        self.refresh_visual(refresh)
        if refresh:
            T.safe_update(self.summary)

    # ================================================================ 產生
    def visual_text(self):
        return V.build(self.kind, self.brief(), self.v_need.value or "edu", self.v_style.value or "clay3d",
                       self.v_layout.value or "snake")

    def refresh_visual(self, refresh=True):
        try:
            self.v_text.value = self.visual_text()
        except Exception as ex:
            self.v_text.value = "（需求單還不完整：%s）" % ex
        if refresh:
            T.safe_update(self.v_text)

    def copy_visual(self):
        self.ctx.copy_text(self.visual_text(), "已複製視覺指令：到 NotebookLM 的 Studio 貼上即可")

    def open_notebook(self):
        if not self.nb_dd.value:
            self.ctx.toast("請先在第 6 步選一本筆記本", True)
            return
        self.ctx.open_url(self.b.notebook(int(self.nb_dd.value))["url"])

    def copy_prompt(self):
        self.ctx.copy_text(A.build_prompt(self.kind, self.brief()),
                           "已複製指令，可以貼到 NotebookLM 官方網頁的對話框使用")

    def show_prompt(self):
        c = self.ctx
        text = A.build_prompt(self.kind, self.brief())
        c.dialog("交給 NotebookLM 的指令", ft.Column([ft.Text(text, size=13, selectable=True)], scroll=ft.ScrollMode.AUTO,
                                                    height=480),
                 [T.btn("複製", I.CONTENT_COPY, lambda e: c.copy_text(text), kind="outline"),
                  T.btn("關閉", on_click=lambda e: c.close())], icon=I.ARTICLE, width=720)

    def say(self, msg):
        self.log.controls.append(ft.Text("%s　%s" % (time.strftime("%H:%M:%S"), msg), size=12, color=T.TEXT))
        self.prog.value = msg
        T.safe_update(self.log)
        T.safe_update(self.prog)

    def start(self):
        if self.busy:
            return
        engine = self.engine.value
        if engine == "NOTEBOOKLM" and not self.nb_dd.value:
            self.ctx.toast("請先選一本 NotebookLM 筆記本（或改用內建範本）", True)
            return
        br = self.brief()
        if not br.topic_name or br.topic_name == "自訂主題":
            self.ctx.toast("請選主題或輸入自訂主題名稱", True)
            return
        self.busy = True
        self.go_btn.disabled = True
        self.ring.visible = True
        self.log.controls.clear()
        T.safe_update(self.go_btn)
        self.say("開始產生「%s」%s…" % (br.topic_name, A.KINDS[self.kind][0]))
        if engine == "NOTEBOOKLM":
            self.say("NotebookLM 依筆記本來源撰寫中，大約 30 秒～3 分鐘，請稍候")
        t0 = time.time()
        stop = threading.Event()

        def ticker():
            while not stop.wait(5):
                self.prog.value = "已等待 %d 秒…" % (time.time() - t0)
                T.safe_update(self.prog)
        self.ctx.page.run_thread(ticker)

        def prog(msg, cur=None, total=None):
            if msg:
                self.say(msg if cur is None else "%s（%s/%s）" % (msg, cur, total))

        def work():
            try:
                jid = self.b.generate(self.kind, br, engine=engine,
                                      notebook_id=int(self.nb_dd.value) if self.nb_dd.value else None,
                                      project_id=self.pid, topic_id=self.topic_id(), style=self.style, progress=prog)
                if self.month.value and self.kind == "SLIDES":
                    self.b.link_plan_job(self.pid, int(self.year.value), int(self.month.value), jid)
            except Exception as ex:
                stop.set()
                self.busy = False
                self.go_btn.disabled = False
                self.ring.visible = False
                self.say("失敗：%s" % ex)
                T.safe_update(self.go_btn)
                T.safe_update(self.ring)
                self.ctx.toast(str(ex), True)
                return
            stop.set()
            self.busy = False
            self.say("完成！耗時 %d 秒" % (time.time() - t0))
            self.ctx.toast("已產生，正在開啟成品")
            self.ctx.app.go("works", job=jid)
        self.ctx.page.run_thread(work)
