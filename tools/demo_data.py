r"""開發用：在開發資料庫（data/）建立 admin/admin123、講師 teacher/teach1，並用內建範本產生幾份示範成品。
用法：python tools/demo_data.py [--reset]"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from nb import artifacts as A  # noqa: E402
from nb.biz import Biz  # noqa: E402
from nb.database import DB  # noqa: E402
from nb.dbserver import LocalDatabaseServer  # noqa: E402
from nb.seed import ROLES  # noqa: E402
from nb.settings import Settings  # noqa: E402

st = Settings.load()
srv = LocalDatabaseServer(st)
srv.start()
try:
    db = DB(st)
    if "--reset" in sys.argv:
        c = db.connect(use_db=False)
        with c.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS `%s`" % st.database)
        c.close()
    db.prepare()
    st.save()
    b = Biz(db)
    if not b.has_users():
        b.create_first_admin("admin", "系統管理員", "admin123")
    b.login("admin", "admin123")
    b.save_company(name="資料助秘教育訓練中心")
    if not db.value("SELECT 1 FROM sys_user WHERE uid='teacher'"):
        b.save_user("teacher", "示範講師", "講師", False, True, ROLES["講師"], pw="teach1", is_new=True)
    if not db.value("SELECT COUNT(*) FROM nb_job"):
        pid = b.default_project_id()
        topics = b.topics(pid)
        for k, t in zip(A.KIND_ORDER, topics):
            br = b.make_brief(pid, t["id"], presenter="WA001 示範病房助理甲", instructor="RN001 示範護理師甲")
            b.generate(k, br, engine="TEMPLATE", project_id=pid, topic_id=t["id"])
    print("ok", b.stats())
finally:
    db.close()
    srv.stop()
