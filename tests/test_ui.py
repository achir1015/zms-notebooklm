"""每個畫面都要能在沒有視窗的情況下建立（抓 Flet API 用錯、變數名稱衝突這類錯誤）。"""
import types

import pytest

from nb.ui import shell
from nb.ui import theme as T


class FakePage:
    web = False
    route = ""

    def run_task(self, *a, **k):
        pass

    def run_thread(self, *a, **k):
        pass

    def show_dialog(self, *a, **k):
        pass

    def update(self, *a, **k):
        pass


@pytest.fixture()
def ctx(biz):
    from nb.settings import Settings
    app = types.SimpleNamespace(page=FakePage(), books=biz, reports=biz, mobile=False, go=lambda *a, **k: None, st=Settings(), update_info=None,
                                find=lambda sid: True)
    c = T.Ctx(app)
    app.ctx = c
    return c


SCREENS = [it[0] for g in shell.menu() for it in g[3]]


@pytest.mark.parametrize("sid", SCREENS)
def test_screen_builds(ctx, sid):
    assert shell.build_screen(sid, ctx) is not None


def test_screen_args(ctx, biz):
    from nb import artifacts as A
    pid = biz.default_project_id()
    tid = biz.topics(pid)[0]["id"]
    for k in A.KIND_ORDER:
        br = biz.make_brief(pid, tid)
        jid = biz.generate(k, br, engine="TEMPLATE", project_id=pid, topic_id=tid)
        shell.build_screen("works", ctx, job=jid)
        shell.build_screen("studio", ctx, kind=k)
    shell.build_screen("studio", ctx, project=pid, month=2)
    shell.build_screen("projects", ctx, project=pid)
    shell.build_screen("plan", ctx, project=pid)
    for lesson in ("intro", "studio", "works"):
        shell.build_screen("help", ctx, lesson=lesson)


def test_menu_and_help_consistent():
    import flet as ft
    from nb.help_text import LESSONS, PAGES
    sids = set(SCREENS)
    for lesson in LESSONS:
        for icon, tone, text, sid in lesson["steps"]:
            assert sid in sids, sid
            assert getattr(ft.Icons, icon)
    assert set(PAGES) <= sids
