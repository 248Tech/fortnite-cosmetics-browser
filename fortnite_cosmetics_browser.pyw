"""Fortnite Cosmetics Browser - a fast Windows app for every Fortnite cosmetic and the daily Item Shop.

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
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.parse
import urllib.request
import webbrowser
from bisect import bisect_right
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk, features

__version__ = "1.0.0"
APP_NAME = "Fortnite Cosmetics Browser"
REPO_URL = "https://github.com/248Tech/fortnite-cosmetics-browser"

API_COSMETICS = "https://fortnite-api.com/v2/cosmetics/br"
API_SHOP = "https://fortnite-api.com/v2/shop"
USER_AGENT = f"FortniteCosmeticsBrowser/{__version__} (+{REPO_URL})"

CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FortniteCosmeticsBrowser"
DATA_FILE = CACHE_DIR / "cosmetics_br.json"
SHOP_FILE = CACHE_DIR / "shop.json"
SETTINGS_FILE = CACHE_DIR / "settings.json"
THUMB_DIR = CACHE_DIR / "thumbs"
MAX_DATA_AGE = 12 * 3600
PHOTO_CACHE_MAX = 1500
IMG_EXT = "webp" if features.check("webp") else "png"

# palette
BG = "#121318"
SIDEBAR = "#181a21"
PANEL = "#1e2029"
PANEL_HOVER = "#272a36"
PANEL_2 = "#2a2d3a"
LINE = "#30333f"
FG = "#eceef3"
MUTED = "#9096a3"
ACCENT = "#4f8cff"
GREEN = "#3ecf7a"
GOLD = "#f2c14e"

RARITY_COLORS = {
    "common": "#7d838d", "uncommon": "#4f9a33", "rare": "#2f7fd6",
    "epic": "#9645d6", "legendary": "#d47a24", "mythic": "#c9a52f",
    "exotic": "#2fb4c6", "transcendent": "#c33f62", "marvel": "#c22f2c",
    "dc": "#2a58ad", "icon": "#279c94", "gaminglegends": "#5243c9",
    "starwars": "#26307f", "dark": "#94208e", "frozen": "#6fb0dc",
    "lava": "#bd4a28", "shadow": "#45454e", "slurp": "#1fa9b9",
}
RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary", "mythic",
                "exotic", "transcendent"]
SORTS = ["Newest", "Oldest", "Name A-Z", "Name Z-A", "Rarity (high-low)", "Rarity (low-high)"]
TILE_SIZES = {"S": 92, "M": 116, "L": 150}
MIN_CATEGORY = 20  # types with fewer items are grouped under "Other"

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
    base = radial_bg(bg, disp)
    base.alpha_composite(im, ((disp - im.width) // 2, (disp - im.height) // 2))
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
    def __init__(self, master, text, right, command, font, small_font, pady=5):
        super().__init__(master, bg=SIDEBAR, cursor="hand2")
        self.active = False
        self.bar = tk.Frame(self, bg=SIDEBAR, width=3)
        self.bar.pack(side="left", fill="y")
        self.lbl = tk.Label(self, text=text, bg=SIDEBAR, fg=FG, font=font, anchor="w",
                            padx=12, pady=pady)
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
        self.lbl.configure(fg=FG if (self.active or hover) else "#c9ccd4")


class VirtualGrid:
    """Canvas grid that only draws visible tiles. Supports titled sections."""

    def __init__(self, app, parent, draw_tile, on_select, on_activate, on_context):
        self.app = app
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
        return self.app.tile

    @property
    def tile_h(self):
        return self.app.tile + self.app.text_h

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
                c.create_text(self.x0, y + rh - int(12 * self.app.scale), text=p["title"],
                              anchor="sw", fill=FG, font=self.app.f_header)
                if p.get("subtitle"):
                    tw = self.app.f_header.measure(p["title"])
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
        self.set_mode(self.settings.get("mode", "browse") if self.settings.get("mode") in ("browse", "shop") else "browse")
        self.show_empty_detail()
        self.load_cosmetics(force=False)
        self.load_shop()
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
            SETTINGS_FILE.write_text(json.dumps({"tile": self.tile_key, "mode": self.mode}), encoding="utf-8")
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
        self.f_header = F(14, fam="Segoe UI Semibold")
        self.f_title = F(17, fam="Segoe UI Semibold")
        self.f_price = F(14, fam="Segoe UI Semibold")
        self.f_logo = F(13, "bold")
        self.f_nav = F(11, fam="Segoe UI Semibold")
        self.f_section = F(8, "bold")

    def _build_style(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL_2,
                     bordercolor=LINE, lightcolor=PANEL_2, darkcolor=PANEL_2, font=self.f_base)
        st.configure("TButton", background=PANEL_2, foreground=FG, padding=(12, 6), borderwidth=0)
        st.map("TButton", background=[("active", "#353a4a"), ("disabled", PANEL)],
               foreground=[("disabled", MUTED)])
        st.configure("Small.TButton", padding=(4, 6))
        st.configure("Accent.TButton", background=ACCENT, foreground="white")
        st.map("Accent.TButton", background=[("active", "#6b9fff"), ("disabled", PANEL_2)])
        st.configure("TCombobox", padding=5, arrowcolor=FG, background=PANEL_2, bordercolor=PANEL_2)
        st.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", FG)],
               selectbackground=[("readonly", PANEL_2)], selectforeground=[("readonly", FG)],
               background=[("active", "#353a4a")])
        st.configure("Vertical.TScrollbar", background=PANEL_2, troughcolor=BG, arrowcolor=MUTED,
                     borderwidth=0, gripcount=0)
        st.map("Vertical.TScrollbar", background=[("active", "#3b4050")])
        self.root.option_add("*TCombobox*Listbox.background", PANEL_2)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
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
        tk.Label(side, text="FORTNITE", bg=SIDEBAR, fg=GOLD, font=self.f_logo, anchor="w",
                 padx=16).pack(fill="x", pady=(int(16 * s), 0))
        tk.Label(side, text="Cosmetics Browser", bg=SIDEBAR, fg=MUTED, font=self.f_small, anchor="w",
                 padx=16).pack(fill="x", pady=(0, int(14 * s)))
        self.nav_browse = SideRow(side, "Cosmetics", "", lambda: self.set_mode("browse"),
                                  self.f_nav, self.f_small, pady=8)
        self.nav_browse.pack(fill="x")
        self.nav_shop = SideRow(side, "Item Shop", "", lambda: self.set_mode("shop"),
                                self.f_nav, self.f_small, pady=8)
        self.nav_shop.pack(fill="x")
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
        self.search_vars = {"browse": tk.StringVar(), "shop": tk.StringVar()}
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
        self.cache_var = tk.StringVar(value="")
        self.cache_lbl = tk.Label(status, textvariable=self.cache_var, bg=SIDEBAR, fg=MUTED, font=self.f_small)
        self.cache_lbl.pack(side="right")

        # grids
        holder = tk.Frame(main, bg=BG)
        holder.pack(side="top", fill="both", expand=True)
        self.grids = {
            "browse": VirtualGrid(self, holder, self.draw_cosmetic_tile, self.show_cosmetic_detail,
                                  lambda it: self.open_url(it["featured"] or it["icon"]), self.context_menu),
            "shop": VirtualGrid(self, holder, self.draw_offer_tile, self.show_offer_detail,
                                lambda it: self.open_url(it["image"]), self.context_menu),
        }
        self.grids["shop"].empty_text = "Loading Item Shop..."

        self.menu = tk.Menu(root, tearoff=0, bg=PANEL_2, fg=FG, activebackground=ACCENT,
                            activeforeground="white", bd=0, font=self.f_base)

        root.bind("<Control-f>", lambda e: (self.search.focus_set(), self.search.select_range(0, "end"), "break")[-1])
        root.bind("<Control-Key-1>", lambda e: self.set_mode("browse"))
        root.bind("<Control-Key-2>", lambda e: self.set_mode("shop"))
        root.bind("<F5>", lambda e: self.refresh_all())
        self.search.bind("<Escape>", lambda e: self.search_vars[self.mode].set(""))

    def _paint_size_btns(self):
        for k, b in self.size_btns.items():
            b.configure(bg=ACCENT if k == self.tile_key else PANEL_2)

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
        self.search.configure(textvariable=self.search_vars[mode])
        self.placeholder.configure(text="Search cosmetics, sets, IDs...   Ctrl+F" if mode == "browse"
                                   else "Search the Item Shop...   Ctrl+F")
        self._update_search_decor()
        if mode == "browse":
            self.browse_tools.pack(side="left")
            self.export_btn.pack(side="right", after=self.cache_lbl, padx=(0, 16))
        else:
            self.browse_tools.pack_forget()
            self.export_btn.pack_forget()
        self.build_sidebar_list()
        self._save_settings()
        self.root.update_idletasks()  # real canvas size before layout
        self.grid.layout()
        sel = self.grid.selected
        if sel is not None and self.grid.flat:
            self.grid.on_select(self.grid.flat[sel])
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

    def build_sidebar_list(self):
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
        else:
            self.side_heading.configure(text="SHOP SECTIONS")
            if self.shop:
                for title, items in self.shop["sections"].items():
                    row = SideRow(inner, title, str(len(items)),
                                  lambda t=title: self.grid.scroll_to_section(t), self.f_base, self.f_small)
                    row.pack(fill="x")
        self.side_list.scroll_top()
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
        else:
            if self.shop:
                n = sum(len(s["items"]) for s in self.grids["shop"].sections)
                rem = (self.shop["reset"] - datetime.now(timezone.utc)).total_seconds()
                when = f"resets in {fmt_remaining(rem)}" if rem > 0 else "refreshing..."
                txt = (f"Item Shop for {self.shop['date'].strftime('%A, %b %d')}   ·   {n} offers"
                       f"   ·   {when}")
            else:
                txt = "Loading the Item Shop..." if "shop" in self.loading else "Item Shop unavailable"
        if self.loading and (self.items or self.shop):
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
                elif kind == "imgskip":
                    self.pending.discard(msg[1])
                elif kind == "imgfail":
                    self.pending.discard(msg[1])
                    self.failed.add(msg[1])
                elif kind == "cosmetics":
                    self._on_cosmetics(*msg[1:])
                elif kind == "shop":
                    self._on_shop(msg[1])
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
            round_rect(c, x, y, x + w, y + h, RADIUS, fill="", outline="#4a5064", width=1)

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
                w.bind("<Enter>", lambda e: [x.configure(bg="#353a4a") for x in (row, a, b)])
                w.bind("<Leave>", lambda e: [x.configure(bg=bg) for x in (row, a, b)])
        return row

    def _store_button(self, parent, cmd):
        ttk.Button(parent, text="↗  Open in Epic Store (Chrome)", style="Accent.TButton",
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
                          "Ctrl+1 / Ctrl+2  -  Cosmetics / Shop",
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
                       fg=GREEN, bg="#17301f")
            tk.Frame(body, bg=PANEL, height=int(6 * self.scale)).pack()
        if it["description"]:
            self._label(body, it["description"], self.f_base, "#c9ccd4", pady=(0, int(12 * self.scale)))
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
