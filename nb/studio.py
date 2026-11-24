"""服務層：筆記本、專案範本、主題庫、人員、年度主題表、成品，以及「產生」流程。

產生流程（比喻：點餐 → 下廚 → 擺盤）：
  1. 點餐：畫面組好 Brief（需求單：專案、主題、人員、對象、張數、風格…）
  2. 下廚：engine=NOTEBOOKLM 時把指令交給 NotebookLM（透過 MCP），拿回依來源寫成的 JSON；
           engine=TEMPLATE 時直接用主題庫範本
  3. 擺盤：整理成固定格式存進 nb_job，畫面可以逐項修改，再匯出 PowerPoint／Word／圖片／網頁
"""
import json
import threading
import time

from . import artifacts as A
from .core import BizError
from .mcp import McpError, make_client, normalize_url

_client = None
_client_lock = threading.Lock()


def mcp():
    """整個程式共用一條 NotebookLM 連線（伺服器啟動要幾秒，開一次就好）。"""
    global _client
    with _client_lock:
        if _client is None:
            _client = make_client()
        return _client


def shutdown_mcp():
    global _client
    with _client_lock:
        c, _client = _client, None
    if c:
        c.stop()


def _j(v, default):
    if v in (None, ""):
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except ValueError:
        return default


class StudioMixin:
    # ================================================================ NotebookLM 連線
    def nlm_status(self):
        self.need("NOTE", 1)
        c = mcp()
        h = c.health()
        return dict(authenticated=bool(h.get("authenticated")), version=c.server_info.get("version", ""),
                    sessions=h.get("active_sessions", 0), raw=h)

    def nlm_login(self, switch=False):
        """開啟看得見的 Chrome，讓使用者自己登入 Google（最多 10 分鐘）。會一直等到登入完成或取消。"""
        self.need("NOTE")
        self.log("nlm_login", "re_auth" if switch else "setup_auth")
        c = mcp()
        return c.call("re_auth" if switch else "setup_auth", {"show_browser": True}, timeout=700)

    def nlm_account_notebooks(self):
        self.need("NOTE", 1)
        items = mcp().account_notebooks()
        have = {r["uuid"] for r in self.db.rows("SELECT uuid FROM nb_notebook")}
        out = []
        for it in items:
            url, uid = normalize_url(it.get("url"))
            if url:
                out.append(dict(title=it.get("title") or "（未命名）", url=url, uuid=uid, added=uid in have))
        return out

    def nlm_ask(self, notebook_id, question, progress=None):
        self.need("NOTE", 1)
        nb = self.notebook(notebook_id)
        r = mcp().ask(nb["url"], question, progress=progress)
        self._touch_notebook(nb["id"])
        self.log("nlm_ask", nb["title"], question[:300])
        return r

    def nlm_add_source(self, notebook_id, kind, content, title=""):
        self.need("NOTE")
        nb = self.notebook(notebook_id)
        if kind not in ("text", "url") or not (content or "").strip():
            raise BizError("請貼上文字或網址")
        r = mcp().add_source(nb["url"], kind, content.strip(), title)
        self.log("nlm_add_source", nb["title"], "%s %s" % (kind, (title or content)[:120]))
        return r

    # ================================================================ 筆記本
    def notebooks(self):
        return self.db.rows("SELECT * FROM nb_notebook ORDER BY is_default DESC, IFNULL(last_used, created_at) DESC")

    def notebook(self, nid):
        r = self.db.row("SELECT * FROM nb_notebook WHERE id=%s", (nid,))
        if not r:
            raise BizError("找不到這本筆記本")
        return r

    def save_notebook(self, nid, url, title, description="", tags="", is_default=False):
        self.need("NOTE")
        url, uid = normalize_url(url)
        if not url:
            raise BizError("網址格式不對，應該像 https://notebooklm.google.com/notebook/xxxxxxxx-xxxx-…")
        if not (title or "").strip():
            raise BizError("請輸入筆記本名稱")
        dup = self.db.value("SELECT id FROM nb_notebook WHERE uuid=%s", (uid,))
        if dup and int(dup) != int(nid or 0):
            raise BizError("這本筆記本已經在清單裡了")
        if is_default:
            self.db.exec("UPDATE nb_notebook SET is_default=0")
        if nid:
            self.db.exec("UPDATE nb_notebook SET uuid=%s, url=%s, title=%s, description=%s, tags=%s, is_default=%s "
                         "WHERE id=%s", (uid, url, title.strip(), description, tags, int(bool(is_default)), nid))
        else:
            self.db.exec("INSERT INTO nb_notebook (uuid, url, title, description, tags, is_default, owner) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                         (uid, url, title.strip(), description, tags, int(bool(is_default)), self.uid))
            nid = self.db.value("SELECT id FROM nb_notebook WHERE uuid=%s", (uid,))
        self.log("notebook_save", title, url)
        return nid

    def delete_notebook(self, nid):
        self.need("NOTE")
        nb = self.notebook(nid)
        self.db.exec("UPDATE nb_project SET notebook_id=NULL WHERE notebook_id=%s", (nid,))
        self.db.exec("DELETE FROM nb_notebook WHERE id=%s", (nid,))
        self.log("notebook_delete", nb["title"], nb["url"])

    def _touch_notebook(self, nid):
        self.db.exec("UPDATE nb_notebook SET use_count=use_count+1, last_used=NOW() WHERE id=%s", (nid,))

    # ================================================================ 專案範本
    def projects(self, active_only=True):
        return self.db.rows("SELECT * FROM nb_project%s ORDER BY is_sample DESC, name" %
                            (" WHERE active=1" if active_only else ""))

    def project(self, pid):
        r = self.db.row("SELECT * FROM nb_project WHERE id=%s", (pid,))
        if not r:
            raise BizError("找不到這個專案")
        r["term_langs"] = _j(r.get("term_langs"), [])
        return r

    def default_project_id(self):
        pid = self.company().get("default_project")
        if pid and self.db.value("SELECT 1 FROM nb_project WHERE id=%s AND active=1", (pid,)):
            return pid
        return self.db.value("SELECT id FROM nb_project WHERE active=1 ORDER BY is_sample DESC, id LIMIT 1")

    PROJECT_FIELDS = ("name", "org", "unit", "unit_full", "cover_title_tpl", "cover_subtitle", "byline_tpl",
                      "presenter_role", "instructor_role", "role_text", "background_text", "purpose_text",
                      "audience_text", "term_langs", "font_title", "font_sub", "font_small", "min_slides", "qa_count",
                      "style", "extra_rules", "spec_md", "notebook_id", "active")

    def save_project(self, pid, **kw):
        self.need("PROJ")
        vals = {k: kw[k] for k in self.PROJECT_FIELDS if k in kw}
        if "name" in vals and not (vals["name"] or "").strip():
            raise BizError("請輸入專案名稱")
        if isinstance(vals.get("term_langs"), list):
            vals["term_langs"] = json.dumps(vals["term_langs"], ensure_ascii=False)
        for k in ("font_title", "font_sub", "font_small", "min_slides", "qa_count"):
            if k in vals:
                try:
                    vals[k] = int(vals[k])
                except (TypeError, ValueError):
                    raise BizError("字級、張數、題數要填數字")
        if pid:
            if vals:
                self.db.exec("UPDATE nb_project SET %s WHERE id=%%s" % ", ".join("`%s`=%%s" % k for k in vals),
                             tuple(vals.values()) + (pid,))
        else:
            vals.setdefault("created_by", self.uid)
            self.db.exec("INSERT INTO nb_project (%s) VALUES (%s)" % (", ".join("`%s`" % k for k in vals),
                                                                       ", ".join(["%s"] * len(vals))),
                         tuple(vals.values()))
            pid = self.db.value("SELECT MAX(id) FROM nb_project")
        self.log("project_save", pid, json.dumps({k: v for k, v in vals.items() if k != "spec_md"}, ensure_ascii=False,
                                                 default=str)[:900])
        return pid

    def copy_project(self, pid, name):
        """以現有專案為範本複製一份（含主題庫，不含人員），稍做修改就能變成其他專案。"""
        self.need("PROJ")
        p = self.project(pid)
        vals = {k: p[k] for k in self.PROJECT_FIELDS if k in p}
        vals["name"] = name or (p["name"] + "（複製）")
        new = self.save_project(None, **vals)
        for t in self.topics(pid, active_only=False):
            self.db.exec("INSERT INTO nb_topic (project_id, code, month, name, source_hint, data, sort, active) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                         (new, t["code"], t["month"], t["name"], t["source_hint"], t["data"], t["sort"], t["active"]))
        return new

    def delete_project(self, pid):
        self.need("PROJ")
        if self.db.value("SELECT 1 FROM nb_job WHERE project_id=%s LIMIT 1", (pid,)):
            raise BizError("這個專案已有成品，請改成「停用」")
        for t in ("nb_topic", "nb_plan"):
            self.db.exec("DELETE FROM %s WHERE project_id=%%s" % t, (pid,))
        self.db.exec("DELETE FROM nb_person WHERE project_id=%s", (pid,))
        self.db.exec("DELETE FROM nb_project WHERE id=%s", (pid,))
        self.log("project_delete", pid)

    # ================================================================ 主題庫
    def topics(self, pid, active_only=True):
        return self.db.rows("SELECT * FROM nb_topic WHERE project_id=%%s%s ORDER BY IFNULL(month, 99), sort, id"
                            % (" AND active=1" if active_only else ""), (pid,))

    def topic(self, tid):
        r = self.db.row("SELECT * FROM nb_topic WHERE id=%s", (tid,))
        if not r:
            raise BizError("找不到這個主題")
        d = _j(r["data"], {})
        d.update(name=r["name"], sourceHint=r["source_hint"], month=r["month"], id=r["code"])
        r["parsed"] = d
        return r

    def save_topic(self, tid, pid, name, month=None, source_hint="", data=None, active=True):
        self.need("PROJ")
        if not (name or "").strip():
            raise BizError("請輸入主題名稱")
        month = int(month) if month not in (None, "", 0, "0") else None
        payload = json.dumps(data or {}, ensure_ascii=False)
        if tid:
            self.db.exec("UPDATE nb_topic SET name=%s, month=%s, source_hint=%s, data=%s, active=%s WHERE id=%s",
                         (name.strip(), month, source_hint, payload, int(bool(active)), tid))
        else:
            self.db.exec("INSERT INTO nb_topic (project_id, name, month, source_hint, data, sort) "
                         "VALUES (%s, %s, %s, %s, %s, 999)", (pid, name.strip(), month, source_hint, payload))
            tid = self.db.value("SELECT MAX(id) FROM nb_topic")
        self.log("topic_save", name)
        return tid

    def delete_topic(self, tid):
        self.need("PROJ")
        self.db.exec("UPDATE nb_plan SET topic_id=NULL WHERE topic_id=%s", (tid,))
        self.db.exec("DELETE FROM nb_topic WHERE id=%s", (tid,))
        self.log("topic_delete", tid)

    # ================================================================ 人員
    def people(self, pid=None, kind=None, active_only=True):
        where, args = [], []
        if pid is not None:
            where.append("project_id IN (0, %s)")
            args.append(pid)
        if kind:
            where.append("kind=%s")
            args.append(kind)
        if active_only:
            where.append("active=1")
        return self.db.rows("SELECT * FROM nb_person%s ORDER BY kind DESC, emp_no, name" %
                            (" WHERE " + " AND ".join(where) if where else ""), tuple(args))

    def save_person(self, rid, pid, kind, emp_no, name, title="", note="", active=True):
        self.need("PEOPLE")
        if not (name or "").strip():
            raise BizError("請輸入姓名")
        if kind not in ("PRESENTER", "INSTRUCTOR"):
            raise BizError("身分只能是簡報人或指導員")
        args = (pid or 0, kind, (emp_no or "").strip(), name.strip(), title or "", note or "", int(bool(active)))
        if rid:
            self.db.exec("UPDATE nb_person SET project_id=%s, kind=%s, emp_no=%s, name=%s, title=%s, note=%s, active=%s "
                         "WHERE id=%s", args + (rid,))
        else:
            self.db.exec("INSERT INTO nb_person (project_id, kind, emp_no, name, title, note, active) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s)", args)
        self.log("person_save", name)

    def import_people(self, pid, text):
        """貼上名單（每行：身分,員編,姓名,職稱；身分寫「簡報人」或「指導員」），同員編會更新。"""
        self.need("PEOPLE")
        n = 0
        for line in (text or "").splitlines():
            parts = [x.strip() for x in line.replace("\t", ",").replace("，", ",").split(",")]
            if len(parts) < 3 or not parts[2]:
                continue
            kind = "INSTRUCTOR" if parts[0] in ("指導員", "護理師", "INSTRUCTOR", "指導") else "PRESENTER"
            rid = self.db.value("SELECT id FROM nb_person WHERE project_id=%s AND emp_no=%s AND emp_no<>''",
                                (pid, parts[1]))
            self.save_person(rid, pid, kind, parts[1], parts[2], parts[3] if len(parts) > 3 else "")
            n += 1
        return n

    def delete_person(self, rid):
        self.need("PEOPLE")
        self.db.exec("DELETE FROM nb_person WHERE id=%s", (rid,))
        self.log("person_delete", rid)

    @staticmethod
    def person_text(p):
        return ("%s %s" % (p.get("emp_no") or "", p["name"])).strip() if p else ""

    # ================================================================ 年度主題表
    def plan(self, pid, roc_year):
        rows = {r["month"]: r for r in self.db.rows("SELECT * FROM nb_plan WHERE project_id=%s AND roc_year=%s",
                                                    (pid, roc_year))}
        return [rows.get(m) or dict(project_id=pid, roc_year=roc_year, month=m, topic_id=None, custom_topic="",
                                    presenter_id=None, instructor_id=None, class_date=None, job_id=None)
                for m in range(1, 13)]

    def save_plan(self, pid, roc_year, month, topic_id=None, custom_topic="", presenter_id=None, instructor_id=None,
                  class_date=None):
        self.need("PROJ")
        self.db.exec("REPLACE INTO nb_plan (project_id, roc_year, month, topic_id, custom_topic, presenter_id, "
                     "instructor_id, class_date, job_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, "
                     "(SELECT job_id FROM (SELECT job_id FROM nb_plan WHERE project_id=%s AND roc_year=%s AND month=%s) x))",
                     (pid, roc_year, month, topic_id or None, custom_topic or "", presenter_id or None,
                      instructor_id or None, class_date or None, pid, roc_year, month))

    def apply_sample_plan(self, pid, roc_year):
        """依主題庫的建議月份，把空白的月份填上主題。"""
        self.need("PROJ")
        n = 0
        for row in self.plan(pid, roc_year):
            if row.get("topic_id") or row.get("custom_topic"):
                continue
            tid = self.db.value("SELECT id FROM nb_topic WHERE project_id=%s AND month=%s AND active=1 LIMIT 1",
                                (pid, row["month"]))
            if tid:
                self.save_plan(pid, roc_year, row["month"], tid, "", row.get("presenter_id"), row.get("instructor_id"),
                               row.get("class_date"))
                n += 1
        return n

    # ================================================================ 需求單
    def make_brief(self, project_id, topic_id=None, topic_name="", **kw):
        p = self.project(project_id) if project_id else {}
        t = self.topic(topic_id)["parsed"] if topic_id else {}
        proj = {k: p.get(k) for k in A.DEFAULT_PROJECT if p.get(k) not in (None, "")}
        return A.Brief(proj, t, topic_name=topic_name or t.get("name", ""), **kw)

    # ================================================================ 產生
    def generate(self, kind, brief, engine="NOTEBOOKLM", notebook_id=None, project_id=None, topic_id=None,
                 style="pastel", progress=None, title=""):
        """產生一份成品並存檔，回傳 job id。NotebookLM 模式會等到回答完成（通常 30 秒～3 分鐘）。"""
        self.need("GEN")
        if kind not in A.KINDS:
            raise BizError("不認得的產出類型")
        t0 = time.time()
        prompt, answer, sources = "", "", []
        if engine == "NOTEBOOKLM":
            if not notebook_id:
                raise BizError("請先選一本 NotebookLM 筆記本")
            nb = self.notebook(notebook_id)
            prompt = A.build_prompt(kind, brief)
            content = None
            try:
                r = mcp().ask(nb["url"], prompt, progress=progress)
                answer = r.get("answer", "") if isinstance(r, dict) else str(r)
                sources = r.get("sources", []) if isinstance(r, dict) else []
                try:
                    content = A.normalize(kind, A.extract_json(answer), brief)
                except ValueError:
                    # 第一次沒照格式回答：每次提問都是新分頁，所以重送完整指令並強調只要 JSON
                    if progress:
                        progress("回答格式不對，請 NotebookLM 重新整理成 JSON…", None, None)
                    r2 = mcp().ask(nb["url"], prompt + "\n\n【重要】上一次的回答不是 JSON。這次只能回覆一段 JSON，"
                                   "第一個字必須是 {，最後一個字必須是 }，不要任何說明文字。", progress=progress)
                    answer += "\n\n----（重新整理）----\n" + r2.get("answer", "")
                    content = A.normalize(kind, A.extract_json(r2.get("answer", "")), brief)
            except McpError as e:
                raise BizError(str(e))
            except ValueError:
                raise BizError("NotebookLM 沒有照格式回答，請再試一次，或到「NotebookLM 連線」直接提問看看原始回答。")
            self._touch_notebook(nb["id"])
            if kind == "SLIDES" and not content["slides"][1:]:
                raise BizError("NotebookLM 沒有產生投影片內容，請確認筆記本裡有相關來源。")
        else:
            content = A.from_template(kind, brief)
        title = title or "%s｜%s" % (brief.topic_name, A.KINDS[kind][0])
        self.db.exec("INSERT INTO nb_job (kind, title, project_id, topic_id, topic_name, notebook_id, engine, style, brief, "
                     "prompt, answer, sources, content, summary, seconds, owner) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, "
                     "%s, %s, %s, %s, %s, %s, %s, %s)",
                     (kind, title[:200], project_id, topic_id, brief.topic_name[:120], notebook_id, engine, style,
                      json.dumps(brief.to_json(), ensure_ascii=False), prompt, answer,
                      json.dumps(sources, ensure_ascii=False), json.dumps(content, ensure_ascii=False),
                      A.summary_of(kind, content), int(time.time() - t0), self.uid))
        jid = self.db.value("SELECT MAX(id) FROM nb_job WHERE owner=%s", (self.uid,))
        self.log("generate", jid, "%s %s %s" % (kind, engine, title))
        return jid

    # ================================================================ 成品
    def jobs(self, kind="", q="", mine_only=False, limit=300):
        self.need("GEN", 1)
        where, args = [], []
        if kind:
            where.append("j.kind=%s")
            args.append(kind)
        if q:
            where.append("(j.title LIKE %s OR j.topic_name LIKE %s)")
            args += ["%" + q + "%"] * 2
        if mine_only or not self.can("ALL", 1):
            where.append("j.owner=%s")
            args.append(self.uid)
        sql = ("SELECT j.id, j.kind, j.title, j.topic_name, j.engine, j.style, j.summary, j.seconds, j.owner, "
               "j.created_at, j.updated_at, n.title AS notebook, p.name AS project FROM nb_job j "
               "LEFT JOIN nb_notebook n ON n.id=j.notebook_id LEFT JOIN nb_project p ON p.id=j.project_id%s "
               "ORDER BY j.updated_at DESC LIMIT %%s" % (" WHERE " + " AND ".join(where) if where else ""))
        return self.db.rows(sql, tuple(args) + (limit,))

    def job(self, jid):
        r = self.db.row("SELECT * FROM nb_job WHERE id=%s", (jid,))
        if not r:
            raise BizError("找不到這份成品")
        if r["owner"] != self.uid and not self.can("ALL", 1):
            raise BizError("這是別人的成品")
        r["content"] = _j(r["content"], {})
        r["brief"] = _j(r["brief"], {})
        r["sources"] = _j(r["sources"], [])
        return r

    def save_job_content(self, jid, content, title=None, style=None):
        r = self.job(jid)
        if r["owner"] != self.uid:
            self.need("ALL")
        else:
            self.need("GEN")
        self.db.exec("UPDATE nb_job SET content=%s, summary=%s, title=%s, style=%s WHERE id=%s",
                     (json.dumps(content, ensure_ascii=False), A.summary_of(r["kind"], content),
                      (title or r["title"])[:200], style or r["style"], jid))
        self.log("job_edit", jid, r["title"])

    def delete_job(self, jid):
        r = self.job(jid)
        if r["owner"] != self.uid:
            self.need("ALL")
        else:
            self.need("GEN")
        self.db.exec("UPDATE nb_plan SET job_id=NULL WHERE job_id=%s", (jid,))
        self.db.exec("DELETE FROM nb_job WHERE id=%s", (jid,))
        self.log("job_delete", jid, r["title"])

    def link_plan_job(self, pid, roc_year, month, jid):
        self.db.exec("UPDATE nb_plan SET job_id=%s WHERE project_id=%s AND roc_year=%s AND month=%s",
                     (jid, pid, roc_year, month))

    def stats(self):
        mine = "" if self.can("ALL", 1) else " WHERE owner=%s"
        args = () if not mine else (self.uid,)
        by = {r["kind"]: r["n"] for r in self.db.rows("SELECT kind, COUNT(*) n FROM nb_job%s GROUP BY kind" % mine, args)}
        return dict(by_kind=by, total=sum(by.values()),
                    notebooks=self.db.value("SELECT COUNT(*) FROM nb_notebook"),
                    projects=self.db.value("SELECT COUNT(*) FROM nb_project WHERE active=1"),
                    nlm=self.db.value("SELECT COUNT(*) FROM nb_job WHERE engine='NOTEBOOKLM'%s" %
                                      (" AND owner=%s" if mine else ""), args))
