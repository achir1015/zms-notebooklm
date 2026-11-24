"""首頁：NotebookLM 連線狀態、五種產出一鍵開始、統計、最近的成品。"""
import datetime as dt

import flet as ft

from .. import rocdate
from ..artifacts import KIND_ORDER, KINDS
from . import theme as T

I = ft.Icons
DESC = {"SLIDES": "封面＋10 張以上＋Q&A，輸出 PowerPoint 與 Word", "MINDMAP": "左右展開，輸出圖片、網頁、XMind",
        "REPORT": "摘要、小節、結論，輸出 Word", "QUIZ": "單選與是非，作答卷、解答、線上作答",
        "INFOGRAPHIC": "一頁式直式海報圖片", "WEBPAGE": "章節、翻牌卡、問答、計分測驗的單頁網站"}


def greet():
    h = dt.datetime.now().hour
    return "早安" if h < 11 else "午安" if h < 14 else "下午好" if h < 18 else "晚安"


class Dashboard(ft.Column):
    def __init__(self, ctx, **kw):
        self.ctx = ctx
        b = ctx.books
        app = ctx.app
        u = b.user
        comp = b.company()
        st = b.stats() if b.can("GEN", 1) else {}
        nbs = b.notebooks()
        default_nb = next((n for n in nbs if n["is_default"]), nbs[0] if nbs else None)
        self.status_chip = hero_chip(I.SYNC, "正在檢查 NotebookLM 連線…")
        hero = ft.Container(ft.Row([
            ft.Column([ft.Text("%s，%s" % (u["name"], greet()), size=24, weight=ft.FontWeight.W_800,
                               color=ft.Colors.WHITE),
                       ft.Text(((comp.get("name") or "") + "　").lstrip("　") +
                               "選一本 NotebookLM 筆記本，在這裡產生簡報、心智圖、報告、測驗與資訊圖表",
                               size=14, color="#DCE6F5"),
                       ft.Row([hero_chip(I.CALENDAR_TODAY, rocdate.show(rocdate.today())), self.status_chip,
                               hero_chip(I.MENU_BOOK, "預設筆記本：%s" % (default_nb["title"] if default_nb else "尚未設定"))],
                              spacing=8, wrap=True),
                       ft.Row([T.btn("開始做簡報", I.SLIDESHOW, lambda e: app.go("studio", kind="SLIDES"), bgcolor=T.GOLD),
                               T.btn("NotebookLM 連線", I.LINK, lambda e: app.go("notebooks"), bgcolor="#2B5BA0")],
                              spacing=8)],
                      spacing=10, expand=True),
            ft.Image(src="icon.png", width=120, height=120)], spacing=20), padding=24, border_radius=20,
            gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                       colors=[T.SIDEBAR_TOP, "#1E4D8C", "#0FA294"]))
        ways = ft.Row([way(getattr(I, KINDS[k][1]), KINDS[k][2], KINDS[k][0], DESC[k],
                           lambda e, k=k: app.go("studio", kind=k)) for k in KIND_ORDER], spacing=12)
        by = st.get("by_kind", {}) if st else {}
        ks = T.kpis([
            T.kpi("我的成品" if not b.can("ALL", 1) else "全部成品", str(st.get("total", 0)), I.INVENTORY_2, "blue",
                  "依 NotebookLM 產生 %s 份" % st.get("nlm", 0), lambda e: app.go("works")),
            T.kpi("簡報", str(by.get("SLIDES", 0)), I.SLIDESHOW, "violet", "PowerPoint", lambda e: app.go("works", kind="SLIDES")),
            T.kpi("心智圖／資訊圖表", "%d／%d" % (by.get("MINDMAP", 0), by.get("INFOGRAPHIC", 0)), I.ACCOUNT_TREE, "pink",
                  "圖片與網頁", lambda e: app.go("works")),
            T.kpi("報告／測驗", "%d／%d" % (by.get("REPORT", 0), by.get("QUIZ", 0)), I.QUIZ, "amber", "Word",
                  lambda e: app.go("works")),
            T.kpi("互動式網頁", str(by.get("WEBPAGE", 0)), I.WEB, "green", "單一 HTML 檔",
                  lambda e: app.go("works", kind="WEBPAGE")),
            T.kpi("筆記本", str(st.get("notebooks", 0)), I.MENU_BOOK, "teal", "專案範本 %s 個" % st.get("projects", 0),
                  lambda e: app.go("notebooks"))]) if st else ft.Container()
        recent = []
        if b.can("GEN", 1):
            for r in b.jobs(limit=10):
                name, icon, tone = KINDS.get(r["kind"], ("?", "HELP", "slate"))
                recent.append(ft.Container(ft.Column([
                    ft.Row([T.icon_tile(getattr(I, icon), tone, 34), T.chip(name, tone),
                            T.chip("NotebookLM" if r["engine"] == "NOTEBOOKLM" else "範本",
                                   "blue" if r["engine"] == "NOTEBOOKLM" else "slate")], spacing=6),
                    ft.Text(r["title"], size=13, weight=ft.FontWeight.W_700, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    T.muted(r["summary"], 11), T.muted(T.show(r["updated_at"])[:16], 11)], spacing=4),
                    width=210, padding=12, border_radius=14, bgcolor=T.CARD, border=ft.Border.all(1, T.LINE), ink=True,
                    on_click=lambda e, i=r["id"]: app.go("works", job=i)))
        rec = T.card(ft.Column([
            ft.Row([T.icon_tile(I.HISTORY, "blue", 32), ft.Text("最近的成品", size=16, weight=ft.FontWeight.W_700, expand=True),
                    T.btn("成品庫", I.ARROW_FORWARD, lambda e: app.go("works"), kind="ghost")]),
            ft.Row(recent, scroll=ft.ScrollMode.AUTO, spacing=10) if recent else
            T.muted("還沒有成品。按上面任一種產出開始，第一次可以先用內建範本試試看。")], spacing=10))
        tips = T.card(ft.Column([
            ft.Row([T.icon_tile(I.TIPS_AND_UPDATES, "amber", 32), ft.Text("使用重點", size=16, weight=ft.FontWeight.W_700)]),
            tip("內容跟著來源", "選 NotebookLM 產生時，內容以筆記本裡的文件為唯一依據；同一主題、不同文案，內容就不同。"),
            tip("範本是起點", "內建範本離線也能用，產生後逐頁修改；正式使用前請由指導員確認內容。"),
            tip("封面固定格式", "封面依專案範本：標題 45pt、次標題 40pt、小標題 32pt；大綱階段只放文字。"),
            tip("換成其他專案", "到「專案範本」複製內定範例，改機構、封面與主題庫，就能做其他專案的簡報。")],
            spacing=8))
        super().__init__([hero, ways, ks, rec, tips], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)
        if b.can("NOTE", 1):
            ctx.page.run_thread(self._check)
        else:
            self._set_status(I.LINK_OFF, "沒有 NotebookLM 權限")

    def _check(self):
        try:
            s = self.ctx.books.nlm_status()
            if s["authenticated"]:
                self._set_status(I.CHECK_CIRCLE, "NotebookLM 已登入")
            else:
                self._set_status(I.LOGIN, "NotebookLM 尚未登入（按 NotebookLM 連線）")
        except Exception as e:
            self._set_status(I.ERROR_OUTLINE, "NotebookLM 無法啟動：%s" % str(e)[:40])

    def _set_status(self, icon, text):
        row = self.status_chip.content
        row.controls[0].icon = icon
        row.controls[1].value = text
        T.safe_update(self.status_chip)


def hero_chip(icon, text):
    return ft.Container(ft.Row([ft.Icon(icon, size=14, color="#DCE6F5"), ft.Text(text, size=12, color="#F1F5FB")],
                               spacing=4, tight=True), bgcolor="#33FFFFFF", border_radius=20,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=4))


def way(icon, tone, title, sub, on_click):
    return ft.Container(ft.Column([T.icon_tile(icon, tone, 44), ft.Text(title, size=15, weight=ft.FontWeight.W_700),
                                   T.muted(sub, 12)], spacing=6), padding=16, bgcolor=T.CARD, border_radius=16,
                        border=ft.Border.all(1, T.LINE), expand=True, ink=True, on_click=on_click)


def tip(title, text):
    return ft.Row([ft.Icon(I.CHECK_CIRCLE_OUTLINE, size=18, color=T.ACCENT),
                   ft.Text(title, size=13, weight=ft.FontWeight.W_700, width=110), ft.Text(text, size=13, expand=True)],
                  vertical_alignment=ft.CrossAxisAlignment.START)
