"""線上版引擎（docs/app/engine.js）與 Python 版（nb/artifacts.py）輸出一致：內建範本、指令、解析回答、純文字編輯格式。"""
import json
import os

import subprocess

import pytest

from nb import artifacts as A
from nb.mcp import find_node
from nb.mockdata import mock_answer
from nb.seed import SAMPLE_PROJECT

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(HERE, "docs", "app", "engine.js")

CASES = [
    dict(presenter="WA001 示範甲", instructor="RN001 示範乙", slide_count=12, notes="著重氣切病人", source_pages="10-12"),
    dict(slide_count=10, level="mid", lang="zh-en", term_langs=["越南"], quiz_count=6),
    dict(slide_count=14, qa_count=3, subtitle="自訂次標題", audience="新進照服員"),
]

JS = r"""
import { readFileSync } from "fs";
import * as E from "./engine.js";
const inp = JSON.parse(readFileSync(0, "utf8")), out = [];
for (const c of inp) {
  const b = new E.Brief(c.project, c.topic, c.kw), r = {};
  for (const k of E.KIND_ORDER) {
    const t = E.fromTemplate(k, b);
    r[k] = { tpl: t, prompt: E.buildPrompt(k, b), norm: E.normalize(k, E.extractJson(c.mock[k]), b),
             text: k === "SLIDES" ? E.outlineText(t) : E.toText(k, t), sum: E.summaryOf(k, t) };
    if (k !== "SLIDES") r[k].back = E.fromText(k, E.toText(k, t), t);
  }
  out.push(r);
}
process.stdout.write(JSON.stringify(out));
"""


def py_side(project, topic, kw, mock):
    b = A.Brief(project, topic, **kw)
    r = {}
    for k in A.KIND_ORDER:
        t = A.from_template(k, b)
        r[k] = dict(tpl=t, prompt=A.build_prompt(k, b), norm=A.normalize(k, A.extract_json(mock[k]), b),
                    text=A.outline_text(t) if k == "SLIDES" else A.to_text(k, t), sum=A.summary_of(k, t))
        if k != "SLIDES":
            r[k]["back"] = A.from_text(k, A.to_text(k, t), t)
    return r


@pytest.mark.skipif(not find_node(), reason="沒有 Node.js")
def test_engine_parity():
    with open(os.path.join(HERE, "nb", "samples", "ward_topics.json"), encoding="utf-8") as f:
        topics = json.load(f)
    proj = {k: v for k, v in dict(SAMPLE_PROJECT, term_langs=json.loads(SAMPLE_PROJECT["term_langs"])).items()
            if k in A.DEFAULT_PROJECT}
    inputs, expect = [], []
    for i, t in enumerate(topics + [{"name": "自訂主題測試"}]):
        kw = CASES[i % len(CASES)]
        tmp = A.Brief(proj, t, **kw)
        mock = {k: mock_answer(A.build_prompt(k, tmp)) for k in A.KIND_ORDER}
        inputs.append(dict(project=proj, topic=t, kw=kw, mock=mock))
        expect.append(py_side(proj, t, kw, mock))
    tmpjs = os.path.join(os.path.dirname(ENGINE), "_parity.mjs")
    with open(tmpjs, "w", encoding="utf-8") as f:
        f.write(JS)
    try:
        r = subprocess.run([find_node(), tmpjs], input=json.dumps(inputs, ensure_ascii=False), capture_output=True,
                           text=True, encoding="utf-8", cwd=os.path.dirname(ENGINE), timeout=120)
    finally:
        os.remove(tmpjs)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert len(got) == len(expect) == 10
    for i, (g, e) in enumerate(zip(got, expect)):
        for k in A.KIND_ORDER:
            for part in e[k]:
                assert g[k][part] == json.loads(json.dumps(e[k][part], ensure_ascii=False)), (i, k, part)

