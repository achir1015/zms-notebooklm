"""下載簡報小圖示：Microsoft Fluent Emoji 3D（MIT 授權，https://github.com/microsoft/fluentui-emoji）。

存到 assets/icons/<代號>.png（縮成 256×256）。已存在的略過。用法：python tools/fetch_icons.py
"""
import io
import os
import sys
import urllib.parse
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "assets", "icons")
BASE = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/"

# 代號: (資料夾名稱, 是否有膚色變化)
ICONS = {
    "droplet": ("Droplet", False), "thermometer": ("Thermometer", False), "soap": ("Soap", False),
    "gloves": ("Gloves", False), "mask": ("Face with medical mask", False), "paper": ("Roll of paper", False),
    "toilet": ("Toilet", False), "trash": ("Wastebasket", False), "lock": ("Locked", False),
    "bed": ("Bed", False), "nurse": ("Health worker", True), "hospital": ("Hospital", False),
    "microbe": ("Microbe", False), "shield": ("Shield", False), "warning": ("Warning", False),
    "noentry": ("No entry", False), "check": ("Check mark button", False), "cross": ("Cross mark", False),
    "megaphone": ("Megaphone", False), "magnifier": ("Magnifying glass tilted left", False),
    "clock": ("Alarm clock", False), "footprints": ("Footprints", False), "target": ("Bullseye", False),
    "toolbox": ("Toolbox", False), "fire": ("Fire", False), "extinguisher": ("Fire extinguisher", False),
    "lungs": ("Lungs", False), "tooth": ("Tooth", False), "bowl": ("Bowl with spoon", False),
    "bandage": ("Adhesive bandage", False), "heart": ("Red heart", False), "speech": ("Speech balloon", False),
    "globe": ("Globe with meridians", False), "books": ("Books", False), "star": ("Star", False),
    "bulb": ("Light bulb", False), "question": ("Red question mark", False), "hands": ("Folded hands", True),
    "smile": ("Smiling face with hearts", False), "arrows": ("Counterclockwise arrows button", False),
    "link": ("Link", False), "bathtub": ("Bathtub", False), "shower": ("Shower", False),
    "syringe": ("Syringe", False), "pill": ("Pill", False), "stethoscope": ("Stethoscope", False),
    "clipboard": ("Clipboard", False), "memo": ("Memo", False), "calendar": ("Calendar", False),
    "people": ("People hugging", False), "handshake": ("Handshake", False), "wave": ("Waving hand", True),
    "thumbsup": ("Thumbs up", True), "sparkles": ("Sparkles", False), "trophy": ("Trophy", False),
    "door": ("Door", False), "ladder": ("Ladder", False), "wheelchair": ("Manual wheelchair", False),
    "sponge": ("Sponge", False), "lotion": ("Lotion bottle", False), "basket": ("Basket", False),
    "teddy": ("Teddy bear", False), "bell": ("Bell", False), "phone": ("Telephone receiver", False),
    "pencil": ("Pencil", False), "graduation": ("Graduation cap", False), "school": ("School", False),
    "chart": ("Bar chart", False), "puzzle": ("Puzzle piece", False), "gear": ("Gear", False),
    "computer": ("Laptop", False), "money": ("Money bag", False), "house": ("House", False),
    "rocket": ("Rocket", False), "seedling": ("Seedling", False), "sun": ("Sun", False),
    "muscle": ("Flexed biceps", True), "eyes": ("Eyes", False), "ear": ("Ear", True), "brain": ("Brain", False),
    "toothbrush": ("Toothbrush", False), "scissors": ("Scissors", False), "ambulance": ("Ambulance", False),
    "car": ("Automobile", False), "coffee": ("Hot beverage", False), "apple": ("Red apple", False),
    "water": ("Potable water", False), "baby": ("Baby bottle", False), "key": ("Key", False),
    "folder": ("File folder", False), "pushpin": ("Pushpin", False), "flag": ("Triangular flag", False),
    "party": ("Party popper", False), "check2": ("Check box with check", False),
}


def url_for(folder, skin):
    name = folder.lower().replace(" ", "_")
    path = folder + ("/Default/3D/%s_3d_default.png" % name if skin else "/3D/%s_3d.png" % name)
    return BASE + urllib.parse.quote(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    bad = []
    for key, (folder, skin) in ICONS.items():
        dst = os.path.join(OUT, key + ".png")
        if os.path.isfile(dst):
            continue
        try:
            with urllib.request.urlopen(url_for(folder, skin), timeout=30) as r:
                im = Image.open(io.BytesIO(r.read())).convert("RGBA")
            im.thumbnail((256, 256), Image.LANCZOS)
            im.save(dst, optimize=True)
            print("ok", key)
        except Exception as e:
            bad.append((key, folder, str(e)[:60]))
    for b in bad:
        print("FAIL", *b)
    print("icons:", len(os.listdir(OUT)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
