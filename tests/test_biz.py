"""資料庫業務：內定範例、產生（範本與 NotebookLM 模擬）、權限、專案複製、年度主題表。"""
import json

import pytest

from nb import artifacts as A
from nb.core import BizError


def test_sample_seeded(biz):
    p = biz.project(biz.default_project_id())
    assert p["is_sample"] and p["name"] == "病房助理技術教育外傭實務訓練"
    assert "CLAUDE.md" in p["spec_md"]
    assert len(biz.topics(p["id"])) == 9
    nb = biz.notebook(p["notebook_id"])
    assert nb["uuid"] == "097207c0-8984-4a58-b041-30ed62c4c23b" and nb["is_default"]
    br = biz.make_brief(p["id"], biz.topics(p["id"])[0]["id"], presenter="WA001 示範甲", instructor="示範護理師")
    assert br.cover_title == "臺北市立聯合醫院忠孝院區 RCW 會陰沖洗教學護理實務"
    assert br.byline == "簡報人：病房助理員 WA001 示範甲 ｜ 護理指導員：護理師示範護理師"


def test_generate_all_kinds(biz):
    pid = biz.default_project_id()
    tid = biz.topics(pid)[0]["id"]
    nid = biz.project(pid)["notebook_id"]
    for engine in ("TEMPLATE", "NOTEBOOKLM"):
        for k in A.KIND_ORDER:
            jid = biz.generate(k, biz.make_brief(pid, tid, slide_count=12), engine=engine, notebook_id=nid,
                               project_id=pid, topic_id=tid)
            j = biz.job(jid)
            assert j["content"] and j["summary"]
            if k == "SLIDES":
                assert j["content"]["slides"][0]["kind"] == "cover"
                assert len(j["content"]["qa"]) == 5
            if engine == "NOTEBOOKLM":
                assert "JSON" in j["prompt"] and j["answer"]
    assert biz.stats()["total"] == 2 * len(A.KIND_ORDER)


def test_bundle_files(biz):
    from nb import render as R
    pid = biz.default_project_id()
    tid = biz.topics(pid)[3]["id"]
    for k in A.KIND_ORDER:
        c = A.from_template(k, biz.make_brief(pid, tid))
        files = R.export_bundle(k, c, "測試")
        assert files and all(len(d) > 100 for _, d in files)


def test_permissions(biz):
    biz.save_user("t1", "講師甲", "講師", False, True, None, pw="abc123", is_new=True)
    biz.logout()
    biz.login("t1", "abc123")
    with pytest.raises(BizError):
        biz.save_project(biz.default_project_id(), name="改名")
    with pytest.raises(BizError):
        biz.save_notebook(None, "https://notebook.google.com/notebook/11111111-2222-3333-4444-555555555555", "x")
    pid = biz.default_project_id()
    jid = biz.generate("QUIZ", biz.make_brief(pid, None, topic_name="拍背"), engine="TEMPLATE", project_id=pid)
    assert biz.job(jid)["owner"] == "t1"


def test_copy_project_and_plan(biz):
    pid = biz.default_project_id()
    new = biz.copy_project(pid, "居家照顧訓練")
    assert len(biz.topics(new)) == 9 and biz.project(new)["is_sample"] == 0
    assert biz.apply_sample_plan(new, 115) == 9
    rows = biz.plan(new, 115)
    assert rows[1]["topic_id"] and not rows[0]["topic_id"]


def test_notebook_url_rules(biz):
    from nb.mcp import normalize_url
    assert normalize_url("https://notebook.google.com/notebook/097207C0-8984-4a58-b041-30ed62c4c23b?x=1")[1] == \
        "097207c0-8984-4a58-b041-30ed62c4c23b"
    with pytest.raises(BizError):
        biz.save_notebook(None, "https://example.com/x", "壞網址")
    with pytest.raises(BizError):
        biz.save_notebook(None, "https://notebooklm.google.com/notebook/097207c0-8984-4a58-b041-30ed62c4c23b", "重複")


def test_extract_json_tolerant():
    t = '好的，以下是內容：\n```json\n{"slides":[{"title":"甲 [1]","points":["一","二",],}],}\n```\n希望有幫助'
    d = A.extract_json(t)
    assert d["slides"][0]["points"] == ["一", "二"]
    assert json.dumps(A.strip_cites(d), ensure_ascii=False).find("[1]") < 0
