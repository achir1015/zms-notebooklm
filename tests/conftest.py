import os
os.environ.setdefault("NB_MCP_MOCK", "1")
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("NB_NO_VOICE", "1")
from nb.database import DB  # noqa: E402
from nb.dbserver import LocalDatabaseServer  # noqa: E402
from nb.settings import Settings, find_mariadb  # noqa: E402

TEST_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_db")


@pytest.fixture(scope="session")
def server():
    os.environ["NB_DATA_DIR"] = TEST_ROOT
    st = Settings(port=3528, password="test-pw-123", database="nb_test", mariadb_bin=find_mariadb(),
                  datadir=os.path.join(TEST_ROOT, "mariadb"))
    srv = LocalDatabaseServer(st)
    srv.start()
    yield st
    srv.stop()


@pytest.fixture()
def db(server):
    d = DB(server)
    c = d.connect(use_db=False)
    with c.cursor() as cur:
        cur.execute("DROP DATABASE IF EXISTS nb_test")
    c.close()
    d.prepare()
    yield d
    d.close()


@pytest.fixture()
def biz(db):
    from nb.biz import Biz
    b = Biz(db)
    b.create_first_admin("admin", "管理員", "admin123")
    b.login("admin", "admin123")
    return b
