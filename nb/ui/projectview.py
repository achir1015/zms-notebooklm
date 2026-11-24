"""專案範本與主題庫、年度主題表、人員名單。

專案範本＝「這種簡報長什麼樣子」：封面格式、指令上下文、對象、預設筆記本、規格文件（CLAUDE.md）。
主題庫＝每個主題一份教案骨架（目的、用物、步驟、注意事項、常見錯誤、Q&A、母語關鍵詞），用純文字格式編輯。
"""
import flet as ft

from .. import artifacts as A
from .. import rocdate
from . import theme as T

I = ft.Icons

# ---------------------------------------------------------------- 主題骨架 ↔ 純文字
TOPIC_SECTIONS = [("hook", "破題"), ("purposes", "目的"), ("supplies", "用物"), ("stepsA", "步驟一"),
                  ("stepsB", "步驟二"), ("cautions", "注意事項"), ("errors", "常見錯誤"), ("report", "立即報告"),
                  ("action", "行動呼籲"), ("qa", "Q&A"), ("terms", "關鍵詞")]


def topic_to_text(d):
    L = []
    for k, lab in TOPIC_SECTIONS:
        v = d.get(k)
        if k in ("hook", "report", "action"):
            L.append("【%s】%s" % (lab, v or ""))
            continue
        if k in ("stepsA", "stepsB"):
            v = v or {"title": "", "items": []}
            L.append("【%s】%s" % (lab, v.get("title", "")))
            L += ["- " + x for x in v.get("items", [])]
        elif k == "errors":
            L.append("【%s】（錯誤 → 正確）" % lab)
            L += ["- %s → %s" % tuple(x) for x in v or [] if len(x) == 2]
        elif k == "qa":
            L.append("【%s】（題目 ｜ 參考答案）" % lab)
            L += ["- %s ｜ %s" % tuple(x) for x in v or [] if len(x) == 2]
        elif k == "terms":
            L.append("【%s】（中文 ｜ 母語一 ｜ 母語二 ｜ …，順序同專案的母語欄）" % lab)
            L += ["- " + " ｜ ".join(x) for x in v or []]
        else:
            L.append("【%s】" % lab)
            L += ["- " + x for x in v or []]
        L.append("")
    return "\n".join(L)


def text_to_topic(text):
    d, cur = {}, None
    names = {lab: k for k, lab in TOPIC_SECTIONS}
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.startswith("【") and "】" in s:
            lab, rest = s[1:].split("】", 1)
            cur = names.get(lab)
            if not cur:
                continue
            rest = rest.strip()
            if cur in ("hook", "report", "action"):
                d[cur] = rest
            elif cur in ("stepsA", "stepsB"):
                d[cur] = {"title": rest, "items": []}
            else:
                d[cur] = []
            continue
        if not s.startswith("- ") or not cur:
            continue
        item = s[2:].strip()
        if cur in ("stepsA", "stepsB"):
            d[cur]["items"].append(item)
        elif cur == "errors":
            a, _, b = item.partition("→")
            d[cur].append([a.strip(), b.strip()])
        elif cur == "qa":
            a, _, b = item.partition("｜")
            d[cur].append([a.strip(), b.strip()])
        elif cur == "terms":
            d[cur].append([x.strip() for x in item.split("｜")])
        elif isinstance(d.get(cur), list):
            d[cur].append(item)
    return d


# ================================================================ 專案範本與主題庫
class Projects(ft.Row):
    def __init__(self, ctx, project=None, **kw):
        self.ctx = ctx
        self.b = ctx.books
        self.can_edit = self.b.can("PROJ", 2)
        self.pid = int(project) if project else self.b.default_project_id()
        self.list = ft.ListView(spacing=6, expand=True)
        left = T.card(ft.Column([
            ft.Row([ft.Text("專案範本", size=16, weight=ft.FontWeight.W_700, expand=True),
                    ft.IconButton(I.ADD, tooltip="新增空白專案", visible=self.can_edit, on_click=lambda e: self.new())]),
            self.list], spacing=10, expand=True), width=300, padding=14)
        self.pane = ft.Container(expand=True)
        super().__init__([left, self.pane], spacing=16, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        self.reload(False)
        if self.pid:
            self.open(self.pid, False)

    def reload(self, refresh=True):
        items = []
        for p in self.b.projects(active_only=False):
            sel = p["id"] == self.pid
            items.append(ft.Container(ft.Row([
                T.icon_tile(I.STAR if p["is_sample"] else I.FOLDER, "amber" if p["is_sample"] else "blue", 34),
                ft.Column([ft.Text(p["name"], size=14, weight=ft.FontWeight.W_700, max_lines=2),
                           ft.Row(([T.chip("內定範例", "amber", size=11)] if p["is_sample"] else []) +
                                  ([] if p["active"] else [T.chip("停用", "slate", size=11)]), spacing=4)],
                          spacing=2, expand=True)], spacing=10), padding=10, border_radius=12, ink=True,
                bgcolor="#EEF3FB" if sel else None, border=ft.Border.all(1, T.PRIMARY if sel else T.LINE),
                on_click=lambda e, i=p["id"]: self.open(i)))
        self.list.controls = items
        if refresh:
            T.safe_update(self.list)

    def new(self):
        pid = self.ctx.guard(self.b.save_project, None, name="新專案", cover_title_tpl="{org} {topic}",
                             byline_tpl="簡報人：{presenter_role} {presenter} ｜ {instructor_role}：{instructor}",
                             term_langs=[], ok="已新增空白專案")
        if pid:
            self.open(pid)

    def open(self, pid, refresh=True):
        self.pid = pid
        p = self.p = self.b.project(pid)
        ed = self.can_edit
        f = {}

        def F(k, label, width=None, **kw):
            f[k] = T.field(label, p.get(k) if p.get(k) is not None else "", width=width, read_only=not ed, **kw)
            return f[k]
        self.f = f
        nbs = self.b.notebooks()
        self.nb_dd = T.dropdown("預設 NotebookLM 筆記本", [(n["id"], n["title"]) for n in nbs], p.get("notebook_id"),
                                width=420, blank="（不指定）", filterable=False)
        self.style_dd = T.dropdown("預設視覺風格", [(s["id"], s["name"]) for s in A.STYLES], p.get("style") or "pastel",
                                   width=200, filterable=False)
        self.langs = T.field("母語關鍵詞欄（每欄「國籍:語言」，用逗號分隔）",
                             "，".join("%s:%s" % tuple(x) for x in p.get("term_langs") or []), read_only=not ed, expand=True,
                             hint_text="印尼:印尼文，越南:越南文，泰國:泰文")
        self.active = T.switch("啟用", p.get("active"), disabled=not ed)
        preview = ft.Text("", size=13, selectable=True)
        self.cover_preview = preview

        def upd(e=None):
            br = self.brief_from_form()
            preview.value = "【%spt】%s\n【%spt】%s\n【%spt】%s" % (
                f["font_title"].value, br.cover_title, f["font_sub"].value, br.subtitle, f["font_small"].value, br.byline)
            T.safe_update(preview)
        for k in ("org", "unit", "unit_full", "cover_title_tpl", "cover_subtitle", "byline_tpl", "presenter_role",
                  "instructor_role", "font_title", "font_sub", "font_small"):
            pass
        form = ft.Column([
            ft.Text("基本資料", size=15, weight=ft.FontWeight.W_700),
            ft.Row([F("name", "專案名稱", 360), self.active], wrap=True),
            ft.Row([F("org", "機構名稱", 300, on_change=upd), F("unit", "單位簡稱", 140, on_change=upd),
                    F("unit_full", "單位全名", 200)], wrap=True, spacing=10),
            ft.Text("封面格式（第一頁固定）", size=15, weight=ft.FontWeight.W_700),
            T.muted("可以用 {org} 機構、{unit} 單位、{topic} 主題、{presenter_role}{presenter} 簡報人、"
                    "{instructor_role}{instructor} 指導員", 12),
            ft.Row([F("cover_title_tpl", "標題範本", None, expand=True, on_change=upd),
                    F("font_title", "字級", 80, on_change=upd)], spacing=10),
            ft.Row([F("cover_subtitle", "次標題", None, expand=True, on_change=upd),
                    F("font_sub", "字級", 80, on_change=upd)], spacing=10),
            ft.Row([F("byline_tpl", "小標題範本", None, expand=True, on_change=upd),
                    F("font_small", "字級", 80, on_change=upd)], spacing=10),
            ft.Row([F("presenter_role", "簡報人職稱", 200, on_change=upd),
                    F("instructor_role", "指導員職稱", 200, on_change=upd),
                    F("min_slides", "最少張數", 110), F("qa_count", "Q&A 題數", 110)], wrap=True, spacing=10),
            ft.Container(preview, bgcolor="#F7F9FC", padding=12, border_radius=10),
            ft.Text("交給 NotebookLM 的指令上下文", size=15, weight=ft.FontWeight.W_700),
            ft.Row([F("role_text", "角色／身分", expand=True)]),
            ft.Row([F("background_text", "任務背景（可用 {unit}{unit_full}{audience}）", multiline=True, min_lines=2, expand=True)]),
            ft.Row([F("purpose_text", "任務目的", multiline=True, min_lines=2, expand=True)]),
            ft.Row([F("audience_text", "預設學員對象", expand=True)]),
            ft.Row([self.langs]),
            ft.Row([F("extra_rules", "其他規則（每次指令都會加上）", multiline=True, min_lines=2, expand=True)]),
            ft.Row([self.nb_dd, self.style_dd], wrap=True, spacing=10),
            ft.Text("範本規格文件（例如原專案的 CLAUDE.md，供製作者參考）", size=15, weight=ft.FontWeight.W_700),
            ft.Row([F("spec_md", "規格文件（Markdown）", multiline=True, min_lines=6, max_lines=18, expand=True)]),
        ], spacing=10)
        upd()
        actions = []
        if ed:
            actions = [T.btn("儲存專案", I.SAVE, lambda e: self.save()),
                       T.btn("複製成新專案", I.FOLDER_COPY, lambda e: self.copy(), kind="outline"),
                       T.btn("用這個專案產生", I.AUTO_AWESOME, lambda e: self.ctx.app.go("studio", project=pid), kind="ghost"),
                       T.btn("刪除", I.DELETE_OUTLINE, lambda e: self.delete(), kind="danger")]
        topics = self.topic_panel()
        tabs = ft.Tabs(selected_index=0, length=2, expand=True, content=ft.Column([
            ft.TabBar(tabs=[ft.Tab(label="專案設定", icon=I.TUNE), ft.Tab(label="主題庫（%d）" % len(self.topics),
                                                                        icon=I.LIST_ALT)]),
            ft.TabBarView(controls=[ft.Column([form], scroll=ft.ScrollMode.AUTO, expand=True), topics], expand=True)],
            expand=True))
        self.pane.content = T.card(ft.Column([
            ft.Row([T.icon_tile(I.STAR if p["is_sample"] else I.FOLDER, "amber", 46, radius=14),
                    ft.Text(p["name"], size=20, weight=ft.FontWeight.W_800, expand=True)] + actions, spacing=8),
            tabs], spacing=10, expand=True), padding=18, expand=True)
        self.reload(False)
        if refresh:
            self.ctx.page.update()

    def parse_langs(self):
        out = []
        for part in (self.langs.value or "").replace(",", "，").split("，"):
            if ":" in part or "：" in part:
                a, b = part.replace("：", ":").split(":", 1)
                if a.strip():
                    out.append([a.strip(), b.strip()])
        return out

    def form_values(self):
        v = {k: c.value for k, c in self.f.items()}
        v.update(term_langs=self.parse_langs(), notebook_id=int(self.nb_dd.value) if self.nb_dd.value else None,
                 style=self.style_dd.value or "pastel", active=self.active.value)
        return v

    def brief_from_form(self):
        v = self.form_values()
        proj = {k: v[k] for k in A.DEFAULT_PROJECT if k in v and v[k] not in (None, "")}
        for k in ("font_title", "font_sub", "font_small", "min_slides", "qa_count"):
            try:
                proj[k] = int(proj.get(k) or A.DEFAULT_PROJECT[k])
            except ValueError:
                proj[k] = A.DEFAULT_PROJECT[k]
        return A.Brief(proj, {}, topic_name="（主題）", presenter="[員工編號 員工姓名]", instructor="[員工姓名]")

    def save(self):
        if self.ctx.guard(self.b.save_project, self.pid, **self.form_values(), ok="已儲存專案"):
            self.open(self.pid)

    def copy(self):
        c = self.ctx
        name = T.field("新專案名稱", self.p["name"] + "（複製）")

        def go(e):
            pid = c.guard(self.b.copy_project, self.pid, name.value.strip(), ok="已複製，主題庫也一起複製了")
            if pid:
                c.close()
                self.open(pid)
        c.dialog("複製成新專案", ft.Column([T.muted("會複製封面格式、指令上下文與主題庫（不含人員與成品）。"), name], tight=True),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close()), T.btn("複製", I.FOLDER_COPY, go)],
                 icon=I.FOLDER_COPY, width=480)

    def delete(self):
        def go():
            if self.ctx.guard(self.b.delete_project, self.pid, ok="已刪除"):
                self.ctx.app.go("projects")
        self.ctx.confirm("刪除專案", "確定刪除「%s」與它的主題庫、年度主題表嗎？" % self.p["name"], go, "刪除")

    # ---------------------------------------------------------------- 主題庫
    def topic_panel(self):
        self.topics = self.b.topics(self.pid, active_only=False)
        self.tlist = ft.ListView(spacing=4, expand=True)
        self.tedit = ft.Container(expand=True)
        for t in self.topics:
            self.tlist.controls.append(ft.Container(ft.Row([
                ft.Text(("%d 月" % t["month"]) if t["month"] else "—", width=44, size=12, color=T.MUTED),
                ft.Text(t["name"], size=14, expand=True, weight=ft.FontWeight.W_600,
                        color=T.TEXT if t["active"] else T.MUTED)]), padding=8, border_radius=10, ink=True,
                on_click=lambda e, i=t["id"]: self.edit_topic(i)))
        add = T.btn("新增主題", I.ADD, lambda e: self.edit_topic(None), kind="outline", visible=self.can_edit)
        if self.topics:
            self.edit_topic(self.topics[0]["id"], False)
        return ft.Row([ft.Container(ft.Column([add, self.tlist], spacing=8), width=230), self.tedit], spacing=14,
                      expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)

    def edit_topic(self, tid, refresh=True):
        t = self.b.topic(tid) if tid else dict(id=None, name="", month=None, source_hint="", active=1,
                                                parsed=A.blank_topic("新主題"))
        ed = self.can_edit
        name = T.field("主題名稱", t["name"], width=260, read_only=not ed)
        month = T.dropdown("建議月份", [(m, "%d 月" % m) for m in range(1, 13)], t["month"], width=130, blank="不指定",
                           filterable=False)
        src = T.field("依據文件名稱", t["source_hint"], expand=True, read_only=not ed)
        body = T.field("教案骨架（照格式修改）", topic_to_text(t["parsed"]), multiline=True, min_lines=20, read_only=not ed,
                       expand=True)
        active = T.switch("啟用", t["active"], disabled=not ed)

        def save(e):
            r = self.ctx.guard(self.b.save_topic, t["id"], self.pid, name.value, month.value, src.value,
                               text_to_topic(body.value), active.value, ok="已儲存主題")
            if r:
                self.open(self.pid)

        def delete(e):
            def go():
                if self.ctx.guard(self.b.delete_topic, t["id"], ok="已刪除主題"):
                    self.open(self.pid)
            self.ctx.confirm("刪除主題", "確定刪除「%s」嗎？" % t["name"], go, "刪除")
        btns = [T.btn("儲存主題", I.SAVE, save)] + ([T.btn("刪除", I.DELETE_OUTLINE, delete, kind="danger")]
                                                   if t["id"] else []) if ed else []
        self.tedit.content = ft.Column([
            ft.Row([name, month, active], wrap=True, spacing=10), ft.Row([src]),
            T.muted("每段用【段名】開頭、每項用「- 」開頭；常見錯誤寫「錯誤 → 正確」，Q&A 與關鍵詞用「｜」分隔。", 12),
            ft.Row([body]), ft.Row(btns, spacing=10)], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        if refresh:
            T.safe_update(self.tedit)


# ================================================================ 年度主題表
class Plan(ft.Column):
    def __init__(self, ctx, project=None, **kw):
        self.ctx = ctx
        self.b = ctx.books
        self.pid = int(project) if project else self.b.default_project_id()
        roc = rocdate.today().year - 1911
        self.proj_dd = T.dropdown("專案", [(p["id"], p["name"]) for p in self.b.projects()], self.pid, width=360,
                                  filterable=False, on_select=lambda e: self.load())
        self.year = T.dropdown("年度", [(y, "民國 %d 年" % y) for y in range(roc - 1, roc + 3)], roc, width=150,
                               filterable=False, on_select=lambda e: self.load())
        self.grid = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        ed = self.b.can("PROJ", 2)
        super().__init__([
            ft.Row([self.proj_dd, self.year,
                    T.btn("套用主題建議月份", I.AUTO_FIX_HIGH, lambda e: self.sample(), kind="outline", visible=ed),
                    T.btn("儲存全年", I.SAVE, lambda e: self.save(), visible=ed)], spacing=10, wrap=True),
            T.muted("一到十二月全部列出、預設空白；每月選主題（或自訂）、簡報人、指導員與上課日期。到產生工具選月份就會自動帶入。", 12),
            self.grid], spacing=12, expand=True)
        self.load(False)

    def load(self, refresh=True):
        self.pid = int(self.proj_dd.value) if self.proj_dd.value else None
        if not self.pid:
            return
        topics = self.b.topics(self.pid)
        ppl = self.b.people(self.pid)
        topt = [(t["id"], t["name"]) for t in topics] + [("custom", "自訂主題…")]
        popt = [(x["id"], "%s %s" % (x["emp_no"], x["name"])) for x in ppl if x["kind"] == "PRESENTER"]
        iopt = [(x["id"], "%s %s" % (x["emp_no"], x["name"])) for x in ppl if x["kind"] == "INSTRUCTOR"]
        self.rows = []
        ctrls = [ft.Row([ft.Text(h, size=12, color=T.MUTED, width=w) for h, w in
                         (("月份", 60), ("主題", 240), ("自訂主題名稱", 200), ("簡報人", 200), ("指導員", 200),
                          ("上課日期", 140), ("簡報", 90))], spacing=10)]
        for r in self.b.plan(self.pid, int(self.year.value)):
            topic = T.dropdown("", topt, "custom" if r.get("custom_topic") and not r.get("topic_id") else r.get("topic_id"),
                               width=240, blank="（空白）", filterable=False)
            custom = T.field("", r.get("custom_topic") or "", width=200)
            pres = T.dropdown("", popt, r.get("presenter_id"), width=200, blank="", filterable=False)
            inst = T.dropdown("", iopt, r.get("instructor_id"), width=200, blank="", filterable=False)
            date = T.field("", rocdate.show(r["class_date"]) if r.get("class_date") else "", width=140,
                           hint_text="115/03/15")
            job = T.btn("開啟", I.SLIDESHOW, lambda e, j=r.get("job_id"): self.ctx.app.go("works", job=j),
                        kind="ghost") if r.get("job_id") else \
                T.btn("製作", I.AUTO_AWESOME, lambda e, m=r["month"]: self.make(m), kind="ghost")
            self.rows.append((r["month"], topic, custom, pres, inst, date))
            ctrls.append(ft.Row([ft.Text("%d 月" % r["month"], width=60, weight=ft.FontWeight.W_700), topic, custom,
                                 pres, inst, date, job], spacing=10))
        self.grid.controls = ctrls
        if refresh:
            self.ctx.page.update()

    def save(self, quiet=False):
        n = 0
        for m, topic, custom, pres, inst, date in self.rows:
            tid = topic.value if topic.value and topic.value != "custom" else None
            d = None
            if (date.value or "").strip():
                try:
                    d = rocdate.read(date.value.strip())
                except Exception:
                    self.ctx.toast("%d 月的日期格式不對（例：115/03/15）" % m, True)
                    return False
            if self.ctx.guard(self.b.save_plan, self.pid, int(self.year.value), m, int(tid) if tid else None,
                              custom.value.strip() if topic.value == "custom" else "",
                              int(pres.value) if pres.value else None, int(inst.value) if inst.value else None, d) is None:
                return False
            n += 1
        if not quiet:
            self.ctx.toast("已儲存 %s 年主題表" % self.year.value)
        return True

    def sample(self):
        if self.save(quiet=True):
            n = self.ctx.guard(self.b.apply_sample_plan, self.pid, int(self.year.value))
            self.ctx.toast("已填入 %s 個月份" % (n if isinstance(n, int) else 0))
            self.load()

    def make(self, month):
        if self.b.can("PROJ", 2) and not self.save(quiet=True):
            return
        self.ctx.app.go("studio", kind="SLIDES", project=self.pid, month=month)


# ================================================================ 人員名單
class People(ft.Column):
    def __init__(self, ctx, **kw):
        self.ctx = ctx
        self.b = ctx.books
        self.ed = self.b.can("PEOPLE", 2)
        self.pid = self.b.default_project_id()
        self.proj_dd = T.dropdown("專案", [(p["id"], p["name"]) for p in self.b.projects()], self.pid, width=360,
                                  filterable=False, on_select=lambda e: self.load())
        self.grid = T.Grid([("kind_text", "身分", "s", 100), ("emp_no", "員工編號", "s", 110), ("name", "姓名", "s", 160),
                            ("title", "職稱", "s", 140), ("note", "備註", "s", 220), ("active_text", "狀態", "s", 80)],
                           on_pick=self.edit if self.ed else None)
        super().__init__([
            ft.Row([self.proj_dd, T.btn("新增人員", I.PERSON_ADD, lambda e: self.edit(None), visible=self.ed),
                    T.btn("貼上名單匯入", I.CONTENT_PASTE, lambda e: self.paste(), kind="outline", visible=self.ed)],
                   spacing=10, wrap=True),
            T.muted("簡報人與指導員名單（例如從月班表整理出的常駐人員）。示範資料是虛構的，請改成自己的名單。", 12),
            T.card(self.grid, expand=True, padding=10)], spacing=12, expand=True)
        self.load(False)

    def load(self, refresh=True):
        self.pid = int(self.proj_dd.value) if self.proj_dd.value else 0
        rows = self.b.people(self.pid, active_only=False)
        for r in rows:
            r["kind_text"] = "簡報人" if r["kind"] == "PRESENTER" else "指導員"
            r["active_text"] = "啟用" if r["active"] else "停用"
        self.grid.set_rows(rows)
        if refresh:
            self.ctx.page.update()

    def edit(self, r):
        c = self.ctx
        r = r or {}
        kind = T.dropdown("身分", [("PRESENTER", "簡報人"), ("INSTRUCTOR", "指導員")], r.get("kind", "PRESENTER"),
                          filterable=False)
        no = T.field("員工編號", r.get("emp_no", ""))
        name = T.field("姓名", r.get("name", ""))
        title = T.field("職稱", r.get("title", ""))
        note = T.field("備註", r.get("note", ""))
        active = T.switch("啟用", r.get("active", 1))

        def save(e):
            if c.guard(self.b.save_person, r.get("id"), self.pid, kind.value, no.value, name.value, title.value,
                       note.value, active.value, ok="已儲存"):
                c.close()
                self.load()

        def delete(e):
            if c.guard(self.b.delete_person, r["id"], ok="已刪除"):
                c.close()
                self.load()
        c.dialog("修改人員" if r else "新增人員", ft.Column([kind, no, name, title, note, active], tight=True, spacing=10),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close())] +
                 ([T.btn("刪除", I.DELETE_OUTLINE, delete, kind="danger")] if r.get("id") else []) +
                 [T.btn("儲存", I.SAVE, save)], icon=I.BADGE, width=460)

    def paste(self):
        c = self.ctx
        box = T.field("名單", "", multiline=True, min_lines=8,
                      hint_text="簡報人,WA003,王小明,病房助理員\n指導員,RN010,李美華,護理師")

        def go(e):
            n = c.guard(self.b.import_people, self.pid, box.value)
            if n is not None:
                c.close()
                c.toast("已匯入 %s 人" % n)
                self.load()
        c.dialog("貼上名單匯入", ft.Column([T.muted("每行：身分,員編,姓名,職稱（可以從 Excel 複製，用 Tab 分隔也可以）；同員編會更新。"),
                                         box], tight=True, spacing=10),
                 [T.btn("取消", kind="ghost", on_click=lambda e: c.close()), T.btn("匯入", I.UPLOAD, go)],
                 icon=I.CONTENT_PASTE, width=560)

