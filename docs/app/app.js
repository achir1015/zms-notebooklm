// 資料助秘NotebookLM MCP簡報 — 線上版主程式（畫面、路由、專案範本、成品庫 IndexedDB、語音教學）。
// 線上版沒有 MCP 伺服器：NotebookLM 走「複製指令 → 在 NotebookLM 貼上 → 把回答貼回來」三步；內建範本離線也能用。
import { DATA } from "./data.js";
import * as E from "./engine.js";
import * as R from "./render.js";

const $ = (s, el = document) => el.querySelector(s);
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const store = {
  get(k, d) { try { const v = localStorage.getItem("nb_" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("nb_" + k, JSON.stringify(v)); } catch (e) { /* 私密模式 */ } },
};
function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = err ? "err" : ""; t.style.display = "block";
  clearTimeout(t._h); t._h = setTimeout(() => { t.style.display = "none"; }, err ? 4500 : 2400);
}
const IOS = window.ZMSIOS, AND = window.ZMSAndroid;
async function download(name, blob) {
  if (IOS || AND) {
    const u8 = new Uint8Array(await blob.arrayBuffer());
    let b = ""; for (let i = 0; i < u8.length; i += 0x8000) b += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    try { if (IOS) await window.webkit.messageHandlers.zms.postMessage({ cmd: "save_file", args: [name, btoa(b)] }); else AND.saveFile(name, btoa(b)); }
    catch (e) { toast("存檔失敗：" + e, true); }
    return;
  }
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
}
async function copy(text, ok = "已複製到剪貼簿") {
  try { await navigator.clipboard.writeText(text); toast(ok); }
  catch (e) { const ta = h(`<textarea style="position:fixed;opacity:0"></textarea>`); ta.value = text; document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove(); toast(ok); }
}
const KIND_IC = { SLIDES: "🖥️", MINDMAP: "🧠", REPORT: "📄", QUIZ: "📝", INFOGRAPHIC: "📊", WEBPAGE: "🌐" };

// ====================================================================== 資料（這台裝置的瀏覽器）
const Data = {
  projects() {
    let ps = store.get("projects", null);
    if (!ps) {                                         // 第一次：放入內定範例
      const p = { ...DATA.sample.project, id: 1, is_sample: 1, notebook: DATA.sample.notebook.url };
      ps = [p]; store.set("projects", ps);
      store.set("topics_1", DATA.sample.topics);
      store.set("people_1", DATA.sample.people.map(([kind, no, name, title]) => ({ kind, no, name, title })));
    }
    return ps;
  },
  project(id) { return this.projects().find((p) => p.id === +id) || this.projects()[0]; },
  saveProject(p) { const ps = this.projects(), i = ps.findIndex((x) => x.id === p.id); if (i >= 0) ps[i] = p; else ps.push(p); store.set("projects", ps); },
  topics(pid) { return store.get("topics_" + pid, []); },
  saveTopics(pid, ts) { store.set("topics_" + pid, ts); },
  people(pid) { return store.get("people_" + pid, []); },
  notebooks() {
    let n = store.get("notebooks", null);
    if (!n) { n = [{ id: 1, title: DATA.sample.notebook.title, url: DATA.sample.notebook.url, desc: "內定範本：病房助理技術教育外傭實務訓練的照護文件" }]; store.set("notebooks", n); }
    return n;
  },
};
const DB = {
  db: null,
  async open() {
    if (this.db) return this.db;
    this.db = await new Promise((ok, no) => {
      const r = indexedDB.open("zms-notebooklm", 1);
      r.onupgradeneeded = () => r.result.createObjectStore("works", { keyPath: "id", autoIncrement: true });
      r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error);
    });
    return this.db;
  },
  async tx(mode, fn) { const db = await this.open(); return new Promise((ok, no) => { const t = db.transaction("works", mode), r = fn(t.objectStore("works")); t.oncomplete = () => ok(r && r.result); t.onerror = () => no(t.error); }); },
  all() { return this.tx("readonly", (s) => s.getAll()).then((x) => (x || []).sort((a, b) => b.updated - a.updated)); },
  get(id) { return this.tx("readonly", (s) => s.get(+id)); },
  put(d) { d.updated = Date.now(); return this.tx("readwrite", (s) => s.put(d)); },
  del(id) { return this.tx("readwrite", (s) => s.delete(+id)); },
};
const projForBrief = (p) => Object.fromEntries(Object.keys(DATA.defaultProject).filter((k) => p[k] !== undefined && p[k] !== "").map((k) => [k, p[k]]));

// ====================================================================== 畫面框架
const MENU = [
  ["總覽", [["home", "首頁", "🏠"]]],
  ["產生", [["studio", "產生工具", "✨"], ["works", "成品庫", "📦"]]],
  ["NotebookLM", [["notebooks", "筆記本", "🔗"]]],
  ["專案範本", [["projects", "專案範本與主題庫", "📁"]]],
  ["說明", [["help", "語音動態教學", "🔊"]]],
];
const TITLES = Object.fromEntries(MENU.flatMap(([, it]) => it.map(([k, t]) => [k, t])));
const S = {};
let current = "home";
function nav() { $("#nav").innerHTML = MENU.map(([g, it]) => `<div class="grp">${g}</div>` + it.map(([k, t, ic]) => `<a href="#${k}" class="${k === current ? "on" : ""}"><span class="ic">${ic}</span>${t}</a>`).join("")).join(""); }
function go(sid, arg) {
  if (!TITLES[sid]) sid = "home";
  stopVoice(); current = sid; nav(); $("#crumb").textContent = TITLES[sid]; $("#side").classList.remove("open");
  const v = $("#view"); v.innerHTML = "";
  Promise.resolve().then(() => (S[sid] || S.home)(v, arg)).catch((e) => { console.error(e); v.innerHTML = `<p class="muted">畫面載入失敗：${esc(e.message)}</p>`; });
}
addEventListener("hashchange", () => { const [s, a] = decodeURIComponent(location.hash.slice(1)).split(":"); go(s || "home", a); });

// ---------------------------------------------------------------- 首頁
const DESC = { SLIDES: "封面固定格式、10 張以上、Q&A，下載 PowerPoint 與 Word", MINDMAP: "左右展開，圖片、網頁、XMind", REPORT: "摘要、小節、結論，Word",
  QUIZ: "作答卷、解答、線上作答", INFOGRAPHIC: "一頁式直式海報", WEBPAGE: "章節、翻牌卡、計分小測驗" };
S.home = async (v) => {
  v.append(h(`<div class="col">
    <div class="hero"><div style="flex:1"><h2>筆記本裡的文件，變成能上課的教材</h2>
      <p>選一本 NotebookLM 筆記本，產生簡報、心智圖、報告、測驗、資訊圖表與互動式網頁。內容以你的來源為依據。</p>
      <div class="row"><a class="btn gold" href="#studio">開始做簡報</a><a class="btn outline" href="#help">🔊 語音教學</a></div></div><img src="icon.png" alt=""></div>
    <div class="ways">${E.KIND_ORDER.map((k) => `<div class="card way" data-k="${k}" style="cursor:pointer"><div class="big" style="font-size:30px">${KIND_IC[k]}</div><b>${DATA.kinds[k][0]}</b><span class="muted">${DESC[k]}</span></div>`).join("")}</div>
    <div class="card"><div class="row"><h3 style="flex:1">最近的成品</h3><a class="btn ghost small" href="#works">成品庫 →</a></div><div id="recent" class="col" style="margin-top:10px"></div></div>
    <div class="card"><h3>線上版與電腦版</h3><p class="muted">線上版不用安裝，成品存在這台裝置的瀏覽器裡；NotebookLM 用「複製指令 → 貼上 → 貼回答案」三步完成。
      想要程式自動向 NotebookLM 提問、讀取帳號裡的筆記本、MariaDB 多人帳號與權限、年度主題表與人員名單，請下載
      <a href="https://github.com/${DATA.repo}/releases/latest" target="_blank">Windows／macOS 電腦版</a>。</p></div></div>`));
  v.querySelectorAll("[data-k]").forEach((c) => c.onclick = () => { location.hash = "studio:" + c.dataset.k; });
  const ws = (await DB.all()).slice(0, 6);
  $("#recent").innerHTML = ws.length ? ws.map(workItem).join("") : '<p class="muted">還沒有成品。按上面任一種產出開始，第一次可以先用內建範本試試看。</p>';
  $("#recent").querySelectorAll("[data-id]").forEach((c) => c.onclick = () => { location.hash = "works:" + c.dataset.id; });
};
const workItem = (w, on) => `<div class="wk ${on ? "on" : ""}" data-id="${w.id}"><div class="ic">${KIND_IC[w.kind]}</div><div style="flex:1;min-width:0"><b>${esc(w.title)}</b>
  <div class="muted">${DATA.kinds[w.kind][0]}・${w.engine === "NOTEBOOKLM" ? "NotebookLM" : "內建範本"}・${esc(w.summary)}</div><div class="muted">${new Date(w.updated).toLocaleString("zh-TW")}</div></div></div>`;

// ---------------------------------------------------------------- 產生工具
S.studio = (v, arg) => {
  const st = { kind: DATA.kinds[arg] ? arg : "SLIDES", pid: store.get("lastProject", 1), style: "pastel", engine: "NOTEBOOKLM" };
  v.append(h(`<div class="studio"><div class="col" id="left"></div><div class="side col" id="right"></div></div>`));
  const left = $("#left"), right = $("#right");
  const card = (no, title, sub, body) => `<div class="card stepc"><div class="no">${no}</div><div class="body"><div><h3>${title}</h3><div class="muted">${sub}</div></div>${body}</div></div>`;
  const render = () => {
    const ps = Data.projects(), p = Data.project(st.pid), ts = Data.topics(p.id), nbs = Data.notebooks(), ppl = Data.people(p.id);
    st.style = st.style || p.style || "pastel";
    left.innerHTML = `<div class="kinds">${E.KIND_ORDER.map((k) => `<button data-kind="${k}" class="${k === st.kind ? "on" : ""}">${KIND_IC[k]} ${DATA.kinds[k][0]}</button>`).join("")}</div>`
      + card(1, "主題", "選專案範本與主題；主題庫沒有就直接輸入", `<div class="fields">
          <label class="fld">專案範本<select id="pid">${ps.map((x) => `<option value="${x.id}" ${x.id === p.id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>
          <label class="fld">主題<select id="tid"><option value="">（自訂主題）</option>${ts.map((t, i) => `<option value="${i}">${t.month ? t.month + " 月｜" : ""}${esc(t.name)}</option>`).join("")}</select></label>
          <label class="fld" id="customBox">自訂主題名稱<input type="text" id="custom" placeholder="例：拍背與排痰"></label></div>`)
      + card(2, "人員", "簡報人與指導員（員編 姓名）", `<div class="fields">
          <label class="fld">${esc(p.presenter_role || "簡報人")}<input type="text" id="pres" list="pl1" placeholder="員編 姓名"></label>
          <label class="fld">${esc(p.instructor_role || "指導員")}<input type="text" id="inst" list="pl2" placeholder="員編 姓名"></label>
          <label class="fld">上課日期<input type="text" id="date" placeholder="115/12/15"></label></div>
          <datalist id="pl1">${ppl.filter((x) => x.kind === "PRESENTER").map((x) => `<option value="${esc(x.no + " " + x.name)}">`).join("")}</datalist>
          <datalist id="pl2">${ppl.filter((x) => x.kind === "INSTRUCTOR").map((x) => `<option value="${esc(x.no + " " + x.name)}">`).join("")}</datalist>`)
      + card(3, "學員", "對象、母語關鍵詞、語言程度", `<label class="fld">學員對象<input type="text" id="aud" value="${esc(p.audience_text)}"></label>
          <div class="row">${(p.term_langs || []).map(([lab, lang]) => `<label><input type="checkbox" class="tl" value="${esc(lab)}" checked> ${esc(lab)}（${esc(lang)}）</label>`).join("") || '<span class="muted">這個專案沒有母語關鍵詞欄</span>'}</div>
          <label class="fld">語言程度<select id="level">${Object.entries(DATA.levels).map(([k, t]) => `<option value="${k}">${t}</option>`).join("")}</select></label>`)
      + card(4, "依據文件", "NotebookLM 以筆記本裡的來源為唯一依據；寫明依據哪一份、哪幾頁", `<div class="fields">
          <label class="fld">依據文件名稱<input type="text" id="src"></label><label class="fld">頁數<input type="text" id="pages" placeholder="282-290"></label></div>
          <label class="fld">本次文案重點與特別要求<textarea id="notes" rows="2" placeholder="同一個主題、不同文案，產生的內容就不同"></textarea></label>`)
      + card(5, "設定", "張數、題數、語言、封面次標題、視覺風格", `<div class="fields">
          <label class="fld">簡報張數<input type="number" id="cnt" value="12" min="${p.min_slides || 10}"></label>
          <label class="fld">Q&A 題數<input type="number" id="qa" value="${p.qa_count || 5}"></label>
          <label class="fld">測驗題數<input type="number" id="qn" value="10"></label>
          <label class="fld">語言<select id="lang">${DATA.langs.map((x) => `<option value="${x.id}">${x.name}</option>`).join("")}</select></label></div>
          <label class="fld">封面次標題<input type="text" id="sub" value="${esc(p.cover_subtitle || "")}"></label>
          <div class="styles">${DATA.styles.map((s) => `<div class="st ${s.id === st.style ? "on" : ""}" data-style="${s.id}">${s.colors.slice(0, 3).map((c) => `<span class="sw" style="background:${c}"></span>`).join("")}<b style="display:block;margin-top:4px">${s.name}</b><span class="muted">${s.desc}</span></div>`).join("")}</div>`)
      + card(6, "產生方式", "依 NotebookLM 筆記本，或用內建範本", `<div class="row">
          <label><input type="radio" name="eng" value="NOTEBOOKLM" ${st.engine === "NOTEBOOKLM" ? "checked" : ""}> 依 NotebookLM 筆記本（建議）</label>
          <label><input type="radio" name="eng" value="TEMPLATE" ${st.engine === "TEMPLATE" ? "checked" : ""}> 內建範本（離線）</label></div>
          <div id="nlm" class="col">
            <label class="fld">NotebookLM 筆記本<select id="nb">${nbs.map((n) => `<option value="${n.id}" ${n.url === p.notebook ? "selected" : ""}>${esc(n.title)}</option>`).join("")}</select></label>
            <div class="row"><b>①</b><button class="btn" id="cpPrompt">複製指令</button><b>②</b><button class="btn outline" id="openNb">開啟筆記本</button><span class="muted">在 NotebookLM 對話框貼上、送出，等它回答完</span></div>
            <div class="row" style="align-items:flex-start"><b>③</b><textarea id="answer" rows="5" style="flex:1" placeholder="把 NotebookLM 的整段回答（JSON）複製貼在這裡"></textarea></div></div>`)
      + card(7, "NotebookLM 官方 AI 插圖版（選用）", "想要 NotebookLM 畫的 3D 插圖版本：選需求、風格、佈局 → 複製 → 貼到 NotebookLM 右側 Studio 的簡報或資訊圖表", `<div class="fields">
          <label class="fld">需求類型<select id="vn">${DATA.visual.needs.map(([k, n]) => `<option value="${k}">${n}</option>`).join("")}</select></label>
          <label class="fld">視覺風格<select id="vs">${DATA.visual.styles.map(([k, n]) => `<option value="${k}" ${k === "clay3d" ? "selected" : ""}>${n}</option>`).join("")}</select></label>
          <label class="fld">佈局結構<select id="vl">${DATA.visual.layouts.map(([k, n]) => `<option value="${k}" ${k === "snake" ? "selected" : ""}>${n}</option>`).join("")}</select></label></div>
          <pre class="prompt" id="vtext"></pre><div class="row"><button class="btn outline" id="cpVisual">複製視覺指令</button><span class="muted">風格與佈局分類參考 Meiko 微課頻道</span></div>`);
    right.innerHTML = `<div class="card col"><h3>📋 需求摘要</h3><div class="sum" id="sum"></div>
      <button class="btn gold" id="gen" style="justify-content:center;padding:14px">✨ 產生</button>
      <button class="btn ghost small" id="showPrompt">看交給 NotebookLM 的指令</button><pre class="prompt" id="promptBox" style="display:none"></pre></div>`;
    bind();
  };
  const brief = () => {
    const p = Data.project(st.pid), ts = Data.topics(p.id), ti = $("#tid").value, t = ti === "" ? null : ts[+ti];
    return new E.Brief(projForBrief(p), t, { topic_name: t ? "" : $("#custom").value.trim(), presenter: $("#pres").value.trim(), instructor: $("#inst").value.trim(),
      date: $("#date").value.trim(), audience: $("#aud").value.trim(), term_langs: [...left.querySelectorAll(".tl:checked")].map((x) => x.value),
      level: $("#level").value, source_title: $("#src").value.trim(), source_pages: $("#pages").value.trim(), notes: $("#notes").value.trim(),
      slide_count: $("#cnt").value, qa_count: $("#qa").value, quiz_count: $("#qn").value, lang: $("#lang").value, style: st.style, subtitle: $("#sub").value.trim() });
  };
  const visual = (b) => {
    const [n, s, l] = [$("#vn").value, $("#vs").value, $("#vl").value], need = DATA.visual.needs.find((x) => x[0] === n), sty = DATA.visual.styles.find((x) => x[0] === s), lay = DATA.visual.layouts.find((x) => x[0] === l);
    const L = [`${DATA.visual.kindWord[st.kind] || "資訊圖表"}設計：「${b.topic_name}」。`];
    if (b.org_text) L.push(`機構名稱一律使用「${b.org_text}」。`);
    L.push(`需求類型：${need[1]}（${need[2]}）。`); if (l !== "auto") L.push(`佈局採「${lay[1]}」：${lay[2]}。`);
    L.push(`風格要求「${sty[1]}」：${sty[2]}。`, `對象：${b.audience}；語言程度：${{ basic: "基礎，用短句與常用字", mid: "日常會話", pro: "專業人員" }[b.level] || b.level}。`,
      `內容以筆記本中的來源為唯一依據${b.source_title ? `（${b.source_title}）` : ""}；全部使用台灣繁體中文。`);
    L.push(st.kind === "SLIDES" ? `簡報約 ${b.slide_count} 張；第一張封面：${b.cover_title}／${b.subtitle}／${b.byline}。最後一張是 Q&A ${b.qa_count} 題。` : "寬螢幕版面，專業又親切，每個重點搭配小圖示。");
    if (b.notes) L.push("本次重點：" + b.notes);
    return L.join("");
  };
  const refresh = () => {
    const b = brief(), nb = Data.notebooks().find((n) => n.id === +$("#nb").value);
    $("#customBox").style.display = $("#tid").value === "" ? "" : "none";
    $("#nlm").style.display = st.engine === "NOTEBOOKLM" ? "" : "none";
    const rows = [["類型", `${KIND_IC[st.kind]} ${DATA.kinds[st.kind][0]}（${st.engine === "NOTEBOOKLM" ? "NotebookLM" : "內建範本"}）`], ["主題", b.topic_name]];
    if (st.kind === "SLIDES") rows.push(["封面標題", b.cover_title], ["次標題", b.subtitle], ["小標題", b.byline], ["張數", `${b.slide_count} 張＋Q&A ${b.qa_count} 題`]);
    if (st.kind === "QUIZ") rows.push(["題數", b.quiz_count + " 題"]);
    rows.push(["對象", b.audience], ["依據", b.source_title + (b.source_pages ? `（${b.source_pages} 頁）` : "")], ["風格", DATA.styles.find((s) => s.id === st.style).name]);
    if (st.engine === "NOTEBOOKLM" && nb) rows.push(["筆記本", nb.title]);
    $("#sum").innerHTML = rows.map(([k, x]) => `<div><b>${k}</b><span>${esc(x || "—")}</span></div>`).join("");
    $("#vtext").textContent = visual(b);
    if ($("#promptBox").style.display !== "none") $("#promptBox").textContent = E.buildPrompt(st.kind, b);
  };
  const bind = () => {
    left.querySelectorAll("[data-kind]").forEach((b) => b.onclick = () => { st.kind = b.dataset.kind; left.querySelectorAll("[data-kind]").forEach((x) => x.classList.toggle("on", x === b)); refresh(); });
    left.querySelectorAll("[data-style]").forEach((b) => b.onclick = () => { st.style = b.dataset.style; left.querySelectorAll("[data-style]").forEach((x) => x.classList.toggle("on", x === b)); refresh(); });
    $("#pid").onchange = () => { st.pid = +$("#pid").value; store.set("lastProject", st.pid); render(); };
    $("#tid").onchange = () => { const t = Data.topics(st.pid)[+$("#tid").value]; $("#src").value = t ? t.sourceHint || "" : ""; refresh(); };
    left.querySelectorAll("input,select,textarea").forEach((x) => { if (!x.onchange) x.addEventListener("input", refresh); });
    left.querySelectorAll("input[name=eng]").forEach((x) => x.onchange = () => { st.engine = x.value; refresh(); });
    $("#cpPrompt").onclick = () => copy(E.buildPrompt(st.kind, brief()), "已複製指令：到 NotebookLM 對話框貼上並送出");
    $("#openNb").onclick = () => { const nb = Data.notebooks().find((n) => n.id === +$("#nb").value); if (nb) window.open(nb.url, "_blank"); };
    $("#cpVisual").onclick = () => copy($("#vtext").textContent, "已複製視覺指令：到 NotebookLM 的 Studio 貼上");
    $("#showPrompt").onclick = () => { const p = $("#promptBox"); p.style.display = p.style.display === "none" ? "" : "none"; refresh(); };
    $("#gen").onclick = generate;
    if (Data.topics(st.pid).length && $("#tid").value === "") { $("#tid").value = "0"; $("#src").value = Data.topics(st.pid)[0].sourceHint || ""; }
    refresh();
  };
  const generate = async () => {
    const b = brief();
    if (!b.topic_name || b.topic_name === "自訂主題") return toast("請選主題或輸入自訂主題名稱", true);
    let content, answer = "", prompt = "";
    if (st.engine === "NOTEBOOKLM") {
      answer = $("#answer").value.trim(); prompt = E.buildPrompt(st.kind, b);
      if (!answer) return toast("請先在 NotebookLM 提問，把回答貼到第 6 步的③", true);
      try { content = E.normalize(st.kind, E.extractJson(answer), b); }
      catch (e) { return toast("回答解析失敗：" + e.message + "。請確認整段回答都有複製到。", true); }
      if (st.kind === "SLIDES" && content.slides.length < 2) return toast("回答裡沒有投影片內容", true);
    } else content = E.fromTemplate(st.kind, b);
    const nb = Data.notebooks().find((n) => n.id === +$("#nb").value);
    const id = await DB.put({ kind: st.kind, title: `${b.topic_name}｜${DATA.kinds[st.kind][0]}`, engine: st.engine, style: st.style, brief: b.toJSON(),
      project: st.pid, topic: b.topic, prompt, answer, notebook: st.engine === "NOTEBOOKLM" && nb ? nb.title : "", content, summary: E.summaryOf(st.kind, content), created: Date.now() });
    toast("已產生，正在開啟成品"); location.hash = "works:" + id;
  };
  render();
};

// ---------------------------------------------------------------- 成品庫
S.works = async (v, arg) => {
  v.append(h(`<div class="works"><div class="card col"><div class="row"><select id="kf"><option value="">全部類型</option>${E.KIND_ORDER.map((k) => `<option value="${k}">${DATA.kinds[k][0]}</option>`).join("")}</select>
    <label class="btn outline small">匯入成品<input type="file" id="imp" accept=".json" hidden></label><button class="btn ghost small" id="exp">匯出全部</button></div><div id="wl"></div></div><div id="wd"></div></div>`));
  let all = await DB.all(), cur = null;
  const list = () => {
    const f = $("#kf").value, ws = all.filter((w) => !f || w.kind === f);
    $("#wl").innerHTML = ws.length ? ws.map((w) => workItem(w, cur && cur.id === w.id)).join("") : '<p class="muted">還沒有成品，到「產生工具」做第一份吧！</p>';
    $("#wl").querySelectorAll("[data-id]").forEach((c) => c.onclick = () => open(+c.dataset.id));
  };
  $("#kf").onchange = list;
  $("#exp").onclick = () => download("NotebookLM簡報成品.json", new Blob([JSON.stringify(all)], { type: "application/json" }));
  $("#imp").onchange = async (e) => { const f = e.target.files[0]; if (!f) return; const ws = JSON.parse(await f.text()); for (const w of ws) { delete w.id; await DB.put(w); } all = await DB.all(); list(); toast(`已匯入 ${ws.length} 份`); };
  const open = async (id) => {
    cur = all.find((w) => w.id === id); if (!cur) return; list();
    const w = cur, d = $("#wd");
    d.innerHTML = `<div class="card col"><div class="row"><span style="font-size:28px">${KIND_IC[w.kind]}</span><input type="text" id="wt" value="${esc(w.title)}" style="flex:1;font-weight:700">
      <select id="ws">${DATA.styles.map((s) => `<option value="${s.id}" ${s.id === w.style ? "selected" : ""}>${s.name}</option>`).join("")}</select>
      <button class="btn" id="save">💾 儲存</button><button class="btn danger small" id="del">刪除</button></div>
      <div class="muted">${DATA.kinds[w.kind][0]}・${w.engine === "NOTEBOOKLM" ? "依 NotebookLM 筆記本" + (w.notebook ? "「" + esc(w.notebook) + "」" : "") : "內建範本"}・${esc(w.summary)}</div>
      <div class="tabs"><button data-t="pv" class="on">👁 預覽</button><button data-t="ed">✏️ 修改</button><button data-t="ex">⬇ 匯出</button><button data-t="src">📄 來源與指令</button></div><div id="tab"></div></div>`;
    const tabs = { pv: preview, ed: editor, ex: exporter, src: source };
    d.querySelectorAll("[data-t]").forEach((b) => b.onclick = () => { d.querySelectorAll("[data-t]").forEach((x) => x.classList.toggle("on", x === b)); tabs[b.dataset.t](); });
    $("#ws").onchange = () => { w.style = $("#ws").value; preview(); d.querySelector("[data-t=pv]").click(); };
    $("#save").onclick = async () => { if (w._text) { try { w.content = E.fromText(w.kind, w._text.value, w.content); } catch (e) { return toast("格式有誤：" + e.message, true); } }
      w.title = $("#wt").value.trim() || w.title; w.summary = E.summaryOf(w.kind, w.content); delete w._text; await DB.put(w); all = await DB.all(); cur = all.find((x) => x.id === w.id); list(); toast("已儲存"); };
    $("#del").onclick = async () => { if (!confirm(`確定刪除「${w.title}」？`)) return; await DB.del(w.id); all = await DB.all(); cur = null; d.innerHTML = ""; list(); toast("已刪除"); };
    preview();
  };
  const preview = async () => {
    const w = cur, t = $("#tab"); t.innerHTML = '<p class="muted">正在畫預覽…</p>';
    const c = w.content;
    if (w.kind === "SLIDES") {
      const imgs = await R.slideImages(c, w.style, 0.6);
      t.innerHTML = imgs.map((u, i) => `<div class="slide"><img src="${u}" alt=""><div class="col" style="flex:1"><b>第 ${i + 1} 頁｜${esc(c.slides[i].label || "")}</b>
        <span class="muted">講者備註：${esc(c.slides[i].notes || "（無）")}</span>${c.slides[i].notes ? `<button class="btn ghost small" data-say="${i}">🔊 朗讀備註</button>` : ""}</div></div>`).join("")
        + ((c.qa || []).length ? `<div class="card"><h3>Q&A</h3><ol>${c.qa.map((x) => `<li><b>${esc(x.q)}</b><br>答：${esc(x.a)}</li>`).join("")}</ol></div>` : "");
      t.querySelectorAll("[data-say]").forEach((b) => b.onclick = () => say(c.slides[+b.dataset.say].notes));
    } else if (w.kind === "MINDMAP") { await document.fonts.ready; t.innerHTML = `<div class="prev"><img src="${R.mindmapCanvas(c).toDataURL()}"></div>`; }
    else if (w.kind === "INFOGRAPHIC") { t.innerHTML = `<div class="prev" style="max-width:600px"><img src="${R.infographicCanvas(c, w.style).toDataURL()}"></div>`; }
    else if (w.kind === "WEBPAGE") { t.innerHTML = ""; const f = h(`<iframe class="web"></iframe>`); t.append(f); f.srcdoc = await R.webpageHtml(c, w.style); }
    else if (w.kind === "REPORT") { t.innerHTML = ""; const f = h(`<iframe class="web"></iframe>`); t.append(f); f.srcdoc = R.reportHtml(c); }
    else if (w.kind === "QUIZ") { t.innerHTML = ""; const f = h(`<iframe class="web"></iframe>`); t.append(f); f.srcdoc = R.quizHtml(c); }
  };
  const editor = () => {
    const w = cur, t = $("#tab"), c = w.content;
    if (w.kind !== "SLIDES") {
      const hint = { MINDMAP: "第一行 # 是中心主題；每個分支一行「- 文字」，往下一層多空兩格。", REPORT: "# 標題、摘要：、## 小節、一般文字是段落、- 是條列、結論：、參考來源：（用；分隔）。",
        QUIZ: "每題「1.（單選）題目」，接 A.～D.、答案：B、解析：…；是非題寫（是非），答案 ○ 或 ✕。", INFOGRAPHIC: "# 標題、副標：、數字：值｜說明、## 區塊與 - 重點、提醒：、頁尾：",
        WEBPAGE: "# 標題、副標：、介紹：；## 章名、摘要：、- 重點、補充：；卡片：正面｜背面；問：／答：；題目：接選項（正確的前面用 *）、解析：；帶走：" }[w.kind];
      t.innerHTML = `<p class="muted">${hint}</p><textarea id="tx" rows="24" style="width:100%"></textarea><p class="muted">改完按上方「儲存」。</p>`;
      $("#tx").value = E.toText(w.kind, c); w._text = $("#tx");
      return;
    }
    w._text = null;
    const draw = () => {
      t.innerHTML = c.slides.map((s, i) => `<div class="ed"><div class="row"><b>第 ${i + 1} 頁</b><input type="text" data-i="${i}" data-k="label" value="${esc(s.label || "")}" style="width:200px">
        <span class="grow"></span>${i > 0 ? `<button class="btn ghost small" data-mv="${i}:-1">↑</button><button class="btn ghost small" data-mv="${i}:1">↓</button><button class="btn danger small" data-rm="${i}">刪除</button>` : ""}</div>
        <input type="text" data-i="${i}" data-k="title" value="${esc(s.title || "")}"><textarea rows="3" data-i="${i}" data-k="points">${esc((s.points || []).join("\n"))}</textarea>
        <textarea rows="2" data-i="${i}" data-k="notes" placeholder="講者備註">${esc(s.notes || "")}</textarea></div>`).join("")
        + `<button class="btn outline" id="addS">＋ 新增一頁</button><h3>Q&A</h3>` + (c.qa || []).map((x, i) => `<div class="row"><input type="text" data-q="${i}" data-k="q" value="${esc(x.q)}" style="flex:1"><input type="text" data-q="${i}" data-k="a" value="${esc(x.a)}" style="flex:1"><button class="btn danger small" data-rq="${i}">✕</button></div>`).join("")
        + `<button class="btn outline" id="addQ">＋ 新增一題</button><p class="muted">每個重點一行。改完按上方「儲存」。</p>`;
      t.querySelectorAll("[data-i]").forEach((x) => x.oninput = () => { const s = c.slides[+x.dataset.i]; s[x.dataset.k] = x.dataset.k === "points" ? x.value.split("\n").map((y) => y.trim()).filter(Boolean) : x.value; });
      t.querySelectorAll("[data-q]").forEach((x) => x.oninput = () => { c.qa[+x.dataset.q][x.dataset.k] = x.value; });
      t.querySelectorAll("[data-mv]").forEach((b) => b.onclick = () => { const [i, d] = b.dataset.mv.split(":").map(Number), j = i + d; if (j >= 1 && j < c.slides.length) { [c.slides[i], c.slides[j]] = [c.slides[j], c.slides[i]]; draw(); } });
      t.querySelectorAll("[data-rm]").forEach((b) => b.onclick = () => { c.slides.splice(+b.dataset.rm, 1); draw(); });
      t.querySelectorAll("[data-rq]").forEach((b) => b.onclick = () => { c.qa.splice(+b.dataset.rq, 1); draw(); });
      $("#addS").onclick = () => { c.slides.splice(Math.max(c.slides.length - 1, 1), 0, { label: "補充重點", title: "新的投影片", points: ["重點"], notes: "" }); draw(); };
      $("#addQ").onclick = () => { (c.qa = c.qa || []).push({ q: "新的題目", a: "" }); draw(); };
    };
    draw();
  };
  const exporter = () => {
    const w = cur, files = { SLIDES: ["PowerPoint（含講者備註）", "簡報大綱 Word", "Q&A 作答卷 Word", "Q&A 解答 Word", "網頁版", "純文字大綱"],
      MINDMAP: ["心智圖 PNG", "網頁", "Markdown", "FreeMind .mm（XMind 可匯入）"], REPORT: ["Word", "Markdown", "網頁"], QUIZ: ["作答卷 Word", "解答 Word", "線上作答網頁"],
      INFOGRAPHIC: ["直式海報 PNG", "網頁"], WEBPAGE: ["互動式網頁 HTML（單一檔案可分享）", "內容 JSON"] }[w.kind];
    $("#tab").innerHTML = `<div class="col"><b>會產生這些檔案：</b><ul>${files.map((f) => `<li>${f}</li>`).join("")}</ul>
      <div class="row"><button class="btn accent" id="zip">⬇ 下載整組（ZIP）</button><span id="one" class="row"></span></div>
      <p class="muted">匯出的是目前的內容（有修改請先儲存）。範本內容為通用版，正式使用前請由指導員確認。</p></div>`;
    const bundle = () => R.exportBundle(w.kind, w.content, $("#wt").value.trim() || w.title, w.style);
    $("#zip").onclick = async () => { toast("正在產生檔案…"); const fs = await bundle(); download((w.title || "成品").replace(/[\\/:*?"<>|\s]+/g, "_") + ".zip", await R.zip(fs)); };
    bundle().then((fs) => { $("#one").innerHTML = fs.map(([n], i) => `<button class="btn outline small" data-f="${i}">${esc(n.split(".").pop().toUpperCase())}：${esc(n)}</button>`).join(""); $("#one").querySelectorAll("[data-f]").forEach((b) => b.onclick = () => download(...fs[+b.dataset.f])); });
  };
  const source = () => {
    const w = cur, b = new E.Brief(projForBrief(Data.project(w.project)), w.topic, w.brief);
    const prompt = w.prompt || E.buildPrompt(w.kind, b);
    $("#tab").innerHTML = `<div class="col">${w.engine === "NOTEBOOKLM" ? "" : '<p class="muted">這份是用內建範本產生的；如果要依文案產生，請到產生工具選 NotebookLM。</p>'}
      <b>交給 NotebookLM 的指令</b><pre class="prompt">${esc(prompt)}</pre><button class="btn outline small" id="cp">複製指令</button>
      ${w.answer ? `<b>NotebookLM 原始回答</b><pre class="prompt">${esc(w.answer)}</pre>` : ""}</div>`;
    $("#cp").onclick = () => copy(prompt);
  };
  list();
  if (arg && all.some((w) => w.id === +arg)) open(+arg); else if (all.length) open(all[0].id);
};

// ---------------------------------------------------------------- 筆記本
S.notebooks = (v) => {
  const draw = () => {
    const ns = Data.notebooks();
    v.innerHTML = "";
    v.append(h(`<div class="col" style="max-width:900px"><div class="card col"><h3>🔗 NotebookLM 筆記本</h3>
      <p class="muted">線上版不能自動登入 Google，所以用「複製指令 → 在 NotebookLM 貼上 → 把回答貼回來」。在 NotebookLM 網頁按右上「分享」可以複製筆記本網址。
      想讓程式自動提問、讀取帳號裡的所有筆記本，請用 <a href="https://github.com/${DATA.repo}/releases/latest" target="_blank">電腦版</a>。</p>
      <div class="row"><input type="text" id="u" placeholder="https://notebook.google.com/notebook/…" style="flex:2"><input type="text" id="t" placeholder="名稱" style="flex:1"><button class="btn" id="add">＋ 加入</button></div></div>
      ${ns.map((n) => `<div class="card row"><span style="font-size:26px">📒</span><div style="flex:1;min-width:0"><b>${esc(n.title)}</b><div class="muted" style="word-break:break-all">${esc(n.url)}</div>${n.desc ? `<div class="muted">${esc(n.desc)}</div>` : ""}</div>
        <a class="btn outline small" href="${esc(n.url)}" target="_blank">開啟</a><button class="btn danger small" data-del="${n.id}">移除</button></div>`).join("")}</div>`));
    $("#add").onclick = () => {
      const m = $("#u").value.trim().match(/https?:\/\/(notebook(?:lm)?\.google\.com)\/notebook\/([0-9a-fA-F-]{36})/);
      if (!m) return toast("網址格式不對，應該像 https://notebook.google.com/notebook/xxxxxxxx-…", true);
      const url = `https://${m[1].toLowerCase()}/notebook/${m[2].toLowerCase()}`, ns2 = Data.notebooks();
      if (ns2.some((n) => n.url === url)) return toast("這本筆記本已經在清單裡了", true);
      ns2.push({ id: Math.max(0, ...ns2.map((n) => n.id)) + 1, title: $("#t").value.trim() || "筆記本", url, desc: "" }); store.set("notebooks", ns2); draw(); toast("已加入");
    };
    v.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => { if (confirm("只從清單移除，不會刪除 NotebookLM 上的筆記本。")) { store.set("notebooks", Data.notebooks().filter((n) => n.id !== +b.dataset.del)); draw(); } });
  };
  draw();
};

// ---------------------------------------------------------------- 專案範本與主題庫
const TOPIC_SECTIONS = [["hook", "破題"], ["purposes", "目的"], ["supplies", "用物"], ["stepsA", "步驟一"], ["stepsB", "步驟二"], ["cautions", "注意事項"],
  ["errors", "常見錯誤"], ["report", "立即報告"], ["action", "行動呼籲"], ["qa", "Q&A"], ["terms", "關鍵詞"]];
function topicToText(d) {
  const L = [];
  for (const [k, lab] of TOPIC_SECTIONS) {
    const v = d[k];
    if (["hook", "report", "action"].includes(k)) { L.push(`【${lab}】${v || ""}`); continue; }
    if (k === "stepsA" || k === "stepsB") { L.push(`【${lab}】${(v || {}).title || ""}`, ...((v || {}).items || []).map((x) => "- " + x)); }
    else if (k === "errors") L.push(`【${lab}】（錯誤 → 正確）`, ...(v || []).filter((x) => x.length === 2).map((x) => `- ${x[0]} → ${x[1]}`));
    else if (k === "qa") L.push(`【${lab}】（題目 ｜ 參考答案）`, ...(v || []).filter((x) => x.length === 2).map((x) => `- ${x[0]} ｜ ${x[1]}`));
    else if (k === "terms") L.push(`【${lab}】（中文 ｜ 母語一 ｜ 母語二 ｜ …）`, ...(v || []).map((x) => "- " + x.join(" ｜ ")));
    else L.push(`【${lab}】`, ...(v || []).map((x) => "- " + x));
    L.push("");
  }
  return L.join("\n");
}
function textToTopic(text) {
  const d = {}, names = Object.fromEntries(TOPIC_SECTIONS.map(([k, l]) => [l, k])); let cur = null;
  for (const ln of text.split(/\r?\n/)) {
    const s = ln.trim();
    if (s.startsWith("【") && s.includes("】")) {
      const [lab, rest0] = s.slice(1).split("】"), rest = (rest0 || "").trim(); cur = names[lab]; if (!cur) continue;
      if (["hook", "report", "action"].includes(cur)) d[cur] = rest; else if (cur === "stepsA" || cur === "stepsB") d[cur] = { title: rest, items: [] }; else d[cur] = [];
      continue;
    }
    if (!s.startsWith("- ") || !cur) continue;
    const it = s.slice(2).trim();
    if (cur === "stepsA" || cur === "stepsB") d[cur].items.push(it);
    else if (cur === "errors") { const [a, ...b] = it.split("→"); d[cur].push([a.trim(), b.join("→").trim()]); }
    else if (cur === "qa") { const [a, ...b] = it.split("｜"); d[cur].push([a.trim(), b.join("｜").trim()]); }
    else if (cur === "terms") d[cur].push(it.split("｜").map((x) => x.trim()));
    else if (Array.isArray(d[cur])) d[cur].push(it);
  }
  return d;
}
const PFIELDS = [["name", "專案名稱"], ["org", "機構名稱"], ["unit", "單位簡稱"], ["unit_full", "單位全名"], ["cover_title_tpl", "封面標題範本（{org}{unit}{topic}）"],
  ["cover_subtitle", "封面次標題"], ["byline_tpl", "封面小標題範本（{presenter_role}{presenter}{instructor_role}{instructor}）"], ["presenter_role", "簡報人職稱"],
  ["instructor_role", "指導員職稱"], ["font_title", "標題字級 pt"], ["font_sub", "次標題字級 pt"], ["font_small", "小標題字級 pt"], ["min_slides", "最少張數"], ["qa_count", "Q&A 題數"],
  ["role_text", "指令：角色／身分"], ["background_text", "指令：任務背景"], ["purpose_text", "指令：任務目的"], ["audience_text", "預設學員對象"], ["extra_rules", "其他規則"]];
S.projects = (v, arg) => {
  let pid = +(arg || store.get("lastProject", 1)), ti = 0;
  const draw = () => {
    const ps = Data.projects(), p = Data.project(pid); pid = p.id; const ts = Data.topics(pid);
    v.innerHTML = "";
    v.append(h(`<div class="split" style="grid-template-columns:260px 1fr"><div class="card list">${ps.map((x) => `<div class="item ${x.id === pid ? "on" : ""}" data-p="${x.id}">${x.is_sample ? "⭐ " : "📁 "}${esc(x.name)}</div>`).join("")}
      <button class="btn outline small" id="cp" style="margin-top:10px">複製成新專案</button></div>
      <div class="col"><div class="card col"><div class="row"><h2 style="flex:1">${esc(p.name)}</h2><button class="btn" id="sv">💾 儲存專案</button>${p.is_sample ? "" : '<button class="btn danger small" id="dl">刪除</button>'}</div>
        <div class="fields">${PFIELDS.map(([k, l]) => `<label class="fld">${l}<input type="text" data-f="${k}" value="${esc(p[k] ?? "")}"></label>`).join("")}</div>
        <label class="fld">母語關鍵詞欄（國籍:語言，用逗號分隔）<input type="text" id="tl" value="${esc((p.term_langs || []).map((x) => x.join(":")).join("，"))}"></label>
        <details><summary class="muted">範本規格文件（CLAUDE.md）</summary><textarea id="spec" rows="12" style="width:100%">${esc(p.spec_md || "")}</textarea></details></div>
      <div class="card col"><div class="row"><h3 style="flex:1">主題庫（${ts.length}）</h3><button class="btn outline small" id="nt">＋ 新增主題</button></div>
        <div class="row"><select id="ts">${ts.map((t, i) => `<option value="${i}" ${i === ti ? "selected" : ""}>${t.month ? t.month + " 月｜" : ""}${esc(t.name)}</option>`).join("")}</select>
          <input type="text" id="tn" placeholder="主題名稱"><input type="text" id="th" placeholder="依據文件名稱" style="flex:1"></div>
        <textarea id="tb" rows="18" style="width:100%"></textarea><div class="row"><button class="btn" id="stp">儲存主題</button><button class="btn danger small" id="dtp">刪除主題</button></div></div></div></div>`));
    const t = ts[ti]; if (t) { $("#tn").value = t.name; $("#th").value = t.sourceHint || ""; $("#tb").value = topicToText(t); }
    v.querySelectorAll("[data-p]").forEach((x) => x.onclick = () => { pid = +x.dataset.p; ti = 0; store.set("lastProject", pid); draw(); });
    $("#ts").onchange = () => { ti = +$("#ts").value; draw(); };
    $("#sv").onclick = () => { v.querySelectorAll("[data-f]").forEach((x) => { p[x.dataset.f] = /^(font_|min_|qa_)/.test(x.dataset.f) ? +x.value || 0 : x.value; });
      p.term_langs = $("#tl").value.split(/[，,]/).filter((x) => x.includes(":") || x.includes("：")).map((x) => x.replace("：", ":").split(":").map((y) => y.trim()));
      p.spec_md = $("#spec").value; Data.saveProject(p); toast("已儲存專案"); draw(); };
    $("#cp").onclick = () => { const name = prompt("新專案名稱", p.name + "（複製）"); if (!name) return; const np = { ...JSON.parse(JSON.stringify(p)), id: Math.max(...ps.map((x) => x.id)) + 1, name, is_sample: 0 };
      Data.saveProject(np); Data.saveTopics(np.id, JSON.parse(JSON.stringify(ts))); pid = np.id; store.set("lastProject", pid); toast("已複製，主題庫也一起複製了"); draw(); };
    if ($("#dl")) $("#dl").onclick = () => { if (!confirm(`刪除「${p.name}」與它的主題庫？`)) return; store.set("projects", ps.filter((x) => x.id !== pid)); pid = 1; draw(); };
    $("#nt").onclick = () => { ts.push({ ...E.blankTopic("新主題"), id: "custom" + Date.now() }); Data.saveTopics(pid, ts); ti = ts.length - 1; draw(); };
    $("#stp").onclick = () => { if (!ts[ti]) return; ts[ti] = { ...ts[ti], ...textToTopic($("#tb").value), name: $("#tn").value.trim() || ts[ti].name, sourceHint: $("#th").value.trim() }; Data.saveTopics(pid, ts); toast("已儲存主題"); draw(); };
    $("#dtp").onclick = () => { if (!ts[ti] || !confirm(`刪除主題「${ts[ti].name}」？`)) return; ts.splice(ti, 1); Data.saveTopics(pid, ts); ti = 0; draw(); };
  };
  draw();
};

// ---------------------------------------------------------------- 語音教學（預錄的臺灣華語自然語音）
const audio = new Audio();
function stopVoice() { audio.pause(); clearInterval(audio._t); if (window.speechSynthesis) speechSynthesis.cancel(); if (AND && AND.ttsStop) AND.ttsStop(); }
function play(src, onTick) {
  stopVoice(); audio.src = src; audio.play().catch(() => toast("無法播放語音（請先點一下畫面）", true));
  if (onTick) audio._t = setInterval(() => { if (audio.duration) onTick(audio.currentTime / audio.duration); if (audio.ended) clearInterval(audio._t); }, 200);
}
function say(text) {
  if (AND && AND.ttsSpeak) { AND.ttsSpeak(text); return; }
  if (!window.speechSynthesis) return toast("這個瀏覽器不支援朗讀", true);
  stopVoice(); const u = new SpeechSynthesisUtterance(text); u.lang = "zh-TW";
  const v = speechSynthesis.getVoices().find((x) => /zh[-_]TW/i.test(x.lang) && /HsiaoChen|Natural|Online/i.test(x.name)) || speechSynthesis.getVoices().find((x) => /zh[-_]TW/i.test(x.lang));
  if (v) u.voice = v; speechSynthesis.speak(u);
}
S.help = (v, arg) => {
  let key = DATA.lessons.some((l) => l.key === arg) ? arg : "intro";
  v.append(h(`<div class="split" style="grid-template-columns:260px 1fr"><div class="card list" id="les"></div><div class="card col" id="stage"></div></div>`));
  const show = (k, auto) => {
    key = k; const L = DATA.lessons.find((l) => l.key === k), i = DATA.lessons.indexOf(L);
    $("#les").innerHTML = DATA.lessons.map((l, n) => `<div class="item ${l.key === k ? "on" : ""}" data-k="${l.key}">${n + 1}. ${l.title}</div>`).join("");
    $("#les").querySelectorAll("[data-k]").forEach((it) => it.onclick = () => show(it.dataset.k, true));
    $("#stage").innerHTML = `<p class="muted">第 ${i + 1} 課，共 ${DATA.lessons.length} 課</p><div class="row"><h2 style="flex:1">${L.title}</h2>
      <button class="btn" id="play">▶ 播放語音教學</button><button class="btn outline" id="stop">■ 停止</button></div>
      <div class="steps">${L.steps.map((s, n) => `<div class="step" data-n="${n}"><div class="n">${n + 1}</div><div>${esc(s.text)}</div>
        ${TITLES[s.page] ? `<a href="#${s.page}" class="btn ghost small">👉 跟著做</a>` : '<span class="muted">（電腦版）</span>'}</div>`).join("")}</div>
      <div class="card" style="background:#F7F9FC;line-height:1.8">${esc(L.voice)}</div>
      <div class="row"><button class="btn outline" id="prev" ${i === 0 ? "disabled" : ""}>‹ 上一課</button><button class="btn" id="next" ${i === DATA.lessons.length - 1 ? "disabled" : ""}>下一課 ›</button></div>`;
    const steps = $("#stage").querySelectorAll(".step");
    $("#play").onclick = () => play(`../voice/${k}.mp3`, (x) => steps.forEach((s, n) => s.classList.toggle("lit", n === Math.min(steps.length - 1, Math.floor(x * steps.length)))));
    $("#stop").onclick = () => { stopVoice(); steps.forEach((s) => s.classList.remove("lit")); };
    $("#prev").onclick = () => show(DATA.lessons[i - 1].key, true); $("#next").onclick = () => show(DATA.lessons[i + 1].key, true);
    if (auto) $("#play").click();
  };
  show(key, false);
};
$("#speakBtn").onclick = () => { if (!audio.paused) return stopVoice(); if (DATA.pages[current]) { play(`../voice/page_${current}.mp3`); toast("🔊 正在播放：" + DATA.pages[current].title); } };
$("#menuBtn").onclick = () => $("#side").classList.toggle("open");

// ====================================================================== 啟動
$("#ver").textContent = "v" + DATA.version;
const newer = (a, b) => { const x = a.split(".").map(Number), y = b.split(".").map(Number); for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); return false; };
const APPVER = IOS ? IOS.version : AND ? (AND.getVersion ? AND.getVersion() : "0") : "";
let updAsset = null;
async function checkUpdate(manual) {
  if (!IOS && !AND) return;
  const suffix = IOS ? "ZMSNotebookLM-ios.ipa" : "-android.apk";
  try {
    const j = await (await fetch(`https://api.github.com/repos/${DATA.repo}/releases/latest`)).json();
    const latest = (j.tag_name || "").replace(/^v/, ""), asset = (j.assets || []).find((x) => x.name.endsWith(suffix));
    if (latest && asset && newer(latest, APPVER)) { updAsset = { url: asset.browser_download_url, ver: latest }; $("#upd").textContent = `⬆ 有新版 v${latest}`; $("#upd").classList.add("show"); if (manual) $("#upd").click(); }
    else if (manual) toast("已經是最新版 v" + APPVER);
  } catch (e) { if (manual) toast("檢查更新需要網路", true); }
}
if (IOS || AND) {
  document.documentElement.classList.add(IOS ? "ios-app" : "android-app", "ios-app");
  $("#edition").textContent = IOS ? "iPhone／iPad 版" : "Android 版"; $("#ver").textContent = "v" + APPVER;
  $("#upd").onclick = () => {
    if (IOS) { location.href = "https://achir1015.github.io/zms-notebooklm/ios/"; return; }
    if (updAsset && confirm(`下載並安裝新版 v${updAsset.ver}（目前 v${APPVER}）？成品與設定都會保留。`)) {
      const r = JSON.parse(AND.installUpdate(updAsset.url, updAsset.ver));
      toast(r.status === "ok" ? "開始下載新版，完成後會跳出安裝畫面" : "更新失敗：" + r.message, r.status !== "ok");
    }
  };
  $("#chkUpd").style.display = ""; $("#chkUpd").onclick = () => checkUpdate(true);
  setTimeout(() => checkUpdate(false), 2000);
}
window.__zmsBack = () => {
  if ($("#side").classList.contains("open")) { $("#side").classList.remove("open"); return true; }
  if (current !== "home") { location.hash = "home"; return true; }
  return false;
};
const [s0, a0] = decodeURIComponent(location.hash.slice(1)).split(":");
go(s0 || "home", a0);
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("../sw.js").catch(() => {});
