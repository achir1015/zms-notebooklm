"""柔和插畫風簡報引擎（活潑、不枯燥）：奶油底、玫瑰棕標題、淡藍底線副標、白色膠囊重點＋彩虹編號、3D 小圖示。

比喻：每張投影片先由「排版師」算出版面（layout → 背景元素＋文字框），再交給兩位「印刷師」：
* png()：用 Pillow 把背景＋文字畫成預覽圖
* pptx()：背景（色塊、膠囊、圖示）做成一張圖片鋪底，文字放成可以編輯的文字框
兩邊用同一份版面，所以預覽和 PowerPoint 長得一樣。

小圖示：Microsoft Fluent Emoji 3D（MIT 授權，assets/icons，由 tools/fetch_icons.py 下載），依每個重點的關鍵字自動挑選。
版型依頁型自動選：封面、破題議程（環狀）、常見錯誤（紅綠對照）、關鍵詞（字卡）、總結、感謝問答、一般清單（左清單＋右大插圖）。
"""
import io
import os
import re

from PIL import Image, ImageDraw, ImageFilter

from .settings import resource_dir

W, H = 1280, 720
PX2PT = 0.75                      # 1280 px ＝ 13.333 吋 ＝ 960 pt

BG = (248, 241, 234)
TITLE = (190, 98, 96)             # 玫瑰棕
TITLE_DARK = (92, 58, 50)
SUB = (52, 102, 160)
SUB_HL = (190, 220, 244)
INK = (58, 52, 50)
MUTED = (120, 110, 105)
WHITE = (255, 255, 255)
RAINBOW = [(84, 150, 214), (226, 118, 140), (98, 184, 112), (236, 180, 60), (238, 138, 82), (150, 118, 208)]
PINK_BLOB = (246, 214, 212)
BLUE_BLOB = (214, 230, 246)

# ---------------------------------------------------------------- 小圖示：關鍵字 → 圖示代號
ICON_RULES = [
    (r"水溫|溫度|°C|度C|攝氏|發燒|體溫", "thermometer"), (r"溫水|沖洗|水|濕|擦拭液", "droplet"),
    (r"洗手|手部衛生|肥皂|乾洗手|酒精", "soap"), (r"手套", "gloves"), (r"口罩|隔離衣|防護", "mask"),
    (r"毛巾|紙巾|衛生紙|擦乾", "paper"), (r"便盆|尿布|如廁|排泄|大小便", "toilet"),
    (r"垃圾|丟棄|廢棄|回收|分類", "trash"), (r"隱私|圍簾|屏風", "lock"),
    (r"床|臥床|平躺|擺位|姿勢|病人", "bed"), (r"護理師|指導員|醫師|醫護|照服員|病房助理", "nurse"),
    (r"醫院|病房|院區|RCW|機構", "hospital"), (r"感染|細菌|病菌|病毒|微生物|交叉", "microbe"),
    (r"預防|保護|安全|管制|避免", "shield"), (r"注意|小心|危險|風險|警示", "warning"),
    (r"不可|禁止|不要|切勿|不能", "noentry"), (r"正確|✓|對的", "check"), (r"錯誤|✗|不對", "cross"),
    (r"報告|通報|告知|告訴|呼叫|立即", "megaphone"), (r"觀察|檢查|評估|確認|核對|辨識", "magnifier"),
    (r"時間|定時|小時|分鐘|每天|頻率|多久", "clock"), (r"步驟|流程|順序|方向|由前往後|由內往外", "footprints"),
    (r"目的|目標|為什麼|重要", "target"), (r"用物|準備|工具|器材|裝備|物品", "toolbox"),
    (r"火災|火|煙", "fire"), (r"滅火|逃生|疏散|避難|撤離|滑墊", "extinguisher"),
    (r"呼吸|氧氣|氣切|痰|抽吸|呼吸器|肺", "lungs"), (r"口腔|牙|漱口|刷牙", "toothbrush"),
    (r"灌食|餵食|鼻胃管|進食|營養|食物", "bowl"), (r"皮膚|壓傷|傷口|破皮|紅腫", "bandage"),
    (r"關心|舒適|尊嚴|愛|溫柔|安心", "heart"), (r"語言|母語|翻譯|印尼|越南|泰", "speech"),
    (r"學習|課程|教育|訓練|上課", "books"), (r"重點|總結|回顧|記住|口訣", "star"),
    (r"提示|技巧|訣竅|建議|小撇步", "bulb"), (r"問題|問答|Q&A|測驗|題", "question"),
    (r"感謝|謝謝|辛苦", "hands"), (r"翻身|轉動|輪流|循環", "arrows"), (r"約束|固定|扣帶|綁", "link"),
    (r"沐浴|洗澡|擦澡|泡澡", "bathtub"), (r"洗頭|淋浴", "shower"), (r"藥|給藥|服藥", "pill"),
    (r"注射|針", "syringe"), (r"聽診|生命徵象|血壓|脈搏", "stethoscope"), (r"紀錄|記錄|表單|簽", "clipboard"),
    (r"清單|檢核|勾選|核對表", "check2"), (r"日期|月份|排程|班表", "calendar"), (r"團隊|合作|分工|配合|一起", "people"),
    (r"家屬|溝通|說明|解釋", "handshake"), (r"示範|練習|實作|演練", "muscle"), (r"輪椅|移位|搬運", "wheelchair"),
    (r"海綿|棉棒|棉球|紗布", "sponge"), (r"乳液|潤膚|保濕|凡士林", "lotion"), (r"門|出口|通道|走道", "door"),
    (r"樓梯|下樓", "ladder"), (r"救護|緊急|急救", "ambulance"), (r"電話|聯絡", "phone"),
    (r"眼|看|視", "eyes"), (r"聽|耳", "ear"), (r"大腦|記憶|意識", "brain"), (r"成果|優秀|表揚", "trophy"),
    (r"行動呼籲|明天開始|出發", "rocket"), (r"成長|改善|品質提升", "seedling"), (r"保暖|溫暖", "sun"),
    (r"剪|修剪|指甲", "scissors"), (r"喝水|飲水", "water"), (r"按鈴|叫人鈴", "bell"),
]
GENERIC = ["sparkles", "star", "bulb", "pushpin", "check2", "heart", "flag", "seedling"]
_icon_cache = {}


def icon_img(key, size):
    k = (key, size)
    if k not in _icon_cache:
        p = os.path.join(resource_dir(), "assets", "icons", key + ".png")
        if not os.path.isfile(p):
            p = os.path.join(resource_dir(), "assets", "icons", "sparkles.png")
        if not os.path.isfile(p):
            _icon_cache[k] = None
        else:
            im = Image.open(p).convert("RGBA")
            _icon_cache[k] = im.resize((size, size), Image.LANCZOS)
    return _icon_cache[k]


def pick_icon(text, used=None, fallback=0):
    used = used if used is not None else set()
    hits = [key for pat, key in ICON_RULES if re.search(pat, text or "")]
    for key in hits:
        if key not in used:
            used.add(key)
            return key
    if hits:
        return hits[0]
    key = GENERIC[fallback % len(GENERIC)]
    return key


# ---------------------------------------------------------------- 字型與文字量測（泰文自動換字型）
_thai_cache = {}
THAI = re.compile(r"[\u0E00-\u0E7F]+")
_probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))


def font(px, bold=False):
    from .render import font as f
    return f(px, bold)


def thai_font(px, bold=False):
    from PIL import ImageFont
    k = (int(px), bold)
    if k not in _thai_cache:
        f = ImageFont.truetype(os.path.join(resource_dir(), "assets", "fonts", "NotoSansThai-VF.ttf"), int(px))
        try:
            f.set_variation_by_axes([700 if bold else 400, 100])
        except Exception:
            pass
        _thai_cache[k] = f
    return _thai_cache[k]


def runs(text):
    """把文字切成 (片段, 是否泰文)。"""
    out, pos = [], 0
    for m in THAI.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def tlen(text, px, bold):
    return sum(_probe.textlength(t, font=thai_font(px, bold) if th else font(px, bold)) for t, th in runs(text))


def draw_text(d, xy, text, px, bold, fill):
    x, y = xy
    for t, th in runs(text):
        f = thai_font(px, bold) if th else font(px, bold)
        d.text((x, y + (px * 0.08 if th else 0)), t, font=f, fill=fill)
        x += d.textlength(t, font=f)


NO_LINE_START = set("，。、）」』：；！？),.;:!?%")


def wrap(text, px, bold, width):
    lines = []
    for para in str(text).translate(str.maketrans({"✗": "×", "✓": "○"})).split("\n"):
        tokens = re.findall(r"[A-Za-z0-9@#%&+\-_./:'’\u0E00-\u0E7F]+|\s+|.", para)
        cur = ""
        for t in tokens:
            if tlen(cur + t, px, bold) <= width or not cur or t in NO_LINE_START:
                cur += t
            else:
                lines.append(cur.rstrip())
                cur = t.lstrip()
        lines.append(cur.rstrip())
    return lines or [""]


def fit(text, width, height, px, bold=False, min_px=14, spacing=1.3):
    """找出放得下的字級：回傳 (字級, 行數)。"""
    px = int(px)
    while px > min_px:
        lines = wrap(text, px, bold, width)
        if len(lines) * px * spacing <= height:
            return px, len(lines)
        px -= 2
    return min_px, len(wrap(text, min_px, bold, width))


class Layout:
    """一張投影片的版面：背景圖層（Pillow 直接畫）＋文字框清單。"""

    def __init__(self):
        self.bg = Image.new("RGBA", (W, H), BG + (255,))
        self.texts = []

    # 文字框：box=(x, y, w, h)
    def text(self, box, text, px, color=INK, bold=False, align="l", valign="t", min_px=14, spacing=1.3):
        x, y, w, h = box
        px, n = fit(text, w, h, px, bold, min_px, spacing)
        self.texts.append(dict(box=(int(x), int(y), int(w), int(h)), text=text, px=px, color=color, bold=bold,
                               align=align, valign=valign, spacing=spacing))
        return px, n

    # ---------------------------------------------------------- 背景元素
    def blob(self, xy, r, color, alpha=170):
        layer = Image.new("RGBA", (W, H), color + (0,))          # 透明部分用同色，模糊時才不會出現灰邊
        ImageDraw.Draw(layer).ellipse([xy[0] - r, xy[1] - r, xy[0] + r, xy[1] + r], fill=color + (alpha,))
        self.bg = Image.alpha_composite(self.bg, layer.filter(ImageFilter.GaussianBlur(6)))

    def shadow_box(self, box, radius, fill=WHITE, shadow=36, outline=None, width=2):
        x, y, w, h = box
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([x + 2, y + 6, x + w + 2, y + h + 6], radius=radius,
                                             fill=(120, 80, 70, shadow))
        self.bg = Image.alpha_composite(self.bg, sh.filter(ImageFilter.GaussianBlur(8)))
        d = ImageDraw.Draw(self.bg)
        d.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill if len(fill) == 4 else fill + (255,),
                            outline=outline, width=width if outline else 0)

    def circle_num(self, cx, cy, r, n, color):
        d = ImageDraw.Draw(self.bg)
        d.ellipse([cx - r, cy - r + 3, cx + r, cy + r + 3], fill=tuple(max(0, c - 40) for c in color) + (255,))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (255,), outline=WHITE + (255,), width=3)
        f = font(int(r * 1.1), True)
        t = str(n)
        d.text((cx - d.textlength(t, font=f) / 2, cy - f.size * 0.62), t, font=f, fill=WHITE)

    def icon(self, key, cx, cy, size, halo=None):
        im = icon_img(key, size)
        if im is None:
            return
        if halo:
            self.blob((cx, cy), int(size * 0.62), halo, 200)
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        a = im.split()[3].point(lambda v: v * 0.25)
        sh.paste((90, 60, 50, 255), (int(cx - size / 2 + 4), int(cy - size / 2 + 10)), a)
        self.bg = Image.alpha_composite(self.bg, sh.filter(ImageFilter.GaussianBlur(6)))
        self.bg.alpha_composite(im, (int(cx - size / 2), int(cy - size / 2)))

    def highlight(self, x, y, w, h, color=SUB_HL):
        d = ImageDraw.Draw(self.bg)
        d.rounded_rectangle([x - 8, y + h * 0.45, x + w + 8, y + h + 4], radius=int(h * 0.3), fill=color + (255,))

    # ---------------------------------------------------------- 輸出
    def png(self, scale=1.0):
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        for t in self.texts:
            x, y, w, h = t["box"]
            lines = wrap(t["text"], t["px"], t["bold"], w)
            lh = t["px"] * t["spacing"]
            total = len(lines) * lh
            yy = y + (h - total) / 2 if t["valign"] == "m" else y
            for ln in lines:
                tw = tlen(ln, t["px"], t["bold"])
                xx = x + (w - tw) / 2 if t["align"] == "c" else x
                draw_text(d, (xx, yy + (lh - t["px"]) / 2), ln, t["px"], t["bold"], t["color"])
                yy += lh
        im = im.convert("RGB")
        if scale != 1.0:
            im = im.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        return buf.getvalue()

    def bg_png(self):
        buf = io.BytesIO()
        self.bg.convert("RGB").save(buf, "PNG", optimize=True)
        return buf.getvalue()


# ================================================================ 版型
def decorate(L, seed=0):
    """四角柔和色塊（每頁位置略有不同，看起來不呆板）。"""
    corners = [((W + 40, -60), 230, PINK_BLOB), ((-80, H + 40), 220, BLUE_BLOB), ((W + 10, H + 70), 160, PINK_BLOB),
               ((-40, -50), 140, BLUE_BLOB)]
    for i, (xy, r, c) in enumerate(corners):
        if (i + seed) % 3 != 2:
            L.blob(xy, r, c, 150)


def head(L, title, sub, x=56, width=W - 112, center=False):
    """標題（玫瑰棕）＋副標（藍字淡藍底線）。回傳內容區起點 y。"""
    px, n = L.text((x, 34, width, 120), title, 46, TITLE, True, "c" if center else "l", min_px=28, spacing=1.2)
    y = 34 + int(n * px * 1.2) + 6
    if sub:
        spx, sn = fit(sub, width, 44, 26, True, 18)
        sw = min(width, tlen(wrap(sub, spx, True, width)[0], spx, True))
        sx = x + (width - sw) / 2 if center else x
        L.highlight(sx, y, sw, spx * 1.2)
        L.text((x, y, width, int(spx * 1.3 * sn) + 4), sub, spx, SUB, True, "c" if center else "l", min_px=18)
        y += int(spx * 1.3 * sn) + 14
    return y + 10


WEAK = {"footprints", "target", "toolbox", "warning", "question", "star", "books", "check", "cross", "nurse"}


def main_icon(s, topic, idx, used):
    """這一頁的大插圖：標題的具體名詞優先（滑墊→滅火器、口腔→牙刷），泛用圖示（腳印、標靶）最後才用。"""
    for src in (s.get("title") or "", " ".join(s.get("points", [])[:2]), topic, s.get("label") or ""):
        hits = [key for pat, key in ICON_RULES if re.search(pat, src)]
        strong = [h for h in hits if h not in WEAK]
        if strong:
            used.add(strong[0])
            return strong[0]
    return pick_icon((s.get("title") or "") + (s.get("label") or "") + topic, used, idx)


SUB_DEFAULTS = [(r"破題|議程", "今天一起學會這幾件事"), (r"目的|重要", "做對了，病人舒服、我們也安全"),
                (r"用物|準備", "齊全的工具，讓你不會手忙腳亂"), (r"步驟.*一|準備與擺位", "一步一步，慢慢來"),
                (r"步驟.*二", "動作要輕，方向要對"), (r"注意|安全|感染", "保護病人，也保護自己"),
                (r"錯誤", "找出錯誤，馬上改正"), (r"關鍵詞|母語", "聽得懂，做得對"),
                (r"總結|回顧|行動", "明天上班就開始做！"), (r"實作|演練", "做過一次，就會記得"),
                (r"情境", "如果是你，會怎麼做？"), (r"檢核|清單", "每天上班檢查一次"), (r"感謝|問答", "大家一起來複習")]


def subtitle_of(s):
    if s.get("subtitle"):
        return s["subtitle"]
    lab = s.get("label", "")
    for pat, text in SUB_DEFAULTS:
        if re.search(pat, lab):
            return text
    return lab if lab and lab not in s.get("title", "") else ""


def layout_cover(s, sizes, topic):
    L = Layout()
    L.blob((W + 30, -40), 260, PINK_BLOB, 160)
    L.blob((-60, H + 20), 250, BLUE_BLOB, 160)
    L.blob((-30, 120), 90, PINK_BLOB, 120)
    pts = s.get("points", [])
    tpx = int(sizes[0] / PX2PT)
    px, n = L.text((80, 40, W - 160, 210), s.get("title", ""), tpx, TITLE_DARK, True, "c", "m", min_px=34, spacing=1.2)
    y = 40 + 210 + 8
    if pts:
        spx, _ = fit(pts[0], W - 360, 60, int(sizes[1] / PX2PT * 0.75), True, 22)
        sw = min(W - 300, tlen(wrap(pts[0], spx, True, W - 360)[0], spx, True) + 70)
        L.shadow_box(((W - sw) / 2, y, sw, spx * 1.25 + 22), 22, (148, 196, 236), shadow=26)
        L.text(((W - sw) / 2, y + 8, sw, spx * 1.25 + 6), pts[0], spx, WHITE, True, "c", "m", min_px=20)
        y += spx * 1.25 + 40
    # 中間插圖：主題圖示在中央，左右是照顧者與醫院
    main = pick_icon(topic + (s.get("title") or ""), set(["hospital", "nurse"]))
    cy = int((y + H - 120) / 2) + 6
    L.blob((W / 2, cy + 10), 150, (255, 255, 255), 150)
    L.icon("nurse", W / 2 - 230, cy + 20, 150)
    L.icon(main if main not in ("nurse", "hospital") else "bed", W / 2, cy, 210)
    L.icon("hospital", W / 2 + 230, cy + 20, 150)
    if len(pts) > 1:
        by = H - 108
        grad = Image.new("RGBA", (W - 240, 74))
        gd = ImageDraw.Draw(grad)
        for i in range(W - 240):
            t = i / (W - 240)
            c = tuple(int(a + (b - a) * t) for a, b in zip((240, 178, 186), (160, 204, 240)))
            gd.line([(i, 0), (i, 74)], fill=c + (255,))
        mask = Image.new("L", grad.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, grad.size[0] - 1, 73], radius=37, fill=255)
        L.shadow_box((120, by, W - 240, 74), 37, WHITE, shadow=30)
        L.bg.paste(grad, (120, by), mask)
        L.text((150, by + 6, W - 300, 62), "　".join(pts[1:]), int(sizes[2] / PX2PT * 0.7), WHITE, True, "c", "m",
               min_px=18)
    return L


def layout_list(s, idx, topic):
    L = Layout()
    decorate(L, idx)
    pts = s.get("points", []) or [""]
    y0 = head(L, s.get("title", ""), subtitle_of(s), width=W - 470)
    used = set()
    main = main_icon(s, topic, idx, used)
    # 右側大插圖
    cx, cy = W - 230, int((y0 + H) / 2) + 10
    L.blob((cx, cy), 190, (255, 255, 255), 170)
    L.blob((cx + 40, cy + 50), 120, PINK_BLOB if idx % 2 else BLUE_BLOB, 140)
    L.icon(main, cx, cy - 10, 250)
    side = [pick_icon(p, used, idx + i + 1) for i, p in enumerate(pts)]
    if len(side) >= 2:
        L.icon(side[0], cx - 150, cy - 140, 90)
        L.icon(side[-1], cx + 140, cy + 130, 80)
    # 左側膠囊清單
    n = len(pts)
    avail = H - 40 - y0
    gap = 14
    ph = min(96, (avail - gap * (n - 1)) / max(n, 1))
    pw = W - 520
    for i, p in enumerate(pts):
        y = y0 + i * (ph + gap)
        L.shadow_box((56, y, pw, ph), int(min(ph / 2, 30)), WHITE, shadow=30)
        L.circle_num(56 + ph * 0.5, y + ph / 2, min(26, ph * 0.33), i + 1, RAINBOW[i % len(RAINBOW)])
        L.icon(side[i], 56 + ph * 0.5 + 52, y + ph / 2, int(min(52, ph * 0.62)))
        tx = 56 + ph * 0.5 + 92
        L.text((tx, y + 6, pw - (tx - 56) - 18, ph - 12), p, 27, INK, True, "l", "m", min_px=16)
    return L


def layout_agenda(s, idx, topic):
    L = Layout()
    decorate(L, idx)
    y0 = head(L, s.get("title", ""), subtitle_of(s))
    pts = s.get("points", [])[:6]
    cx, cy = W / 2, (y0 + H) / 2 + 10
    d = ImageDraw.Draw(L.bg)
    rx, ry = 330, (H - y0) / 2 - 46
    for a in range(0, 360, 6):                       # 虛線環
        import math
        t = math.radians(a)
        x, y = cx + rx * math.cos(t), cy + ry * math.sin(t)
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(200, 210, 230, 255))
    L.blob((cx, cy), 120, (255, 255, 255), 200)
    used = set()
    L.icon(main_icon(s, topic, idx, used), cx, cy, 190)
    import math
    n = max(len(pts), 1)
    for i, p in enumerate(pts):
        ang = math.radians(-90 + 360 * i / n)
        px_, py_ = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
        bw, bh = 400, 74
        bx = px_ + 20 if math.cos(ang) >= -0.01 else px_ - bw - 20
        if abs(math.cos(ang)) < 0.2:
            bx = px_ - bw / 2
        by = py_ - bh / 2
        bx = max(24, min(W - bw - 24, bx))
        L.shadow_box((bx, by, bw, bh), 31, WHITE, shadow=28)
        L.circle_num(bx + 32, by + bh / 2, 24, i + 1, RAINBOW[i % len(RAINBOW)])
        L.icon(pick_icon(p, used, i), bx + 86, by + bh / 2, 46)
        L.text((bx + 116, by + 6, bw - 130, bh - 12), p, 24, INK, True, "l", "m", min_px=15)
    return L


def split_pair(p):
    t = re.sub(r"^[✗×xX✘]\s*", "", p.strip())
    m = re.split(r"\s*(?:→|->|⇒)\s*", t, maxsplit=1)
    if len(m) == 2:
        w = re.sub(r"^(錯誤|錯)[：:]\s*", "", m[0]).strip()
        r = re.sub(r"^[✓○✔]\s*|^(正確|對)[：:]\s*", "", m[1]).strip()
        return w, r
    return None


def layout_compare(s, idx, topic):
    L = Layout()
    pairs, others = [], []
    for p in s.get("points", []):
        sp = split_pair(p)
        (pairs.append(sp) if sp else others.append(p))
    # 左紅右綠底
    left = Image.new("RGBA", (W // 2, H))
    right = Image.new("RGBA", (W - W // 2, H))
    for img, c1, c2 in ((left, (236, 196, 184), (226, 150, 144)), (right, (204, 232, 208), (226, 214, 190))):
        gd = ImageDraw.Draw(img)
        for x in range(img.size[0]):
            t = x / img.size[0]
            gd.line([(x, 0), (x, H)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)) + (255,))
    L.bg.paste(left, (0, 0))
    L.bg.paste(right, (W // 2, 0))
    y0 = head(L, s.get("title", ""), subtitle_of(s) or "找出錯誤，馬上改正", width=W - 112)
    L.icon("cross", W // 4, y0 + 40, 90)
    L.icon("check", W * 3 // 4, y0 + 40, 90)
    rows = pairs or [(p, "") for p in others]
    n = max(len(rows), 1)
    top = y0 + 100
    bottom = H - (96 if others and pairs else 30)
    rh = min(100, (bottom - top) / n)
    used = set()
    for i, (w, r) in enumerate(rows):
        y = top + i * rh
        for x0, txt, mark, col in ((40, w, "cross", (196, 60, 60)), (W // 2 + 40, r, "check", (40, 130, 70))):
            if not txt:
                continue
            L.shadow_box((x0, y + 6, W // 2 - 80, rh - 14), 22, (255, 255, 255, 225), shadow=22)
            L.icon(pick_icon(txt, used, i) if mark == "check" else mark, x0 + 40, y + rh / 2 - 1, int(min(46, rh * 0.5)))
            L.text((x0 + 76, y + 10, W // 2 - 170, rh - 22), txt, 24, col, True, "l", "m", min_px=14)
    if others and pairs:
        txt = "　".join(others)
        L.shadow_box((40, H - 86, W - 80, 64), 32, (255, 246, 230), shadow=28)
        L.icon("megaphone", 90, H - 54, 54)
        L.text((130, H - 80, W - 200, 52), txt, 24, (150, 70, 40), True, "l", "m", min_px=14)
    return L


def layout_terms(s, idx, topic):
    L = Layout()
    decorate(L, idx)
    y0 = head(L, s.get("title", ""), subtitle_of(s) or "聽得懂，做得對", center=True)
    pts = s.get("points", [])[:8]
    n = max(len(pts), 1)
    cols = 2 if n > 3 else 1
    rows = (n + cols - 1) // cols
    cw = (W - 120 - 30 * (cols - 1)) / cols
    ch = min(120, (H - 30 - y0 - 16 * (rows - 1)) / rows)
    used = set()
    for i, p in enumerate(pts):
        r, c = divmod(i, cols)
        x, y = 60 + c * (cw + 30), y0 + r * (ch + 16)
        L.shadow_box((x, y, cw, ch), 24, WHITE, shadow=26)
        term, _, rest = p.partition("：")
        L.icon(pick_icon(term, used, i), x + ch * 0.45, y + ch / 2, int(ch * 0.6))
        L.text((x + ch * 0.9, y + 8, cw - ch, ch * 0.42), term, 30, TITLE, True, "l", "m", min_px=16)
        langs = rest.replace("｜", "  ·  ") if rest else ""
        L.text((x + ch * 0.9, y + ch * 0.46, cw - ch - 16, ch * 0.5), langs, 19, SUB, False, "l", "t", min_px=12)
    return L


def layout_summary(s, idx, topic):
    L = Layout()
    decorate(L, idx)
    y0 = head(L, s.get("title", ""), subtitle_of(s) or "每一次都不能忘記的事", center=True)
    for i in range(4):
        L.icon("star", W / 2 - 165 + i * 110, y0 + 46, 84)
    pts = s.get("points", [])[:6]
    n = max(len(pts), 1)
    cols = 2 if n > 2 else 1
    rows = (n + cols - 1) // cols
    top = y0 + 108
    cw = (W - 120 - 30 * (cols - 1)) / cols
    ch = min(110, (H - 30 - top - 16 * (rows - 1)) / rows)
    used = {"star"}
    tints = [(253, 232, 232), (226, 238, 250), (232, 246, 232), (252, 244, 222)]
    for i, p in enumerate(pts):
        r, c = divmod(i, cols)
        x, y = 60 + c * (cw + 30), top + r * (ch + 16)
        L.shadow_box((x, y, cw, ch), 26, tints[i % 4], shadow=24)
        L.icon(pick_icon(p, used, i), x + 52, y + ch / 2, int(min(70, ch * 0.7)))
        L.text((x + 100, y + 8, cw - 120, ch - 16), p, 24, INK, True, "l", "m", min_px=14)
    return L


def layout_thanks(s, idx, topic):
    L = Layout()
    L.blob((W + 30, -40), 260, PINK_BLOB, 170)
    L.blob((-60, H + 20), 250, BLUE_BLOB, 170)
    L.text((80, 50, W - 160, 90), s.get("title", "感謝聆聽"), 58, TITLE_DARK, True, "c", "m", min_px=30)
    L.text((80, 140, W - 160, 40), subtitle_of(s) or "大家一起來複習", 26, SUB, True, "c", "m", min_px=16)
    pts = s.get("points", [])[:5]
    used = set()
    for i, p in enumerate(pts):
        bw = 620
        x = W / 2 - bw / 2 + (-80 if i % 2 == 0 else 80)
        y = 200 + i * 92
        col = (250, 214, 216) if i % 2 == 0 else (200, 224, 246)
        L.shadow_box((x, y, bw, 72), 24, col, shadow=24)
        d = ImageDraw.Draw(L.bg)
        tail = [(x + 40, y + 70), (x + 70, y + 70), (x + 34, y + 92)] if i % 2 == 0 else \
            [(x + bw - 40, y + 70), (x + bw - 70, y + 70), (x + bw - 34, y + 92)]
        d.polygon(tail, fill=col + (255,))
        L.icon(pick_icon(p, used, i), x + 40, y + 36, 44)
        L.text((x + 74, y + 8, bw - 96, 56), p, 22, INK, True, "l", "m", min_px=13)
    L.icon("nurse", 130, H - 110, 170)
    L.icon("wave", 260, H - 190, 80)
    L.icon("question", W - 140, H - 120, 150)
    L.icon("bulb", W - 270, 230, 70)
    return L


def layout_for(s, idx, total, topic="", sizes=(45, 40, 32)):
    lab = (s.get("label") or "") + " " + (s.get("title") or "")
    pts = s.get("points", [])
    if s.get("kind") == "cover" or idx == 0:
        return layout_cover(s, sizes, topic)
    if idx == total - 1 and re.search(r"感謝|問答|Q&A", lab):
        return layout_thanks(s, idx, topic)
    if re.search(r"關鍵詞|母語|詞彙", lab):
        return layout_terms(s, idx, topic)
    if re.search(r"錯誤|正確做法", lab) or (pts and sum(1 for p in pts if split_pair(p)) >= max(2, len(pts) // 2)):
        return layout_compare(s, idx, topic)
    if re.search(r"破題|議程|大綱|今天", lab) and 3 <= len(pts) <= 6:
        return layout_agenda(s, idx, topic)
    if re.search(r"總結|回顧|重點整理|行動呼籲", lab):
        return layout_summary(s, idx, topic)
    return layout_list(s, idx, topic)


# ================================================================ 對外介面
def slide_png(s, idx, total, sizes=(45, 40, 32), topic="", scale=1.0):
    return layout_for(s, idx, total, topic, sizes).png(scale)


def pptx(content, path, topic=""):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Emu, Pt

    from .render import CJK_FONT
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    k = 12192000 / W                                    # 每像素 EMU
    sizes = (content.get("cover") or {}).get("sizes") or (45, 40, 32)
    slides = content.get("slides", [])
    for idx, s in enumerate(slides):
        L = layout_for(s, idx, len(slides), topic, sizes)
        sl = prs.slides.add_slide(prs.slide_layouts[6])
        sl.shapes.add_picture(io.BytesIO(L.bg_png()), 0, 0, prs.slide_width, prs.slide_height)
        for t in L.texts:
            x, y, w, h = t["box"]
            tb = sl.shapes.add_textbox(Emu(int(x * k)), Emu(int(y * k)), Emu(int(w * k)), Emu(int(h * k)))
            tf = tb.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE if t["valign"] == "m" else MSO_ANCHOR.TOP
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if t["align"] == "c" else PP_ALIGN.LEFT
            p.line_spacing = t["spacing"] * 0.92
            r = p.add_run()
            r.text = t["text"]
            r.font.size = Pt(round(t["px"] * PX2PT * 0.96, 1))     # 正黑體比思源黑體略寬，縮一點點免得換行不同
            r.font.bold = t["bold"]
            r.font.color.rgb = RGBColor(*t["color"][:3])
            r.font.name = CJK_FONT
            rpr = r._r.get_or_add_rPr()
            rpr.append(rpr.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}ea",
                                       {"typeface": CJK_FONT}))
        if s.get("notes"):
            sl.notes_slide.notes_text_frame.text = s["notes"]
    prs.core_properties.title = slides[0]["title"] if slides else ""
    prs.core_properties.author = "資料助秘NotebookLM MCP簡報"
    prs.save(path)
    return path
