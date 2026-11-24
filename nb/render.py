"""美編：把 content JSON 排成檔案。

* 簡報：PowerPoint（.pptx，含講者備註）＋ 每頁預覽圖（PNG）＋ Word 三份（大綱、Q&A 作答卷、Q&A 解答）
* 心智圖：PNG、互動網頁（可收合）、Markdown、FreeMind（.mm，XMind 可匯入）
* 報告：Word、Markdown、網頁
* 測驗：Word 兩份（作答卷、解答）、互動網頁（可直接作答、自動計分）
* 資訊圖表：PNG（直式海報）、網頁
所有檔案都在本機產生，不需要網路。
"""
import base64
import html
import io
import json
import os
import re
import zipfile
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

from .artifacts import KINDS, STYLE_BY_ID, STYLES, mindmap_markdown, outline_text
from .settings import resource_dir

CJK_FONT = "Microsoft JhengHei"          # pptx／docx 字型（Mac 會自動換成蘋方）
_font_cache = {}


def font(size, bold=False):
    key = (int(size), bold)
    if key not in _font_cache:
        path = os.path.join(resource_dir(), "assets", "fonts", "NotoSansTC-VF.ttf")
        f = ImageFont.truetype(path, int(size))
        try:
            f.set_variation_by_axes([700 if bold else 400])
        except Exception:
            pass
        _font_cache[key] = f
    return _font_cache[key]


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def style_of(sid):
    return STYLE_BY_ID.get(sid) or STYLES[0]


NO_LINE_START = set("，。、）」』：；！？),.;:!?%")
GLYPH_FIX = str.maketrans({"✗": "×", "✓": "○", "✔": "○", "✘": "×", "□": "☐"})


def wrap(draw, text, f, width):
    """中文逐字斷行（英文單字不拆開）。"""
    lines = []
    for para in str(text).split("\n"):
        tokens = re.findall(r"[A-Za-z0-9@#%&+\-_./:'’]+|\s+|.", para)
        cur = ""
        for t in tokens:
            if draw.textlength(cur + t, font=f) <= width or not cur or t in NO_LINE_START:
                cur += t
            else:
                lines.append(cur.rstrip())
                cur = t.lstrip()
        lines.append(cur.rstrip())
    return lines or [""]


def text_block(draw, xy, text, f, width, fill, spacing=1.35, max_lines=None):
    x, y = xy
    lines = wrap(draw, text, f, width)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    lh = int(f.size * spacing)
    for ln in lines:
        draw.text((x, y), ln, font=f, fill=fill)
        y += lh
    return y


# ================================================================ 簡報：預覽圖
SW, SH = 1280, 720


def slide_png(slide, idx, total, style="pastel", cover_sizes=(45, 40, 32), topic=""):
    """畫一張投影片預覽（與 pptx 版面相同比例）。回傳 PNG bytes。"""
    if style == "pastel":
        from . import deck
        return deck.slide_png(slide, idx, total, cover_sizes, topic)
    dark, main, accent, light, ink = [hex2rgb(c) for c in style_of(style)["colors"]]
    im = Image.new("RGB", (SW, SH), light)
    d = ImageDraw.Draw(im)
    k = SW / 960.0                                    # pptx 寬 960pt → 像素
    if slide.get("kind") == "cover" or idx == 0:
        _gradient(im, dark, main)
        d = ImageDraw.Draw(im)
        d.rectangle([0, SH - 14, SW, SH], fill=accent)
        y = 150
        y = text_block(d, (90, y), slide.get("title", ""), font(cover_sizes[0] * k * 0.9, True), SW - 180,
                       (255, 255, 255), 1.25, 3) + 26
        d.rectangle([90, y, 230, y + 6], fill=accent)
        pts = slide.get("points", [])
        y += 34
        if pts:
            y = text_block(d, (90, y), pts[0], font(cover_sizes[1] * k * 0.62), SW - 180, (230, 238, 250), 1.3, 2) + 24
        for p in pts[1:]:
            y = text_block(d, (90, y), p, font(cover_sizes[2] * k * 0.55), SW - 180, (205, 218, 240), 1.3, 2) + 10
        return _png(im)
    last = idx == total - 1 and ("感謝" in slide.get("label", "") or "感謝" in slide.get("title", ""))
    if last:
        _gradient(im, main, dark)
        d = ImageDraw.Draw(im)
        f = font(64, True)
        t = slide.get("title", "感謝聆聽")
        d.text(((SW - d.textlength(t, font=f)) / 2, 230), t, font=f, fill=(255, 255, 255))
        y = 340
        for p in slide.get("points", [])[:4]:
            f2 = font(26)
            d.text(((SW - d.textlength(p, font=f2)) / 2, y), p, font=f2, fill=(220, 230, 245))
            y += 46
        return _png(im)
    # 一般內容頁：上方色帶＋標題、左側編號圓點
    d.rectangle([0, 0, SW, 132], fill=main)
    d.rectangle([0, 132, SW, 138], fill=accent)
    lab = slide.get("label", "")
    if lab:
        fl = font(18, True)
        w = d.textlength(lab, font=fl) + 28
        d.rounded_rectangle([60, 20, 60 + w, 52], radius=16, fill=accent)
        d.text((74, 23), lab, font=fl, fill=dark)
    text_block(d, (60, 60), slide.get("title", ""), font(38, True), SW - 200, (255, 255, 255), 1.2, 2)
    fpn = font(18)
    d.text((SW - 90, 98), "%d / %d" % (idx + 1, total), font=fpn, fill=(220, 230, 245))
    pts = slide.get("points", [])
    size = _point_size(pts)
    f = font(size)
    y = 175
    # 重點平均分布在內容區（與 PowerPoint 版面一致），但間距最多 70 像素
    heights = [min(len(wrap(d, p, f, SW - 220 - size)), 3) * int(size * 1.32) for p in pts]
    free = (SH - 60 - y) - sum(heights)
    gap = max(int(size * 0.45), min(70, free // max(len(pts), 1)))
    for i, p in enumerate(pts):
        if y > SH - 60:
            break
        d.ellipse([70, y + 4, 70 + size + 8, y + size + 12], fill=main)
        n = str(i + 1)
        fn = font(size * 0.62, True)
        d.text((70 + (size + 8 - d.textlength(n, font=fn)) / 2, y + 4 + (size + 8 - fn.size) / 2 - 2), n,
               font=fn, fill=(255, 255, 255))
        y = text_block(d, (70 + size + 26, y), p, f, SW - 220 - size, ink, 1.32, 3) + gap
    return _png(im)


def _point_size(pts):
    total = sum(len(p) for p in pts)
    n = len(pts)
    if n <= 4 and total < 120:
        return 34
    if n <= 5 and total < 190:
        return 30
    if n <= 6 and total < 260:
        return 26
    return 22


def _gradient(im, c1, c2):
    d = ImageDraw.Draw(im)
    w, h = im.size
    for x in range(0, w, 4):
        t = x / w
        c = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        d.rectangle([x, 0, x + 4, h], fill=c)


def _png(im, scale=1.0):
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ================================================================ 簡報：PowerPoint
def topic_of(content):
    return (content.get("cover") or {}).get("title", "")


def slides_pptx(content, path, style="pastel"):
    if style == "pastel":
        from . import deck
        return deck.pptx(content, path, topic_of(content))
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Pt

    dark, main, accent, light, ink = [RGBColor(*hex2rgb(c)) for c in style_of(style)["colors"]]
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)       # 16:9
    W, H = prs.slide_width, prs.slide_height
    blank = prs.slide_layouts[6]
    sizes = (content.get("cover") or {}).get("sizes") or [45, 40, 32]
    slides = content.get("slides", [])

    def rect(sl, x, y, w, h, color, shape=MSO_SHAPE.RECTANGLE):
        s = sl.shapes.add_shape(shape, x, y, w, h)
        s.fill.solid()
        s.fill.fore_color.rgb = color
        s.line.fill.background()
        s.shadow.inherit = False
        return s

    def text(sl, x, y, w, h, paras, size, color, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, gap=6):
        tb = sl.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        for i, ptxt in enumerate(paras if isinstance(paras, list) else [paras]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.space_after = Pt(gap)
            r = p.add_run()
            r.text = ptxt
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.color.rgb = color
            r.font.name = CJK_FONT
            rpr = r._r.get_or_add_rPr()
            ea = rpr.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}ea", {"typeface": CJK_FONT})
            rpr.append(ea)
        return tb

    for idx, s in enumerate(slides):
        sl = prs.slides.add_slide(blank)
        bg = sl.background.fill
        bg.solid()
        last = idx == len(slides) - 1 and ("感謝" in s.get("label", "") or "感謝" in s.get("title", ""))
        if s.get("kind") == "cover" or idx == 0:
            bg.fore_color.rgb = dark
            rect(sl, 0, H - Emu(120000), W, Emu(120000), accent)
            rect(sl, 0, 0, Emu(260000), H, main)
            pts = s.get("points", [])
            text(sl, Emu(700000), Emu(900000), W - Emu(1400000), Emu(2500000), s.get("title", ""), sizes[0],
                 RGBColor(255, 255, 255), True, anchor=MSO_ANCHOR.BOTTOM)
            rect(sl, Emu(700000), Emu(3550000), Emu(1300000), Emu(60000), accent)
            if pts:
                text(sl, Emu(700000), Emu(3750000), W - Emu(1400000), Emu(1300000), pts[0], sizes[1],
                     RGBColor(0xE6, 0xEE, 0xFA), True)
            if len(pts) > 1:
                text(sl, Emu(700000), Emu(5150000), W - Emu(1400000), Emu(1200000), pts[1:], sizes[2],
                     RGBColor(0xCD, 0xDA, 0xF0))
        elif last:
            bg.fore_color.rgb = main
            text(sl, 0, Emu(1900000), W, Emu(1200000), s.get("title", "感謝聆聽"), 54, RGBColor(255, 255, 255), True,
                 PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
            text(sl, Emu(900000), Emu(3300000), W - Emu(1800000), Emu(2600000), s.get("points", []), 22,
                 RGBColor(0xDC, 0xE6, 0xF5), align=PP_ALIGN.CENTER)
        else:
            bg.fore_color.rgb = light
            rect(sl, 0, 0, W, Emu(1240000), main)
            rect(sl, 0, Emu(1240000), W, Emu(56000), accent)
            if s.get("label"):
                lab = rect(sl, Emu(560000), Emu(170000), Emu(260000 + 140000 * len(s["label"])), Emu(300000), accent,
                           MSO_SHAPE.ROUNDED_RECTANGLE)
                lab.text_frame.text = s["label"]
                r = lab.text_frame.paragraphs[0].runs[0]
                r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(13), True, dark, CJK_FONT
            text(sl, Emu(560000), Emu(480000), W - Emu(2000000), Emu(760000), s.get("title", ""), 32,
                 RGBColor(255, 255, 255), True, anchor=MSO_ANCHOR.MIDDLE)
            text(sl, W - Emu(1300000), Emu(820000), Emu(1000000), Emu(300000), "%d / %d" % (idx + 1, len(slides)), 12,
                 RGBColor(0xDC, 0xE6, 0xF5), align=PP_ALIGN.RIGHT)
            pts = s.get("points", [])
            size = {34: 28, 30: 24, 26: 22, 22: 18}[_point_size(pts)]
            y0, avail = Emu(1600000), H - Emu(1900000)
            step = int(avail / max(len(pts), 1))
            for i, p in enumerate(pts):
                y = y0 + step * i
                c = rect(sl, Emu(620000), y + Emu(40000), Emu(420000), Emu(420000), main, MSO_SHAPE.OVAL)
                c.text_frame.text = str(i + 1)
                r = c.text_frame.paragraphs[0].runs[0]
                r.font.size, r.font.bold, r.font.color.rgb = Pt(16), True, RGBColor(255, 255, 255)
                c.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                text(sl, Emu(1200000), y, W - Emu(1900000), step, p, size, ink)
        if s.get("notes"):
            sl.notes_slide.notes_text_frame.text = s["notes"]
    prs.core_properties.title = slides[0]["title"] if slides else ""
    prs.core_properties.author = "資料助秘NotebookLM MCP簡報"
    prs.save(path)
    return path


# ================================================================ Word（自己組 .docx，不依賴範本）
def _docx_new():
    import docx
    from docx.oxml.ns import qn
    from docx.shared import Pt
    doc = docx.Document()
    st = doc.styles["Normal"]
    st.font.name = CJK_FONT
    st.font.size = Pt(12)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), CJK_FONT)
    for name in ("Heading 1", "Heading 2", "Heading 3", "Title"):
        try:
            s = doc.styles[name]
            s.font.name = CJK_FONT
            s.element.rPr.rFonts.set(qn("w:eastAsia"), CJK_FONT)
        except Exception:
            pass
    return doc


def slides_outline_docx(content, path):
    doc = _docx_new()
    cov = content.get("cover", {})
    doc.add_heading(cov.get("title", "簡報大綱"), 0)
    if cov.get("subtitle"):
        doc.add_paragraph(cov["subtitle"])
    if cov.get("byline"):
        doc.add_paragraph(cov["byline"])
    for i, s in enumerate(content.get("slides", []), 1):
        doc.add_heading("投影片 %d｜%s" % (i, s.get("label", "")), 2)
        doc.add_paragraph(s.get("title", "")).runs[0].bold = True
        for p in s.get("points", []):
            doc.add_paragraph(p, style="List Bullet")
        if s.get("notes"):
            doc.add_paragraph("講者備註：" + s["notes"]).italic = True
    if content.get("qa"):
        doc.add_heading("Q&A %d 題" % len(content["qa"]), 1)
        for i, x in enumerate(content["qa"], 1):
            doc.add_paragraph("%d. %s" % (i, x["q"]))
            doc.add_paragraph("答：" + x["a"])
    doc.save(path)
    return path


def qa_docx(content, path, answers=False):
    """Q&A：answers=False 題目＋空白作答；True 完整解答。"""
    doc = _docx_new()
    cov = content.get("cover", {})
    doc.add_heading("%s　Q&A %s" % (cov.get("title", ""), "解答" if answers else "作答卷"), 1)
    if not answers:
        doc.add_paragraph("姓名：＿＿＿＿＿＿＿＿　國籍：＿＿＿＿＿＿　日期：＿＿＿＿＿＿＿　得分：＿＿＿＿")
    for i, x in enumerate(content.get("qa", []), 1):
        doc.add_paragraph("%d. %s" % (i, x["q"])).runs[0].bold = True
        if answers:
            doc.add_paragraph("答：" + x["a"])
        else:
            for _ in range(3):
                doc.add_paragraph("＿" * 34)
    doc.save(path)
    return path


def report_docx(content, path):
    doc = _docx_new()
    doc.add_heading(content.get("title", "報告"), 0)
    for k in ("org", "byline"):
        if content.get(k):
            doc.add_paragraph(content[k])
    if content.get("summary"):
        doc.add_heading("摘要", 1)
        doc.add_paragraph(content["summary"])
    for s in content.get("sections", []):
        doc.add_heading(s.get("heading", ""), 1)
        for p in s.get("paragraphs", []):
            doc.add_paragraph(p)
        for b in s.get("bullets", []):
            doc.add_paragraph(b, style="List Bullet")
    if content.get("conclusion"):
        doc.add_heading("結論", 1)
        doc.add_paragraph(content["conclusion"])
    if content.get("references"):
        doc.add_heading("參考來源", 1)
        for r in content["references"]:
            doc.add_paragraph(r, style="List Number")
    doc.save(path)
    return path


def quiz_docx(content, path, answers=False):
    doc = _docx_new()
    doc.add_heading("%s%s" % (content.get("title", "測驗"), "　解答" if answers else ""), 1)
    if not answers:
        doc.add_paragraph("姓名：＿＿＿＿＿＿＿＿　日期：＿＿＿＿＿＿＿　得分：＿＿＿＿")
    for i, q in enumerate(content.get("questions", []), 1):
        tag = {"single": "單選", "tf": "是非", "short": "問答"}[q["type"]]
        doc.add_paragraph("%d.（%s）%s" % (i, tag, q["q"])).runs[0].bold = True
        if q["type"] == "single":
            for j, o in enumerate(q["options"]):
                doc.add_paragraph("　（%s）%s" % ("ABCD"[j] if j < 4 else j + 1, o))
        elif q["type"] == "tf":
            doc.add_paragraph("　（　）○ 對　（　）✕ 錯" if not answers else "")
        if answers:
            doc.add_paragraph("答案：%s%s" % (q["answer"], ("　解析：" + q["explain"]) if q.get("explain") else ""))
        elif q["type"] == "short":
            for _ in range(2):
                doc.add_paragraph("＿" * 34)
    doc.save(path)
    return path


# ================================================================ 心智圖
BRANCH_COLORS = ["#1E4D8C", "#0FA294", "#E0A526", "#C2185B", "#7C3AED", "#EA580C", "#0284C7", "#16A34A",
                 "#9333EA", "#DC2626"]


def mindmap_png(content, scale=1.0):
    """左右對稱的心智圖：中心主題在中間，分支輪流放左右兩邊。"""
    root = content.get("root") or {"text": "主題", "children": []}
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    F = [font(34, True), font(24, True), font(19), font(16)]
    PADX, PADY, GAPX, GAPY = [26, 18, 12, 10], [16, 10, 6, 5], 70, 12

    def size(n, depth):
        f = F[min(depth, 3)]
        lines = wrap(probe, n["text"], f, 260 if depth else 320)
        w = max(probe.textlength(ln, font=f) for ln in lines) + PADX[min(depth, 3)] * 2
        h = len(lines) * f.size * 1.3 + PADY[min(depth, 3)] * 2
        n["_lines"], n["_w"], n["_h"] = lines, w, h
        kids = n.get("children") or []
        for k in kids:
            size(k, depth + 1)
        n["_th"] = max(h, sum(k["_th"] for k in kids) + GAPY * (len(kids) - 1)) if kids else h

    size(root, 0)
    kids = root.get("children") or []
    right, left, hr, hl = [], [], 0, 0
    for k in kids:                                   # 讓左右高度接近
        if hr <= hl:
            right.append(k)
            hr += k["_th"] + GAPY * 3
        else:
            left.append(k)
            hl += k["_th"] + GAPY * 3

    def depth_w(n, d=0):
        return n["_w"] + (GAPX + max(depth_w(k, d + 1) for k in n["children"]) if n.get("children") else 0)

    wr = max([depth_w(k) for k in right] or [0])
    wl = max([depth_w(k) for k in left] or [0])
    H = int(max(hr, hl, root["_h"]) + 120)
    W = int(wl + wr + root["_w"] + GAPX * 2 + 120)
    im = Image.new("RGB", (W, H), (250, 251, 253))
    d = ImageDraw.Draw(im)
    cx = 60 + wl + GAPX
    cy = H / 2

    def draw_node(n, x, y, depth, color, side):
        """x 是節點靠近中心那一側的 x；y 是中心。"""
        w, h = n["_w"], n["_h"]
        x0 = x if side > 0 else x - w
        box = [x0, y - h / 2, x0 + w, y + h / 2]
        rgb = hex2rgb(color)
        if depth == 1:
            d.rounded_rectangle(box, radius=14, fill=rgb)
            fg = (255, 255, 255)
        elif depth == 2:
            d.rounded_rectangle(box, radius=10, fill=tuple(int(c + (255 - c) * 0.85) for c in rgb), outline=rgb, width=2)
            fg = (31, 41, 55)
        else:
            d.line([box[0], box[3], box[2], box[3]], fill=rgb, width=2)
            fg = (55, 65, 81)
        f = F[min(depth, 3)]
        ty = y - len(n["_lines"]) * f.size * 1.3 / 2 + 1
        for ln in n["_lines"]:
            d.text((x0 + PADX[min(depth, 3)], ty), ln, font=f, fill=fg)
            ty += f.size * 1.3
        kids = n.get("children") or []
        if not kids:
            return
        top = y - (sum(k["_th"] for k in kids) + GAPY * (len(kids) - 1)) / 2
        ex = x0 + w if side > 0 else x0
        for k in kids:
            ky = top + k["_th"] / 2
            kx = ex + GAPX * side
            _curve(d, (ex, y), (kx, ky), rgb, 3 if depth == 1 else 2)
            draw_node(k, kx, ky, depth + 1, color, side)
            top += k["_th"] + GAPY

    for side, group in ((1, right), (-1, left)):
        total = sum(k["_th"] for k in group) + GAPY * 3 * (len(group) - 1)
        top = cy - total / 2
        for k in group:
            color = BRANCH_COLORS[kids.index(k) % len(BRANCH_COLORS)]
            ky = top + k["_th"] / 2
            sx = cx + (root["_w"] if side > 0 else 0)
            kx = sx + GAPX * side
            _curve(d, (sx, cy), (kx, ky), hex2rgb(color), 4)
            draw_node(k, kx, ky, 1, color, side)
            top += k["_th"] + GAPY * 3
    box = [cx, cy - root["_h"] / 2, cx + root["_w"], cy + root["_h"] / 2]
    d.rounded_rectangle(box, radius=22, fill=(20, 50, 92), outline=(224, 165, 38), width=4)
    ty = cy - len(root["_lines"]) * F[0].size * 1.3 / 2
    for ln in root["_lines"]:
        d.text((cx + PADX[0], ty), ln, font=F[0], fill=(255, 255, 255))
        ty += F[0].size * 1.3
    return _png(im, scale)


def _curve(d, a, b, color, width):
    (x1, y1), (x2, y2) = a, b
    pts = []
    for i in range(21):
        t = i / 20
        mx = x1 + (x2 - x1) * 0.5
        # 三次貝茲：a → (mx,y1) → (mx,y2) → b
        x = (1 - t) ** 3 * x1 + 3 * (1 - t) ** 2 * t * mx + 3 * (1 - t) * t * t * mx + t ** 3 * x2
        y = (1 - t) ** 3 * y1 + 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3 * y2
        pts.append((x, y))
    d.line(pts, fill=color, width=width, joint="curve")


def mindmap_freemind(content):
    def node(n):
        kids = "".join(node(k) for k in n.get("children", []))
        return '<node TEXT="%s">%s</node>' % (escape(n["text"], {'"': "&quot;"}), kids)
    return '<map version="1.0.1">%s</map>' % node(content["root"])


def mindmap_html(content, title):
    def li(n):
        kids = n.get("children", [])
        inner = "<ul>%s</ul>" % "".join(li(k) for k in kids) if kids else ""
        return "<li%s><span>%s</span>%s</li>" % (' class="has"' if kids else "", html.escape(n["text"]), inner)
    png = base64.b64encode(mindmap_png(content)).decode()
    return _page(title, """
<style>.tree ul{list-style:none;padding-left:22px;border-left:2px solid #dbe3ef;margin:4px 0}
.tree li{margin:4px 0}.tree span{display:inline-block;padding:4px 10px;border-radius:8px;background:#eef3fb;cursor:pointer}
.tree li.has>span::before{content:'▾ ';color:#1E4D8C}.tree li.closed>span::before{content:'▸ '}
.tree li.closed>ul{display:none}img{max-width:100%;border-radius:12px;border:1px solid #e5e9f0}</style>
<p><img src="data:image/png;base64,""" + png + """" alt="心智圖"></p>
<h2>大綱（點一下可以收合）</h2><div class="tree"><ul>""" + li(content["root"]) + """</ul></div>
<script>document.querySelectorAll('.tree li.has>span').forEach(s=>s.onclick=()=>s.parentNode.classList.toggle('closed'))</script>""")


# ================================================================ 資訊圖表
def infographic_png(content, style="pastel", scale=1.0):
    dark, main, accent, light, ink = [hex2rgb(c) for c in style_of(style)["colors"]]
    W = 1080
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    secs = content.get("sections", [])
    colw = (W - 60 * 2 - 30) / 2
    fh, fp = font(30, True), font(23)

    def sec_h(s):
        h = 70
        for p in s.get("points", []):
            h += len(wrap(probe, p, fp, colw - 70)) * fp.size * 1.4 + 14
        return h + 16

    rows = [secs[i:i + 2] for i in range(0, len(secs), 2)]
    head_h = 400
    H = 470 + (190 if content.get("stats") else 0) + sum(max(sec_h(s) for s in r) + 30 for r in rows) + 220
    im = Image.new("RGB", (W, int(H)), light)
    d = ImageDraw.Draw(im)
    t_lines = len(wrap(probe, content.get("title", ""), font(62, True), W - 120)[:3])
    s_lines = len(wrap(probe, content.get("subtitle", ""), font(28), W - 120)[:3]) if content.get("subtitle") else 0
    head_h = int(70 + t_lines * 62 * 1.2 + 18 + s_lines * 28 * 1.35 + 60)
    H += head_h - 400
    im = Image.new("RGB", (W, int(H)), light)
    d = ImageDraw.Draw(im)
    head = Image.new("RGB", (W, head_h))
    _gradient(head, dark, main)
    im.paste(head, (0, 0))
    d.rectangle([0, head_h, W, head_h + 12], fill=accent)
    y = text_block(d, (60, 70), content.get("title", ""), font(62, True), W - 120, (255, 255, 255), 1.2, 3) + 18
    text_block(d, (60, y), content.get("subtitle", ""), font(28), W - 120, (225, 234, 248), 1.35, 3)
    y = head_h + 50
    stats = content.get("stats", [])
    if stats:
        n = len(stats)
        cw = (W - 120 - 24 * (n - 1)) / n
        for i, s in enumerate(stats):
            x = 60 + i * (cw + 24)
            d.rounded_rectangle([x, y, x + cw, y + 160], radius=22, fill=(255, 255, 255), outline=main, width=3)
            fv = font(54 if len(s["value"]) <= 4 else 34, True)
            v = s["value"]
            d.text((x + (cw - d.textlength(v, font=fv)) / 2, y + 22), v, font=fv, fill=main)
            fl = font(21)
            text_block(d, (x + 14, y + 100), s["label"], fl, cw - 28, ink, 1.25, 2)
        y += 190
    for r in rows:
        hh = max(sec_h(s) for s in r)
        for j, s in enumerate(r):
            x = 60 + j * (colw + 30)
            color = hex2rgb(BRANCH_COLORS[(secs.index(s)) % len(BRANCH_COLORS)])
            d.rounded_rectangle([x, y, x + colw, y + hh], radius=20, fill=(255, 255, 255))
            d.rounded_rectangle([x, y, x + colw, y + 58], radius=20, fill=color)
            d.rectangle([x, y + 38, x + colw, y + 58], fill=color)
            d.text((x + 24, y + 10), s.get("heading", ""), font=fh, fill=(255, 255, 255))
            py = y + 76
            for p in s.get("points", []):
                d.ellipse([x + 26, py + 10, x + 38, py + 22], fill=color)
                py = text_block(d, (x + 52, py), p, fp, colw - 70, ink, 1.4) + 14
        y += hh + 30
    if content.get("tip"):
        d.rounded_rectangle([60, y, W - 60, y + 120], radius=24, fill=accent)
        text_block(d, (96, y + 22), "重點提醒：" + content["tip"], font(28, True), W - 190, dark, 1.3, 2)
        y += 150
    if content.get("footer"):
        d.text((60, y), content["footer"], font=font(20), fill=(120, 130, 145))
    im = im.crop((0, 0, W, int(min(H, y + 60))))
    return _png(im, scale)


# ================================================================ 網頁輸出
def _page(title, body):
    return ("<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>%s</title>"
            "<style>body{font-family:'Noto Sans TC','Microsoft JhengHei','PingFang TC',sans-serif;max-width:1000px;"
            "margin:0 auto;padding:24px;color:#1f2937;background:#f6f8fb;line-height:1.7}h1{color:#14325C}"
            "h2{color:#1E4D8C;border-left:6px solid #E0A526;padding-left:10px}.card{background:#fff;border-radius:14px;"
            "padding:16px 20px;margin:14px 0;box-shadow:0 2px 8px #0000000d}footer{color:#888;font-size:13px;margin-top:30px}"
            "</style></head><body><h1>%s</h1>%s<footer>由 資料助秘NotebookLM MCP簡報 產生</footer></body></html>"
            % (html.escape(title), html.escape(title), body))


def slides_html(content, style="pastel"):
    imgs = []
    slides = content.get("slides", [])
    for i, s in enumerate(slides):
        b64 = base64.b64encode(slide_png(s, i, len(slides), style, (content.get("cover") or {}).get("sizes")
                                         or (45, 40, 32), topic_of(content))).decode()
        note = ("<p class='n'>講者備註：%s</p>" % html.escape(s["notes"])) if s.get("notes") else ""
        imgs.append("<div class='card'><img src='data:image/png;base64,%s' style='width:100%%;border-radius:8px'>%s</div>"
                    % (b64, note))
    qa = "".join("<li><b>%s</b><br>答：%s</li>" % (html.escape(x["q"]), html.escape(x["a"]))
                 for x in content.get("qa", []))
    return _page((content.get("cover") or {}).get("title", "簡報"),
                 "<style>.n{color:#555;font-size:14px}</style>" + "".join(imgs) +
                 ("<h2>Q&A</h2><ol class='card'>%s</ol>" % qa if qa else ""))


def report_html(content):
    L = []
    for k in ("org", "byline"):
        if content.get(k):
            L.append("<p>%s</p>" % html.escape(content[k]))
    if content.get("summary"):
        L.append("<div class='card'><b>摘要</b><p>%s</p></div>" % html.escape(content["summary"]))
    for s in content.get("sections", []):
        L.append("<h2>%s</h2>" % html.escape(s.get("heading", "")))
        L += ["<p>%s</p>" % html.escape(p) for p in s.get("paragraphs", [])]
        if s.get("bullets"):
            L.append("<ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(b) for b in s["bullets"]))
    if content.get("conclusion"):
        L.append("<h2>結論</h2><p>%s</p>" % html.escape(content["conclusion"]))
    if content.get("references"):
        L.append("<h2>參考來源</h2><ol>%s</ol>" % "".join("<li>%s</li>" % html.escape(r) for r in content["references"]))
    return _page(content.get("title", "報告"), "".join(L))


def report_markdown(content):
    L = ["# " + content.get("title", "報告"), ""]
    for k in ("org", "byline"):
        if content.get(k):
            L += [content[k], ""]
    if content.get("summary"):
        L += ["## 摘要", content["summary"], ""]
    for s in content.get("sections", []):
        L += ["## " + s.get("heading", "")] + s.get("paragraphs", []) + ["- " + b for b in s.get("bullets", [])] + [""]
    if content.get("conclusion"):
        L += ["## 結論", content["conclusion"], ""]
    if content.get("references"):
        L += ["## 參考來源"] + ["%d. %s" % (i, r) for i, r in enumerate(content["references"], 1)]
    return "\n".join(L)


def quiz_html(content):
    data = json.dumps(content.get("questions", []), ensure_ascii=False)
    return _page(content.get("title", "測驗"), """
<style>.q{background:#fff;border-radius:14px;padding:14px 18px;margin:12px 0}.o{display:block;margin:6px 0;padding:8px 12px;
border:1px solid #dbe3ef;border-radius:10px;cursor:pointer}.o.sel{background:#e8f0fb;border-color:#1E4D8C}
.o.ok{background:#dcfce7;border-color:#16a34a}.o.bad{background:#fee2e2;border-color:#dc2626}.ex{color:#555;display:none}
button{font-size:18px;padding:10px 26px;border-radius:12px;border:0;background:#1E4D8C;color:#fff;cursor:pointer}
#score{font-size:22px;font-weight:700;color:#0FA294}</style><div id="qs"></div>
<p><button onclick="grade()">交卷</button> <span id="score"></span></p>
<script>const Q=""" + data + """;const L='ABCD';const pick={};
const box=document.getElementById('qs');
Q.forEach((q,i)=>{const d=document.createElement('div');d.className='q';
d.innerHTML='<b>'+(i+1)+'. '+q.q+'</b>';const opts=q.type==='tf'?['○','✕']:q.options;
if(q.type==='short'){d.innerHTML+='<textarea style="width:100%;height:70px"></textarea>'}
opts.forEach((o,j)=>{const a=q.type==='tf'?o:L[j];const e=document.createElement('label');e.className='o';
e.textContent=(q.type==='tf'?'':'('+a+') ')+o;e.onclick=()=>{pick[i]=a;d.querySelectorAll('.o').forEach(x=>x.classList.remove('sel'));e.classList.add('sel')};
e.dataset.a=a;d.appendChild(e)});const ex=document.createElement('p');ex.className='ex';
ex.textContent='答案：'+q.answer+(q.explain?'　'+q.explain:'');d.appendChild(ex);box.appendChild(d)});
function grade(){let ok=0,n=0;document.querySelectorAll('.q').forEach((d,i)=>{const q=Q[i];d.querySelector('.ex').style.display='block';
if(q.type==='short')return;n++;if(pick[i]===q.answer)ok++;d.querySelectorAll('.o').forEach(e=>{if(e.dataset.a===q.answer)e.classList.add('ok');
else if(e.dataset.a===pick[i])e.classList.add('bad')})});document.getElementById('score').textContent='答對 '+ok+' / '+n+' 題（'+Math.round(ok*100/Math.max(n,1))+' 分）'}
</script>""")


def infographic_html(content, style="pastel"):
    b64 = base64.b64encode(infographic_png(content, style)).decode()
    return _page(content.get("title", "資訊圖表"),
                 "<p><img src='data:image/png;base64,%s' style='max-width:100%%;border-radius:12px'></p>" % b64)


# ================================================================ 互動式網頁（單一 HTML 檔，離線可開、可分享）
WEBPAGE_CSS = """
*{box-sizing:border-box}body{margin:0;font-family:'Noto Sans TC','Microsoft JhengHei','PingFang TC',sans-serif;color:#1f2937;
background:#f4f6fa;line-height:1.75;font-size:17px}
header{background:linear-gradient(135deg,var(--dark),var(--main));color:#fff;padding:48px 24px 40px}
header .in,main{max-width:980px;margin:0 auto}header h1{margin:0 0 8px;font-size:34px}header p{margin:0;opacity:.9}
.by{font-size:14px;opacity:.75;margin-top:10px}
nav{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid #e5e9f0;overflow-x:auto;white-space:nowrap}
nav a{display:inline-block;padding:12px 16px;color:var(--main);text-decoration:none;font-weight:600}
nav a.on{border-bottom:3px solid var(--accent)}
main{padding:20px 18px 60px}h2{color:var(--dark);margin:34px 0 12px;border-left:6px solid var(--accent);padding-left:12px}
.intro{background:#fff;border-radius:16px;padding:18px 22px;box-shadow:0 2px 10px #0000000d}
.sec{background:#fff;border-radius:16px;margin:12px 0;box-shadow:0 2px 10px #0000000d;overflow:hidden}
.sec>button{all:unset;display:flex;gap:12px;align-items:center;width:100%;padding:16px 20px;cursor:pointer;box-sizing:border-box}
.num{flex:none;width:36px;height:36px;border-radius:50%;background:var(--main);color:#fff;display:grid;place-items:center;font-weight:700}
.sec h3{margin:0;font-size:19px}.sec small{color:#6b7280;display:block}.arrow{margin-left:auto;transition:.2s}
.sec.open .arrow{transform:rotate(90deg)}.body{display:none;padding:0 22px 18px 70px}.sec.open .body{display:block}
.body li{margin:4px 0}.detail{background:var(--light);border-radius:10px;padding:10px 14px;margin-top:8px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}
.card{perspective:800px;height:150px;cursor:pointer}.card .f{position:relative;width:100%;height:100%;transition:.5s;transform-style:preserve-3d}
.card.flip .f{transform:rotateY(180deg)}.card .s{position:absolute;inset:0;backface-visibility:hidden;border-radius:16px;
display:grid;place-items:center;padding:14px;text-align:center;box-shadow:0 2px 10px #0000001a}
.card .a{background:var(--main);color:#fff;font-size:20px;font-weight:700}.card .b{background:#fff;transform:rotateY(180deg);font-size:15px}
details{background:#fff;border-radius:14px;margin:10px 0;padding:12px 18px;box-shadow:0 2px 10px #0000000d}
summary{cursor:pointer;font-weight:700;color:var(--dark)}
.q{background:#fff;border-radius:16px;padding:16px 20px;margin:12px 0;box-shadow:0 2px 10px #0000000d}
.opt{display:block;width:100%;text-align:left;margin:8px 0;padding:10px 14px;border:1px solid #dbe3ef;border-radius:12px;
background:#fff;font-size:16px;cursor:pointer}.opt.ok{background:#dcfce7;border-color:#16a34a}.opt.bad{background:#fee2e2;border-color:#dc2626}
.ex{display:none;color:#475569;margin-top:6px}.q.done .ex{display:block}
#score{font-size:22px;font-weight:800;color:var(--main)}
.take{margin-top:30px;background:var(--accent);color:var(--dark);border-radius:18px;padding:20px 24px;font-size:20px;font-weight:700}
.tools{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}.tools button{border:0;border-radius:10px;padding:8px 14px;background:var(--main);color:#fff;cursor:pointer}
footer{text-align:center;color:#94a3b8;font-size:13px;padding:30px}
@media print{nav,.tools{display:none}.body{display:block!important}}
"""

WEBPAGE_JS = r"""
const $=s=>document.querySelector(s),esc=t=>String(t||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
$('#t').textContent=C.title;$('#st').textContent=C.subtitle||'';$('#by').textContent=C.byline||'';$('#ft').textContent=C.footer||'';
const m=$('#m'),parts=[];let h='';
if(C.intro){h+='<div class="intro" id="p-intro">'+esc(C.intro)+'</div>';parts.push(['p-intro','介紹'])}
if((C.sections||[]).length){
 h+='<h2 id="p-sec">重點章節</h2><div class="tools"><button onclick="openAll(1)">全部展開</button><button onclick="openAll(0)">全部收起</button></div>';
 C.sections.forEach((s,i)=>{h+='<div class="sec'+(i==0?' open':'')+'"><button onclick="this.parentNode.classList.toggle(\'open\')"><span class="num">'+(i+1)+
  '</span><span><h3>'+esc(s.heading)+'</h3><small>'+esc(s.summary)+'</small></span><span class="arrow">▶</span></button><div class="body"><ul>'+
  (s.points||[]).map(p=>'<li>'+esc(p)+'</li>').join('')+'</ul>'+(s.detail?'<div class="detail">'+esc(s.detail)+'</div>':'')+'</div></div>'});
 parts.push(['p-sec','章節'])}
if((C.cards||[]).length){h+='<h2 id="p-card">關鍵詞翻牌卡</h2><p>點一下卡片翻面。</p><div class="cards">'+C.cards.map(c=>
 '<div class="card" onclick="this.classList.toggle(\'flip\')"><div class="f"><div class="s a">'+esc(c.front)+'</div><div class="s b">'+esc(c.back)+'</div></div></div>').join('')+'</div>';
 parts.push(['p-card','翻牌卡'])}
if((C.faq||[]).length){h+='<h2 id="p-faq">常見問答</h2>'+C.faq.map(f=>'<details><summary>'+esc(f.q)+'</summary><p>'+esc(f.a)+'</p></details>').join('');parts.push(['p-faq','問答'])}
if((C.quiz||[]).length){h+='<h2 id="p-quiz">小測驗</h2><div id="qz"></div><p id="score"></p><div class="tools"><button onclick="resetQ()">重新作答</button></div>';parts.push(['p-quiz','測驗'])}
if(C.takeaway)h+='<div class="take">帶走一句話：'+esc(C.takeaway)+'</div>';
m.innerHTML=h;$('#nav').innerHTML=parts.map(p=>'<a href="#'+p[0]+'">'+p[1]+'</a>').join('');
function openAll(o){document.querySelectorAll('.sec').forEach(s=>s.classList.toggle('open',!!o))}
let got=0,done=0;
function resetQ(){got=0;done=0;$('#score').textContent='';$('#qz').innerHTML=(C.quiz||[]).map((q,i)=>'<div class="q" id="q'+i+'"><b>'+(i+1)+'. '+
 esc(q.q)+'</b>'+q.options.map((o,j)=>'<button class="opt" onclick="pick('+i+','+j+')">'+esc(o)+'</button>').join('')+'<div class="ex">'+esc(q.explain)+'</div></div>').join('')}
function pick(i,j){const d=$('#q'+i);if(d.classList.contains('done'))return;d.classList.add('done');const q=C.quiz[i],b=d.querySelectorAll('.opt');
 if(b[q.answer])b[q.answer].classList.add('ok');if(j!==q.answer)b[j].classList.add('bad');else got++;done++;
 $('#score').textContent='已作答 '+done+'／'+C.quiz.length+' 題，答對 '+got+' 題'+(done==C.quiz.length?'（'+Math.round(got*100/done)+' 分）':'')}
if((C.quiz||[]).length)resetQ();
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting)document.querySelectorAll('nav a').forEach(a=>
 a.classList.toggle('on',a.getAttribute('href')=='#'+e.target.id))}),{rootMargin:'-40% 0px -55% 0px'});
parts.forEach(p=>{const el=document.getElementById(p[0]);if(el)io.observe(el)});
"""


def webpage_html(content, style="pastel"):
    dark, main, accent, light, ink = style_of(style)["colors"]
    data = json.dumps(content, ensure_ascii=False).replace("</", "<\\/")
    return ("<!doctype html><html lang='zh-Hant-TW'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>%s</title><style>"
            ":root{--dark:%s;--main:%s;--accent:%s;--light:%s;--ink:%s}%s</style></head><body>"
            "<header><div class='in'><h1 id='t'></h1><p id='st'></p><div class='by' id='by'></div></div></header>"
            "<nav id='nav'></nav><main id='m'></main>"
            "<footer>由 資料助秘NotebookLM MCP簡報 產生　<span id='ft'></span></footer>"
            "<script>const C=%s;%s</script></body></html>"
            % (html.escape(content.get("title", "互動學習")), dark, main, accent, light, ink, WEBPAGE_CSS, data, WEBPAGE_JS))


# ================================================================ 一次輸出整組檔案
def export_bundle(kind, content, title, style="pastel"):
    """回傳 [(檔名, bytes)]：這種產出物的全部檔案。"""
    import tempfile
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", title).strip("_")[:60] or "成品"
    out = []
    tmp = tempfile.mkdtemp(prefix="nbexp_")

    def disk(name, fn, *a, **kw):
        p = os.path.join(tmp, name)
        fn(content, p, *a, **kw)
        with open(p, "rb") as f:
            out.append((name, f.read()))

    if kind == "SLIDES":
        disk(safe + ".pptx", slides_pptx, style)
        disk(safe + "_簡報大綱.docx", slides_outline_docx)
        disk(safe + "_QA作答卷.docx", qa_docx, False)
        disk(safe + "_QA解答.docx", qa_docx, True)
        out.append((safe + ".html", slides_html(content, style).encode("utf-8")))
        out.append((safe + "_大綱.txt", outline_text(content).encode("utf-8-sig")))
    elif kind == "MINDMAP":
        out.append((safe + ".png", mindmap_png(content)))
        out.append((safe + ".html", mindmap_html(content, title).encode("utf-8")))
        out.append((safe + ".md", mindmap_markdown(content["root"]).encode("utf-8")))
        out.append((safe + ".mm", mindmap_freemind(content).encode("utf-8")))
    elif kind == "REPORT":
        disk(safe + ".docx", report_docx)
        out.append((safe + ".md", report_markdown(content).encode("utf-8")))
        out.append((safe + ".html", report_html(content).encode("utf-8")))
    elif kind == "QUIZ":
        disk(safe + "_作答卷.docx", quiz_docx, False)
        disk(safe + "_解答.docx", quiz_docx, True)
        out.append((safe + ".html", quiz_html(content).encode("utf-8")))
    elif kind == "INFOGRAPHIC":
        out.append((safe + ".png", infographic_png(content, style)))
        out.append((safe + ".html", infographic_html(content, style).encode("utf-8")))
    elif kind == "WEBPAGE":
        out.append((safe + ".html", webpage_html(content, style).encode("utf-8")))
        out.append((safe + "_內容.json", json.dumps(content, ensure_ascii=False, indent=1).encode("utf-8")))
    return out


def bundle_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    return buf.getvalue()


def preview_pngs(kind, content, style="pastel", scale=0.5):
    """畫面預覽用的圖片清單。"""
    if kind == "SLIDES":
        s = content.get("slides", [])
        sizes = (content.get("cover") or {}).get("sizes") or (45, 40, 32)
        return [_scale(slide_png(x, i, len(s), style, sizes, topic_of(content)), scale) for i, x in enumerate(s)]
    if kind == "MINDMAP":
        return [mindmap_png(content, 0.6)]
    if kind == "INFOGRAPHIC":
        return [infographic_png(content, style, 0.6)]
    return []


def _scale(png, scale):
    if scale == 1.0:
        return png
    im = Image.open(io.BytesIO(png))
    return _png(im, scale)


KIND_FILES = {k: v[0] for k, v in KINDS.items()}
