"""Fortnite Cosmetics Browser - a fast Windows app for every Fortnite cosmetic, the daily Item Shop
and a Sprite collection tracker.

Made by 248Tech - https://248tech.com
Source: https://github.com/248Tech/fortnite-cosmetics-browser (MIT License)

Data and images come from the community API at https://fortnite-api.com. No Epic account or login needed.
Fortnite is a trademark of Epic Games, Inc. This project is not affiliated with or endorsed by Epic Games.
Requires: Python 3.10+ and Pillow.
"""
import csv
import gzip
import hashlib
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.parse
import urllib.request
import webbrowser
from bisect import bisect_right
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFilter, ImageTk, features

__version__ = "1.1.0"
APP_NAME = "Fortnite Cosmetics Browser"
REPO_URL = "https://github.com/248Tech/fortnite-cosmetics-browser"

API_COSMETICS = "https://fortnite-api.com/v2/cosmetics/br"
API_SHOP = "https://fortnite-api.com/v2/shop"
SPRITES_URL = "https://248tech.github.io/fortnite-cosmetics-browser/data/sprites.json"
WEAPONS_URL = "https://248tech.github.io/fortnite-cosmetics-browser/data/weapons.json"
MAP_URL = "https://248tech.github.io/fortnite-cosmetics-browser/data/map.json"
NEWS_URL = "https://248tech.github.io/fortnite-cosmetics-browser/data/news.json"
USER_AGENT = f"FortniteCosmeticsBrowser/{__version__} (+{REPO_URL})"

CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FortniteCosmeticsBrowser"
DATA_FILE = CACHE_DIR / "cosmetics_br.json"
SHOP_FILE = CACHE_DIR / "shop.json"
SETTINGS_FILE = CACHE_DIR / "settings.json"
SPRITES_FILE = CACHE_DIR / "sprites.json"
WEAPONS_FILE = CACHE_DIR / "weapons.json"
MAP_FILE = CACHE_DIR / "map.json"
NEWS_FILE = CACHE_DIR / "news.json"
MAP_DIR = CACHE_DIR / "map"  # tile + icon cache
PROGRESS_FILE = CACHE_DIR / "sprite_progress.json"
SPRITE_IMG_FILE = CACHE_DIR / "sprite_images.json"
SPRITE_IMG_DIR = CACHE_DIR / "sprite_images"  # user-supplied art: <id>.png / <id>_<variant>.png
WIKI_API = "https://fortnite.fandom.com/api.php"
API_NEWS_BR = "https://fortnite-api.com/v2/news/br"
SPRITE_IMG_MAX_AGE = 6 * 3600
THUMB_DIR = CACHE_DIR / "thumbs"
MAX_DATA_AGE = 12 * 3600
PHOTO_CACHE_MAX = 1500
IMG_EXT = "webp" if features.check("webp") else "png"

# palette - matches Fortnite.GG (dark greys, yellow accent)
BG = "#2f3136"
SIDEBAR = "#202225"
PANEL = "#232428"
PANEL_HOVER = "#2b2d31"
PANEL_2 = "#18191c"
LINE = "#3a3c42"
HOVER = "#36393f"
FG = "#ffffff"
FG_2 = "#dcddde"
MUTED = "#b9bbbe"
MUTED_2 = "#8e9297"
ACCENT = "#fce51e"     # Fortnite.GG yellow
ACCENT_FG = "#111111"  # text on yellow
GREEN = "#6ee959"
RED = "#ee4245"
GOLD = "#fce51e"
DISPLAY_FONT = "Bahnschrift SemiBold Condensed"  # heavy condensed, close to the site's look

RARITY_COLORS = {
    "common": "#7d838d", "uncommon": "#4f9a33", "rare": "#2f7fd6",
    "epic": "#9645d6", "legendary": "#d47a24", "mythic": "#c9a52f",
    "exotic": "#2fb4c6", "transcendent": "#c33f62", "marvel": "#c22f2c",
    "dc": "#2a58ad", "icon": "#279c94", "gaminglegends": "#5243c9",
    "starwars": "#26307f", "dark": "#94208e", "frozen": "#6fb0dc",
    "lava": "#bd4a28", "shadow": "#45454e", "slurp": "#1fa9b9",
}
# Fortnite.GG sprite card colours: rarity chip (bg, fg) and top-of-card gradient
SPRITE_CHIPS = {"common": ("#40464d", "#b7bfc5"), "rare": ("#00458a", "#00fffb"), "epic": ("#4c197b", "#ec27ff"),
                "legendary": ("#8a3c1e", "#fbc363"), "mythic": ("#7c5d26", "#fff0a6")}
SPRITE_THEMES = {"common": "#3a3f45", "rare": "#104273", "epic": "#4d1566", "legendary": "#743e0a", "mythic": "#a89442"}
FGG_SPRITES = "https://fortnite.gg/sprites"
FGG_ICON = "https://fortnite.gg/img/x/sprites/icons/T_Icon_BR_Creature_Sprite_{name}{suffix}_L.webp"
RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary", "mythic",
                "exotic", "transcendent"]
SORTS = ["Newest", "Oldest", "Name A-Z", "Name Z-A", "Rarity (high-low)", "Rarity (low-high)"]
TILE_SIZES = {"S": 92, "M": 116, "L": 150}
MIN_CATEGORY = 20  # types with fewer items are grouped under "Other"
MODES = ("browse", "shop", "sprites", "weapons", "map", "news")
FN_NEWS = "https://www.fortnite.com/news?lang=en-US"
FGG_NEWS = "https://fortnite.gg/news"
FGG_MAP = "https://fortnite.gg/"
MAP_OCEAN = "#0f3b57"
WEAPON_POOLS = ["Current loot pool", "All weapons"]
WEAPON_SORTS = ["Class", "Name", "Damage", "DPS", "Fire rate", "Magazine", "Reload", "Chest chance"]
WEAPON_SORT_KEYS = {"Damage": ("dmg", -1), "DPS": ("dps", -1), "Fire rate": ("rate", -1), "Magazine": ("mag", -1),
                    "Reload": ("reload", 1)}
# (key, label, unit, lower_is_better)
WEAPON_STATS = [("dmg", "Damage", "", False), ("head", "Headshot damage", "", False), ("dps", "DPS", "", False),
                ("rate", "Fire rate", "/s", False), ("mag", "Magazine", "", False), ("reload", "Reload", "s", True),
                ("struct", "Structure damage", "", False), ("spread", "Spread", "", True),
                ("vrecoil", "Vertical recoil", "", True), ("hrecoil", "Horizontal recoil", "", True),
                ("ads", "Aim down sights", "s", True)]
FGG_WEAPON = "https://fortnite.gg/weapons/weapon/{slug}?mode=battle-royale"

RADIUS = 10  # rescaled for DPI at startup

# fortnite.com item pages: /item-shop/<category>/<name-slug>-<md5("Backend:id")[-8:]>
EPIC_SHOP = "https://www.fortnite.com/item-shop"
EPIC_CATEGORIES = {  # verified URL segments
    "AthenaCharacter": "outfits", "AthenaDance": "emotes", "AthenaItemWrap": "wraps",
    "CosmeticShoes": "kicks", "AthenaSkyDiveContrail": "contrails",
}
EPIC_ASSET_TYPES = {"CosmeticShoes": "Kicks"}  # site naming differs from the API


def web_slug(name):
    n = name.lower()
    n = re.sub(r"[^a-z0-9\s]", "", n)
    return re.sub(r"\s+", "-", n.strip())


def epic_item_url(it):
    backend = it.get("backend") or ""
    cat = EPIC_CATEGORIES.get(backend)
    if cat and it["name"] != it["id"] and web_slug(it["name"]):
        h = hashlib.md5(f"{backend}:{it['id'].lower()}".encode("utf-8")).hexdigest()[-8:]
        return f"{EPIC_SHOP}/{cat}/{web_slug(it['name'])}-{h}?lang=en-US"
    q = {"assetType": EPIC_ASSET_TYPES.get(backend, it["type"]), "itemNotAvailable": "true",
         "title": it["name"], "lang": "en-US"}
    return f"{EPIC_SHOP}?{urllib.parse.urlencode(q)}"


def find_chrome():
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as k:
                    path = winreg.QueryValue(k, None)
                    if path and os.path.exists(path):
                        return path
            except OSError:
                pass
    except ImportError:
        pass
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            path = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.exists(path):
                return path
    return None


# ---------------------------------------------------------------- helpers
def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data


def url_key(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def thumb_path(url, store):
    return THUMB_DIR / f"{url_key(url)}_{store}.{IMG_EXT}"


def hex_rgb(h):
    h = h.lstrip("#")[:6]
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def shade(color, f):
    """f > 0 lightens toward white, f < 0 darkens."""
    rgb = hex_rgb(color)
    if f >= 0:
        return rgb_hex(tuple(c + (255 - c) * f for c in rgb))
    return rgb_hex(tuple(c * (1 + f) for c in rgb))


def rarity_color(key):
    return RARITY_COLORS.get(key, "#5d6270")


def rarity_bg(key):
    c = rarity_color(key)
    return (shade(c, 0.22), shade(c, -0.5))


def rarity_rank(key):
    return RARITY_ORDER.index(key) if key in RARITY_ORDER else len(RARITY_ORDER)


def parse_dt(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def fmt_remaining(seconds):
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


_grad_cache = {}
_mask_cache = {}


def radial_bg(colors, size):
    key = (colors, size)
    g = _grad_cache.get(key)
    if g is None:
        center, edge = colors
        mask = Image.radial_gradient("L").resize((size, size), Image.BILINEAR)
        g = Image.composite(Image.new("RGBA", (size, size), hex_rgb(edge) + (255,)),
                            Image.new("RGBA", (size, size), hex_rgb(center) + (255,)), mask)
        _grad_cache[key] = g
    return g.copy()


def linear_bg(top, bottom, size):
    key = ("lin", top, bottom, size)
    g = _grad_cache.get(key)
    if g is None:
        t, b = hex_rgb(top), hex_rgb(bottom)
        col = Image.new("RGBA", (1, size))
        for y in range(size):
            k = min(1.0, y / max(1, size - 1) * 1.15)
            col.putpixel((0, y), tuple(int(t[i] + (b[i] - t[i]) * k) for i in range(3)) + (255,))
        g = _grad_cache[key] = col.resize((size, size))
    return g.copy()


def card_bg(bg, size):
    """bg: (center, edge) radial, or ("lin", top, bottom) linear; optional trailing "dim"."""
    if bg[0] == "lin":
        return linear_bg(bg[1], bg[2], size)
    return radial_bg(tuple(bg[:2]), size)


def round_mask(size, corners):
    key = (size, corners)
    m = _mask_cache.get(key)
    if m is None:
        r = RADIUS
        extra = r if corners == "top" else 0
        m = Image.new("L", (size, size + extra), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size + extra - 1), r, fill=255)
        m = m.crop((0, 0, size, size))
        _mask_cache[key] = m
    return m


def load_stored(url, store):
    """Return (RGBA image <= store px, newly_downloaded). Disk-cached as resized thumbnails."""
    if url.startswith("local:"):  # user-supplied file, never cached
        im = Image.open(url[6:].rsplit("?", 1)[0]).convert("RGBA")
        im.thumbnail((store, store), Image.LANCZOS)
        return im, False
    path = thumb_path(url, store)
    if path.exists():
        try:
            im = Image.open(path)
            im.load()
            return im.convert("RGBA"), False
        except Exception:
            path.unlink(missing_ok=True)
    data = http_get(url, timeout=30)
    im = Image.open(BytesIO(data)).convert("RGBA")
    if max(im.size) > store:
        im.thumbnail((store, store), Image.LANCZOS)
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    if IMG_EXT == "webp":
        im.save(tmp, "WEBP", quality=90, method=4)
    else:
        im.save(tmp, "PNG", optimize=True)
    os.replace(tmp, path)
    return im, True


def compose(im, disp, bg, corners):
    w, h = im.size
    r = min(disp / w, disp / h)
    im = im.resize((max(1, round(w * r)), max(1, round(h * r))), Image.LANCZOS)
    if not bg:
        return im
    base = card_bg(bg, disp)
    base.alpha_composite(im, ((disp - im.width) // 2, (disp - im.height) // 2))
    if bg[-1] == "dim":  # e.g. a sprite you haven't captured
        base = Image.blend(base, Image.new("RGBA", base.size, hex_rgb(PANEL) + (255,)), 0.6)
    if corners:
        base.putalpha(round_mask(disp, corners))
    return base


def make_icon(size=256):
    """App icon: rounded square with a sparkle, drawn at 4x then downsampled."""
    s = size * 4
    im = Image.composite(
        Image.new("RGBA", (s, s), hex_rgb("#4a1f9e") + (255,)),
        Image.new("RGBA", (s, s), hex_rgb("#6fa0ff") + (255,)),
        Image.radial_gradient("L").resize((s, s), Image.BILINEAR))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), int(s * 0.22), fill=255)
    im.putalpha(mask)
    d = ImageDraw.Draw(im)

    def sparkle(cx, cy, big, small, fill):
        pts = []
        for k in range(8):
            ang = math.pi / 4 * k - math.pi / 2
            rad = big if k % 2 == 0 else small
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        d.polygon(pts, fill=fill)

    sparkle(s * 0.46, s * 0.54, s * 0.33, s * 0.085, (255, 255, 255, 255))
    sparkle(s * 0.76, s * 0.25, s * 0.12, s * 0.035, hex_rgb(GOLD) + (255,))
    return im.resize((size, size), Image.LANCZOS)


def round_rect(c, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


# ---------------------------------------------------------------- data
def normalize_cosmetics(raw):
    out = []
    for c in raw:
        t = c.get("type") or {}
        r = c.get("rarity") or {}
        s = c.get("set") or {}
        intro = c.get("introduction") or {}
        imgs = c.get("images") or {}
        cid = c.get("id", "")
        name = (c.get("name") or "").strip()
        if name.lower() in ("", "null", "tbd"):
            name = cid
        tname = (t.get("displayValue") or "").strip()
        if tname.lower() in ("", "null"):
            tname = "Unknown"
        desc = (c.get("description") or "").strip()
        if desc.lower() == "null":
            desc = ""
        it = {
            "key": cid, "id": cid, "name": name, "description": desc, "type": tname,
            "rarity": r.get("displayValue") or "Unknown",
            "rarity_key": (r.get("value") or "").lower(),
            "backend": t.get("backendValue") or "",
            "set": s.get("value") or "", "intro": intro.get("text") or "",
            "added": c.get("added") or "",
            "small": imgs.get("smallIcon") or imgs.get("icon") or "",
            "icon": imgs.get("icon") or imgs.get("featured") or imgs.get("smallIcon") or "",
            "featured": imgs.get("featured") or imgs.get("icon") or "",
        }
        it["search"] = " ".join([name, cid, it["set"], tname, it["rarity"]]).lower()
        out.append(it)
    return out


def normalize_shop(data):
    entries = []
    for e in data.get("entries") or []:
        br = e.get("brItems") or []
        tracks = e.get("tracks") or []
        cars = e.get("cars") or []
        inst = e.get("instruments") or []
        bundle = e.get("bundle") or {}
        renders = (e.get("newDisplayAsset") or {}).get("renderImages") or []
        first = (br or cars or inst or [None])[0] or {}
        title = bundle.get("name") or first.get("name") or (tracks[0].get("title") if tracks else "") or "Offer"

        image = bundle.get("image") or (renders[0].get("image") if renders else "")
        if not image and br:
            im = br[0].get("images") or {}
            image = im.get("featured") or im.get("icon") or im.get("smallIcon") or ""
        if not image and (cars or inst):
            image = ((cars or inst)[0].get("images") or {}).get("large") or ""
        if not image and tracks:
            image = tracks[0].get("albumArt") or ""

        rkey = ((first.get("rarity") or {}).get("value") or "").lower()
        colors = e.get("colors") or {}
        if colors.get("color1"):
            bg = ("#" + colors["color1"][:6], "#" + (colors.get("color3") or colors.get("color2") or colors["color1"])[:6])
            bg = (shade(bg[0], -0.1), shade(bg[1], -0.35))
        elif tracks:
            bg = ("#3a3150", "#17141f")
        else:
            bg = rarity_bg(rkey)

        contents = []
        for x in br:
            contents.append({"kind": "br", "id": x.get("id"),
                             "name": x.get("name") if (x.get("name") or "").lower() not in ("", "null") else x.get("id"),
                             "type": (x.get("type") or {}).get("displayValue") or "Item"})
        for x in cars:
            contents.append({"kind": "car", "id": x.get("id"), "name": x.get("name"),
                             "type": (x.get("type") or {}).get("displayValue") or "Car"})
        for x in inst:
            contents.append({"kind": "instrument", "id": x.get("id"), "name": x.get("name"),
                             "type": (x.get("type") or {}).get("displayValue") or "Instrument"})
        for x in tracks:
            contents.append({"kind": "track", "id": x.get("id"), "name": x.get("title"),
                             "type": "Jam Track", "artist": x.get("artist"),
                             "year": x.get("releaseYear"), "bpm": x.get("bpm"),
                             "duration": x.get("duration")})

        if bundle:
            kind = f"Bundle · {len(contents)} items"
        elif tracks:
            kind = f"Jam Track · {tracks[0].get('artist') or ''}".strip(" ·")
        else:
            kind = contents[0]["type"] if contents else "Offer"

        layout = e.get("layout") or {}
        section = (layout.get("name") or "").strip() or "More Offers"
        sindex = layout.get("index") if layout.get("index") is not None else 999
        banner = (e.get("banner") or {})
        it = {
            "key": e.get("offerId") or e.get("devName"), "offer_id": e.get("offerId") or "",
            "name": title, "kind": kind, "image": image, "bg": bg, "rarity_key": rkey,
            "final": e.get("finalPrice") or 0, "regular": e.get("regularPrice") or 0,
            "banner": banner.get("value") or "", "banner_hot": banner.get("intensity") == "High",
            "out": parse_dt(e.get("outDate") or ""), "giftable": bool(e.get("giftable")),
            "section": section, "sindex": sindex, "sort": e.get("sortPriority") or 0,
            "contents": contents,
        }
        it["search"] = " ".join([title, kind, section] + [c["name"] or "" for c in contents]).lower()
        entries.append(it)

    by_section = OrderedDict()
    for it in sorted(entries, key=lambda x: (x["sindex"], x["section"].lower())):
        by_section.setdefault(it["section"], []).append(it)
    for items in by_section.values():
        items.sort(key=lambda x: (-x["sort"], -x["final"]))
    date = parse_dt(data.get("date") or "") or datetime.now(timezone.utc)
    return {"date": date, "reset": date + timedelta(days=1), "vbuck": data.get("vbuckIcon") or "",
            "sections": by_section, "entries": entries}


# ---------------------------------------------------------------- sprites
# Epic has no public Sprite API, so the catalog is a hand-maintained JSON file published with the
# web demo (docs/data/sprites.json). New sprites, variants and seasons are data changes only.
SPRITE_RARITIES = ["rare", "epic", "legendary", "mythic"]
SPRITE_FILTERS = ["All", "Missing", "Owned", "Mastered", "Not mastered"]
SPRITE_SORTS = ["Default", "Name A-Z", "Rarity (high-low)", "Missing first", "Owned first"]


def bundled_sprites_path():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for p in (base / "sprites.json", base / "docs" / "data" / "sprites.json"):
        if p.exists():
            return p
    return None


def is_out(day):
    """True when a YYYY-MM-DD release date is today or earlier (or not set)."""
    return not day or day <= date.today().isoformat()


def fmt_day(day):
    try:
        d = date.fromisoformat(day)
        return f"{d:%b} {d.day}"
    except Exception:
        return day or ""


def normalize_sprites(data):
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("unsupported sprite data")
    variants = OrderedDict()
    for v in data.get("variants") or []:
        if v.get("id"):
            variants[v["id"]] = {"id": v["id"], "name": v.get("name") or v["id"].title(),
                                 "color": v.get("color") or GOLD, "description": v.get("description") or "",
                                 "release": v.get("releaseDate") or "", "fgg": v.get("fgg") or "",
                                 "theme": v.get("theme") or v.get("color") or GOLD}
    seasons = []
    for se in data.get("seasons") or []:
        sprites = []
        for sp in se.get("sprites") or []:
            if not sp.get("id"):
                continue
            rk = (sp.get("rarity") or "rare").lower()
            vids = [v for v in sp.get("variants") or [] if v in variants]
            upcoming = [v for v in sp.get("upcoming") or [] if v in variants and v not in vids]
            it = {
                "key": f"{se['id']}:{sp['id']}", "id": sp["id"], "season": se["id"],
                "name": sp.get("name") or sp["id"], "rarity_key": rk, "rarity": rk.title(),
                "color": sp.get("color") or rarity_color(rk), "ability": sp.get("ability") or "",
                "where": sp.get("where") or "", "release": sp.get("releaseDate") or "",
                "variants": vids, "upcoming": upcoming,
                "image": sp.get("image") or "", "images": sp.get("images") or {},
                "wiki": sp.get("wiki") or "", "fgg": sp.get("fgg") or "",
            }
            it["search"] = " ".join([it["name"], it["id"], it["rarity"], it["ability"]]
                                    + [variants[v]["name"] for v in vids]).lower()
            sprites.append(it)
        seasons.append({"id": se["id"], "name": se.get("name") or se["id"],
                        "label": se.get("label") or se.get("name") or se["id"],
                        "version": se.get("version") or "", "start": se.get("start") or "",
                        "how": se.get("howToGet") or "", "sprites": sprites})
    if not seasons:
        raise ValueError("no seasons in sprite data")
    ids = [s["id"] for s in seasons]
    return {"seasons": seasons, "current": data.get("current") if data.get("current") in ids else ids[-1],
            "variants": variants, "dust": data.get("dustCost") or {}, "updated": data.get("updated") or ""}


class SpriteProgress:
    """Per-user tracking, one Owned/Mastered pair per card (base sprite or variant):
    {season: {sprite: {captured, mastered, variants: {variant: true}, vmastered: {variant: true}}}}.

    Keyed by variant id, so variants added to the catalog later are tracked with no code change.
    The export format is shared with the web demo."""

    EMPTY = {"captured": False, "mastered": False, "variants": {}, "vmastered": {}}

    def __init__(self, path):
        self.path = path
        self.data = {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.data = self._clean(raw.get("progress") if "progress" in raw else raw)
        except Exception:
            pass

    @staticmethod
    def _clean(prog):
        out = {}
        for season, sprites in (prog or {}).items():
            if not isinstance(sprites, dict):
                continue
            for sid, rec in sprites.items():
                if not isinstance(rec, dict):
                    continue
                vm = {k: True for k, v in (rec.get("vmastered") or {}).items() if v}
                r = {"captured": bool(rec.get("captured") or rec.get("mastered")), "mastered": bool(rec.get("mastered")),
                     "variants": {k: True for k, v in (rec.get("variants") or {}).items() if v}, "vmastered": vm}
                r["variants"].update(vm)  # mastered implies owned
                if r["captured"] or r["variants"]:
                    out.setdefault(str(season), {})[str(sid)] = r
        return out

    def get(self, sp):
        rec = self.data.get(sp["season"], {}).get(sp["id"])
        return rec or {k: (dict(v) if isinstance(v, dict) else v) for k, v in self.EMPTY.items()}

    def owned(self, sp, v=None):
        rec = self.get(sp)
        return rec["variants"].get(v, False) if v else rec["captured"]

    def mastered(self, sp, v=None):
        rec = self.get(sp)
        return rec["vmastered"].get(v, False) if v else rec["mastered"]

    def set(self, sp, v, what, value=None):
        """what: "owned" | "mastered" for the base sprite (v=None) or one variant."""
        rec = self.get(sp)
        rec = {"captured": rec["captured"], "mastered": rec["mastered"],
               "variants": dict(rec["variants"]), "vmastered": dict(rec["vmastered"])}
        own = self.owned(sp, v)
        mas = self.mastered(sp, v)
        if what == "owned":
            own = (not own) if value is None else value
            mas = mas and own  # un-owning clears mastered
        else:
            mas = (not mas) if value is None else value
            own = own or mas  # can't master what you never caught
        if v:
            for d, on in ((rec["variants"], own), (rec["vmastered"], mas)):
                if on:
                    d[v] = True
                else:
                    d.pop(v, None)
        else:
            rec["captured"], rec["mastered"] = own, mas
        season = self.data.setdefault(sp["season"], {})
        if rec["captured"] or rec["variants"]:
            season[sp["id"]] = rec
        else:
            season.pop(sp["id"], None)
        self.save()

    def export_obj(self):
        return {"app": "fortnite-cosmetics-browser", "kind": "sprite-progress", "schema": 1,
                "exported": datetime.now(timezone.utc).isoformat(timespec="seconds"), "progress": self.data}

    def save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.export_obj(), indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            pass

    def import_obj(self, obj, merge=True):
        incoming = self._clean(obj.get("progress") if isinstance(obj, dict) and "progress" in obj else obj)
        if not merge:
            self.data = {}
        for season, sprites in incoming.items():
            for sid, rec in sprites.items():
                cur = self.data.setdefault(season, {}).get(sid) or self.EMPTY
                self.data[season][sid] = {"captured": cur["captured"] or rec["captured"],
                                          "mastered": cur["mastered"] or rec["mastered"],
                                          "variants": {**cur["variants"], **rec["variants"]},
                                          "vmastered": {**cur.get("vmastered", {}), **rec["vmastered"]}}
        self.save()
        return sum(len(v) for v in incoming.values())


def sprite_entries(season, variants):
    """One card per base sprite and per variant (Fortnite.GG layout)."""
    out = []
    for order, sp in enumerate(season["sprites"]):
        for vi, v in enumerate([None] + sp["variants"] + sp["upcoming"]):
            vd = variants.get(v) if v else None
            upcoming = v in sp["upcoming"]
            release = sp["release"] if not is_out(sp["release"]) else (vd["release"] if vd else "")
            e = {"key": f"{sp['key']}|{v or ''}", "sp": sp, "v": v, "season": sp["season"], "id": sp["id"],
                 "name": f"{vd['name']} {sp['name']}" if vd else sp["name"], "rarity_key": sp["rarity_key"],
                 "theme": vd["theme"] if vd else SPRITE_THEMES.get(sp["rarity_key"], "#3a3f45"),
                 "out": not upcoming and is_out(sp["release"]) and (not vd or is_out(vd["release"])),
                 "upcoming": upcoming, "release": release, "order": (order, vi)}
            e["search"] = f"{sp['search']} {e['name'].lower()}"
            out.append(e)
    return out


def fgg_icon(sp, v, variants):
    if not sp.get("fgg"):
        return ""
    return FGG_ICON.format(name=sp["fgg"], suffix=variants[v]["fgg"] if v else "")


def wiki_candidates(sp, variant, variants):
    """Fortnite Wiki file names to try, following its naming convention for sprite icons
    ("Fire Sprite - Item - Fortnite.png", "Gold Fire Sprite - Item - Fortnite.png")."""
    names = [sp["wiki"]] if sp["wiki"] else [sp["name"], f"{sp['name']} Sprite"]
    pre = f"{variants[variant]['name']} " if variant else ""
    return [f"File:{pre}{n} - Item - Fortnite.png" for n in dict.fromkeys(names)]


def resolve_wiki_images(data):
    """Map "<sprite key>|<variant or ''>" -> image URL using the Fortnite Wiki API (one request per 50 files)."""
    want = {}
    for se in data["seasons"]:
        for sp in se["sprites"]:
            for v in [None] + sp["variants"] + sp["upcoming"]:
                want[f"{sp['key']}|{v or ''}"] = wiki_candidates(sp, v, data["variants"])
    titles = list(dict.fromkeys(t for c in want.values() for t in c))
    found = {}
    for i in range(0, len(titles), 50):
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(titles[i:i + 50]), "prop": "imageinfo",
                                    "iiprop": "url", "iiurlwidth": 512, "format": "json", "formatversion": 2})
        for page in json.loads(http_get(f"{WIKI_API}?{q}", timeout=30)).get("query", {}).get("pages", []):
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("thumburl") or info.get("url"):
                found[page["title"]] = info.get("thumburl") or info["url"]
    norm = lambda t: t.replace("_", " ")
    found = {norm(k): v for k, v in found.items()}
    return {k: next((found[norm(t)] for t in c if norm(t) in found), "") for k, c in want.items()}


def sprite_art(sp, variant, size, variants, corners="top", bg=None):
    """Stand-in Sprite art drawn locally (no official artwork is available from any API)."""
    S = size * 4
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    vdef = variants.get(variant) if variant else None
    body = sp["color"]
    if variant == "gold":
        body = "#f2c14e"
    elif vdef:
        body = rgb_hex(tuple((a * 0.45 + b * 0.55) for a, b in zip(hex_rgb(body), hex_rgb(vdef["color"]))))
    glow_c = vdef["color"] if vdef else shade(body, 0.3)

    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((S * .16, S * .2, S * .84, S * .88), fill=hex_rgb(glow_c) + (150,))
    layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(S * .07)))
    d = ImageDraw.Draw(layer)
    cx, cy, r = S * .5, S * .58, S * .25
    if variant == "cursed":  # horns
        for sx in (-1, 1):
            d.polygon([(cx + sx * r * .35, cy - r * .7), (cx + sx * r * .85, cy - r * 1.55),
                       (cx + sx * r * .8, cy - r * .5)], fill=hex_rgb(shade(vdef["color"], -0.35)) + (255,))
    # teardrop body: circle + flame tip
    d.polygon([(cx - r * .62, cy - r * .55), (cx + r * .12, cy - r * 1.75), (cx + r * .66, cy - r * .5)],
              fill=hex_rgb(body) + (255,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=hex_rgb(body) + (255,))
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse((cx - r * .7, cy - r * .78, cx - r * .05, cy - r * .2), fill=(255, 255, 255, 90))
    layer.alpha_composite(hl.filter(ImageFilter.GaussianBlur(S * .012)))
    d = ImageDraw.Draw(layer)
    for sx in (-1, 1):  # eyes
        ex = cx + sx * r * .36
        d.ellipse((ex - r * .2, cy - r * .2, ex + r * .2, cy + r * .32), fill=(255, 255, 255, 255))
        d.ellipse((ex - r * .1, cy - r * .02, ex + r * .1, cy + r * .26), fill=(24, 22, 36, 255))
        d.ellipse((ex - r * .07, cy, ex - r * .01, cy + r * .07), fill=(255, 255, 255, 255))
    if variant == "fortune":  # ruby
        gx, gy, g = cx, cy - r * .55, r * .2
        d.polygon([(gx, gy - g), (gx + g * .8, gy), (gx, gy + g), (gx - g * .8, gy)], fill=(255, 64, 92, 255),
                  outline=(255, 214, 222, 255), width=max(1, S // 90))
    if variant == "gold":  # sparkles
        for (sx, sy, k) in ((.22, .3, .06), (.8, .24, .045), (.78, .78, .05)):
            x0, y0, k = S * sx, S * sy, S * k
            d.polygon([(x0, y0 - k), (x0 + k * .28, y0 - k * .28), (x0 + k, y0), (x0 + k * .28, y0 + k * .28),
                       (x0, y0 + k), (x0 - k * .28, y0 + k * .28), (x0 - k, y0), (x0 - k * .28, y0 - k * .28)],
                      fill=(255, 244, 200, 255))
    base = card_bg(bg, size) if bg else radial_bg(rarity_bg(sp["rarity_key"]), size)
    base.alpha_composite(layer.resize((size, size), Image.LANCZOS))
    if corners:
        base.putalpha(round_mask(size, corners))
    return base


# ---------------------------------------------------------------- weapons & items
def bundled_data_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for p in (base / name, base / "docs" / "data" / name):
        if p.exists():
            return p
    return None


def fmt_stat(v, unit=""):
    if v is None:
        return "-"
    if isinstance(v, float):
        v = round(v, 2)
        v = int(v) if float(v).is_integer() else v
    return f"{v}{unit}"


def normalize_weapons(data):
    """docs/data/weapons.json (scraped from Fortnite.GG by tools/scrape_fortnitegg.py) -> app items."""
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("unsupported weapon data")
    img = data.get("imageBase") or "https://fortnite.gg/img/weapons/"
    classes = data.get("classes") or {}
    order = {c: i for i, c in enumerate(classes)}

    def item(w, pool):
        rar = w.get("rarities") or [v["rarity"] for v in w.get("variants", [])]
        stats = w.get("stats") or {v["rarity"]: {"dmg": v.get("dmg"), "dps": v.get("dps")} for v in w.get("variants", [])}
        it = {"key": ("pool:" if pool else "all:") + w["slug"], "slug": w["slug"], "name": w.get("name") or w["slug"],
              "cat": w.get("cat") or "", "cat_label": classes.get(w.get("cat"), (w.get("cat") or "Other").title()),
              "image": img + w["icon"] if w.get("icon") else "", "rarities": rar, "stats": stats,
              "rates": w.get("rates") or {}, "desc": w.get("desc") or w.get("blurb") or "", "ammo": w.get("ammo") or "",
              "falloff": w.get("falloff") or [], "where": w.get("where") or {}, "also": w.get("also") or {},
              "modes": w.get("modes") or [], "special": w.get("loot") == "special", "pool": pool,
              "headmult": w.get("headmult"), "corder": order.get(w.get("cat"), 99),
              "weapon": any(st.get("dmg") is not None for st in stats.values())}
        it["search"] = " ".join([it["name"], it["cat_label"], it["ammo"], " ".join(rar)]).lower()
        return it

    return {"pool": [item(w, True) for w in data.get("lootPool") or []],
            "all": [item(w, False) for w in data.get("catalog") or []],
            "classes": classes, "updated": data.get("updated") or "", "mode": data.get("mode") or "Battle Royale"}


# ---------------------------------------------------------------- widgets
class ScrollFrame(tk.Frame):
    """Vertically scrollable frame (mouse wheel), no visible scrollbar."""

    def __init__(self, master, bg, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))

    def bind_tree(self, widget=None):
        widget = widget or self
        widget.bind("<MouseWheel>", self._wheel, add="+")
        for ch in widget.winfo_children():
            self.bind_tree(ch)

    def _wheel(self, e):
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120) * 2, "units")
        return "break"

    def scroll_top(self):
        self.canvas.yview_moveto(0)


class SideRow(tk.Frame):
    def __init__(self, master, text, right, command, font, small_font, pady=5, image=None):
        super().__init__(master, bg=SIDEBAR, cursor="hand2")
        self.active = False
        self.bar = tk.Frame(self, bg=SIDEBAR, width=3)
        self.bar.pack(side="left", fill="y")
        self.lbl = tk.Label(self, text=text, bg=SIDEBAR, fg=FG, font=font, anchor="w",
                            padx=12, pady=pady, image=image or "", compound="left")
        self.lbl.pack(side="left", fill="x", expand=True)
        self.right = tk.Label(self, text=right, bg=SIDEBAR, fg=MUTED, font=small_font, padx=12)
        self.right.pack(side="right")
        for w in (self, self.lbl, self.right):
            w.bind("<Button-1>", lambda e: command())
            w.bind("<Enter>", lambda e: self._paint(True))
            w.bind("<Leave>", lambda e: self._paint(False))

    def set_active(self, active):
        self.active = active
        self._paint(False)

    def set_right(self, text):
        self.right.configure(text=text)

    def _paint(self, hover):
        bg = PANEL_2 if self.active else (PANEL_HOVER if hover else SIDEBAR)
        for w in (self, self.lbl, self.right):
            w.configure(bg=bg)
        self.bar.configure(bg=ACCENT if self.active else bg)
        self.lbl.configure(fg=FG if (self.active or hover) else FG_2)


class VirtualGrid:
    """Canvas grid that only draws visible tiles. Supports titled sections."""

    def __init__(self, app, parent, draw_tile, on_select, on_activate, on_context, on_click_local=None):
        self.app = app
        self.on_click_local = on_click_local  # (item, x, y inside the card) -> handled
        self.text_h = None  # overrides app.text_h
        self.wide = False   # True: double-width 16:9 cards (news)
        self.draw_tile = draw_tile
        self.on_select = on_select
        self.on_activate = on_activate
        self.on_context = on_context
        self.frame = tk.Frame(parent, bg=BG)
        self.canvas = tk.Canvas(self.frame, bg=BG, highlightthickness=0, takefocus=1,
                                yscrollincrement=int(30 * app.scale))
        self.vsb = ttk.Scrollbar(self.frame, orient="vertical", command=self._yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.sections, self.flat, self.rows, self.row_y, self.pos = [], [], [], [], []
        self.section_y = {}
        self.cols, self.x0, self.total_h = 1, 0, 1
        self.selected = None
        self.hover = None
        self.empty_text = "Loading..."

        c = self.canvas
        c.bind("<Configure>", lambda e: self.layout())
        c.bind("<Button-1>", self._click)
        c.bind("<Double-Button-1>", self._double)
        c.bind("<Button-3>", self._right)
        c.bind("<MouseWheel>", lambda e: self.scroll(int(-e.delta / 120) * 3, "units"))
        c.bind("<Motion>", self._motion)
        c.bind("<Leave>", lambda e: self._set_hover(None))
        for key, d in (("<Left>", -1), ("<Right>", 1)):
            c.bind(key, lambda e, d=d: self.move(d))
        c.bind("<Up>", lambda e: self.move(-self.cols))
        c.bind("<Down>", lambda e: self.move(self.cols))
        c.bind("<Home>", lambda e: self.select(0))
        c.bind("<End>", lambda e: self.select(len(self.flat) - 1))
        c.bind("<Prior>", lambda e: self.scroll(-1, "pages"))
        c.bind("<Next>", lambda e: self.scroll(1, "pages"))
        c.bind("<Return>", lambda e: self.selected is not None and self.on_activate(self.flat[self.selected]))

    # sizing
    @property
    def tile_w(self):
        if self.wide:
            cw = max(1, self.canvas.winfo_width())
            return max(self.app.tile, min(cw - 2 * self.app.gap, self.app.tile * 2 + self.app.gap))
        return self.app.tile

    @property
    def img_h(self):
        return round(self.tile_w * 9 / 16) if self.wide else self.app.tile

    @property
    def tile_h(self):
        return self.img_h + (self.text_h or self.app.text_h)

    def set_sections(self, sections, keep_key=None):
        self.sections = sections
        self.flat = [it for s in sections for it in s["items"]]
        self.selected = None
        self.hover = None
        self.canvas.yview_moveto(0)
        self.layout()
        if keep_key is not None and self.select_key(keep_key, notify=False):
            return
        self.redraw()

    def layout(self):
        app = self.app
        cw = max(1, self.canvas.winfo_width())
        w, h, pad = self.tile_w, self.tile_h, app.gap
        header_h = app.header_h
        self.cols = max(1, (cw - pad) // (w + pad))
        grid_w = self.cols * (w + pad) - pad
        self.x0 = max(pad, (cw - grid_w) // 2)
        y = pad
        rows, pos, self.section_y = [], [None] * len(self.flat), {}
        idx = 0
        for s in self.sections:
            if s.get("title"):
                self.section_y[s["title"]] = y
                rows.append((y, header_h, "header", s))
                y += header_h
            n = len(s["items"])
            for r in range(math.ceil(n / self.cols)):
                start = idx + r * self.cols
                cnt = min(self.cols, n - r * self.cols)
                rows.append((y, h, "tiles", (start, cnt)))
                for k in range(cnt):
                    pos[start + k] = (self.x0 + k * (w + pad), y)
                y += h + pad
            idx += n
        self.rows, self.pos = rows, pos
        self.row_y = [r[0] for r in rows]
        self.total_h = max(y + pad, self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, cw, self.total_h))
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        if self.app.grid is not self:
            return
        self.app.wanted = set()
        if not self.flat:
            c.create_text(c.winfo_width() // 2, int(90 * self.app.scale), text=self.empty_text,
                          fill=MUTED, font=self.app.f_header, justify="center")
            return
        top = c.canvasy(0)
        bottom = top + c.winfo_height()
        i = max(0, bisect_right(self.row_y, top) - 1)
        w, h = self.tile_w, self.tile_h
        while i < len(self.rows) and self.rows[i][0] < bottom:
            y, rh, kind, p = self.rows[i]
            if kind == "header":
                c.create_text(self.x0, y + rh - int(12 * self.app.scale), text=p["title"].upper(),
                              anchor="sw", fill=FG, font=self.app.f_header)
                if p.get("subtitle"):
                    tw = self.app.f_header.measure(p["title"].upper())
                    c.create_text(self.x0 + tw + int(12 * self.app.scale), y + rh - int(14 * self.app.scale),
                                  text=p["subtitle"], anchor="sw", fill=MUTED, font=self.app.f_small)
            else:
                start, cnt = p
                for k in range(cnt):
                    idx = start + k
                    x = self.pos[idx][0]
                    self.draw_tile(c, self.flat[idx], x, y, w, h, idx == self.hover, idx == self.selected)
            i += 1

    # interaction
    def _yview(self, *args):
        self.canvas.yview(*args)
        self.redraw()

    def scroll(self, n, what):
        self.canvas.yview_scroll(n, what)
        self.redraw()

    def hit(self, ex, ey):
        x, y = self.canvas.canvasx(ex), self.canvas.canvasy(ey)
        i = bisect_right(self.row_y, y) - 1
        if i < 0:
            return None
        ry, rh, kind, p = self.rows[i]
        if kind != "tiles" or y > ry + rh or x < self.x0:
            return None
        col, rx = divmod(int(x - self.x0), self.tile_w + self.app.gap)
        if col >= p[1] or rx > self.tile_w:
            return None
        return p[0] + col

    def _set_hover(self, idx):
        if idx != self.hover:
            self.hover = idx
            self.canvas.configure(cursor="hand2" if idx is not None else "")
            self.redraw()

    def _motion(self, e):
        self._set_hover(self.hit(e.x, e.y))

    def _click(self, e):
        self.canvas.focus_set()
        idx = self.hit(e.x, e.y)
        if idx is not None:
            self.select(idx)
            if self.on_click_local:
                px, py = self.pos[idx]
                self.on_click_local(self.flat[idx], self.canvas.canvasx(e.x) - px, self.canvas.canvasy(e.y) - py)

    def _double(self, e):
        idx = self.hit(e.x, e.y)
        if idx is not None:
            self.on_activate(self.flat[idx])

    def _right(self, e):
        idx = self.hit(e.x, e.y)
        if idx is not None:
            self.select(idx)
            self.on_context(self.flat[idx], e)

    def move(self, d):
        if not self.flat:
            return
        cur = self.selected if self.selected is not None else -d if d > 0 else len(self.flat)
        self.select(max(0, min(len(self.flat) - 1, cur + d)))

    def select(self, idx, notify=True):
        if not self.flat:
            return
        self.selected = idx
        self.ensure_visible(idx)
        if notify:
            self.on_select(self.flat[idx])

    def select_key(self, key, notify=True):
        for i, it in enumerate(self.flat):
            if it["key"] == key:
                self.select(i, notify)
                return True
        return False

    def ensure_visible(self, idx):
        _, y = self.pos[idx]
        top = self.canvas.canvasy(0)
        hgt = self.canvas.winfo_height()
        pad = self.app.gap
        if y - pad < top:
            self.canvas.yview_moveto(max(0, y - pad - self.app.header_h * 0.5) / self.total_h)
        elif y + self.tile_h + pad > top + hgt:
            self.canvas.yview_moveto((y + self.tile_h + pad - hgt) / self.total_h)
        self.redraw()

    def scroll_to_section(self, title):
        if title in self.section_y:
            self.canvas.yview_moveto(self.section_y[title] / self.total_h)
            self.redraw()



def _norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def normalize_news(data, motds=()):
    """data/news.json (Fortnite.GG archive of Epic's news) + Epic's live in-game motds (fortnite-api.com)."""
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("items"), list):
        raise ValueError("unsupported news data")
    live = {_norm_title(m.get("title")): m for m in motds or () if m.get("title")}
    items = []
    for i, n in enumerate(data["items"]):
        items.append({"key": f"fgg:{n.get('id') or i}", "id": str(n.get("id") or i), "title": n.get("title") or "",
                      "desc": n.get("desc") or "", "date": n.get("date") or "", "image": n.get("image") or "",
                      "image_large": n.get("imageLarge") or n.get("image") or "", "links": n.get("links") or [],
                      "votes": n.get("votes"), "live": _norm_title(n.get("title")) in live, "epic": False})
    known = {_norm_title(n["title"]) for n in items}
    today = date.today().isoformat()
    fresh = [{"key": f"epic:{m.get('id') or t}", "id": f"epic-{m.get('id') or t}", "title": m["title"], "desc": m.get("body") or "",
              "date": today, "image": m.get("tileImage") or m.get("image") or "", "image_large": m.get("image") or m.get("tileImage") or "",
              "links": [], "votes": None, "live": True, "epic": True}
             for t, m in live.items() if t not in known]
    allitems = fresh + items
    for n in allitems:
        n["search"] = f"{n['title']} {n['desc']}".lower()
    return {"items": allitems, "updated": data.get("updated") or "", "live_count": len(live)}


def fmt_news_date(iso):
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    except (TypeError, ValueError):
        return ""


def normalize_map(data):
    """Validate data/map.json (scraped from Fortnite.GG) and index its layers."""
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("groups"), list):
        raise ValueError("unsupported map data")
    layers = {}
    for g in data["groups"]:
        for l in g.get("layers") or []:
            l["group_name"] = g.get("name") or g.get("id", "")
            layers[l["id"]] = l
    data["layers"] = layers
    return data


def _map_image(src, mode):
    im = Image.open(src)
    if mode == "RGB" and (im.mode in ("RGBA", "LA") or "transparency" in im.info):
        bg = Image.new("RGBA", im.size, MAP_OCEAN)  # edge tiles are transparent: show ocean, not black
        bg.alpha_composite(im.convert("RGBA"))
        return bg.convert("RGB")
    return im.convert(mode)


def fetch_map_image(url, path, mode):
    """Download (or read from the disk cache) one map tile / icon and return a PIL image."""
    if path.exists():
        return _map_image(path, mode)
    raw = http_get(url, timeout=30)
    im = _map_image(BytesIO(raw), mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{threading.get_ident()}.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return im


class MapView:
    """Pan/zoom map on a Tk canvas: Fortnite.GG tiles, clustered icon markers, lines, labels.

    World coordinates are 0..256 (x right, y down) like data/map.json; at zoom z a world unit is 2^z pixels and
    Fortnite.GG serves 256 px tiles for z = 3..8. Quacks like VirtualGrid so App can treat it as the 'map' grid.
    """
    CLUSTER_CELL = 46
    CLUSTER_UNTIL = 5.2

    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=BG)
        self.canvas = tk.Canvas(self.frame, bg=MAP_OCEAN, highlightthickness=0, takefocus=1, cursor="fleur")
        self.canvas.pack(fill="both", expand=True, padx=int(12 * app.scale), pady=(0, int(12 * app.scale)))
        # VirtualGrid-compatible bits
        self.flat, self.sections, self.selected, self.text_h, self.empty_text = [], [], None, None, "Loading the map..."
        self.on_select = lambda it: None
        self.data, self.layers, self.enabled = None, {}, set()
        self.view = [128.0, 128.0, 2.0]
        self.min_z = None
        self.tile_raw = OrderedDict()   # (z, x, y) -> PIL image
        self.tile_ph = OrderedDict()    # (z, x, y, px[, parent]) -> PhotoImage
        self.icon_raw = {}              # icon id -> PIL RGBA
        self.icon_ph = {}               # (icon id, px) -> PhotoImage
        self.pending, self.bad = set(), set()
        self.hits, self.hit_sel, self.hover = [], None, None
        self._drag, self._redraw_job = None, None
        c = self.canvas
        c.bind("<Configure>", lambda e: self._on_resize())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag_move)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Double-Button-1>", lambda e: self.zoom_at(e.x, e.y, 1))
        c.bind("<MouseWheel>", lambda e: self.zoom_at(e.x, e.y, 0.5 * (1 if e.delta > 0 else -1)))
        c.bind("<Motion>", self._motion)
        c.bind("<Leave>", lambda e: self._set_hover(None))
        for key, dz in (("<plus>", 0.5), ("<equal>", 0.5), ("<KP_Add>", 0.5), ("<minus>", -0.5), ("<KP_Subtract>", -0.5)):
            c.bind(key, lambda e, dz=dz: self.zoom_at(self.w / 2, self.h / 2, dz))
        for key, d in (("<Left>", (80, 0)), ("<Right>", (-80, 0)), ("<Up>", (0, 80)), ("<Down>", (0, -80))):
            c.bind(key, lambda e, d=d: self.pan(*d))
        c.bind("0", lambda e: self.fit())

    # ---- VirtualGrid duck-typing
    def layout(self):
        self.redraw()

    def set_sections(self, *a, **k):
        self.redraw()

    def select_key(self, *a, **k):
        return False

    def move(self, d):
        pass

    def scroll_to_section(self, title):
        pass

    # ---- data
    @property
    def w(self):
        return max(1, self.canvas.winfo_width())

    @property
    def h(self):
        return max(1, self.canvas.winfo_height())

    def set_data(self, data, enabled):
        first = self.data is None or self.data.get("version") != data.get("version")
        self.data, self.layers = data, data["layers"]
        self.enabled = set(enabled)
        if first:
            self.tile_raw.clear()
            self.tile_ph.clear()
            self.min_z = None
            self.fit()
        self.redraw()

    def set_enabled(self, ids):
        self.enabled = set(ids)
        if self.hit_sel and self.hit_sel["layer"]["id"] not in self.enabled:
            self.hit_sel = None
        self.redraw()

    def bounds(self):
        xs, ys = [], []
        for l in self.layers.values():
            if l["kind"] == "markers":
                for m in l["markers"]:
                    for x, y in m["pts"]:
                        xs.append(x)
                        ys.append(y)
            elif l["kind"] == "labels":
                for b in l["labels"]:
                    xs.append(b["pt"][0])
                    ys.append(b["pt"][1])
        if not xs:
            return 0, 0, 256, 256
        pad = 10
        return max(0, min(xs) - pad), max(0, min(ys) - pad), min(256, max(xs) + pad), min(256, max(ys) + pad)

    def fit(self):
        if not self.data or self.w < 50:
            return
        x0, y0, x1, y1 = self.bounds()
        z = math.log2(min(self.w / (x1 - x0), self.h / (y1 - y0)))
        self.min_z = max(0.5, z - 0.6)
        self.set_view((x0 + x1) / 2, (y0 + y1) / 2, z)

    def _on_resize(self):
        if self.data and self.min_z is None:
            self.fit()
        self.schedule_redraw(30)

    # ---- view math
    def set_view(self, x, y, z):
        z = max(self.min_z or 0.5, min(7.5, z))
        self.view = [max(0.0, min(256.0, x)), max(0.0, min(256.0, y)), z]
        self.redraw()

    def scale(self):
        return 2 ** self.view[2]

    def to_screen(self, x, y):
        s = self.scale()
        return (x - self.view[0]) * s + self.w / 2, (y - self.view[1]) * s + self.h / 2

    def to_world(self, sx, sy):
        s = self.scale()
        return (sx - self.w / 2) / s + self.view[0], (sy - self.h / 2) / s + self.view[1]

    def zoom_at(self, sx, sy, dz):
        wx, wy = self.to_world(sx, sy)
        z = max(self.min_z or 0.5, min(7.5, self.view[2] + dz))
        s = 2 ** z
        self.set_view(wx - (sx - self.w / 2) / s, wy - (sy - self.h / 2) / s, z)

    def pan(self, dx, dy):
        s = self.scale()
        self.set_view(self.view[0] - dx / s, self.view[1] - dy / s, self.view[2])

    def fly_to(self, pt, z=None):
        self.set_view(pt[0], pt[1], z if z is not None else max(self.view[2], 4.5))

    # ---- images (workers download, main thread makes PhotoImages)
    def _want_tile(self, key):
        if key in self.tile_raw or key in self.pending or key in self.bad:
            return
        self.pending.add(key)
        z, x, y = key
        url = self.data["tiles"].replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
        path = MAP_DIR / re.sub(r"[^\w.-]", "_", str(self.data.get("version"))) / f"{z}_{x}_{y}.webp"
        results = self.app.results

        def work():
            try:
                results.put(("maptile", key, fetch_map_image(url, path, "RGB")))
            except Exception:
                results.put(("maptile", key, None))
        self.app.pool.submit(work)

    def on_tile(self, key, im):
        self.pending.discard(key)
        if im is None:
            self.bad.add(key)
            return
        self.tile_raw[key] = im
        while len(self.tile_raw) > 500:
            self.tile_raw.popitem(last=False)
        self.schedule_redraw()

    def icon_photo(self, icon, px):
        if icon is None or not self.data:
            return None
        ph = self.icon_ph.get((icon, px))
        if ph:
            return ph
        im = self.icon_raw.get(icon)
        if im is None:
            key = ("icon", icon)
            if key not in self.pending and key not in self.bad:
                self.pending.add(key)
                url, path, results = f"{self.data['iconBase']}{icon}.png", MAP_DIR / "icons" / f"{icon}.png", self.app.results

                def work():
                    try:
                        results.put(("mapicon", icon, fetch_map_image(url, path, "RGBA")))
                    except Exception:
                        results.put(("mapicon", icon, None))
                self.app.pool.submit(work)
            return None
        ph = ImageTk.PhotoImage(im.resize((px, px), Image.LANCZOS))
        self.icon_ph[(icon, px)] = ph
        return ph

    def on_icon(self, icon, im):
        self.pending.discard(("icon", icon))
        if im is None:
            self.bad.add(("icon", icon))
            return
        self.icon_raw[icon] = im
        self.schedule_redraw()

    def schedule_redraw(self, ms=40):
        if self._redraw_job is None:
            self._redraw_job = self.canvas.after(ms, self._do_scheduled)

    def _do_scheduled(self):
        self._redraw_job = None
        self.redraw()

    # ---- drawing
    def redraw(self):
        c = self.canvas
        c.delete("all")
        if self.app.grid is not self:
            return
        self.hits = []
        if not self.data:
            c.create_text(self.w // 2, int(90 * self.app.scale), text=self.empty_text, fill=FG_2,
                          font=self.app.f_header, justify="center")
            return
        self._draw_tiles(c)
        z = self.view[2]
        on = [l for l in self.layers.values() if l["id"] in self.enabled]
        for l in on:
            if l["kind"] == "lines":
                self._draw_lines(c, l)
        for l in on:
            if l["kind"] == "tunnels":
                self._draw_tunnels(c, l)
        for l in on:
            if l["kind"] == "markers":
                self._draw_markers(c, l, z)
        for l in on:
            if l["kind"] == "labels":
                self._draw_labels(c, l, z)
        if self.hit_sel and not self.hit_sel.get("label"):
            sx, sy = self.to_screen(*self.hit_sel["pt"])
            r = 17 * self.app.scale
            c.create_oval(sx - r, sy - r, sx + r, sy + r, outline=ACCENT, width=3)
        if self.hover:
            self._draw_tip(c)

    def _tile_photo(self, zt, tx, ty, px):
        key = (zt, tx, ty, px)
        ph = self.tile_ph.get(key)
        if ph:
            self.tile_ph.move_to_end(key)
            return ph
        raw = self.tile_raw.get((zt, tx, ty))
        if raw is not None:
            ph = ImageTk.PhotoImage(raw if px == 256 else raw.resize((px, px), Image.BILINEAR))
        else:
            self._want_tile((zt, tx, ty))
            ph = None
            for pz in range(zt - 1, self.data["tileMinZoom"] - 1, -1):  # parent tile while this one loads
                f = 2 ** (zt - pz)
                par = self.tile_raw.get((pz, tx // f, ty // f))
                if par is not None:
                    sub = 256 / f
                    box = ((tx % f) * sub, (ty % f) * sub, (tx % f + 1) * sub, (ty % f + 1) * sub)
                    return ImageTk.PhotoImage(par.crop(tuple(int(v) for v in box)).resize((px, px), Image.BILINEAR))
            return None
        self.tile_ph[key] = ph
        while len(self.tile_ph) > 260:
            self.tile_ph.popitem(last=False)
        return ph

    def _draw_tiles(self, c):
        d = self.data
        zt = max(d["tileMinZoom"], min(d["tileMaxZoom"], round(self.view[2])))
        n = 2 ** zt
        unit = d["worldSize"] / n
        size = unit * self.scale()
        px = max(1, math.ceil(size))
        wx0, wy0 = self.to_world(0, 0)
        wx1, wy1 = self.to_world(self.w, self.h)
        self._frame_refs = []
        for ty in range(max(0, int(wy0 // unit)), min(n - 1, int(wy1 // unit)) + 1):
            for tx in range(max(0, int(wx0 // unit)), min(n - 1, int(wx1 // unit)) + 1):
                ph = self._tile_photo(zt, tx, ty, px)
                if ph:
                    sx, sy = self.to_screen(tx * unit, ty * unit)
                    c.create_image(round(sx), round(sy), image=ph, anchor="nw")
                    self._frame_refs.append(ph)  # parent-crop placeholders aren't cached

    def _visible(self, sx, sy, m=30):
        return -m < sx < self.w + m and -m < sy < self.h + m

    def _marker(self, c, ph, sx, sy, size, hit):
        if ph:
            c.create_image(sx, sy, image=ph)
        else:
            c.create_oval(sx - 5, sy - 5, sx + 5, sy + 5, fill=ACCENT, outline="")
        h = self.hover
        if h and h["layer"] is hit["layer"] and h["pt"] is hit["pt"]:
            r = size / 2 + 3
            c.create_oval(sx - r, sy - r, sx + r, sy + r, outline="white", width=2)
        self.hits.append({**hit, "sx": sx, "sy": sy, "r": size / 2 + 4})

    def _draw_markers(self, c, l, z):
        s = self.app.scale
        base = (20 if z < 3.5 else 24 if z < 5 else 30) * s
        cluster = l["cluster"] and z < self.CLUSTER_UNTIL
        cell = self.CLUSTER_CELL * s
        for m in l["markers"]:
            icon = m.get("icon") if m.get("icon") is not None else l.get("icon")
            size = base * (m.get("size") or 40) / 40
            ph = self.icon_photo(icon, max(8, int(size)))
            cells = {}
            for pt in m["pts"]:
                sx, sy = self.to_screen(*pt)
                if not self._visible(sx, sy):
                    continue
                if cluster:
                    k = (int(sx // cell), int(sy // cell))
                    cc = cells.get(k)
                    if cc:
                        cc[0] += 1
                        cc[1] += pt[0]
                        cc[2] += pt[1]
                    else:
                        cells[k] = [1, pt[0], pt[1], pt]
                else:
                    self._marker(c, ph, sx, sy, size, {"layer": l, "pt": pt, "icon": icon})
            for n, x, y, pt0 in cells.values():
                pt = (x / n, y / n) if n > 1 else pt0
                sx, sy = self.to_screen(*pt)
                self._marker(c, ph, sx, sy, size, {"layer": l, "pt": pt, "icon": icon, "count": n if n > 1 else 0})
                if n > 1:
                    bx, by = sx + size / 2 - 4, sy - size / 2 - 2
                    label = str(n)
                    tw = max(16 * s, self.app.f_pill.measure(label) + 8 * s)
                    rr = 8 * s
                    c.create_oval(bx - tw / 2, by - rr, bx - tw / 2 + 2 * rr, by + rr, fill=ACCENT, outline="")
                    c.create_oval(bx + tw / 2 - 2 * rr, by - rr, bx + tw / 2, by + rr, fill=ACCENT, outline="")
                    c.create_rectangle(bx - tw / 2 + rr, by - rr, bx + tw / 2 - rr, by + rr, fill=ACCENT, outline="")
                    c.create_text(bx, by, text=label, fill=ACCENT_FG, font=self.app.f_pill)

    def _draw_lines(self, c, l):
        col = l.get("color") or "#ffcc7b"
        for a, b in l["lines"]:
            ax, ay = self.to_screen(*a)
            bx, by = self.to_screen(*b)
            if not (self._visible(ax, ay, 200) or self._visible(bx, by, 200)):
                continue
            c.create_line(ax, ay, bx, by, fill=col, width=7, capstyle="round")
            c.create_line(ax, ay, bx, by, fill="#222222", width=3, capstyle="round")
            for x, y, pt in ((ax, ay, a), (bx, by, b)):
                c.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#222222", outline=col, width=2)
                self.hits.append({"layer": l, "pt": pt, "icon": l.get("icon"), "sx": x, "sy": y, "r": 9})

    def _draw_tunnels(self, c, l):
        for t in l["tunnels"]:
            col = t.get("color") or "#7fd1ff"
            icon = t.get("icon") if t.get("icon") is not None else l.get("icon")
            size = int(24 * self.app.scale)
            ph = self.icon_photo(icon, size)
            for a, b in t["pairs"]:
                ax, ay = self.to_screen(*a)
                bx, by = self.to_screen(*b)
                if not (self._visible(ax, ay, 200) or self._visible(bx, by, 200)):
                    continue
                c.create_line(ax, ay, bx, by, fill=col, width=2, dash=(6, 5))
                self._marker(c, ph, ax, ay, size, {"layer": l, "pt": a, "icon": icon, "to": b})

    def _draw_labels(self, c, l, z):
        major = l["id"] == "poi"
        if not major and z < 3.4:
            return
        size = round(max(11, min(18, 7 + z * 2.2))) if major else round(max(9, min(13, 4 + z * 1.6)))
        font = (DISPLAY_FONT if DISPLAY_FONT in tkfont.families(self.canvas) else "Segoe UI", -int(size * self.app.scale),
                "bold" if major else "normal")
        for b in l["labels"]:
            sx, sy = self.to_screen(*b["pt"])
            if not self._visible(sx, sy, 120):
                continue
            txt = b["name"].upper() if major else b["name"]
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, 2), (2, 0), (-2, 0), (0, -2)):
                c.create_text(sx + dx, sy + dy, text=txt, fill="#000000", font=font)
            item = c.create_text(sx, sy, text=txt, fill="#ffffff" if major else "#e6e6e6", font=font)
            x0, y0, x1, y1 = c.bbox(item)
            self.hits.append({"layer": l, "pt": b["pt"], "name": b["name"], "label": True, "sx": sx, "sy": sy,
                              "hw": (x1 - x0) / 2, "hh": (y1 - y0) / 2})

    def _draw_tip(self, c):
        h = self.hover
        app = self.app
        lname = self.layers[h["layer"]["id"]]["name"]
        txt = h["name"] if h.get("label") else f"{h['count']} {lname} (click to zoom)" if h.get("count") else lname
        x, y = h["sx"] + 16, h["sy"] + 12
        t = c.create_text(x + 8, y + 4, text=txt, anchor="nw", fill="white", font=app.f_bold)
        x0, y0, x1, y1 = c.bbox(t)
        r = c.create_rectangle(x0 - 7, y0 - 3, x1 + 7, y1 + 3, fill="#111111", outline="")
        c.tag_lower(r, t)

    # ---- input
    def hit_at(self, sx, sy):
        for h in reversed(self.hits):
            if h.get("label"):
                if abs(sx - h["sx"]) <= h["hw"] and abs(sy - h["sy"]) <= h["hh"]:
                    return h
            elif (sx - h["sx"]) ** 2 + (sy - h["sy"]) ** 2 <= h["r"] ** 2:
                return h
        return None

    def _set_hover(self, h):
        old = self.hover
        if (h and h["pt"]) is not (old and old["pt"]):
            self.hover = h
            self.canvas.configure(cursor="hand2" if h else "fleur")
            self.redraw()

    def _motion(self, e):
        if self._drag is None and self.data:
            self._set_hover(self.hit_at(e.x, e.y))

    def _press(self, e):
        self.canvas.focus_set()
        self._drag = {"start": (e.x, e.y), "last": (e.x, e.y), "moved": False}

    def _drag_move(self, e):
        d = self._drag
        if not d:
            return
        if not d["moved"] and abs(e.x - d["start"][0]) + abs(e.y - d["start"][1]) < 5:
            return
        d["moved"] = True
        dx, dy = e.x - d["last"][0], e.y - d["last"][1]
        d["last"] = (e.x, e.y)
        s = self.scale()
        self.view[0] = max(0.0, min(256.0, self.view[0] - dx / s))
        self.view[1] = max(0.0, min(256.0, self.view[1] - dy / s))
        self.hover = None
        self.canvas.move("all", dx, dy)  # cheap while dragging; full redraw a moment later
        self.schedule_redraw(90)

    def _release(self, e):
        d, self._drag = self._drag, None
        if not d or not self.data:
            return
        if d["moved"]:
            self.redraw()
            return
        h = self.hit_at(e.x, e.y)
        if h and h.get("count"):
            self.fly_to(h["pt"], min(7.5, self.view[2] + 1.5))
            return
        self.hit_sel = h
        self.redraw()
        if h:
            self.app.show_map_hit(h)
        else:
            self.app.show_map_info()

    def select_hit(self, h):
        self.hit_sel = h
        self.redraw()


# ---------------------------------------------------------------- app
class App:
    def __init__(self, root):
        global RADIUS
        self.root = root
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        s = self.scale
        RADIUS = int(10 * s)
        self.gap = int(12 * s)
        self.text_h = int(46 * s)
        self.header_h = int(52 * s)
        self.big = int(300 * s)
        self.detail_wrap = int(310 * s)
        self.thumb_store = 128 if s <= 1.15 else 256
        self.shop_store = 256 if s <= 1.15 else 384

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(CACHE_DIR / "img", ignore_errors=True)  # v1 cache layout
        self.settings = self._load_settings()
        self.tile_key = self.settings.get("tile", "M") if self.settings.get("tile") in TILE_SIZES else "M"
        self.tile = int(TILE_SIZES[self.tile_key] * s)

        self.items, self.items_by_id, self.small_urls = [], {}, set()
        self.cat = "All"
        self.cats = []
        self.shop = None
        self.shop_by_item = {}
        self.shop_error = None
        self.loading = set()
        self.cached_count, self.cache_total = 0, 0
        self.prefetching, self.prefetch_stop = False, False
        self.sprites, self.sprite_error = None, None
        self.progress = SpriteProgress(PROGRESS_FILE)
        self.sprite_filter, self.sprite_season = "All", None
        self.sprite_entries_all = []
        self.weapons, self.weapon_error, self.weapon_rarity = None, None, {}
        self.map_data, self.map_error = None, None
        self.news, self.news_error = None, None
        self.map_on = set(self.settings.get("map_layers") or []) if isinstance(self.settings.get("map_layers"), list) else None
        self.sprite_photos = {}
        self.sprite_imgs = {}
        self.sprite_news = []
        self.detail_wait = set()
        self._detail_refresh_job = None

        self.photos = OrderedDict()
        self.pending, self.failed, self.wanted = set(), set(), set()
        self.results = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=12)
        self.detail_ck, self.detail_photo, self.detail_img = None, None, None
        self._filter_job = None
        self._ellipsis = {}
        self.mode = None
        self.grid = None

        self._icon = ImageTk.PhotoImage(make_icon(64))
        root.iconphoto(True, self._icon)
        self._build_fonts()
        self._build_style()
        self._build_ui()
        self.set_mode(self.settings.get("mode") if self.settings.get("mode") in MODES else "browse")
        self.show_empty_detail()
        self.load_cosmetics(force=False)
        self.load_shop()
        self.load_sprites()
        self.load_weapons()
        self.load_map()
        self.load_news()
        root.after(30, self._poll)
        root.after(1000, self._tick)

    # ------------------------------------------------------------ settings
    def _load_settings(self):
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self):
        try:
            data = {"tile": self.tile_key, "mode": self.mode}
            if getattr(self, "map_on", None) is not None:
                data["map_layers"] = sorted(self.map_on)
            SETTINGS_FILE.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------ styling
    def _build_fonts(self):
        F = lambda size, weight="normal", fam="Segoe UI", **kw: tkfont.Font(family=fam, size=size, weight=weight, **kw)
        self.f_base = F(10)
        self.f_bold = F(10, fam="Segoe UI Semibold")
        self.f_tile = F(9, fam="Segoe UI Semibold")
        self.f_small = F(8)
        self.f_strike = F(8, overstrike=1)
        self.f_pill = F(7, "bold")
        disp = DISPLAY_FONT if DISPLAY_FONT in tkfont.families(self.root) else "Segoe UI Black"
        self.f_header = F(16, fam=disp)
        self.f_title = F(20, fam=disp)
        self.f_price = F(15, fam=disp)
        self.f_logo = F(16, fam=disp)
        self.f_nav = F(12, fam=disp)
        self.f_section = F(9, fam=disp)
        self.f_hero = F(24, fam=disp)
        self.f_stat = F(17, fam=disp)
        self.f_chip = F(10, fam=disp)

    def _build_style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL_2,
                     bordercolor=LINE, lightcolor=PANEL_2, darkcolor=PANEL_2, font=self.f_base)
        st.configure("TButton", background=PANEL_2, foreground=FG, padding=(12, 6), borderwidth=0)
        st.map("TButton", background=[("active", HOVER), ("disabled", PANEL)],
               foreground=[("disabled", MUTED)])
        st.configure("Small.TButton", padding=(4, 6))
        st.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_FG, font=self.f_bold)
        st.map("Accent.TButton", background=[("active", "#fff36a"), ("disabled", PANEL_2)])
        st.configure("TCombobox", padding=5, arrowcolor=FG, background=PANEL_2, bordercolor=PANEL_2)
        st.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", FG)],
               selectbackground=[("readonly", PANEL_2)], selectforeground=[("readonly", FG)],
               background=[("active", HOVER)])
        st.configure("Vertical.TScrollbar", background=PANEL_2, troughcolor=BG, arrowcolor=MUTED,
                     borderwidth=0, gripcount=0)
        st.map("Vertical.TScrollbar", background=[("active", HOVER)])
        self.root.option_add("*TCombobox*Listbox.background", PANEL_2)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_FG)
        self.root.option_add("*TCombobox*Listbox.font", self.f_base)
        self.root.configure(bg=BG)

    # ------------------------------------------------------------ layout
    def _build_ui(self):
        root, s = self.root, self.scale
        root.title(f"{APP_NAME} by 248Tech")
        root.geometry(f"{int(1400 * s)}x{int(860 * s)}")
        root.minsize(int(960 * s), int(560 * s))

        # sidebar
        side = tk.Frame(root, bg=SIDEBAR, width=int(220 * s))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="FORTNITE", bg=SIDEBAR, fg=FG, font=self.f_logo, anchor="w",
                 padx=16).pack(fill="x", pady=(int(16 * s), 0))
        tk.Label(side, text="Cosmetics Browser", bg=SIDEBAR, fg=MUTED, font=self.f_small, anchor="w",
                 padx=16).pack(fill="x", pady=(0, int(14 * s)))
        self.nav_browse = SideRow(side, "COSMETICS", "", lambda: self.set_mode("browse"),
                                  self.f_nav, self.f_small, pady=8)
        self.nav_browse.pack(fill="x")
        self.nav_shop = SideRow(side, "ITEM SHOP", "", lambda: self.set_mode("shop"),
                                self.f_nav, self.f_small, pady=8)
        self.nav_shop.pack(fill="x")
        self.nav_sprites = SideRow(side, "SPRITES", "", lambda: self.set_mode("sprites"),
                                   self.f_nav, self.f_small, pady=8)
        self.nav_sprites.pack(fill="x")
        self.nav_weapons = SideRow(side, "WEAPONS & ITEMS", "", lambda: self.set_mode("weapons"),
                                   self.f_nav, self.f_small, pady=8)
        self.nav_weapons.pack(fill="x")
        self.nav_map = SideRow(side, "MAP", "", lambda: self.set_mode("map"), self.f_nav, self.f_small, pady=8)
        self.nav_map.pack(fill="x")
        self.nav_news = SideRow(side, "NEWS", "", lambda: self.set_mode("news"), self.f_nav, self.f_small, pady=8)
        self.nav_news.pack(fill="x")
        self.side_heading = tk.Label(side, text="", bg=SIDEBAR, fg=MUTED, font=self.f_section,
                                     anchor="w", padx=16)
        self.side_heading.pack(fill="x", pady=(int(18 * s), int(4 * s)))
        foot = tk.Frame(side, bg=SIDEBAR)
        foot.pack(side="bottom", fill="x", pady=(0, int(10 * s)))
        tk.Frame(foot, bg=LINE, height=1).pack(fill="x", pady=(0, int(8 * s)))
        for text, url, color in ((f"v{__version__}  ·  by 248Tech", "https://248tech.com", MUTED),
                                 ("★ Star on GitHub", REPO_URL, ACCENT)):
            lbl = tk.Label(foot, text=text, bg=SIDEBAR, fg=color, font=self.f_small, anchor="w",
                           padx=16, cursor="hand2")
            lbl.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
        self.side_list = ScrollFrame(side, bg=SIDEBAR)
        self.side_list.pack(fill="both", expand=True, pady=(0, int(8 * s)))

        # detail panel
        self.detail = ScrollFrame(root, bg=PANEL, width=int(350 * s))
        self.detail.pack(side="right", fill="y")
        self.detail.pack_propagate(False)
        self.blank_big = tk.PhotoImage(width=self.big, height=self.big)

        main = tk.Frame(root, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        # toolbar
        bar = tk.Frame(main, bg=BG)
        bar.pack(side="top", fill="x", padx=int(14 * s), pady=(int(12 * s), int(4 * s)))

        sw = tk.Frame(bar, bg=PANEL_2, highlightthickness=1, highlightbackground=PANEL_2,
                      highlightcolor=ACCENT)
        sw.pack(side="left")
        tk.Label(sw, text="⌕", bg=PANEL_2, fg=MUTED, font=self.f_bold).pack(side="left", padx=(8, 0))
        self.search_vars = {m: tk.StringVar() for m in MODES}
        for v in self.search_vars.values():
            v.trace_add("write", lambda *_: self._on_search_change())
        self.search = tk.Entry(sw, bg=PANEL_2, fg=FG, insertbackground=FG, relief="flat",
                               font=self.f_base, width=28, bd=0)
        self.search.pack(side="left", padx=(6, 8), pady=int(6 * s))
        self.search.bind("<FocusIn>", lambda e: sw.configure(highlightbackground=ACCENT))
        self.search.bind("<FocusOut>", lambda e: sw.configure(highlightbackground=PANEL_2))
        self.search.bind("<Down>", lambda e: (self.grid.canvas.focus_set(), self.grid.move(1)))
        self.placeholder = tk.Label(sw, text="", bg=PANEL_2, fg=MUTED, font=self.f_base, cursor="xterm")
        self.placeholder.bind("<Button-1>", lambda e: self.search.focus_set())
        self.clear_btn = tk.Label(sw, text="✕", bg=PANEL_2, fg=MUTED, font=self.f_small, cursor="hand2")
        self.clear_btn.bind("<Button-1>", lambda e: self.search_vars[self.mode].set(""))

        self.browse_tools = tk.Frame(bar, bg=BG)
        tk.Label(self.browse_tools, text="Rarity", bg=BG, fg=MUTED, font=self.f_small).pack(side="left", padx=(16, 6))
        self.rarity_var = tk.StringVar(value="All")
        self.rarity_cb = ttk.Combobox(self.browse_tools, textvariable=self.rarity_var, state="readonly",
                                      width=17, values=["All"])
        self.rarity_cb.pack(side="left")
        self.rarity_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())
        tk.Label(self.browse_tools, text="Sort", bg=BG, fg=MUTED, font=self.f_small).pack(side="left", padx=(14, 6))
        self.sort_var = tk.StringVar(value=SORTS[0])
        sort_cb = ttk.Combobox(self.browse_tools, textvariable=self.sort_var, values=SORTS,
                               state="readonly", width=15)
        sort_cb.pack(side="left")
        sort_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())

        self.sprite_bar = tk.Frame(bar, bg=BG)
        tk.Label(self.sprite_bar, text="VARIANT", bg=BG, fg=MUTED, font=self.f_section).pack(side="left", padx=(16, 6))
        self.sprite_variant_var = tk.StringVar(value="All")
        self.sprite_variant_cb = ttk.Combobox(self.sprite_bar, textvariable=self.sprite_variant_var, state="readonly",
                                              width=11, values=["All", "Base"])
        self.sprite_variant_cb.pack(side="left")
        self.sprite_variant_cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter("sprites"))
        tk.Label(self.sprite_bar, text="SORT BY", bg=BG, fg=MUTED, font=self.f_section).pack(side="left", padx=(14, 6))
        self.sprite_sort_var = tk.StringVar(value=SPRITE_SORTS[0])
        cb = ttk.Combobox(self.sprite_bar, textvariable=self.sprite_sort_var, values=SPRITE_SORTS,
                          state="readonly", width=15)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter("sprites"))

        self.weapon_bar = tk.Frame(bar, bg=BG)
        self.weapon_pool_var = tk.StringVar(value=WEAPON_POOLS[0])
        cb = ttk.Combobox(self.weapon_bar, textvariable=self.weapon_pool_var, values=WEAPON_POOLS, state="readonly", width=22)
        cb.pack(side="left", padx=(16, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: (self.apply_filter("weapons"), self.build_sidebar_list()))
        tk.Label(self.weapon_bar, text="SORT BY", bg=BG, fg=MUTED, font=self.f_section).pack(side="left", padx=(14, 6))
        self.weapon_sort_var = tk.StringVar(value=WEAPON_SORTS[0])
        cb = ttk.Combobox(self.weapon_bar, textvariable=self.weapon_sort_var, values=WEAPON_SORTS, state="readonly", width=13)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.apply_filter("weapons"))

        right = tk.Frame(bar, bg=BG)
        right.pack(side="right")
        self.refresh_btn = ttk.Button(right, text="↻", width=3, command=self.refresh_all)
        self.refresh_btn.pack(side="right")
        seg = tk.Frame(right, bg=PANEL_2)
        seg.pack(side="right", padx=(0, 12))
        self.size_btns = {}
        for k in TILE_SIZES:
            b = tk.Label(seg, text=k, bg=PANEL_2, fg=FG, font=self.f_bold, width=3, pady=4, cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, k=k: self.set_tile_size(k))
            self.size_btns[k] = b
        self._paint_size_btns()

        # status bar
        status = tk.Frame(main, bg=SIDEBAR)
        status.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar()
        tk.Label(status, textvariable=self.status_var, bg=SIDEBAR, fg=MUTED, font=self.f_small,
                 anchor="w", padx=14, pady=6).pack(side="left", fill="x", expand=True)
        self.cache_btn = tk.Label(status, text="Download all icons", bg=SIDEBAR, fg=ACCENT,
                                  font=self.f_small, cursor="hand2", padx=14)
        self.cache_btn.pack(side="right")
        self.cache_btn.bind("<Button-1>", lambda e: self.toggle_prefetch())
        self.export_btn = tk.Label(status, text="Export CSV", bg=SIDEBAR, fg=ACCENT,
                                   font=self.f_small, cursor="hand2", padx=4)
        self.export_btn.bind("<Button-1>", lambda e: self.export_csv())
        self.sprite_tools = tk.Frame(status, bg=SIDEBAR)
        for text, cmd in (("Import progress", self.import_progress), ("Export progress", self.export_progress)):
            lbl = tk.Label(self.sprite_tools, text=text, bg=SIDEBAR, fg=ACCENT, font=self.f_small,
                           cursor="hand2", padx=8)
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, c=cmd: c())
        self.cache_var = tk.StringVar(value="")
        self.cache_lbl = tk.Label(status, textvariable=self.cache_var, bg=SIDEBAR, fg=MUTED, font=self.f_small)
        self.cache_lbl.pack(side="right")

        # sprite hero header (title, Owned / Mastered counters, season chips)
        self.sprite_hero = tk.Frame(main, bg=BG)
        box = tk.Frame(self.sprite_hero, bg="#26282c", padx=int(18 * s), pady=int(12 * s))
        box.pack(pady=(int(6 * s), int(4 * s)))
        self.hero_title = tk.Label(box, text="", bg="#26282c", fg=FG, font=self.f_hero)
        self.hero_title.pack()
        stats = tk.Frame(box, bg="#26282c")
        stats.pack(pady=(int(8 * s), 0))
        self.hero_stats = {}
        for key, cap in (("owned", "OWNED"), ("mastered", "MASTERED")):
            cell = tk.Frame(stats, bg="#323439", padx=int(14 * s), pady=int(6 * s))
            cell.pack(side="left", padx=int(5 * s))
            v = tk.Label(cell, text="0 / 0", bg="#323439", fg=FG, font=self.f_stat)
            v.pack()
            tk.Label(cell, text=cap, bg="#323439", fg=MUTED, font=self.f_section).pack()
            self.hero_stats[key] = v
        self.hero_chips = tk.Frame(self.sprite_hero, bg=BG)
        self.hero_chips.pack(pady=(int(4 * s), int(6 * s)))

        # grids
        holder = tk.Frame(main, bg=BG)
        holder.pack(side="top", fill="both", expand=True)
        self.grid_holder = holder
        self.grids = {
            "browse": VirtualGrid(self, holder, self.draw_cosmetic_tile, self.show_cosmetic_detail,
                                  lambda it: self.open_url(it["featured"] or it["icon"]), self.context_menu),
            "shop": VirtualGrid(self, holder, self.draw_offer_tile, self.show_offer_detail,
                                lambda it: self.open_url(it["image"]), self.context_menu),
            "sprites": VirtualGrid(self, holder, self.draw_sprite_tile, self.show_sprite_detail,
                                   lambda e: self.toggle_entry(e, "owned"), self.context_menu,
                                   on_click_local=self._sprite_card_click),
        }
        self.grids["sprites"].text_h = int(84 * s)
        self.grids["weapons"] = VirtualGrid(self, holder, self.draw_weapon_tile, self.show_weapon_detail,
                                            lambda w: self.open_in_chrome(FGG_WEAPON.format(slug=w["slug"])),
                                            self.context_menu)
        self.grids["weapons"].text_h = int(62 * s)
        self.grids["weapons"].empty_text = "Loading weapons..."
        self.grids["map"] = MapView(self, holder)
        self.grids["news"] = VirtualGrid(self, holder, self.draw_news_tile, self.show_news_detail,
                                         lambda n: self.open_url(n["image_large"] or n["image"]), self.context_menu)
        self.grids["news"].wide = True
        self.grids["news"].text_h = int(78 * s)
        self.grids["news"].empty_text = "Loading Fortnite news..."
        self.grids["shop"].empty_text = "Loading Item Shop..."
        self.grids["sprites"].empty_text = "Loading Sprites..."
        sc = self.grids["sprites"].canvas
        sc.bind("<space>", lambda e: self._sprite_key("owned"))
        for key in ("m", "M"):
            sc.bind(key, lambda e: self._sprite_key("mastered"))

        self.menu = tk.Menu(root, tearoff=0, bg=PANEL_2, fg=FG, activebackground=ACCENT,
                            activeforeground=ACCENT_FG, bd=0, font=self.f_base)

        root.bind("<Control-f>", lambda e: (self.search.focus_set(), self.search.select_range(0, "end"), "break")[-1])
        root.bind("<Control-Key-1>", lambda e: self.set_mode("browse"))
        root.bind("<Control-Key-2>", lambda e: self.set_mode("shop"))
        root.bind("<Control-Key-3>", lambda e: self.set_mode("sprites"))
        root.bind("<Control-Key-4>", lambda e: self.set_mode("weapons"))
        root.bind("<Control-Key-5>", lambda e: self.set_mode("map"))
        root.bind("<Control-Key-6>", lambda e: self.set_mode("news"))
        self.search.bind("<Return>", self._search_return)
        root.bind("<Control-v>", self._ctrl_v, add="+")
        root.bind("<F5>", lambda e: self.refresh_all())
        self.search.bind("<Escape>", lambda e: self.search_vars[self.mode].set(""))

    def _search_return(self, e):
        if self.mode == "map" and self.map_data:
            terms = self.search_vars["map"].get().lower().split()
            locs = [b for b in self.map_locations() if all(t in b["name"].lower() for t in terms)]
            if terms and locs:
                self.goto_map_location(locs[0])
            return "break"

    def _ctrl_v(self, e):
        if self.mode == "sprites" and e.widget is not self.search:
            self.paste_sprite_photo()
            return "break"

    def _paint_size_btns(self):
        for k, b in self.size_btns.items():
            b.configure(bg=ACCENT if k == self.tile_key else PANEL_2, fg=ACCENT_FG if k == self.tile_key else FG)

    def set_tile_size(self, k):
        self.tile_key = k
        self.tile = int(TILE_SIZES[k] * self.scale)
        self._paint_size_btns()
        self._save_settings()
        for g in self.grids.values():
            key = g.flat[g.selected]["key"] if g.selected is not None else None
            g.layout()
            if key is not None:
                g.select_key(key, notify=False)

    # ------------------------------------------------------------ modes
    def set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        for m, g in self.grids.items():
            g.frame.pack_forget()
        self.grid = self.grids[mode]
        self.grid.frame.pack(fill="both", expand=True)
        self.nav_browse.set_active(mode == "browse")
        self.nav_shop.set_active(mode == "shop")
        self.nav_sprites.set_active(mode == "sprites")
        self.nav_weapons.set_active(mode == "weapons")
        self.nav_map.set_active(mode == "map")
        self.nav_news.set_active(mode == "news")
        self.search.configure(textvariable=self.search_vars[mode])
        self.placeholder.configure(text={"browse": "Search cosmetics, sets, IDs...",
                                         "shop": "Search the Item Shop...",
                                         "sprites": "Search sprites...",
                                         "weapons": "Search weapons & items...",
                                         "map": "Search layers & locations...",
                                         "news": "Search Fortnite news..."}[mode])
        self._update_search_decor()
        (self.browse_tools.pack(side="left") if mode == "browse" else self.browse_tools.pack_forget())
        (self.sprite_bar.pack(side="left") if mode == "sprites" else self.sprite_bar.pack_forget())
        (self.weapon_bar.pack(side="left") if mode == "weapons" else self.weapon_bar.pack_forget())
        if mode == "sprites":
            self.sprite_hero.pack(side="top", fill="x", before=self.grid_holder)
        else:
            self.sprite_hero.pack_forget()
        for w in (self.cache_btn, self.cache_lbl, self.export_btn, self.sprite_tools):
            w.pack_forget()
        if mode == "sprites":
            self.sprite_tools.pack(side="right", padx=(0, 8))
        elif mode in ("map", "news"):
            pass
        else:  # right-packed: first packed sits furthest right
            self.cache_btn.pack(side="right")
            self.cache_lbl.pack(side="right")
            if mode == "browse":
                self.export_btn.pack(side="right", padx=(0, 16))
        self.build_sidebar_list()
        self._save_settings()
        self.root.update_idletasks()  # real canvas size before layout
        self.grid.layout()
        sel = self.grid.selected
        if mode == "map":
            if self.grid.hit_sel:
                self.show_map_hit(self.grid.hit_sel)
            else:
                self.show_map_info()
        elif sel is not None and self.grid.flat:
            self.grid.on_select(self.grid.flat[sel])
        else:
            self.show_empty_detail()
        self.update_status()

    def _update_search_decor(self):
        has = bool(self.search_vars[self.mode].get())
        if has:
            self.placeholder.place_forget()
            self.clear_btn.pack(side="left", padx=(0, 8))
        else:
            self.placeholder.place(in_=self.search, x=0, rely=0.5, anchor="w")
            self.clear_btn.pack_forget()

    def _on_search_change(self):
        self._update_search_decor()
        if self._filter_job:
            self.root.after_cancel(self._filter_job)
        self._filter_job = self.root.after(160, self.apply_filter)

    def build_sidebar_list(self, keep_scroll=False):
        top = self.side_list.canvas.yview()[0] if keep_scroll else 0
        inner = self.side_list.inner
        for w in inner.winfo_children():
            w.destroy()
        self.side_rows = {}
        if self.mode == "browse":
            self.side_heading.configure(text="CATEGORIES")
            counts = Counter(it["cat"] for it in self.items)
            cats = [("All", len(self.items))] + [(c, counts[c]) for c in self.cats]
            for c, n in cats:
                row = SideRow(inner, c, f"{n:,}" if n else "", lambda c=c: self.set_category(c),
                              self.f_base, self.f_small)
                row.pack(fill="x")
                row.set_active(c == self.cat)
                self.side_rows[c] = row
        elif self.mode == "sprites":
            self._build_sprite_sidebar(inner)
        elif self.mode == "map":
            self._build_map_sidebar(inner)
        elif self.mode == "news":
            self.side_heading.configure(text="NEWS")
            for sec in self.grids["news"].sections:
                SideRow(inner, sec["title"], str(len(sec["items"])),
                        lambda t=sec["title"]: self.grid.scroll_to_section(t), self.f_base, self.f_small).pack(fill="x")
            tk.Label(inner, text="OFFICIAL", bg=SIDEBAR, fg=MUTED, font=self.f_section, anchor="w",
                     padx=16).pack(fill="x", pady=(int(12 * self.scale), int(2 * self.scale)))
            SideRow(inner, "fortnite.com/news", "↗", lambda: self.open_in_chrome(FN_NEWS), self.f_base, self.f_small).pack(fill="x")
            SideRow(inner, "Fortnite.GG archive", "↗", lambda: self.open_in_chrome(FGG_NEWS), self.f_base, self.f_small).pack(fill="x")
        elif self.mode == "weapons":
            self.side_heading.configure(text="CLASSES")
            for sec in self.grids["weapons"].sections:
                if sec.get("title"):
                    row = SideRow(inner, sec["title"], str(len(sec["items"])),
                                  lambda t=sec["title"]: self.grid.scroll_to_section(t), self.f_base, self.f_small)
                    row.pack(fill="x")
        else:
            self.side_heading.configure(text="SHOP SECTIONS")
            if self.shop:
                for title, items in self.shop["sections"].items():
                    row = SideRow(inner, title, str(len(items)),
                                  lambda t=title: self.grid.scroll_to_section(t), self.f_base, self.f_small)
                    row.pack(fill="x")
        self.side_list.scroll_top()
        if top:
            self.side_list.update_idletasks()
            self.side_list.canvas.yview_moveto(top)
        self.side_list.bind_tree()

    def set_category(self, c):
        self.cat = c
        for k, row in self.side_rows.items():
            row.set_active(k == c)
        self.apply_filter()

    # ------------------------------------------------------------ loading
    def refresh_all(self):
        self.load_cosmetics(force=True)
        self.load_shop()
        self.load_sprites()
        self.load_weapons()
        self.load_map()
        self.load_news()

    def _set_loading(self, what, on):
        (self.loading.add if on else self.loading.discard)(what)
        self.refresh_btn.state(["disabled"] if self.loading else ["!disabled"])
        self.update_status()

    def load_cosmetics(self, force):
        if "cosmetics" in self.loading:
            return
        self._set_loading("cosmetics", True)

        def work():
            try:
                import time
                fresh = DATA_FILE.exists() and time.time() - DATA_FILE.stat().st_mtime < MAX_DATA_AGE
                if force or not fresh:
                    try:
                        raw = http_get(API_COSMETICS, timeout=120)
                        if json.loads(raw).get("status") != 200:
                            raise RuntimeError("bad API status")
                        DATA_FILE.write_bytes(raw)
                    except Exception:
                        if not DATA_FILE.exists():
                            raise
                payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                items = normalize_cosmetics(payload.get("data") or [])
                names = set(os.listdir(THUMB_DIR))
                suffix = f"_{self.thumb_store}.{IMG_EXT}"
                urls = {it["small"] for it in items if it["small"]}
                cached = sum(1 for u in urls if url_key(u) + suffix in names)
                self.results.put(("cosmetics", items, urls, cached))
            except Exception as e:
                self.results.put(("error", "cosmetics", e))

        threading.Thread(target=work, daemon=True).start()

    def load_shop(self):
        if "shop" in self.loading:
            return
        self._set_loading("shop", True)

        def work():
            try:
                try:
                    raw = http_get(API_SHOP, timeout=60)
                    if json.loads(raw).get("status") != 200:
                        raise RuntimeError("bad API status")
                    SHOP_FILE.write_bytes(raw)
                except Exception:
                    if not SHOP_FILE.exists():
                        raise
                payload = json.loads(SHOP_FILE.read_text(encoding="utf-8"))
                self.results.put(("shop", normalize_shop(payload.get("data") or {})))
            except Exception as e:
                self.results.put(("error", "shop", e))

        threading.Thread(target=work, daemon=True).start()

    def _on_cosmetics(self, items, urls, cached):
        self._set_loading("cosmetics", False)
        counts = Counter(it["type"] for it in items)
        main_types = [t for t, n in counts.most_common() if n >= MIN_CATEGORY and t != "Unknown"]
        main_set = set(main_types)
        for it in items:
            it["cat"] = it["type"] if it["type"] in main_set else "Other"
        self.cats = main_types + (["Other"] if any(it["cat"] == "Other" for it in items) else [])
        if self.cat not in self.cats:
            self.cat = "All"
        self.items = items
        self.items_by_id = {it["id"]: it for it in items}
        self.small_urls = urls
        self.cached_count, self.cache_total = cached, len(urls)
        self._update_cache_label()

        key_of = {it["rarity"]: it["rarity_key"] for it in items}
        rar = sorted(set(key_of), key=lambda r: (rarity_rank(key_of[r]), r))
        self.rarity_cb["values"] = ["All"] + rar
        if self.rarity_var.get() not in self.rarity_cb["values"]:
            self.rarity_var.set("All")
        self.nav_browse.set_right(f"{len(items):,}")
        if self.mode == "browse":
            self.build_sidebar_list()
        self.apply_filter("browse")

    def _on_shop(self, shop):
        self._set_loading("shop", False)
        self.shop = shop
        self.shop_error = None
        self.shop_by_item = {}
        for e in shop["entries"]:
            for c in e["contents"]:
                if c["kind"] == "br" and c["id"]:
                    cur = self.shop_by_item.get(c["id"])
                    # prefer the single-item offer over bundles
                    if cur is None or len(e["contents"]) < len(cur["contents"]):
                        self.shop_by_item[c["id"]] = e
        if shop["vbuck"]:
            self.request_image(shop["vbuck"], 64, int(15 * self.scale), None, check=False)
            self.request_image(shop["vbuck"], 64, int(22 * self.scale), None, check=False)
        if self.mode == "shop":
            self.build_sidebar_list()
        self.apply_filter("shop")
        self.grids["browse"].redraw()
        self._tick(reschedule=False)

    # ------------------------------------------------------------ filtering
    def apply_filter(self, mode=None):
        mode = mode or self.mode
        if self._filter_job:
            self.root.after_cancel(self._filter_job)
            self._filter_job = None
        if mode == "map":
            if self.mode == "map":
                self.build_sidebar_list()
            self.update_status()
            return
        terms = self.search_vars[mode].get().lower().split()
        g = self.grids[mode]
        keep = g.flat[g.selected]["key"] if g.selected is not None else None
        if mode == "browse":
            cat, rar = self.cat, self.rarity_var.get()
            view = [it for it in self.items
                    if (cat == "All" or it["cat"] == cat)
                    and (rar == "All" or it["rarity"] == rar)
                    and all(t in it["search"] for t in terms)]
            sort = self.sort_var.get()
            if sort == "Newest":
                view.sort(key=lambda i: i["added"], reverse=True)
            elif sort == "Oldest":
                view.sort(key=lambda i: i["added"])
            elif sort == "Name A-Z":
                view.sort(key=lambda i: i["name"].lower())
            elif sort == "Name Z-A":
                view.sort(key=lambda i: i["name"].lower(), reverse=True)
            elif sort == "Rarity (high-low)":
                view.sort(key=lambda i: (-rarity_rank(i["rarity_key"]), i["name"].lower()))
            else:
                view.sort(key=lambda i: (rarity_rank(i["rarity_key"]), i["name"].lower()))
            g.empty_text = "No cosmetics match your filters." if self.items else "Loading cosmetics..."
            g.set_sections([{"title": None, "items": view}], keep_key=keep)
            self.view_count = len(view)
        elif mode == "weapons":
            g.empty_text = (f"Couldn't load weapon stats.\n{self.weapon_error}\n\nPress F5 to retry."
                            if self.weapon_error and not self.weapons else
                            "Nothing matches." if self.weapons else "Loading weapons...")
            g.set_sections(self.weapon_sections(terms), keep_key=keep)
            if self.mode == "weapons":
                self.build_sidebar_list()
        elif mode == "news":
            g.empty_text = (f"Couldn't load the news.\n{self.news_error}\n\nPress F5 to retry."
                            if self.news_error and not self.news else
                            "No stories match." if self.news else "Loading Fortnite news...")
            g.set_sections(self.news_sections(terms), keep_key=keep)
            if self.mode == "news":
                self.build_sidebar_list()
        elif mode == "sprites":
            g.empty_text = (f"Couldn't load the Sprite list.\n{self.sprite_error}\n\nPress F5 to retry."
                            if self.sprite_error and not self.sprites else
                            "No sprites match." if self.sprites else "Loading Sprites...")
            g.set_sections(self.sprite_sections(terms), keep_key=keep)
        else:
            sections = []
            if self.shop:
                for title, items in self.shop["sections"].items():
                    its = [it for it in items if all(t in it["search"] for t in terms)]
                    if its:
                        sections.append({"title": title, "subtitle": f"{len(its)} offers", "items": its})
                g.empty_text = "Nothing in today's shop matches your search."
            elif self.shop_error:
                g.empty_text = f"Couldn't load the Item Shop.\n{self.shop_error}\n\nPress F5 to retry."
            g.set_sections(sections, keep_key=keep)
        self.update_status()

    def update_status(self):
        if self.mode == "browse":
            if "cosmetics" in self.loading and not self.items:
                txt = "Downloading cosmetics from fortnite-api.com..."
            else:
                upd = datetime.fromtimestamp(DATA_FILE.stat().st_mtime).strftime("%b %d, %H:%M") if DATA_FILE.exists() else "-"
                txt = f"Showing {getattr(self, 'view_count', 0):,} of {len(self.items):,} cosmetics   ·   data updated {upd}"
        elif self.mode == "sprites":
            txt = self.sprite_status()
        elif self.mode == "news":
            if self.news:
                txt = (f"Fortnite news   ·   {len(self.grids['news'].flat)} stories   ·   {self.news['live_count']} in game now   ·   "
                       f"archive updated {self.news['updated'].replace('T', ' ')}   ·   Epic news via Fortnite.GG & fortnite-api.com")
            else:
                txt = "Loading Fortnite news..." if "news" in self.loading else "News unavailable"
        elif self.mode == "map":
            if self.map_data:
                txt = (f"Season {self.map_data.get('season')} map   ·   {len(self.map_on or ())} layers on   ·   "
                       f"updated {self.map_data.get('updated')}   ·   map & data: Fortnite.GG")
            else:
                txt = "Loading the map..." if "map" in self.loading else "Map unavailable"
        elif self.mode == "weapons":
            if self.weapons:
                n = len(self.grids["weapons"].flat)
                txt = (f"{self.weapon_pool_var.get()}   ·   {n} shown   ·   stats updated {self.weapons['updated']}"
                       f"   ·   data: Fortnite.GG")
            else:
                txt = "Loading weapon stats..." if "weapons" in self.loading else "Weapon stats unavailable"
        else:
            if self.shop:
                n = sum(len(s["items"]) for s in self.grids["shop"].sections)
                rem = (self.shop["reset"] - datetime.now(timezone.utc)).total_seconds()
                when = f"resets in {fmt_remaining(rem)}" if rem > 0 else "refreshing..."
                txt = (f"Item Shop for {self.shop['date'].strftime('%A, %b %d')}   ·   {n} offers"
                       f"   ·   {when}")
            else:
                txt = "Loading the Item Shop..." if "shop" in self.loading else "Item Shop unavailable"
        if self.loading and (self.items or self.shop or self.sprites) and self.mode != "map":
            txt += "   ·   refreshing..."
        self.status_var.set(txt)

    def _tick(self, reschedule=True):
        if self.shop:
            rem = (self.shop["reset"] - datetime.now(timezone.utc)).total_seconds()
            self.nav_shop.set_right(fmt_remaining(rem) if rem > 0 else "new")
            if rem < -60 and "shop" not in self.loading:
                self.load_shop()
        if self.mode == "shop":
            self.update_status()
        if reschedule:
            self.root.after(20000, self._tick)

    # ------------------------------------------------------------ images
    def request_image(self, url, store, disp, bg=None, check=True, corners="top"):
        if not url:
            return None
        ck = (url, disp, bg, corners if bg else None)
        ph = self.photos.get(ck)
        if ph is not None:
            self.photos.move_to_end(ck)
            return ph
        if check:
            self.wanted.add(ck)
        if ck in self.pending or ck in self.failed:
            return None
        self.pending.add(ck)
        self.pool.submit(self._image_job, ck, store, check)
        return None

    def _image_job(self, ck, store, check):
        url, disp, bg, corners = ck
        try:
            if check and ck not in self.wanted:
                self.results.put(("imgskip", ck))
                return
            im, new = load_stored(url, store)
            self.results.put(("img", ck, compose(im, disp, bg, corners),
                              new and store == self.thumb_store and url in self.small_urls))
        except Exception:
            self.results.put(("imgfail", ck))

    def _poll(self):
        dirty = False
        try:
            for _ in range(300):
                msg = self.results.get_nowait()
                kind = msg[0]
                if kind == "img":
                    _, ck, im, counted = msg
                    self.pending.discard(ck)
                    ph = ImageTk.PhotoImage(im)
                    self.photos[ck] = ph
                    while len(self.photos) > PHOTO_CACHE_MAX:
                        self.photos.popitem(last=False)
                    if counted:
                        self.cached_count += 1
                        self._update_cache_label()
                    if ck == self.detail_ck and self.detail_img is not None:
                        self.detail_photo = ph
                        self.detail_img.configure(image=ph)
                    if ck in self.wanted or (self.shop and ck[0] == self.shop["vbuck"]):
                        dirty = True
                    if ck in self.detail_wait:
                        self.detail_wait.discard(ck)
                        self._refresh_sprite_detail()
                elif kind == "imgskip":
                    self.pending.discard(msg[1])
                elif kind == "imgfail":
                    self.pending.discard(msg[1])
                    self.failed.add(msg[1])
                elif kind == "cosmetics":
                    self._on_cosmetics(*msg[1:])
                elif kind == "shop":
                    self._on_shop(msg[1])
                elif kind == "sprites":
                    self._on_sprites(*msg[1:])
                elif kind == "weapons":
                    self._set_loading("weapons", False)
                    self.weapons, self.weapon_error = msg[1], None
                    self.nav_weapons.set_right(str(len(msg[1]["pool"])))
                    self.apply_filter("weapons")
                elif kind == "map":
                    self._on_map(msg[1])
                elif kind == "news":
                    self._set_loading("news", False)
                    self.news, self.news_error = msg[1], None
                    week = (date.today() - timedelta(days=7)).isoformat()
                    self.nav_news.set_right(str(sum(1 for n in msg[1]["items"] if n["date"] >= week)) or "")
                    self.apply_filter("news")
                elif kind == "maptile":
                    self.grids["map"].on_tile(msg[1], msg[2])
                elif kind == "mapicon":
                    self.grids["map"].on_icon(msg[1], msg[2])
                    if self.mode == "map" and msg[2] is not None:
                        self._schedule_map_sidebar()
                elif kind == "sprite_news":
                    self.sprite_news = msg[1]
                    self._refresh_sprite_detail()
                elif kind == "sprite_imgs":
                    self.sprite_imgs = msg[1]
                    self.grids["sprites"].redraw()
                    self._refresh_sprite_detail()
                elif kind == "prefetch":
                    self.cached_count = msg[1]
                    self._update_cache_label()
                elif kind == "prefetch_end":
                    self.prefetching = False
                    self.cached_count = msg[1]
                    self._update_cache_label()
                elif kind == "error":
                    _, what, err = msg
                    self._set_loading(what, False)
                    if what == "shop":
                        self.shop_error = err
                        self.apply_filter("shop")
                    elif what == "sprites":
                        self.sprite_error = err
                        self.apply_filter("sprites")
                    elif what == "weapons":
                        self.weapon_error = err
                        self.apply_filter("weapons")
                    elif what == "news":
                        self.news_error = err
                        self.apply_filter("news")
                    elif what == "map":
                        self.map_error = err
                        self.grids["map"].empty_text = f"Couldn't load the map.\n{err}\n\nPress F5 to retry."
                        self.grids["map"].redraw()
                        if self.mode == "map":
                            self.build_sidebar_list()
                    elif not self.items:
                        messagebox.showerror("Load failed", f"Could not download cosmetics:\n{err}")
                        self.grids["browse"].empty_text = f"Couldn't load cosmetics.\n{err}\n\nPress F5 to retry."
                        self.grids["browse"].redraw()
        except queue.Empty:
            pass
        if dirty:
            self.grid.redraw()
        self.root.after(30, self._poll)

    # ------------------------------------------------------------ icon cache
    def _update_cache_label(self):
        if not self.cache_total:
            self.cache_var.set("")
            return
        pct = 100 * self.cached_count / self.cache_total
        self.cache_var.set(f"Icons cached {self.cached_count:,} / {self.cache_total:,} ({pct:.0f}%)")
        if self.prefetching:
            self.cache_btn.configure(text="Stopping..." if self.prefetch_stop else "Pause")
        elif self.cached_count >= self.cache_total:
            self.cache_btn.configure(text="All icons cached ✓", fg=GREEN, cursor="")
        else:
            self.cache_btn.configure(text="Download all icons", fg=ACCENT, cursor="hand2")

    def toggle_prefetch(self):
        if self.prefetching:
            self.prefetch_stop = True
            self._update_cache_label()
            return
        if not self.small_urls or self.cached_count >= self.cache_total:
            return
        self.prefetching, self.prefetch_stop = True, False
        self._update_cache_label()
        urls = sorted(self.small_urls)
        store = self.thumb_store

        def one(u):
            try:
                load_stored(u, store)
                return True
            except Exception:
                return False

        def work():
            todo = [u for u in urls if not thumb_path(u, store).exists()]
            done = len(urls) - len(todo)
            with ThreadPoolExecutor(max_workers=8) as ex:
                for i in range(0, len(todo), 64):
                    if self.prefetch_stop:
                        break
                    done += sum(ex.map(one, todo[i:i + 64]))
                    self.results.put(("prefetch", done))
            self.results.put(("prefetch_end", done))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ tile drawing
    def ellipsize(self, text, font, width):
        key = (text, width, str(font))
        out = self._ellipsis.get(key)
        if out is None:
            if font.measure(text) <= width:
                out = text
            else:
                lo, hi = 0, len(text)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if font.measure(text[:mid].rstrip() + "…") <= width:
                        lo = mid
                    else:
                        hi = mid - 1
                out = text[:lo].rstrip() + "…"
            if len(self._ellipsis) > 20000:
                self._ellipsis.clear()
            self._ellipsis[key] = out
        return out

    def _pill(self, c, x, y, text, bg, fg="white"):
        s = self.scale
        t = c.create_text(x + int(7 * s), y + int(3 * s), text=text, anchor="nw", fill=fg, font=self.f_pill)
        x1, y1, x2, y2 = c.bbox(t)
        rr = round_rect(c, x, y, x2 + int(7 * s), y2 + int(3 * s), int(6 * s), fill=bg, outline="")
        c.tag_raise(t, rr)

    def _finish_card(self, c, x, y, w, h, hover, sel):
        if sel:
            round_rect(c, x - 2, y - 2, x + w + 2, y + h + 2, RADIUS + 2, fill="", outline=ACCENT, width=2)
        elif hover:
            round_rect(c, x, y, x + w, y + h, RADIUS, fill="", outline="#5a5d66", width=1)

    def draw_cosmetic_tile(self, c, it, x, y, w, h, hover, sel):
        s = self.scale
        round_rect(c, x, y, x + w, y + h, RADIUS, fill=PANEL_HOVER if hover else PANEL, outline="")
        bg = rarity_bg(it["rarity_key"])
        ph = self.request_image(it["small"], self.thumb_store, w, bg)
        if ph is not None:
            c.create_image(x, y, image=ph, anchor="nw")
        else:
            round_rect(c, x, y, x + w, y + w, RADIUS, fill=shade(bg[1], 0.15), outline="")
        c.create_rectangle(x, y + w - int(3 * s), x + w, y + w, fill=rarity_color(it["rarity_key"]), outline="")
        pad = int(8 * s)
        c.create_text(x + pad, y + w + int(7 * s), anchor="nw", fill=FG, font=self.f_tile,
                      text=self.ellipsize(it["name"], self.f_tile, w - 2 * pad))
        c.create_text(x + pad, y + w + int(25 * s), anchor="nw", fill=MUTED, font=self.f_small,
                      text=self.ellipsize(it["type"], self.f_small, w - 2 * pad))
        if it["id"] in self.shop_by_item:
            self._pill(c, x + int(6 * s), y + int(6 * s), "IN SHOP", "#1f8f50")
        self._finish_card(c, x, y, w, h, hover, sel)

    def draw_offer_tile(self, c, it, x, y, w, h, hover, sel):
        s = self.scale
        round_rect(c, x, y, x + w, y + h, RADIUS, fill=PANEL_HOVER if hover else PANEL, outline="")
        ph = self.request_image(it["image"], self.shop_store, w, it["bg"])
        if ph is not None:
            c.create_image(x, y, image=ph, anchor="nw")
        else:
            round_rect(c, x, y, x + w, y + w, RADIUS, fill=it["bg"][1], outline="")
        pad = int(8 * s)
        c.create_text(x + pad, y + w + int(7 * s), anchor="nw", fill=FG, font=self.f_tile,
                      text=self.ellipsize(it["name"], self.f_tile, w - 2 * pad))
        px = x + pad
        py = y + w + int(25 * s)
        vb = self.shop and self.request_image(self.shop["vbuck"], 64, int(15 * s), None, check=False)
        if vb:
            c.create_image(px, py + int(7 * s), image=vb, anchor="w")
            px += int(18 * s)
        t = c.create_text(px, py, anchor="nw", fill=FG, font=self.f_small, text=f"{it['final']:,}")
        if it["regular"] > it["final"]:
            c.create_text(c.bbox(t)[2] + int(6 * s), py, anchor="nw", fill=MUTED, font=self.f_strike,
                          text=f"{it['regular']:,}")
        if it["banner"]:
            self._pill(c, x + int(6 * s), y + int(6 * s),
                       self.ellipsize(it["banner"].upper(), self.f_pill, w - int(26 * s)),
                       GOLD if it["banner_hot"] else "#11131a", "#1a1405" if it["banner_hot"] else "white")
        self._finish_card(c, x, y, w, h, hover, sel)

    # ------------------------------------------------------------ detail panel
    def _detail_reset(self):
        for w in self.detail.inner.winfo_children():
            w.destroy()
        self.detail.scroll_top()
        self.detail_ck, self.detail_photo, self.detail_img = None, None, None
        body = tk.Frame(self.detail.inner, bg=PANEL)
        body.pack(fill="both", expand=True, padx=int(20 * self.scale), pady=int(20 * self.scale))
        return body

    def _detail_image(self, body, url, store, bg):
        ph = self.request_image(url, store, self.big, bg, check=False, corners="all")
        self.detail_ck = (url, self.big, bg, "all") if bg else (url, self.big, None, None)
        self.detail_photo = ph
        self.detail_img = tk.Label(body, image=ph or self.blank_big, bg=PANEL, bd=0, cursor="hand2")
        self.detail_img.pack(pady=(0, int(14 * self.scale)))
        self.detail_img.bind("<Button-1>", lambda e: self.open_url(url))

    def _label(self, parent, text, font=None, fg=FG, **pack):
        lbl = tk.Label(parent, text=text, bg=PANEL, fg=fg, font=font or self.f_base, justify="left",
                       anchor="w", wraplength=self.detail_wrap)
        lbl.pack(anchor="w", fill="x", **pack)
        return lbl

    def _badges(self, parent, badges):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(anchor="w", pady=(int(6 * self.scale), int(10 * self.scale)))
        for text, bg, fg in badges:
            tk.Label(row, text=text, bg=bg, fg=fg, font=self.f_pill, padx=8, pady=3).pack(side="left", padx=(0, 6))

    def _facts(self, parent, facts):
        f = tk.Frame(parent, bg=PANEL)
        f.pack(anchor="w", fill="x", pady=(0, int(12 * self.scale)))
        for i, (k, v) in enumerate(facts):
            tk.Label(f, text=k, bg=PANEL, fg=MUTED, font=self.f_small, anchor="nw").grid(
                row=i, column=0, sticky="nw", padx=(0, 12), pady=2)
            tk.Label(f, text=v, bg=PANEL, fg=FG, font=self.f_small, anchor="nw", justify="left",
                     wraplength=int(230 * self.scale)).grid(row=i, column=1, sticky="nw", pady=2)

    def _buttons(self, parent, buttons):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(anchor="w", fill="x", pady=(int(4 * self.scale), 0))
        for i, (text, cmd) in enumerate(buttons):
            ttk.Button(row, text=text, command=cmd, style="Small.TButton").pack(
                side="left", fill="x", expand=True, padx=(0 if i == 0 else 6, 0))

    def _link(self, parent, text, sub, cmd, fg=FG, bg=PANEL_2):
        row = tk.Frame(parent, bg=bg, cursor="hand2" if cmd else "")
        row.pack(fill="x", pady=(0, 4))
        a = tk.Label(row, text=text, bg=bg, fg=fg, font=self.f_tile, anchor="w", padx=10, pady=5,
                     wraplength=int(200 * self.scale), justify="left")
        a.pack(side="left", fill="x", expand=True)
        b = tk.Label(row, text=sub, bg=bg, fg=MUTED, font=self.f_small, padx=10)
        b.pack(side="right")
        if cmd:
            for w in (row, a, b):
                w.bind("<Button-1>", lambda e: cmd())
                w.bind("<Enter>", lambda e: [x.configure(bg=HOVER) for x in (row, a, b)])
                w.bind("<Leave>", lambda e: [x.configure(bg=bg) for x in (row, a, b)])
        return row

    def _store_button(self, parent, cmd):
        ttk.Button(parent, text="Open in Epic Store (Chrome)", style="Accent.TButton",
                   command=cmd).pack(fill="x", pady=(int(8 * self.scale), 0))

    def offer_store_url(self, e):
        br = [c for c in e["contents"] if c["kind"] == "br"]
        if len(e["contents"]) == 1 and br and br[0]["id"] in self.items_by_id:
            return epic_item_url(self.items_by_id[br[0]["id"]])
        return f"{EPIC_SHOP}?lang=en-US"  # bundle / jam track page IDs aren't derivable

    def open_in_chrome(self, url):
        chrome = find_chrome()
        try:
            if chrome:
                subprocess.Popen([chrome, url], close_fds=True)
                self.status_var.set(f"Opened in Chrome: {url}")
                return
        except OSError:
            pass
        webbrowser.open(url)
        self.status_var.set(f"Chrome not found - opened in default browser: {url}")

    def show_empty_detail(self):
        body = self._detail_reset()
        tk.Label(body, text="✦", bg=PANEL, fg=LINE, font=("Segoe UI", 48)).pack(pady=(int(80 * self.scale), 8))
        self._label(body, "Select an item", self.f_header).configure(anchor="center", justify="center")
        self._label(body, "Click any tile to see its details.\n\n"
                          "Arrow keys  -  move selection\n"
                          "Enter / double-click  -  open image\n"
                          "Right-click  -  copy name / ID\n"
                          "Ctrl+F  -  search      F5  -  refresh\n"
                          "Ctrl+1 - 6  -  Cosmetics / Shop / Sprites / Weapons / Map / News\n\n"
                          "Sprites:  click Owned / Mastered on a card,\nSpace owned,  M mastered,  Ctrl+V paste photo",
                    self.f_small, MUTED).configure(anchor="center", justify="center")

    def show_cosmetic_detail(self, it):
        body = self._detail_reset()
        bg = rarity_bg(it["rarity_key"])
        self._detail_image(body, it["icon"], 512, bg)
        self._label(body, it["name"], self.f_title)
        self._badges(body, [(it["rarity"].upper(), rarity_color(it["rarity_key"]), "white"),
                            (it["type"].upper(), PANEL_2, FG)])
        offer = self.shop_by_item.get(it["id"])
        if offer:
            self._link(body, "●  In the Item Shop now",
                       f"{offer['final']:,} V-Bucks  ›", lambda: self.goto_offer(offer["key"]),
                       fg=GREEN, bg="#1f3a24")
            tk.Frame(body, bg=PANEL, height=int(6 * self.scale)).pack()
        if it["description"]:
            self._label(body, it["description"], self.f_base, FG_2, pady=(0, int(12 * self.scale)))
        facts = []
        if it["set"]:
            facts.append(("Set", it["set"]))
        if it["intro"]:
            facts.append(("Introduced", it["intro"].replace("Introduced in ", "").rstrip(".")))
        if it["added"]:
            facts.append(("Added", it["added"][:10]))
        facts.append(("ID", it["id"]))
        self._facts(body, facts)
        self._buttons(body, [("Copy ID", lambda: self.copy(it["id"], "ID")),
                             ("Copy name", lambda: self.copy(it["name"], "name")),
                             ("Open image", lambda: self.open_url(it["featured"] or it["icon"]))])
        self._store_button(body, lambda: self.open_in_chrome(epic_item_url(it)))
        self.detail.bind_tree()

    def show_offer_detail(self, e):
        body = self._detail_reset()
        s = self.scale
        self._detail_image(body, e["image"], 512, e["bg"])
        self._label(body, e["name"], self.f_title)
        badges = [(e["kind"].upper(), PANEL_2, FG)]
        if e["banner"]:
            badges.insert(0, (e["banner"].upper(), GOLD if e["banner_hot"] else "#3a3f52",
                              "#1a1405" if e["banner_hot"] else "white"))
        self._badges(body, badges)

        price = tk.Frame(body, bg=PANEL)
        price.pack(anchor="w", pady=(0, int(4 * s)))
        vb = self.request_image(self.shop["vbuck"], 64, int(22 * s), None, check=False) if self.shop else None
        if vb:
            tk.Label(price, image=vb, bg=PANEL).pack(side="left", padx=(0, 6))
        tk.Label(price, text=f"{e['final']:,}" + ("" if vb else " V-Bucks"), bg=PANEL, fg=FG,
                 font=self.f_price).pack(side="left")
        if e["regular"] > e["final"]:
            tk.Label(price, text=f"{e['regular']:,}", bg=PANEL, fg=MUTED,
                     font=tkfont.Font(family="Segoe UI", size=11, overstrike=1)).pack(side="left", padx=(10, 0))
            tk.Label(price, text=f"Save {e['regular'] - e['final']:,}", bg=PANEL, fg=GREEN,
                     font=self.f_small).pack(side="left", padx=(8, 0))

        facts = [("Section", e["section"])]
        if e["out"]:
            rem = (e["out"] - datetime.now(timezone.utc)).total_seconds()
            facts.append(("Leaves", f"in {fmt_remaining(rem)}  ({e['out'].astimezone().strftime('%b %d, %I:%M %p')})"))
        facts.append(("Giftable", "Yes" if e["giftable"] else "No"))
        tk.Frame(body, bg=PANEL, height=int(6 * s)).pack()
        self._facts(body, facts)

        if e["contents"]:
            tk.Label(body, text=f"INCLUDES ({len(e['contents'])})", bg=PANEL, fg=MUTED,
                     font=self.f_section, anchor="w").pack(anchor="w", fill="x", pady=(0, 6))
            for ci in e["contents"]:
                if ci["kind"] == "track":
                    mins, secs = divmod(ci.get("duration") or 0, 60)
                    sub = f"{ci.get('artist') or ''} · {ci.get('year') or ''} · {mins}:{secs:02d}"
                    self._link(body, ci["name"] or "Jam Track", sub.strip(" ·"), None)
                else:
                    known = ci["kind"] == "br" and ci["id"] in self.items_by_id
                    self._link(body, ci["name"] or ci["id"], ci["type"] + ("  ›" if known else ""),
                               (lambda cid=ci["id"]: self.goto_cosmetic(cid)) if known else None)
            tk.Frame(body, bg=PANEL, height=int(8 * s)).pack()
        self._buttons(body, [("Copy name", lambda: self.copy(e["name"], "name")),
                             ("Copy offer ID", lambda: self.copy(e["offer_id"], "offer ID")),
                             ("Open image", lambda: self.open_url(e["image"]))])
        self._store_button(body, lambda: self.open_in_chrome(self.offer_store_url(e)))
        self.detail.bind_tree()

    # ------------------------------------------------------------ navigation / actions
    def goto_offer(self, key):
        self.set_mode("shop")
        self.search_vars["shop"].set("")
        self.apply_filter("shop")
        self.grid.canvas.focus_set()
        self.grid.select_key(key)

    def goto_cosmetic(self, cid):
        self.set_mode("browse")
        self.search_vars["browse"].set("")
        self.rarity_var.set("All")
        self.cat = "All"
        for k, row in getattr(self, "side_rows", {}).items():
            row.set_active(k == "All")
        self.apply_filter("browse")
        self.grid.canvas.focus_set()
        self.grid.select_key(cid)

    def context_menu(self, it, e):
        m = self.menu
        m.delete(0, "end")
        if "sp" in it:
            self._sprite_menu(m, it)
            m.tk_popup(e.x_root, e.y_root)
            return
        if "image_large" in it:  # news story
            m.add_command(label="Copy headline", command=lambda: self.copy(it["title"], "headline"))
            m.add_command(label="Open image", command=lambda: self.open_url(it["image_large"] or it["image"]))
            m.add_command(label="Fortnite news on fortnite.com", command=lambda: self.open_in_chrome(FN_NEWS))
            m.tk_popup(e.x_root, e.y_root)
            return
        if "slug" in it:
            m.add_command(label="Copy name", command=lambda: self.copy(it["name"], "name"))
            m.add_command(label="Copy stats", command=lambda: self.copy(self.weapon_stats_text(it), "stats"))
            m.add_command(label="View on Fortnite.GG", command=lambda: self.open_in_chrome(FGG_WEAPON.format(slug=it["slug"])))
            m.tk_popup(e.x_root, e.y_root)
            return
        m.add_command(label="Copy name", command=lambda: self.copy(it["name"], "name"))
        if "id" in it:
            m.add_command(label="Copy ID", command=lambda: self.copy(it["id"], "ID"))
            m.add_command(label="Open image", command=lambda: self.open_url(it["featured"] or it["icon"]))
            m.add_command(label="Open in Epic Store (Chrome)", command=lambda: self.open_in_chrome(epic_item_url(it)))
            if it["id"] in self.shop_by_item:
                m.add_separator()
                m.add_command(label="Show in Item Shop",
                              command=lambda: self.goto_offer(self.shop_by_item[it["id"]]["key"]))
        else:
            m.add_command(label="Copy offer ID", command=lambda: self.copy(it["offer_id"], "offer ID"))
            m.add_command(label="Open image", command=lambda: self.open_url(it["image"]))
            m.add_command(label="Open in Epic Store (Chrome)", command=lambda: self.open_in_chrome(self.offer_store_url(it)))
        m.tk_popup(e.x_root, e.y_root)

    def copy(self, text, what):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f"Copied {what}: {text}")

    def open_url(self, url):
        if url:
            webbrowser.open(url)

    # ------------------------------------------------------------ sprites
    def load_sprites(self):
        if "sprites" in self.loading:
            return
        self._set_loading("sprites", True)

        def work():
            errors = []
            try:  # live catalog -> last good copy -> copy shipped with the app
                raw = http_get(SPRITES_URL, timeout=30)
                data = normalize_sprites(json.loads(raw))
                SPRITES_FILE.write_bytes(raw)
                self.results.put(("sprites", data, "live"))
                return
            except Exception as e:
                errors.append(e)
            for path, src in ((SPRITES_FILE, "cached"), (bundled_sprites_path(), "built-in")):
                try:
                    if path and path.exists():
                        self.results.put(("sprites", normalize_sprites(json.loads(path.read_text(encoding="utf-8"))), src))
                        return
                except Exception as e:
                    errors.append(e)
            self.results.put(("error", "sprites", errors[0]))

        threading.Thread(target=work, daemon=True).start()

    def _on_sprites(self, data, source):
        self._set_loading("sprites", False)
        self.sprites, self.sprite_error, self.sprite_source = data, None, source
        if self.sprite_season not in [s["id"] for s in data["seasons"]]:
            self.sprite_season = data["current"]
        self.sprite_photos.clear()
        self._sprite_counts_changed()
        self.apply_filter("sprites")
        self.load_sprite_images(data)
        self.load_sprite_news()

    def load_sprite_images(self, data):
        """Find real sprite art on the Fortnite Wiki (cached 6 h). Missing art falls back to drawn stand-ins."""
        try:
            cached = json.loads(SPRITE_IMG_FILE.read_text(encoding="utf-8"))
            self.sprite_imgs = cached.get("map") or {}
            import time
            if time.time() - cached.get("time", 0) < SPRITE_IMG_MAX_AGE and set(self.sprite_imgs) >= {
                    f"{sp['key']}|" for se in data["seasons"] for sp in se["sprites"]}:
                return
        except Exception:
            pass

        def work():
            try:
                import time
                found = resolve_wiki_images(data)
                SPRITE_IMG_FILE.write_text(json.dumps({"time": time.time(), "map": found}), encoding="utf-8")
                self.results.put(("sprite_imgs", found))
            except Exception:
                pass  # offline: keep cached map / drawn art

        threading.Thread(target=work, daemon=True).start()

    def load_sprite_news(self):
        """Official Sprite art from Epic: Battle Royale news cards that mention Sprites (via fortnite-api.com)."""
        def work():
            try:
                motds = (json.loads(http_get(API_NEWS_BR, timeout=30)).get("data") or {}).get("motds") or []
                news = [{"title": m.get("title") or "", "body": m.get("body") or "",
                         "image": m.get("tileImage") or m.get("image") or ""}
                        for m in motds if "sprite" in f"{m.get('title')} {m.get('body')}".lower()]
                self.results.put(("sprite_news", [n for n in news if n["image"]]))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    # -- user photos (screenshots of the in-game collection, etc.) - per card (base or variant)
    def _photo_name(self, sp, variant):
        return f"{sp['id']}_{variant}" if variant else sp["id"]

    def _selected_entry(self):
        g = self.grids["sprites"]
        return g.flat[g.selected] if g.selected is not None and g.flat else None

    def set_sprite_photo(self, e, im):
        SPRITE_IMG_DIR.mkdir(parents=True, exist_ok=True)
        name = self._photo_name(e["sp"], e["v"])
        for ext in ("png", "webp", "jpg"):
            (SPRITE_IMG_DIR / f"{name}.{ext}").unlink(missing_ok=True)
        im = im.convert("RGBA")
        im.thumbnail((512, 512), Image.LANCZOS)
        im.save(SPRITE_IMG_DIR / f"{name}.png")
        self.status_var.set(f"Photo set for {e['name']}")
        self.grids["sprites"].redraw()
        self._refresh_sprite_detail()

    def paste_sprite_photo(self, e=None):
        e = e or self._selected_entry()
        if not e:
            return
        try:
            from PIL import ImageGrab
            clip = ImageGrab.grabclipboard()
        except Exception:
            clip = None
        if isinstance(clip, list):  # copied files
            clip = next((Image.open(f) for f in clip if str(f).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))), None)
        if clip is None:
            self.status_var.set("Clipboard has no image. Take a screenshot with Win+Shift+S, then press Ctrl+V.")
            return
        self.set_sprite_photo(e, clip)

    def choose_sprite_photo(self, e):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")])
        if path:
            try:
                self.set_sprite_photo(e, Image.open(path))
            except Exception as err:
                messagebox.showerror("Not an image", str(err))

    def remove_sprite_photo(self, e):
        name = self._photo_name(e["sp"], e["v"])
        for ext in ("png", "webp", "jpg"):
            (SPRITE_IMG_DIR / f"{name}.{ext}").unlink(missing_ok=True)
        self.status_var.set("Photo removed")
        self.grids["sprites"].redraw()
        self._refresh_sprite_detail()

    def _photo_controls(self, body, e):
        s = self.scale
        self._section_label(body, "YOUR PHOTO")
        row = tk.Frame(body, bg=PANEL)
        row.pack(anchor="w", fill="x")
        for i, (text, cmd) in enumerate((("Paste  Ctrl+V", lambda: self.paste_sprite_photo(e)),
                                         ("File...", lambda: self.choose_sprite_photo(e)),
                                         ("Remove", lambda: self.remove_sprite_photo(e)))):
            ttk.Button(row, text=text, command=cmd, style="Small.TButton").pack(
                side="left", fill="x", expand=True, padx=(0 if i == 0 else 4, 0))
        self._label(body, "Optional: use your own screenshot instead of the Fortnite.GG image.",
                    self.f_small, MUTED_2, pady=(4, int(6 * s)))

    def _section_label(self, body, text):
        tk.Label(body, text=text, bg=PANEL, fg=MUTED, font=self.f_section, anchor="w").pack(
            anchor="w", fill="x", pady=(int(10 * self.scale), 6))

    def _news_cards(self, body):
        if not self.sprite_news:
            return
        s = self.scale
        self._section_label(body, "FROM EPIC NEWS")
        w = self.big
        for n in self.sprite_news:
            ph = self.request_image(n["image"], 720, w, None, check=False)
            if ph is None:
                self.detail_wait.add((n["image"], w, None, None))
            lbl = tk.Label(body, image=ph or "", bg=PANEL, bd=0, cursor="hand2")
            if ph:
                lbl.pack(anchor="w", pady=(0, 4))
                lbl.bind("<Button-1>", lambda ev, u=n["image"]: self.open_url(u.split("?")[0]))
            self._label(body, n["title"], self.f_tile)
            self._label(body, n["body"], self.f_small, MUTED, pady=(0, int(10 * s)))

    # -- images
    def sprite_image_url(self, sp, variant):
        """Art for a card: your photo > URL in sprites.json > Fortnite.GG > Fortnite Wiki > '' (drawn stand-in)."""
        name = f"{sp['id']}_{variant}" if variant else sp["id"]
        for ext in ("png", "webp", "jpg"):
            f = SPRITE_IMG_DIR / f"{name}.{ext}"
            if f.exists():
                return f"local:{f}?{f.stat().st_mtime_ns}"
        explicit = sp["images"].get(variant) if variant else sp["image"]
        return (explicit or fgg_icon(sp, variant, self.sprites["variants"])
                or self.sprite_imgs.get(f"{sp['key']}|{variant or ''}", ""))

    def entry_image(self, e, size, corners="top", check=True, dim=False):
        """PhotoImage of the card art (real image once loaded, else the drawn stand-in)."""
        bg = ("lin", e["theme"], PANEL) + (("dim",) if dim else ())
        url = self.sprite_image_url(e["sp"], e["v"])
        if url:
            ph = self.request_image(url, 512, size, bg, check=check, corners=corners)
            if ph is not None:
                return ph
            if not check and (url, size, bg, corners) not in self.failed:
                self.detail_wait.add((url, size, bg, corners))
        return self.sprite_photo(e, size, corners, bg)

    def sprite_photo(self, e, size, corners, bg):
        ck = (e["key"], size, corners, bg)
        ph = self.sprite_photos.get(ck)
        if ph is None:
            im = sprite_art(e["sp"], e["v"], size, self.sprites["variants"], corners, bg=bg[:3])
            if bg[-1] == "dim":
                alpha = im.getchannel("A")
                im = Image.blend(im, Image.new("RGBA", im.size, hex_rgb(PANEL) + (255,)), 0.6)
                im.putalpha(alpha)
            ph = self.sprite_photos[ck] = ImageTk.PhotoImage(im)
        return ph

    # -- data views
    def sprite_season_obj(self):
        if not self.sprites:
            return None
        return next((s for s in self.sprites["seasons"] if s["id"] == self.sprite_season), self.sprites["seasons"][-1])

    def season_entries(self, season=None):
        se = season or self.sprite_season_obj()
        return sprite_entries(se, self.sprites["variants"]) if se else []

    def sprite_stats(self, season=None):
        live = [e for e in self.season_entries(season) if e["out"]]
        return {"total": len(live), "owned": sum(self.progress.owned(e["sp"], e["v"]) for e in live),
                "mastered": sum(self.progress.mastered(e["sp"], e["v"]) for e in live)}

    def entry_matches(self, e, flt):
        own, mas = self.progress.owned(e["sp"], e["v"]), self.progress.mastered(e["sp"], e["v"])
        return {"Missing": not own, "Owned": own, "Mastered": mas, "Not mastered": own and not mas}.get(flt, True)

    def _variant_filter_ok(self, e):
        vf = self.sprite_variant_var.get()
        if vf == "All":
            return True
        if vf == "Base":
            return e["v"] is None
        return e["v"] is not None and self.sprites["variants"][e["v"]]["name"] == vf

    def sprite_sections(self, terms):
        se = self.sprite_season_obj()
        if not se:
            return []
        names = ["All", "Base"] + [v["name"] for v in self.sprites["variants"].values()]
        self.sprite_variant_cb["values"] = names
        if self.sprite_variant_var.get() not in names:
            self.sprite_variant_var.set("All")
        es = [e for e in self.season_entries(se) if self._variant_filter_ok(e)
              and self.entry_matches(e, self.sprite_filter) and all(t in e["search"] for t in terms)]
        sort = self.sprite_sort_var.get()
        rank = lambda e: SPRITE_RARITIES.index(e["rarity_key"]) if e["rarity_key"] in SPRITE_RARITIES else 9
        if sort == "Name A-Z":
            es.sort(key=lambda e: e["name"].lower())
        elif sort == "Rarity (high-low)":
            es.sort(key=lambda e: (-rank(e), e["order"]))
        elif sort == "Missing first":
            es.sort(key=lambda e: (self.progress.owned(e["sp"], e["v"]), e["order"]))
        elif sort == "Owned first":
            es.sort(key=lambda e: (not self.progress.owned(e["sp"], e["v"]), e["order"]))
        if sort != "Default":
            return [{"title": None, "items": es}] if es else []
        sections = []
        for rk in SPRITE_RARITIES + sorted({e["rarity_key"] for e in es} - set(SPRITE_RARITIES)):
            its = [e for e in es if e["rarity_key"] == rk]
            if its:
                sections.append({"title": rk.title(), "subtitle": self._section_sub(its), "items": its})
        return sections

    def _section_sub(self, its):
        live = [e for e in its if e["out"]]
        return f"{sum(self.progress.owned(e['sp'], e['v']) for e in live)} / {len(live)} owned"

    def sprite_status(self):
        if not self.sprites:
            return "Loading the Sprite list..." if "sprites" in self.loading else "Sprite list unavailable"
        st = self.sprite_stats()
        se = self.sprite_season_obj()
        src = {"live": "", "cached": "   ·   offline list", "built-in": "   ·   built-in list"}.get(getattr(self, "sprite_source", ""), "")
        return (f"{se['name']}   ·   Owned {st['owned']}/{st['total']}   ·   Mastered {st['mastered']}/{st['total']}"
                f"   ·   Sprite images: Fortnite.GG{src}")

    def _sprite_counts_changed(self):
        if self.sprites:
            st = self.sprite_stats()
            self.nav_sprites.set_right(f"{st['owned']}/{st['total']}")
            self._update_hero(st)
        if self.mode == "sprites":
            self.build_sidebar_list()
        self.update_status()

    def _update_hero(self, st):
        se = self.sprite_season_obj()
        self.hero_title.configure(text=f"{se['name'].upper()} SPRITES")
        self.hero_stats["owned"].configure(text=f"{st['owned']} / {st['total']}")
        self.hero_stats["mastered"].configure(text=f"{st['mastered']} / {st['total']}")
        for w in self.hero_chips.winfo_children():
            w.destroy()
        for season in self.sprites["seasons"]:
            on = season["id"] == se["id"]
            chip = tk.Label(self.hero_chips, text=season["name"], bg=FG if on else PANEL_2, fg=ACCENT_FG if on else FG,
                            font=self.f_chip, padx=int(10 * self.scale), pady=int(4 * self.scale), cursor="hand2")
            chip.pack(side="left", padx=3)
            chip.bind("<Button-1>", lambda ev, sid=season["id"]: self.set_sprite_season(sid))

    def _build_sprite_sidebar(self, inner):
        self.side_heading.configure(text="MY COLLECTION")
        es = [e for e in self.season_entries() if self._variant_filter_ok(e)] if self.sprites else []
        for f in SPRITE_FILTERS:
            n = sum(1 for e in es if self.entry_matches(e, f))
            row = SideRow(inner, f, str(n) if self.sprites else "", lambda f=f: self.set_sprite_filter(f),
                          self.f_base, self.f_small)
            row.pack(fill="x")
            row.set_active(f == self.sprite_filter)
            self.side_rows[f] = row

    def set_sprite_filter(self, f):
        self.sprite_filter = f
        for k, row in self.side_rows.items():
            row.set_active(k == f)
        self.apply_filter("sprites")

    def set_sprite_season(self, sid):
        self.sprite_season = sid
        self._sprite_counts_changed()
        self.apply_filter("sprites")

    # -- card drawing (Fortnite.GG style: art, name, Owned / Mastered checkboxes)
    def _checkbox(self, c, x, y, on, color, label, enabled=True):
        s = self.scale
        b = int(15 * s)
        round_rect(c, x, y, x + b, y + b, int(4 * s), fill=color if on else "", outline=color if on else "#6b6e75",
                   width=max(1, int(1.5 * s)))
        if on:
            c.create_text(x + b / 2, y + b / 2, text="✓", fill=ACCENT_FG, font=self.f_pill)
        c.create_text(x + b + int(7 * s), y + b / 2, text=label, anchor="w", fill=FG_2 if enabled else MUTED_2,
                      font=self.f_small)

    def draw_sprite_tile(self, c, e, x, y, w, h, hover, sel):
        s = self.scale
        sp, v = e["sp"], e["v"]
        own, mas = self.progress.owned(sp, v), self.progress.mastered(sp, v)
        round_rect(c, x, y, x + w, y + h, RADIUS, fill=PANEL_HOVER if hover else PANEL, outline="")
        c.create_image(x, y, image=self.entry_image(e, w), anchor="nw")
        if mas:
            c.create_text(x + w - int(8 * s), y + int(4 * s), text="♛", anchor="ne", fill=ACCENT, font=self.f_header)
        pad = int(9 * s)
        c.create_text(x + pad, y + w + int(6 * s), anchor="nw", fill=FG, font=self.f_tile,
                      text=self.ellipsize(e["name"], self.f_tile, w - 2 * pad))
        if e["out"]:
            self._checkbox(c, x + pad, y + w + int(30 * s), own, GREEN, "Owned")
            self._checkbox(c, x + pad, y + w + int(55 * s), mas, ACCENT, "Mastered")
        else:
            when = f"Coming {fmt_day(e['release'])}" if e["release"] else "Not released yet"
            c.create_text(x + pad, y + w + int(34 * s), anchor="nw", fill=RED, font=self.f_small, text="🔒 " + when)
        self._finish_card(c, x, y, w, h, hover, sel)

    def _sprite_card_click(self, e, lx, ly):
        if not e["out"]:
            return
        s, w = self.scale, self.tile
        if w + 25 * s <= ly < w + 50 * s:
            self.toggle_entry(e, "owned")
        elif w + 50 * s <= ly < w + 76 * s:
            self.toggle_entry(e, "mastered")

    def _check_row(self, parent, on, text, sub, color, cmd, enabled=True):
        bg = "#1f3a24" if on else PANEL_2
        row = tk.Frame(parent, bg=bg, cursor="hand2" if enabled else "")
        row.pack(fill="x", pady=(0, 4))
        box = tk.Label(row, text="☑" if on else "☐", bg=bg, fg=color if on else MUTED,
                       font=("Segoe UI Symbol", 13), padx=8)
        box.pack(side="left")
        a = tk.Label(row, text=text, bg=bg, fg=FG if enabled else MUTED, font=self.f_tile, anchor="w", pady=6)
        a.pack(side="left", fill="x", expand=True)
        b = tk.Label(row, text=sub, bg=bg, fg=MUTED, font=self.f_small, padx=10)
        b.pack(side="right")
        if enabled:
            for wd in (row, box, a, b):
                wd.bind("<Button-1>", lambda ev: cmd())
                wd.bind("<Enter>", lambda ev: [x.configure(bg=HOVER) for x in (row, box, a, b)])
                wd.bind("<Leave>", lambda ev: [x.configure(bg=bg) for x in (row, box, a, b)])

    def show_sprite_detail(self, e):
        body = self._detail_reset()
        s = self.scale
        sp, v = e["sp"], e["v"]
        V = self.sprites["variants"]
        self.detail_wait.clear()
        self.detail_img = tk.Label(body, image=self.entry_image(e, self.big, "all", check=False), bg=PANEL, bd=0)
        self.detail_img.pack(pady=(0, int(12 * s)))
        self._label(body, e["name"].upper(), self.f_title)
        chip_bg, chip_fg = SPRITE_CHIPS.get(sp["rarity_key"], (PANEL_2, FG))
        badges = [(sp["rarity"].upper(), chip_bg, chip_fg)]
        if v:
            badges.append((V[v]["name"].upper(), V[v]["theme"], "white"))
        badges.append(("SPRITE", PANEL_2, FG))
        if not e["out"]:
            badges.append(((f"COMING {fmt_day(e['release'])}" if e["release"] else "UNRELEASED").upper(), RED, "white"))
        self._badges(body, badges)
        if sp["ability"]:
            self._label(body, sp["ability"], self.f_base, FG_2, pady=(0, int(4 * s)))
        if v and V[v]["description"]:
            self._label(body, V[v]["description"], self.f_small, MUTED, pady=(0, int(4 * s)))

        self._section_label(body, "MY PROGRESS")
        on = e["out"]
        self._check_row(body, self.progress.owned(sp, v), "Owned", "Space", GREEN,
                        lambda: self.toggle_entry(e, "owned"), enabled=on)
        self._check_row(body, self.progress.mastered(sp, v), "Mastered", "M", ACCENT,
                        lambda: self.toggle_entry(e, "mastered"), enabled=on)

        # versions strip: base + every variant, with status rings like the site
        self._section_label(body, "VERSIONS")
        strip = tk.Frame(body, bg=PANEL)
        strip.pack(anchor="w")
        vs = int(54 * s)
        for other in [x for x in self.season_entries() if x["sp"] is sp]:
            own, mas = self.progress.owned(sp, other["v"]), self.progress.mastered(sp, other["v"])
            ring = RED if not other["out"] else ACCENT if mas else GREEN if own else "#55585f"
            cell = tk.Frame(strip, bg=ring if other["key"] == e["key"] or own or not other["out"] else PANEL, padx=2, pady=2)
            cell.pack(side="left", padx=(0, 6))
            img = tk.Label(cell, image=self.entry_image(other, vs, "all", check=False), bg=PANEL, bd=0, cursor="hand2")
            img.pack()
            cap = V[other["v"]]["name"] if other["v"] else "Base"
            mark = "🔒 " if not other["out"] else "♛ " if mas else "✓ " if own else ""
            lbl = tk.Label(cell, text=mark + cap, bg=PANEL, fg=ring if ring != "#55585f" else MUTED, font=self.f_small)
            lbl.pack(fill="x")
            for wd in (img, lbl):
                wd.bind("<Button-1>", lambda ev, k=other["key"]: self.goto_sprite_entry(k))

        facts = []
        cost = (self.sprites["dust"].get(sp["rarity_key"]) or {})
        if cost:
            facts.append(("Resummon", f"{cost.get('variant' if v else 'base', 0):,} Dust  (half when mastered)"))
        se = self.sprite_season_obj()
        facts.append(("Where", sp["where"] or se["how"]))
        facts.append(("Season", se["label"]))
        url = self.sprite_image_url(sp, v)
        facts.append(("Image", "Your photo" if url.startswith("local:") else "Fortnite.GG" if "fortnite.gg" in url else
                      "Fortnite Wiki" if "wikia" in url else "Sprite list" if url else "Stand-in"))
        tk.Frame(body, bg=PANEL, height=int(10 * s)).pack()
        self._facts(body, facts)
        self._buttons(body, [("Copy name", lambda: self.copy(e["name"], "name")),
                             ("All versions", lambda: self.mark_sprite_all(sp, True)),
                             ("Clear all", lambda: self.mark_sprite_all(sp, False))])
        ttk.Button(body, text="View on Fortnite.GG", style="Accent.TButton",
                   command=lambda: self.open_in_chrome(FGG_SPRITES)).pack(fill="x", pady=(int(8 * s), 0))
        self._photo_controls(body, e)
        self._news_cards(body)
        self.detail.bind_tree()

    def goto_sprite_entry(self, key):
        g = self.grids["sprites"]
        if not g.select_key(key):
            self.sprite_variant_var.set("All")
            self.sprite_filter = "All"
            self.search_vars["sprites"].set("")
            self.apply_filter("sprites")
            self.build_sidebar_list()
            g.select_key(key)

    def _refresh_sprite_detail(self):
        if self._detail_refresh_job:
            return

        def run():
            self._detail_refresh_job = None
            g = self.grids["sprites"]
            if self.mode == "sprites" and g.selected is not None and g.flat:
                y = self.detail.canvas.yview()[0]
                self.show_sprite_detail(g.flat[g.selected])
                self.root.update_idletasks()
                self.detail.canvas.yview_moveto(y)

        self._detail_refresh_job = self.root.after(60, run)

    def toggle_entry(self, e, what, value=None):
        if not e["out"]:
            return
        self.progress.set(e["sp"], e["v"], what, value)
        self._after_progress(e)

    def mark_sprite_all(self, sp, on):
        for e in self.season_entries():
            if e["sp"] is sp and (e["out"] or not on):
                self.progress.set(sp, e["v"], "mastered" if on else "owned", on)
        g = self.grids["sprites"]
        self._after_progress(g.flat[g.selected] if g.selected is not None else None)

    def _after_progress(self, e):
        g = self.grids["sprites"]
        if self.sprite_filter != "All" or self.sprite_sort_var.get() in ("Missing first", "Owned first"):
            top = g.canvas.yview()[0]
            self.apply_filter("sprites")
            g.canvas.yview_moveto(top)
            if not e or not g.select_key(e["key"], notify=False):
                g.redraw()
                self.show_empty_detail()
                self._sprite_counts_changed()
                return
        for sec in g.sections:
            if sec.get("title"):
                sec["subtitle"] = self._section_sub(sec["items"])
        g.redraw()
        self._sprite_counts_changed()
        if e and self.mode == "sprites" and g.selected is not None and g.flat[g.selected]["key"] == e["key"]:
            self._refresh_sprite_detail()

    def _sprite_key(self, what):
        e = self._selected_entry()
        if e:
            self.toggle_entry(e, what)

    def _sprite_menu(self, m, e):
        sp, v = e["sp"], e["v"]
        if e["out"]:
            m.add_command(label=("✓ " if self.progress.owned(sp, v) else "    ") + "Owned",
                          command=lambda: self.toggle_entry(e, "owned"))
            m.add_command(label=("✓ " if self.progress.mastered(sp, v) else "    ") + "Mastered",
                          command=lambda: self.toggle_entry(e, "mastered"))
            m.add_separator()
        m.add_command(label="Copy name", command=lambda: self.copy(e["name"], "name"))
        m.add_command(label="Paste photo  (Ctrl+V)", command=lambda: self.paste_sprite_photo(e))
        m.add_command(label="View on Fortnite.GG", command=lambda: self.open_in_chrome(FGG_SPRITES))

    # ------------------------------------------------------------ weapons & items
    def load_weapons(self):
        if "weapons" in self.loading:
            return
        self._set_loading("weapons", True)

        def work():
            errors = []
            try:  # live (refreshed daily by GitHub Actions) -> last good copy -> copy shipped with the app
                raw = http_get(WEAPONS_URL, timeout=30)
                data = normalize_weapons(json.loads(raw))
                WEAPONS_FILE.write_bytes(raw)
                self.results.put(("weapons", data))
                return
            except Exception as e:
                errors.append(e)
            for path in (WEAPONS_FILE, bundled_data_path("weapons.json")):
                try:
                    if path and path.exists():
                        self.results.put(("weapons", normalize_weapons(json.loads(path.read_text(encoding="utf-8")))))
                        return
                except Exception as e:
                    errors.append(e)
            self.results.put(("error", "weapons", errors[0]))

        threading.Thread(target=work, daemon=True).start()

    def weapon_rar(self, w):
        """Selected rarity for a weapon (default: lowest available, like Fortnite.GG cards)."""
        r = self.weapon_rarity.get(w["key"])
        return r if r in w["rarities"] else (w["rarities"][0] if w["rarities"] else "")

    def weapon_sections(self, terms):
        if not self.weapons:
            return []
        pool = self.weapon_pool_var.get() == WEAPON_POOLS[0]
        items = [w for w in self.weapons["pool" if pool else "all"] if all(t in w["search"] for t in terms)]
        sort = self.weapon_sort_var.get()
        if sort == "Class":
            secs = {}
            for w in sorted(items, key=lambda w: (w["corder"], w["special"], 0 if pool else w["name"].lower())):
                secs.setdefault(w["cat_label"], []).append(w)
            return [{"title": t, "subtitle": f"{len(v)}", "items": v} for t, v in secs.items()]
        if sort == "Name":
            items.sort(key=lambda w: w["name"].lower())
        elif sort == "Chest chance":
            items.sort(key=lambda w: -(w["rates"].get("chests") or 0))
        else:
            key, sign = WEAPON_SORT_KEYS[sort]
            def val(w):
                v = (w["stats"].get(self.weapon_rar(w)) or {}).get(key)
                return (v is None, sign * (v or 0))
            items.sort(key=val)
        return [{"title": None, "items": items}] if items else []

    def weapon_stats_text(self, w):
        st = w["stats"].get(self.weapon_rar(w)) or {}
        parts = [f"{lbl} {fmt_stat(st.get(k), u)}" for k, lbl, u, _ in WEAPON_STATS if st.get(k) is not None]
        return f"{w['name']} ({self.weapon_rar(w).title()}): " + ", ".join(parts) if parts else w["name"]

    def draw_weapon_tile(self, c, w, x, y, wd, h, hover, sel):
        s = self.scale
        r = self.weapon_rar(w)
        rc = rarity_color(r)
        round_rect(c, x, y, x + wd, y + h, RADIUS, fill=PANEL_HOVER if hover else PANEL, outline="")
        bg = ("lin", shade(rc, -0.35), PANEL)
        ph = self.request_image(w["image"], 256, wd, bg) if w["image"] else None
        if ph is not None:
            c.create_image(x, y, image=ph, anchor="nw")
        else:
            round_rect(c, x, y, x + wd, y + wd, RADIUS, fill=shade(rc, -0.45), outline="")
        if w["special"]:
            self._pill(c, x + int(6 * s), y + int(6 * s), "SPECIAL", "#11131a")
        # rarity pips
        px = x + int(8 * s)
        for rr in w["rarities"]:
            c.create_rectangle(px, y + wd - int(9 * s), px + int(12 * s), y + wd - int(5 * s), fill=rarity_color(rr),
                               outline="white" if rr == r else "")
            px += int(15 * s)
        pad = int(8 * s)
        c.create_text(x + pad, y + wd + int(6 * s), anchor="nw", fill=FG, font=self.f_tile,
                      text=self.ellipsize(w["name"], self.f_tile, wd - 2 * pad))
        st = w["stats"].get(r) or {}
        if st.get("dmg") is not None:
            line = f"{fmt_stat(st.get('dmg'))} DMG  ·  {fmt_stat(st.get('dps'))} DPS"
        else:
            line = w["cat_label"]
        c.create_text(x + pad, y + wd + int(24 * s), anchor="nw", fill=FG_2, font=self.f_small,
                      text=self.ellipsize(line, self.f_small, wd - 2 * pad))
        ch = w["rates"].get("chests")
        if ch is not None:
            c.create_text(x + pad, y + wd + int(40 * s), anchor="nw", fill=MUTED_2, font=self.f_small,
                          text=self.ellipsize(f"Chests {fmt_stat(ch)}%", self.f_small, wd - 2 * pad))
        self._finish_card(c, x, y, wd, h, hover, sel)

    def set_weapon_rarity(self, w, r):
        self.weapon_rarity[w["key"]] = r
        self.grids["weapons"].redraw()
        y = self.detail.canvas.yview()[0]
        self.show_weapon_detail(w)
        self.root.update_idletasks()
        self.detail.canvas.yview_moveto(y)

    def _stat_tiles(self, body, w, st):
        s = self.scale
        tiles = [("DAMAGE", fmt_stat(st.get("dmg")), f"{fmt_stat(st.get('head'))} headshot" if st.get("head") is not None else ""),
                 ("DPS", fmt_stat(st.get("dps")), f"{fmt_stat(st.get('rate'))} shots / s" if st.get("rate") is not None else ""),
                 ("MAGAZINE", fmt_stat(st.get("mag")), "per reload"),
                 ("RELOAD", fmt_stat(st.get("reload"), "s"), ""),
                 ("STRUCTURES", fmt_stat(st.get("struct")), "damage to builds"),
                 ("HEADSHOT", f"{fmt_stat(w['headmult'])}×" if w.get("headmult") else
                  (f"{fmt_stat(round(st['head'] / st['dmg'], 2))}×" if st.get("head") and st.get("dmg") else "-"), "multiplier")]
        grid = tk.Frame(body, bg=PANEL)
        grid.pack(fill="x", pady=(0, int(8 * s)))
        for i, (lbl, val, sub) in enumerate(tiles):
            cell = tk.Frame(grid, bg="#2b2d31", padx=int(8 * s), pady=int(6 * s))
            cell.grid(row=i // 3, column=i % 3, sticky="nsew", padx=2, pady=2)
            grid.columnconfigure(i % 3, weight=1)
            tk.Label(cell, text=lbl, bg="#2b2d31", fg=MUTED, font=self.f_section, anchor="w").pack(fill="x")
            tk.Label(cell, text=val, bg="#2b2d31", fg=FG, font=self.f_stat, anchor="w").pack(fill="x")
            tk.Label(cell, text=sub, bg="#2b2d31", fg=MUTED_2, font=self.f_small, anchor="w").pack(fill="x")

    def _stat_matrix(self, body, w):
        s = self.scale
        rars = [r for r in w["rarities"] if r in w["stats"]]
        rows = [(k, lbl, u, low) for k, lbl, u, low in WEAPON_STATS if any(w["stats"][r].get(k) is not None for r in rars)]
        if len(rars) < 2 or not rows:
            return
        self._section_label(body, "ALL RARITIES")
        t = tk.Frame(body, bg=PANEL)
        t.pack(fill="x")
        tk.Label(t, text="", bg=PANEL).grid(row=0, column=0)
        for j, r in enumerate(rars, 1):
            tk.Label(t, text=r[:4].upper(), bg=PANEL, fg=rarity_color(r), font=self.f_section).grid(row=0, column=j, sticky="e", padx=3)
        for i, (k, lbl, u, low) in enumerate(rows, 1):
            vals = [w["stats"][r].get(k) for r in rars]
            nums = [v for v in vals if v is not None]
            best = (min(nums) if low else max(nums)) if nums and len(set(nums)) > 1 else None
            tk.Label(t, text=lbl, bg=PANEL, fg=MUTED, font=self.f_small, anchor="w").grid(row=i, column=0, sticky="w", pady=1)
            for j, v in enumerate(vals, 1):
                tk.Label(t, text=fmt_stat(v, u), bg=PANEL, fg=ACCENT if v is not None and v == best else FG_2,
                         font=self.f_small).grid(row=i, column=j, sticky="e", padx=3)
        t.columnconfigure(0, weight=1)

    def _falloff_chart(self, body, pts):
        if len(pts) < 2:
            return
        s = self.scale
        self._section_label(body, "DAMAGE BY DISTANCE")
        W, H, pad = self.detail_wrap, int(110 * s), int(22 * s)
        c = tk.Canvas(body, width=W, height=H, bg="#2b2d31", highlightthickness=0)
        c.pack(anchor="w")
        xmax = max(p[0] for p in pts) or 1
        ymax = max(p[1] for p in pts) * 1.15 or 1
        X = lambda d: pad + (W - pad - 26 * s) * d / xmax
        Y = lambda v: H - 18 * s - (H - 30 * s) * v / ymax
        c.create_line(pad, H - 18 * s, W - 10, H - 18 * s, fill=LINE)
        coords = [v for p in pts for v in (X(p[0]), Y(p[1]))]
        c.create_line(*coords, fill=ACCENT, width=max(2, int(2 * s)))
        for d, v in pts:
            c.create_oval(X(d) - 3, Y(v) - 3, X(d) + 3, Y(v) + 3, fill=ACCENT, outline="")
            c.create_text(X(d), Y(v) - 9 * s, text=fmt_stat(round(v, 1)), fill=FG_2, font=self.f_small)
            c.create_text(X(d), H - 8 * s, text=f"{fmt_stat(d)}m", fill=MUTED_2, font=self.f_small)

    def show_weapon_detail(self, w):
        body = self._detail_reset()
        s = self.scale
        r = self.weapon_rar(w)
        bg = ("lin", shade(rarity_color(r), -0.35), PANEL)
        self._detail_image(body, w["image"], 512, bg) if w["image"] else None
        self._label(body, w["name"].upper(), self.f_title)
        badges = [(w["cat_label"].upper(), PANEL_2, FG)]
        if w["ammo"]:
            badges.append((w["ammo"].upper(), "#3a3c42", FG))
        if w["special"]:
            badges.append(("SPECIAL", ACCENT, ACCENT_FG))
        self._badges(body, badges)
        if w["desc"]:
            self._label(body, w["desc"], self.f_base, FG_2, pady=(0, int(8 * s)))
        # rarity selector
        if w["rarities"]:
            row = tk.Frame(body, bg=PANEL)
            row.pack(anchor="w", pady=(0, int(8 * s)))
            for rr in w["rarities"]:
                on = rr == r
                b = tk.Label(row, text=rr.upper(), bg=rarity_color(rr) if on else PANEL_2, fg="white",
                             font=self.f_chip, padx=int(8 * s), pady=int(3 * s), cursor="hand2",
                             highlightthickness=1, highlightbackground=rarity_color(rr))
                b.pack(side="left", padx=(0, 4))
                b.bind("<Button-1>", lambda e, rr=rr: self.set_weapon_rarity(w, rr))
        st = w["stats"].get(r) or {}
        if st.get("dmg") is not None:
            self._stat_tiles(body, w, st)
            idx = w["rarities"].index(r) if r in w["rarities"] else 0
            if w["falloff"]:
                self._falloff_chart(body, w["falloff"][min(idx, len(w["falloff"]) - 1)])
            self._stat_matrix(body, w)
        where = w["where"] or {k.replace("-", " ").title(): v for k, v in w["rates"].items()}
        if where:
            self._section_label(body, f"WHERE TO FIND IT  ·  {self.weapons['mode'].upper()}")
            mx = max(where.values()) or 1
            for k, v in where.items():
                row = tk.Frame(body, bg=PANEL)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=k, bg=PANEL, fg=FG_2, font=self.f_small, width=14, anchor="w").pack(side="left")
                bar = tk.Canvas(row, height=int(8 * s), bg="#2b2d31", highlightthickness=0, width=int(150 * s))
                bar.pack(side="left", padx=4)
                bar.create_rectangle(0, 0, int(150 * s * v / mx), int(8 * s), fill=ACCENT, outline="")
                tk.Label(row, text=f"{fmt_stat(v)}%", bg=PANEL, fg=FG, font=self.f_small).pack(side="right")
            if w["also"]:
                self._label(body, "Also from: " + ", ".join(f"{k} ({fmt_stat(v)}%)" for k, v in w["also"].items()),
                            self.f_small, MUTED, pady=(4, 0))
        facts = []
        if w["modes"]:
            facts.append(("Modes", ", ".join(w["modes"])))
        if not w["pool"]:
            facts.append(("Pool", "Not in the current Battle Royale loot pool" if not any(
                p["slug"] == w["slug"] for p in self.weapons["pool"]) else "In the current loot pool"))
        facts.append(("Data", f"Fortnite.GG · updated {self.weapons['updated']}"))
        tk.Frame(body, bg=PANEL, height=int(8 * s)).pack()
        self._facts(body, facts)
        self._buttons(body, [("Copy name", lambda: self.copy(w["name"], "name")),
                             ("Copy stats", lambda: self.copy(self.weapon_stats_text(w), "stats"))])
        ttk.Button(body, text="View on Fortnite.GG", style="Accent.TButton",
                   command=lambda: self.open_in_chrome(FGG_WEAPON.format(slug=w["slug"]))).pack(fill="x", pady=(int(8 * s), 0))
        self.detail.bind_tree()

    # ------------------------------------------------------------ news
    def load_news(self):
        if "news" in self.loading:
            return
        self._set_loading("news", True)

        def work():
            try:
                motds = (json.loads(http_get(API_NEWS_BR, timeout=30)).get("data") or {}).get("motds") or []
            except Exception:
                motds = []
            errors = []
            try:  # live (refreshed every 3 h by GitHub Actions) -> last good copy -> copy shipped with the app
                raw = http_get(NEWS_URL, timeout=30)
                data = normalize_news(json.loads(raw), motds)
                NEWS_FILE.write_bytes(raw)
                self.results.put(("news", data))
                return
            except Exception as e:
                errors.append(e)
            for path in (NEWS_FILE, bundled_data_path("news.json")):
                try:
                    if path and path.exists():
                        self.results.put(("news", normalize_news(json.loads(path.read_text(encoding="utf-8")), motds)))
                        return
                except Exception as e:
                    errors.append(e)
            self.results.put(("error", "news", errors[0]))

        threading.Thread(target=work, daemon=True).start()

    def news_sections(self, terms):
        if not self.news:
            return []
        match = lambda n: all(t in n["search"] for t in terms)
        secs = {}
        live = [n for n in self.news["items"] if n["live"] and match(n)]
        if live:
            secs["In game now"] = live
        for n in self.news["items"]:
            if n["live"] or not match(n):
                continue
            try:
                title = datetime.strptime(n["date"], "%Y-%m-%d").strftime("%B %Y")
            except ValueError:
                title = "Older"
            secs.setdefault(title, []).append(n)
        return [{"title": t, "subtitle": f"{len(v)} {'story' if len(v) == 1 else 'stories'}", "items": v} for t, v in secs.items()]

    def draw_news_tile(self, c, n, x, y, wd, h, hover, sel):
        s = self.scale
        ih = round(wd * 9 / 16)
        round_rect(c, x, y, x + wd, y + h, RADIUS, fill=PANEL_HOVER if hover else PANEL, outline="")
        ph = self.request_image(n["image"], 960, wd, None) if n["image"] else None
        if ph is not None:
            c.create_image(x, y, image=ph, anchor="nw")
        else:
            c.create_rectangle(x, y, x + wd, y + ih, fill=PANEL_2, outline="")
        if n["live"]:
            self._pill(c, x + int(8 * s), y + int(8 * s), "IN GAME NOW", "#1f7a2e")
        pad = int(10 * s)
        meta = fmt_news_date(n["date"])
        if n["votes"] and n["votes"].get("fire") is not None:
            meta += f"   ·   {round(n['votes']['fire'])}% liked"
        c.create_text(x + pad, y + ih + int(7 * s), anchor="nw", fill=MUTED_2, font=self.f_small, text=meta)
        c.create_text(x + pad, y + ih + int(22 * s), anchor="nw", fill=FG, font=self.f_chip,
                      text=self.ellipsize(n["title"].upper(), self.f_chip, wd - 2 * pad))
        desc = n["desc"]
        words, lines, cur = desc.split(), [], ""
        for wd_ in words:  # two-line clamp
            t = f"{cur} {wd_}".strip()
            if self.f_small.measure(t) > wd - 2 * pad and cur:
                lines.append(cur)
                cur = wd_
                if len(lines) == 2:
                    break
            else:
                cur = t
        if len(lines) < 2 and cur:
            lines.append(cur)
        if len(lines) == 2 and " ".join(lines) != desc:
            lines[1] = self.ellipsize(lines[1] + " …", self.f_small, wd - 2 * pad)
        for i, ln in enumerate(lines[:2]):
            c.create_text(x + pad, y + ih + int((42 + i * 15) * s), anchor="nw", fill=MUTED, font=self.f_small, text=ln)
        self._finish_card(c, x, y, wd, h, hover, sel)

    def show_news_detail(self, n):
        body = self._detail_reset()
        s = self.scale
        url = n["image_large"] or n["image"]
        if url:
            disp = int(310 * s)
            ph = self.request_image(url, 960, disp, None, check=False)
            self.detail_ck = (url, disp, None, None)
            self.detail_photo = ph
            self.detail_img = tk.Label(body, image=ph or "", bg=PANEL_2, bd=0, cursor="hand2",
                                       width=disp if not ph else 0, height=round(disp * 9 / 16) if not ph else 0)
            self.detail_img.pack(pady=(0, int(14 * s)))
            self.detail_img.bind("<Button-1>", lambda e: self.open_url(url))
        self._label(body, n["title"].upper(), self.f_title)
        badges = [(fmt_news_date(n["date"]).upper(), PANEL_2, FG)]
        if n["live"]:
            badges.insert(0, ("IN GAME NOW", ACCENT, ACCENT_FG))
        self._badges(body, badges)
        if n["desc"]:
            self._label(body, n["desc"], self.f_base, FG_2, pady=(0, int(10 * s)))
        if n["links"]:
            self._section_label(body, "LINKS")
            lower = {k.lower(): k for k in self.items_by_id}
            for ln in n["links"]:
                cid = lower.get((ln.get("cosmetic") or "").lower())
                if cid:
                    self._link(body, ln["label"], f"{self.items_by_id[cid]['name']}  ›", lambda cid=cid: self.goto_cosmetic(cid))
                else:
                    self._link(body, ln["label"], "Island on Fortnite.GG ↗" if ln.get("island") else "Fortnite.GG ↗",
                               lambda u=ln["url"]: self.open_in_chrome(u))
            tk.Frame(body, bg=PANEL, height=int(6 * s)).pack()
        facts = [("Published", fmt_news_date(n["date"]) or "-"),
                 ("Source", "Epic in-game news (live)" if n["epic"] else "Epic's Fortnite news, archived by Fortnite.GG")]
        if n["votes"]:
            v = n["votes"]
            facts.append(("Player votes", (f"{round(v['fire'])}% liked · " if v.get("fire") is not None else "") +
                          f"{v.get('total', 0):,} votes on Fortnite.GG"))
        self._facts(body, facts)
        self._buttons(body, [("Copy headline", lambda: self.copy(n["title"], "headline")),
                             ("Open image", lambda: self.open_url(url))])
        ttk.Button(body, text="Read Fortnite news on fortnite.com", style="Accent.TButton",
                   command=lambda: self.open_in_chrome(FN_NEWS)).pack(fill="x", pady=(int(8 * s), 0))
        ttk.Button(body, text="News archive on Fortnite.GG",
                   command=lambda: self.open_in_chrome(FGG_NEWS)).pack(fill="x", pady=(int(6 * s), 0))
        self.detail.bind_tree()

    # ------------------------------------------------------------ interactive map
    def load_map(self):
        if "map" in self.loading:
            return
        self._set_loading("map", True)

        def work():
            errors = []
            try:  # live (refreshed daily by GitHub Actions) -> last good copy -> copy shipped with the app
                raw = http_get(MAP_URL, timeout=30)
                data = normalize_map(json.loads(raw))
                MAP_FILE.write_bytes(raw)
                self.results.put(("map", data))
                return
            except Exception as e:
                errors.append(e)
            for path in (MAP_FILE, bundled_data_path("map.json")):
                try:
                    if path and path.exists():
                        self.results.put(("map", normalize_map(json.loads(path.read_text(encoding="utf-8")))))
                        return
                except Exception as e:
                    errors.append(e)
            self.results.put(("error", "map", errors[0]))

        threading.Thread(target=work, daemon=True).start()

    def _on_map(self, data):
        self._set_loading("map", False)
        self.map_data, self.map_error = data, None
        layers = data["layers"]
        if self.map_on is None:
            self.map_on = {i for i in data.get("defaultOn") or [] if i in layers}
        else:
            self.map_on = {i for i in self.map_on if i in layers}
        self.nav_map.set_right(f"S{data.get('season')}")
        self.grids["map"].set_data(data, self.map_on)
        if self.mode == "map":
            self.build_sidebar_list()
            if not self.grids["map"].hit_sel:
                self.show_map_info()
        self.update_status()

    def set_map_layers(self, ids):
        self.map_on = set(ids)
        self._save_settings()
        mv = self.grids["map"]
        mv.set_enabled(self.map_on)
        self.build_sidebar_list(keep_scroll=True)
        if mv.hit_sel:
            self.show_map_hit(mv.hit_sel)
        else:
            self.show_map_info()
        self.update_status()

    def toggle_map_layer(self, lid):
        on = set(self.map_on or ())
        on.symmetric_difference_update({lid})
        self.set_map_layers(on)

    def map_locations(self):
        out = []
        for lid in ("poi", "landmarks"):
            for b in (self.map_data["layers"].get(lid) or {}).get("labels", []):
                out.append({**b, "major": lid == "poi"})
        return out

    def nearest_location(self, pt):
        best, bd = None, float("inf")
        for b in self.map_locations():
            d = math.hypot(b["pt"][0] - pt[0], b["pt"][1] - pt[1]) * (0.8 if b["major"] else 1)
            if d < bd:
                best, bd = b, d
        return best

    def goto_map_location(self, b):
        lid = "poi" if b["major"] else "landmarks"
        if lid not in self.map_on:
            self.toggle_map_layer(lid)
        mv = self.grids["map"]
        hit = {"layer": self.map_data["layers"][lid], "pt": b["pt"], "name": b["name"], "label": True}
        mv.hit_sel = hit
        mv.fly_to(b["pt"], 4.6)
        self.show_map_hit(hit)

    def _schedule_map_sidebar(self):
        if getattr(self, "_map_side_job", None) is None:
            def run():
                self._map_side_job = None
                if self.mode == "map":
                    self.build_sidebar_list(keep_scroll=True)
                    mv = self.grids["map"]
                    self.show_map_hit(mv.hit_sel) if mv.hit_sel else self.show_map_info()
            self._map_side_job = self.root.after(250, run)

    def _build_map_sidebar(self, inner):
        self.side_heading.configure(text="MAP LAYERS")
        if not self.map_data:
            tk.Label(inner, text="Map unavailable" if self.map_error else "Loading the map...", bg=SIDEBAR, fg=MUTED,
                     font=self.f_small, anchor="w", padx=16).pack(fill="x")
            return
        s = self.scale
        mv = self.grids["map"]
        terms = self.search_vars["map"].get().lower().split()
        hit = lambda txt: all(t in txt.lower() for t in terms)
        sub = lambda text: tk.Label(inner, text=text.upper(), bg=SIDEBAR, fg=MUTED, font=self.f_section, anchor="w",
                                    padx=16).pack(fill="x", pady=(int(10 * s), int(2 * s)))
        if terms:
            locs = [b for b in self.map_locations() if hit(b["name"])][:12]
            if locs:
                sub("Go to location")
                for b in locs:
                    SideRow(inner, b["name"], "POI" if b["major"] else "", lambda b=b: self.goto_map_location(b),
                            self.f_base, self.f_small).pack(fill="x")
        else:
            row = tk.Frame(inner, bg=SIDEBAR)
            row.pack(fill="x", pady=(0, int(2 * s)))
            layers = self.map_data["layers"]
            for text, ids in (("Show all", lambda: list(layers)), ("Hide all", lambda: []),
                              ("Default", lambda: [i for i in self.map_data.get("defaultOn") or [] if i in layers])):
                lbl = tk.Label(row, text=text, bg=SIDEBAR, fg=ACCENT, font=self.f_small, cursor="hand2", padx=8)
                lbl.pack(side="left", padx=(8 if text == "Show all" else 0, 0))
                lbl.bind("<Button-1>", lambda e, ids=ids: self.set_map_layers(ids()))
        any_row = False
        for g in self.map_data["groups"]:
            ls = [l for l in g["layers"] if not terms or hit(f"{l['name']} {l.get('sub', '')} {g['name']}")]
            if not ls:
                continue
            sub(g["name"])
            for l in ls:
                ph = mv.icon_photo(l.get("icon"), int(20 * s)) if l.get("icon") is not None else None
                r = SideRow(inner, f" {l['name']}", f"{l['n']:,}", lambda lid=l["id"]: self.toggle_map_layer(lid),
                            self.f_base, self.f_small, pady=3, image=ph)
                r.pack(fill="x")
                r.set_active(l["id"] in self.map_on)
                any_row = True
        if not any_row and not terms:
            tk.Label(inner, text="No layers.", bg=SIDEBAR, fg=MUTED, font=self.f_small, padx=16).pack(fill="x")

    def show_map_info(self):
        if self.mode != "map":
            return
        body = self._detail_reset()
        s = self.scale
        if not self.map_data:
            self._label(body, "FORTNITE MAP", self.f_title)
            self._label(body, f"Couldn't load the map.\n{self.map_error}" if self.map_error else "Loading the map...",
                        self.f_base, MUTED)
            return
        d = self.map_data
        self._label(body, "FORTNITE MAP", self.f_title)
        self._badges(body, [(f"SEASON {d.get('season')}", ACCENT, ACCENT_FG), (f"MAP {d.get('version')}", PANEL_2, FG)])
        self._label(body, "Drag to pan, scroll to zoom, click a marker for details. Numbers on icons are clusters: "
                          "click one to zoom in. Pick layers on the left.  + / - zoom, arrows pan, 0 resets.",
                    self.f_base, FG_2, pady=(0, int(10 * s)))
        on = [d["layers"][i] for i in d["layers"] if i in (self.map_on or ())]
        self._facts(body, [("Layers on", f"{len(on)} of {len(d['layers'])}"),
                           ("Markers shown", f"{sum(l['n'] for l in on):,}"),
                           ("Data", f"Fortnite.GG · updated {d.get('updated')}")])
        legend = [l for l in on if l["kind"] != "labels"]
        if legend:
            self._section_label(body, "SHOWING  ·  CLICK TO SHOW ONLY THAT LAYER")
            mv = self.grids["map"]
            for l in legend:
                row = self._link(body, f" {l['name']}", f"{l['n']:,}", lambda lid=l["id"]: self.set_map_layers([lid, "poi"]))
                ph = mv.icon_photo(l.get("icon"), int(20 * s))
                if ph:
                    row.winfo_children()[0].configure(image=ph, compound="left")
        self._buttons(body, [("Reset view", lambda: self.grids["map"].fit()),
                             ("Default layers", lambda: self.set_map_layers(
                                 [i for i in d.get("defaultOn") or [] if i in d["layers"]]))])
        ttk.Button(body, text="Open the full map on Fortnite.GG", style="Accent.TButton",
                   command=lambda: self.open_in_chrome(FGG_MAP)).pack(fill="x", pady=(int(8 * s), 0))
        self.detail.bind_tree()

    def show_map_hit(self, h):
        body = self._detail_reset()
        s = self.scale
        mv = self.grids["map"]
        l = self.map_data["layers"][h["layer"]["id"]]
        title = h["name"] if h.get("label") else l["name"]
        icon = h.get("icon") if h.get("icon") is not None else l.get("icon")
        ph = mv.icon_photo(icon, int(72 * s)) if icon is not None else None
        if ph:
            self._map_icon_ref = ph
            tk.Label(body, image=ph, bg="#2b2d31", width=int(300 * s), height=int(110 * s)).pack(fill="x", pady=(0, int(14 * s)))
        self._label(body, title.upper(), self.f_title)
        self._badges(body, [(l["group_name"].upper(), PANEL_2, FG)] +
                     ([] if h.get("label") else [(l["name"].upper(), "#3a3c42", FG)]))
        facts = [("Layer", f"{l['name']} · {l['group_name']}")]
        near = None if h.get("label") else self.nearest_location(h["pt"])
        if near:
            facts.append(("Nearest place", near["name"]))
        if l.get("sub"):
            facts.append(("Note", l["sub"]))
        if h.get("to"):
            facts.append(("Leads to", f"{h['to'][0]:.1f}, {h['to'][1]:.1f}"))
        facts += [("On this map", f"{l['n']:,} {'places' if l['kind'] == 'labels' else 'markers'}"),
                  ("Map position", f"{h['pt'][0]:.1f}, {h['pt'][1]:.1f}")]
        self._facts(body, facts)
        self._buttons(body, [("Zoom here", lambda: mv.fly_to(h["pt"], max(mv.view[2] + 1, 5.5))),
                             ("Only this layer", lambda: self.set_map_layers([l["id"]] if l["kind"] == "labels" else [l["id"], "poi"])),
                             ("Hide layer", lambda: self.set_map_layers((self.map_on or set()) - {l["id"]}))])
        self._buttons(body, [("Copy name", lambda: self.copy(title, "name")),
                             ("Copy position", lambda: self.copy(f"{h['pt'][0]:.1f}, {h['pt'][1]:.1f}", "position"))])
        ttk.Button(body, text="Open the full map on Fortnite.GG", style="Accent.TButton",
                   command=lambda: self.open_in_chrome(FGG_MAP)).pack(fill="x", pady=(int(8 * s), 0))
        self.detail.bind_tree()

    def export_progress(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile="fortnite_sprite_progress.json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(json.dumps(self.progress.export_obj(), indent=1), encoding="utf-8")
            self.status_var.set(f"Exported sprite progress to {path}")

    def import_progress(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            n = self.progress.import_obj(json.loads(Path(path).read_text(encoding="utf-8-sig")))
        except Exception as e:
            messagebox.showerror("Import failed", f"Not a sprite progress file:\n{e}")
            return
        self.apply_filter("sprites")
        self._sprite_counts_changed()
        self.status_var.set(f"Imported progress for {n} sprites (merged with what you had)")

    def export_csv(self):
        g = self.grids["browse"]
        if not g.flat:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="fortnite_cosmetics.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        cols = ["id", "name", "type", "rarity", "set", "intro", "added", "description", "icon"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(g.flat)
        self.status_var.set(f"Exported {len(g.flat):,} cosmetics to {path}")


def main():
    try:  # crisp rendering on high-DPI displays + own taskbar icon
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("248Tech.FortniteCosmeticsBrowser")
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
