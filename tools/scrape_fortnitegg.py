"""Build docs/data/weapons.json, map.json, news.json, stats.json and locker/*.json from Fortnite.GG.

Sources (used with the site owner's permission):
  https://fortnite.gg/weapons                         current Battle Royale loot pool (cards + spawn rates)
  https://fortnite.gg/weapons/compare?api=catalog     every weapon line with per-rarity damage / DPS
  https://fortnite.gg/weapons/weapon/<slug>           full stat matrix, damage falloff, where to find it
  https://fortnite.gg/  (+ /data/en.js, /data/spawns.js)  interactive map: layers, markers, named locations
  https://fortnite.gg/news?page=N                      archive of Epic's official Fortnite news (image, date, text, links)
  https://fortnite.gg/cosmetics (+ /data/items/all.en.js)  every outfit, emote, pickaxe, glider...; showcase clips at fnggcdn.com/items/<id>/
  https://fortnite.gg/stats[/<mode>]?leaderboard=<key>  season leaderboards (level / wins / kills / time / rank), top 40

Standard library only. Run:
  python tools/scrape_fortnitegg.py                 # all three files
  python tools/scrape_fortnitegg.py --only news     # just one (weapons | map | news | locker | stats)
Options: --out docs/data/weapons.json  --map-out docs/data/map.json  --news-out docs/data/news.json
         --locker-dir docs/data/locker  --stats-out docs/data/stats.json
         --news-pages 5  --delay 0.6
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://fortnite.gg"
UA = "FortniteCosmeticsBrowser/1.1 (+https://github.com/248Tech/fortnite-cosmetics-browser)"
IMG_BASE = f"{BASE}/img/weapons/"

# matrix row label -> key
STAT_KEYS = {
    "Damage": "dmg", "Headshot damage": "head", "Damage per second": "dps", "Fire rate": "rate",
    "Magazine size": "mag", "Reload time": "reload", "Structure damage": "struct", "Spread": "spread",
    "Vertical recoil": "vrecoil", "Horizontal recoil": "hrecoil", "Aim down sights": "ads",
    "Pellets": "pellets", "Charge time": "charge", "Headshot multiplier": "headmult",
}


def get(path, accept_json=False):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json" if accept_json else "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8")
    return json.loads(data) if accept_json else data


def text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def num(s):
    s = text(s).replace(",", "").replace("×", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    v = float(m.group())
    return int(v) if v.is_integer() else v


def parse_rates(block):
    """Spawn chance per source: {"chests": 11.3, ...} (any rarity, from the title attribute)."""
    out = {}
    for src, title in re.findall(r"data-src='([^']+)' title='[^:']*: any rarity ([\d.]+)%'", block):
        out[src] = float(title)
    return out


def parse_loot_pool(page):
    cats = {}
    for cat, label in re.findall(r"<section class='weapons-group' data-cat='([^']+)'><h2>([^<]+)<", page):
        cats[cat] = html.unescape(label)
    items = []
    for sec in re.finditer(r"<section class='weapons-group' data-cat='([^']+)'>(.*?)(?=<section class='weapons-group'|</div></div><footer|$)", page, re.S):
        cat, body = sec.group(1), sec.group(2)
        for card in re.finditer(r"<article class='weapons-card ([^']*)' data-slug='([^']+)' data-loot='([^']*)' data-icon='([^']*)'>(.*?)</article>", body, re.S):
            cls, slug, loot, icon, inner = card.groups()
            name = text((re.search(r"<h3>(.*?)</h3>", inner) or [None, slug])[1])
            rar = re.findall(r"class='weapons-pip r-([a-z]+)", inner)
            img = (re.search(r"<img src='/img/weapons/([^']+)'", inner) or [None, icon])[1]
            blurb = text((re.search(r"<p class='weapons-blurb'>(.*?)</p>", inner, re.S) or [None, ""])[1])
            items.append({"slug": slug, "name": name, "cat": cat, "loot": loot, "icon": img, "rarities": rar,
                          "blurb": blurb, "rates": parse_rates(inner)})
    return cats, items


def parse_detail(page):
    d = {}
    m = re.search(r"<p class='weapons-desc'>(.*?)</p>", page, re.S)
    d["desc"] = text(m.group(1)) if m else ""
    m = re.search(r"class='weapons-ammo[^']*'>([^<]+)<", page)
    d["ammo"] = text(m.group(1)) if m else ""
    d["ids"] = dict(re.findall(r"data-r='([a-z]+)' data-id='([^']+)'", page))
    # full stat matrix (all rarities)
    m = re.search(r"<table class='weapons-matrix'>(.*?)</table>", page, re.S)
    if m:
        heads = re.findall(r"<th class='r-([a-z]+)'", m.group(1))
        stats = {r: {} for r in heads}
        for label, cells in re.findall(r"<tr><th>([^<]+)</th>(.*?)</tr>", m.group(1), re.S):
            key = STAT_KEYS.get(html.unescape(label).strip(), re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_"))
            for r, cell in zip(heads, re.findall(r"<td[^>]*>(.*?)</td>", cells, re.S)):
                v = num(cell)
                if v is not None:
                    stats[r][key] = v
        d["stats"] = stats
    # single-rarity weapons have no matrix: read the headline tiles instead
    tiles = re.findall(r"<div class='weapons-tile[^']*'><span>([^<]+)</span><b>(.*?)</b>(?:<em>(.*?)</em>)?", page)
    if not d.get("stats") and tiles and d["ids"]:
        st = {}
        for label, val, em in tiles:
            label = text(label)
            if label == "Damage":
                st["dmg"] = num(val)
                if "headshot" in (em or ""):
                    st["head"] = num(em)
            elif label == "DPS":
                st["dps"] = num(val)
                if "shots" in (em or ""):
                    st["rate"] = num(em)
            elif label in ("Magazine", "Reload", "Structures"):
                st[{"Magazine": "mag", "Reload": "reload", "Structures": "struct"}[label]] = num(val)
        d["stats"] = {next(iter(d["ids"])): {k: v for k, v in st.items() if v is not None}}
    # headline tiles of the first pane give the headshot multiplier
    m = re.search(r"<span>Headshot</span><b>([\d.]+)×", page)
    if m:
        d["headmult"] = float(m.group(1))
    # damage falloff chart per rarity pane
    charts = re.findall(r"data-chart='([^']+)'", page)
    d["falloff"] = []
    for c in charts:
        try:
            d["falloff"].append(json.loads(html.unescape(c)).get("points") or [])
        except Exception:
            d["falloff"].append([])
    # items: where to find it + "also from"
    finds = re.findall(r"<div class='weapons-find'><span>([^<]+)</span>.*?<b>([\d.]+)%</b>", page, re.S)
    if finds:
        d["where"] = {text(k): float(v) for k, v in finds}
    also = re.findall(r"<em title='([\d.]+)%'>([^<]+)</em>", page)
    if also:
        d["also"] = {text(k): float(v) for v, k in also}
    d["modes"] = [text(x) for x in re.findall(r"<a class='weapons-home[^']*' href='[^']*'[^>]*>([^<]+)<em>", page)]
    return d


# ---------------------------------------------------------------- map
# The home page loads window.Data (en.js: layer tree, names, icons) and window.Spawns (spawns.js: big coordinate
# lists). en.js is a JS object literal that references Spawns.<key> and L10N['text'], so we substitute those and
# parse it as JSON. Map coordinates are Leaflet CRS.Simple [lat, lng] in [-256..0, 0..256]; we store [x, y] with
# x = lng and y = -lat (0..256, y down) so both apps can use plain screen math.
DEFAULT_ON = ["poi", "landmarks", "chests", "rare_chests", "vaults", "key_vaults"]


def load_js_object(src, spawns=None):
    body = src[src.index("=") + 1:].strip().rstrip(";")
    if spawns is not None:
        body = re.sub(r"(?:window\.)?Spawns\.(\w+)",lambda m: json.dumps(spawns.get(m.group(1), [])), body)
    body = re.sub(r"L10N\[(['\"])(.*?)\1\]", lambda m: json.dumps(m.group(2)), body)
    return json.loads(body)


def split_name(raw):
    """'Chests<div ...>gold outline = 100% spawn rate</div>' -> ('Chests', 'gold outline = 100% spawn rate')."""
    raw = raw or ""
    m = re.match(r"(.*?)<div[^>]*>(.*?)</div>", raw, re.S)
    return (text(m.group(1)), text(m.group(2))) if m else (text(raw), "")


def xy(c):
    return [round(c[1], 2), round(-c[0], 2)]


def parse_map(data, now=None):
    now = now or datetime.now(timezone.utc)

    def live(o):
        u = o.get("until")
        if not u:
            return True
        try:
            return datetime.fromisoformat(u.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) > now
        except ValueError:
            return True

    tree = data.get("data") or {}
    spawn_subs = (tree.get("spawns") or {}).get("sub") or {}
    groups = []
    for gid, g in tree.items():
        if not isinstance(g, dict) or not g.get("sub") or not live(g):
            continue
        gname, _ = split_name(g.get("name") or gid)
        layers = []
        for lid, l in g["sub"].items():
            if not isinstance(l, dict) or not live(l):
                continue
            markers = list(l.get("markers") or [])
            for ref in l.get("spawns") or []:  # layer that reuses other spawn layers' markers
                markers += (spawn_subs.get(ref) or {}).get("markers") or []
            name, sub = split_name(l.get("name") or lid)
            layer = {"id": lid, "name": name, "sub": sub, "icon": l.get("menu_icon"), "cluster": bool(l.get("cluster"))}
            if l.get("color"):
                layer["color"] = l["color"]
            pts, lines, labels, tunnels = [], [], [], []
            for m in markers:
                coords = m.get("coords") or []
                if not coords:
                    continue
                if m.get("name") and not m.get("icon") and isinstance(coords[0], (int, float)):
                    labels.append({"name": text(m["name"]), "pt": xy(coords)})
                elif m.get("line"):
                    lines += [[xy(a), xy(b)] for a, b in coords]
                elif m.get("tunnel"):
                    col = m["tunnel"] if isinstance(m["tunnel"], str) else None
                    tunnels.append({"icon": m.get("icon"), "color": col, "pairs": [[xy(a), xy(b)] for a, b in coords]})
                elif isinstance(coords[0], (int, float)):
                    pts.append({"icon": m.get("icon"), **({"size": m["size"]} if m.get("size") else {}), "pts": [xy(coords)]})
                else:
                    pts.append({"icon": m.get("icon"), **({"size": m["size"]} if m.get("size") else {}),
                                "pts": [xy(c) for c in coords if len(c) >= 2]})
            if labels:
                layer.update(kind="labels", labels=labels, n=len(labels))
            elif lines:
                layer.update(kind="lines", lines=lines, n=len(lines))
            elif tunnels:
                layer.update(kind="tunnels", tunnels=tunnels, n=sum(len(t["pairs"]) for t in tunnels))
            else:
                pts = [m for m in pts if m["pts"]]
                layer.update(kind="markers", markers=pts, n=sum(len(m["pts"]) for m in pts))
            if layer["n"]:
                layers.append(layer)
        if layers:
            groups.append({"id": gid, "name": gname, "icon": g.get("menu_icon"), "layers": layers})
    order = {"poi": 0, "spawns": 1}  # locations first in the layer list
    groups.sort(key=lambda g: order.get(g["id"], 2))
    return groups


def scrape_map():
    home = get("/")
    def script(name):
        m = re.search(r"['\"](/data/%s\.js\?v=\d+)['\"]" % name, home)
        return get(m.group(1) if m else f"/data/{name}.js")
    spawns_src = script("spawns")
    time.sleep(0.5)
    en_src = script("en")
    spawns = load_js_object(spawns_src)
    data = load_js_object(en_src, spawns)
    version = str(data.get("map") or "")
    groups = parse_map(data)
    return {
        "schema": 1,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Fortnite.GG (https://fortnite.gg/)",
        "season": data.get("season"),
        "version": version,
        "tiles": f"{BASE}/maps/{version}/{{z}}/{{x}}/{{y}}.webp",
        "tileMinZoom": 3,
        "tileMaxZoom": 8,
        "worldSize": 256,
        "iconBase": f"{BASE}/icons/",
        "defaultOn": DEFAULT_ON,
        "groups": groups,
    }


# ---------------------------------------------------------------- news
# fortnite.com/news itself is behind Cloudflare (403 for any script) and its /api/news route is feature-flagged off,
# so we use Fortnite.GG's archive of Epic's official news posts (12 per page, newest first).
NEWS_SPLIT = "<div class='news'>"


def parse_news_page(page):
    items = []
    for block in page.split(NEWS_SPLIT)[1:]:
        block = block.split("<div class='pagination'>")[0]
        title = re.search(r"<h3>(.*?)</h3>", block, re.S)
        if not title:
            continue
        img = re.search(r"<img src='([^']+)'", block)
        big = re.search(r"modal\(&quot;([^&]+(?:&amp;[^&]+)*)&quot;|modal\(\"([^\"]+)\"", block)
        date = re.search(r"<div class='date'>(.*?)</div>", block)
        desc = re.search(r"<div class='desc'>(.*?)</div>", block, re.S)
        votes = re.search(r"data-id='(\d+)' data-total='(\d+)' data-sum='(\d+)'", block)
        fire = re.search(r"bar-fire' style='width:([\d.]+)%", block)
        it = {"id": votes.group(1) if votes else "", "title": text(title.group(1)), "desc": text(desc.group(1)) if desc else ""}
        try:
            it["date"] = datetime.strptime(text(date.group(1)), "%b %d, %Y").strftime("%Y-%m-%d") if date else ""
        except ValueError:
            it["date"] = ""
        if img:
            it["image"] = html.unescape(img.group(1))
        if big:
            it["imageLarge"] = html.unescape(big.group(1) or big.group(2))
        links = []
        for href, label in re.findall(r"<a href='([^']+)' class='button[^']*'[^>]*>(.*?)</a>", block, re.S):
            href = html.unescape(href)
            ln = {"label": text(label) or "Open", "url": href if href.startswith("http") else BASE + href}
            m = re.match(r"/cosmetics\?id=([^&]+)", href)
            if m:
                ln["cosmetic"] = m.group(1)
            m = re.match(r"/island/([^?#]+)", href)
            if m:
                ln["island"] = m.group(1)
            links.append(ln)
        if links:
            it["links"] = links
        if votes and int(votes.group(2)):
            it["votes"] = {"total": int(votes.group(2)), "fire": float(fire.group(1)) if fire else None}
        items.append(it)
    return items


def scrape_news(pages, delay):
    items, seen = [], set()
    for n in range(1, pages + 1):
        if n > 1:
            time.sleep(delay)
        page = get("/news" if n == 1 else f"/news?page={n}")
        got = parse_news_page(page)
        for it in got:
            key = it["id"] or (it["title"], it["date"])
            if key not in seen:
                seen.add(key)
                items.append(it)
        if not got or f"news?page={n + 1}" not in page:
            break
    return {
        "schema": 1,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "source": "Fortnite.GG news archive (https://fortnite.gg/news) of Epic's official Fortnite news",
        "official": "https://www.fortnite.com/news",
        "items": items,
    }


# ---------------------------------------------------------------- locker (every cosmetic type, with showcase clips)
# (our id, Fortnite.GG type number, fortnite-api.com type.value, plural label, singular label, has showcase video)
LOCKER_TYPES = [
    ("outfit", 1, "outfit", "Outfits", "Outfit", True),
    ("emote", 6, "emote", "Emotes", "Emote", True),
    ("backpack", 2, "backpack", "Back Blings", "Back Bling", True),
    ("pickaxe", 3, "pickaxe", "Pickaxes", "Pickaxe", True),
    ("glider", 4, "glider", "Gliders", "Glider", True),
    ("sidekick", 32, "sidekick", "Sidekicks", "Sidekick", True),
    ("kicks", 31, "shoe", "Kicks", "Kicks", True),
    ("wrap", 7, "wrap", "Wraps", "Wrap", True),
    ("contrail", 5, "contrail", "Contrails", "Contrail", True),
    ("aura", 26, "aura", "Auras", "Aura", True),
    ("emoji", 10, "emoji", "Emoticons", "Emoticon", True),
    ("spray", 9, "spray", "Sprays", "Spray", False),
    ("loadingscreen", 12, "loadingscreen", "Loading Screens", "Loading Screen", False),
]
# Fortnite.GG tag numbers (from its cosmetics-v2.js filter map). 12 (LEGO-ready) and 18 are too common to be useful.
LOCKER_TAGS = {1: "styles", 2: "reactive", 3: "traversal", 4: "builtin", 5: "synced", 6: "animated", 14: "dance",
               17: "unreleased"}
LOCKER_SOURCES = {1: "Item Shop", 3: "Battle Pass", 4: "Fortnite Crew", 5: "Challenges", 6: "Exclusive", 7: "Pack",
                  8: "OG Pass", 9: "Music Pass", 10: "LEGO Pass", 11: "Rocket League", 12: "Tournament"}
FGG_RARITY = {1: "common", 2: "uncommon", 3: "rare", 4: "epic", 5: "legendary", 6: "dark", 7: "frozen", 8: "lava",
              9: "shadow", 10: "slurp", 11: "icon", 12: "starwars", 13: "dc", 14: "marvel", 15: "gaminglegends",
              16: "crew"}
_JS_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|([{,])([A-Za-z_$][\w$]*):|,(\s*[\]}])')


def js_literal(src):
    """Parse a JS array/object literal with bare keys and trailing commas (Fortnite.GG's items file) as JSON."""
    def fix(m):
        if m.group(3) is not None:
            return m.group(3)  # trailing comma
        return m.group(0) if m.group(1) is None else f'{m.group(1)}"{m.group(2)}":'
    return json.loads(_JS_TOKEN.sub(fix, src))


def yymmdd(n):
    s = str(n or "")
    return f"20{s[0:2]}-{s[2:4]}-{s[4:6]}" if len(s) == 6 else ""


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def api_cosmetic_ids():
    """{fortnite-api type.value: {normalized name: [(added date, Epic id), ...]}} for every BR cosmetic."""
    req = urllib.request.Request("https://fortnite-api.com/v2/cosmetics/br?language=en",
                                 headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    out = {}
    for c in json.loads(raw)["data"]:
        t = (c.get("type") or {}).get("value") or ""
        out.setdefault(t, {}).setdefault(_norm(c.get("name")), []).append(((c.get("added") or "")[:10], c["id"]))
    return out


def parse_locker(items_js, seasons_html="", ids=None):
    """-> ({our type id: [item, ...] newest first}, {season number: "C7 MS"})"""
    sets = js_literal(re.search(r"Sets=(\[.*?\]);?\s*(?:\n|Items=)", items_js, re.S).group(1))
    m = re.search(r"Items=(\[.*?\]);?\s*(?:\n|$)", items_js, re.S)
    raw = js_literal(m.group(1))
    seasons = {v: (f"C{c} {lbl}" if lbl else f"Season {v}")
               for v, c, lbl in re.findall(r"data-key='season' data-val='(\d+)' data-chapter='(\d+)'>([^<]*)", seasons_html)}
    ids = ids or {}
    by_fgg = {fgg: (tid, api) for tid, fgg, api, *_ in LOCKER_TYPES}
    out = {tid: [] for tid, *_ in LOCKER_TYPES}
    for x in raw:
        if x.get("type") not in by_fgg or x["id"] >= 9_000_000:  # 9999999 = Fortnite.GG placeholder entry
            continue
        tid, api = by_fgg[x["type"]]
        added = yymmdd(x.get("added"))
        e = {"g": x["id"], "name": x.get("name") or str(x["id"]), "rarity": FGG_RARITY.get(x.get("rarity"), "common"),
             "season": x.get("season") or 0, "added": added, "img": x.get("img") or 1}
        cands = ids.get(api, {}).get(_norm(e["name"]))
        if cands:  # same name can exist twice (re-releases, LEGO): take the closest release date
            def gap(c):
                try:
                    return abs((datetime.fromisoformat(c[0]) - datetime.fromisoformat(added)).days)
                except ValueError:
                    return 99999
            e["id"] = min(cands, key=gap)[1]
        # note: the items file's "s" flag is NOT "has sound" (checked against item pages), so it isn't kept
        tags = [LOCKER_TAGS[t] for t in x.get("t") or [] if t in LOCKER_TAGS]
        if tags:
            e["tags"] = tags
        if isinstance(x.get("set"), int) and 0 <= x["set"] < len(sets):
            e["set"] = sets[x["set"]].title()
        if x.get("source") in LOCKER_SOURCES:
            e["source"] = LOCKER_SOURCES[x["source"]]
        if x.get("p"):
            e["price"] = x["p"]
        if x.get("l"):
            e["lastSeen"] = yymmdd(x["l"])
        out[tid].append(e)
    for lst in out.values():
        lst.sort(key=lambda e: (e["added"], e["g"]), reverse=True)
    return out, seasons


def scrape_locker():
    """-> (index dict, {type id: type file dict})"""
    page = get("/cosmetics?type=outfit")
    m = re.search(r"/data/items/all\.en\.js\?v=\d+", page)
    items_js = get(m.group(0) if m else "/data/items/all.en.js")
    try:
        ids = api_cosmetic_ids()
    except Exception as e:  # matching is a bonus; the locker still works without Epic ids
        print(f"fortnite-api.com cosmetics list failed ({e})", file=sys.stderr)
        ids = {}
    by_type, seasons = parse_locker(items_js, page, ids)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    index = {
        "schema": 1,
        "updated": updated,
        "source": "Fortnite.GG (https://fortnite.gg/cosmetics)",
        "video": "https://fnggcdn.com/items/{g}/video.mp4",
        "videoSD": "https://fnggcdn.com/items/{g}/video-sd.mp4",
        "icon": "https://fortnite.gg/img/items/{g}/icon.jpg?{img}",
        "featured": "https://fortnite.gg/img/items/{g}/featured.png?{img}",
        "page": "https://fortnite.gg/cosmetics?id={g}",
        "seasons": seasons,
        "types": [{"id": tid, "name": name, "single": single, "api": api, "video": video, "count": len(by_type[tid]),
                   "matched": sum(1 for e in by_type[tid] if e.get("id")), "file": f"{tid}.json"}
                  for tid, fgg, api, name, single, video in LOCKER_TYPES],
    }
    files = {tid: {"schema": 1, "type": tid, "updated": updated, "items": by_type[tid]} for tid in by_type}
    return index, files


# ---------------------------------------------------------------- stats leaderboards
STATS_MODES = [("all", "/stats", "All modes"), ("br", "/stats/br", "Battle Royale"), ("blitz", "/stats/blitz", "Blitz"),
               ("og", "/stats/og", "OG"), ("reload", "/stats/reload", "Reload"), ("ranked", "/stats/ranked", "Ranked"),
               ("ranked-reload", "/stats/ranked-reload", "Ranked Reload"), ("arena", "/stats/arena", "Arenas Boxfights")]


def parse_board_value(cell, key):
    if key == "rank":  # <img src='/img/stats/ranks/21.png?2' ...>UNREAL (25%)
        icon = re.search(r"/ranks/(\d+)\.png", cell)
        m = re.match(r"(.*?)\s*\((\d+(?:\.\d+)?)%\)\s*$", text(cell))
        return {"rank": int(icon.group(1)) if icon else None, "text": (m.group(1) if m else text(cell)).strip(),
                "pct": float(m.group(2)) if m else None}
    if key == "time":  # "166H 54M" -> minutes
        t = text(cell).upper()
        h, mnt = re.search(r"(\d+)\s*H", t), re.search(r"(\d+)\s*M", t)
        return (int(h.group(1)) * 60 if h else 0) + (int(mnt.group(1)) if mnt else 0)
    return num(cell)


def parse_board(page, key):
    m = re.search(r"<h2>.*?>([^<>]*Leaderboard)</h2>.*?<th[^>]*>#</th><th>[^<]*</th><th>([^<]*)</th>(.*?)</tbody>", page, re.S)
    if not m:
        return None
    rows = []
    for r in re.finditer(r"<tr><td>(\d+)</td><td><a href='([^']*)'>(.*?)</a></td><td>(.*?)</td></tr>", m.group(3), re.S):
        href = html.unescape(r.group(2))
        plat = re.search(r"[?&]platform=(\w+)", href)
        row = {"rank": int(r.group(1)), "name": text(r.group(3)), "value": parse_board_value(r.group(4), key)}
        if plat and plat.group(1) != "epic":
            row["platform"] = plat.group(1)
        rows.append(row)
    return {"title": text(m.group(1)), "column": text(m.group(2)), "rows": rows}


def scrape_stats(delay):
    boards, season = [], ""
    for mode, path, name in STATS_MODES:
        page = get(path)
        sm = re.search(r"Season ([A-Z0-9]+)\s*<", page) or re.search(r"Season ([A-Z0-9]+)", page)
        season = season or (sm.group(1) if sm else "")
        keys = []
        for k in re.findall(r"leaderboard=(\w+)", page):
            if k not in keys:
                keys.append(k)
        for key in keys:
            time.sleep(delay)
            try:
                b = parse_board(get(f"{path}?leaderboard={key}"), key)
            except Exception as e:  # keep the other boards
                print(f"  {mode}/{key}: failed ({e})", file=sys.stderr)
                continue
            if b and b["rows"]:
                boards.append({"mode": mode, "key": key, **b})
                print(f"  {mode}/{key}: {len(b['rows'])} players")
        time.sleep(delay)
    return {
        "schema": 1,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "source": "Fortnite.GG (https://fortnite.gg/stats)",
        "season": season,
        "modes": [{"id": m, "path": p, "name": n} for m, p, n in STATS_MODES],
        "playerApi": BASE + "{path}?player={name}{platform}&ajax",
        "playerPage": BASE + "{path}?player={name}{platform}",
        "rankIcon": BASE + "/img/stats/ranks/{rank}.png?2",
        "boards": boards,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "data" / "weapons.json"))
    ap.add_argument("--map-out", default=str(Path(__file__).resolve().parent.parent / "docs" / "data" / "map.json"))
    ap.add_argument("--delay", type=float, default=0.6, help="seconds between detail-page requests")
    ap.add_argument("--news-out", default=str(Path(__file__).resolve().parent.parent / "docs" / "data" / "news.json"))
    ap.add_argument("--news-pages", type=int, default=5, help="news pages to read (12 stories each)")
    ap.add_argument("--locker-dir", default=str(Path(__file__).resolve().parent.parent / "docs" / "data" / "locker"))
    ap.add_argument("--stats-out", default=str(Path(__file__).resolve().parent.parent / "docs" / "data" / "stats.json"))
    ap.add_argument("--only", choices=["weapons", "map", "news", "locker", "stats"], help="scrape just one of the files")
    args = ap.parse_args()

    if args.only in (None, "stats"):
        st = scrape_stats(args.delay)
        Path(args.stats_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.stats_out).write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"stats: season {st['season']}, {len(st['boards'])} leaderboards -> {args.stats_out}"
              f" ({Path(args.stats_out).stat().st_size // 1024} KB)")
        if args.only == "stats":
            return

    if args.only in (None, "locker"):
        index, files = scrape_locker()
        out_dir = Path(args.locker_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for tid, data in files.items():
            (out_dir / f"{tid}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        total = sum(t["count"] for t in index["types"])
        size = sum(f.stat().st_size for f in out_dir.glob("*.json")) // 1024
        print(f"locker: {total} items in {len(files)} types ({sum(t['matched'] for t in index['types'])} matched to Epic ids)"
              f" -> {out_dir} ({size} KB)")
        for t in index["types"]:
            print(f"  {t['name']}: {t['count']} ({t['matched']} matched)")
        if args.only == "locker":
            return

    if args.only in (None, "news"):
        news = scrape_news(args.news_pages, args.delay)
        Path(args.news_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.news_out).write_text(json.dumps(news, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"news: {len(news['items'])} stories -> {args.news_out} ({Path(args.news_out).stat().st_size // 1024} KB)")
        if args.only == "news":
            return

    if args.only in (None, "map"):
        mp = scrape_map()
        Path(args.map_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.map_out).write_text(json.dumps(mp, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        n = sum(l["n"] for g in mp["groups"] for l in g["layers"])
        print(f"map {mp['version']}: {sum(len(g['layers']) for g in mp['groups'])} layers, {n} markers"
              f" -> {args.map_out} ({Path(args.map_out).stat().st_size // 1024} KB)")
        if args.only == "map":
            return

    page = get("/weapons")
    cats, pool = parse_loot_pool(page)
    print(f"loot pool: {len(pool)} entries in {len(cats)} classes")
    catalog = get("/weapons/compare?api=catalog", accept_json=True)
    print(f"catalog: {len(catalog.get('lines', []))} weapon lines")

    for i, it in enumerate(pool, 1):
        time.sleep(args.delay)
        try:
            it.update(parse_detail(get(f"/weapons/weapon/{it['slug']}?mode=battle-royale")))
            print(f"  [{i}/{len(pool)}] {it['name']}: {len(it.get('stats') or {})} rarities")
        except Exception as e:  # keep the card even if its detail page fails
            print(f"  [{i}/{len(pool)}] {it['name']}: detail failed ({e})", file=sys.stderr)

    lines = []
    for ln in catalog.get("lines", []):
        lines.append({
            "slug": ln["s"], "name": ln["n"], "cat": ln["c"], "icon": ln.get("i") or "",
            "modes": [catalog["modes"][m] for m in ln.get("m", []) if m < len(catalog["modes"])],
            "variants": [{"id": v[0], "rarity": v[1], "dmg": v[2], "dps": v[3], **({"icon": v[4]} if len(v) > 4 and v[4] else {})}
                         for v in ln.get("v", [])],
        })
    out = {
        "schema": 1,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Fortnite.GG (https://fortnite.gg/weapons)",
        "mode": "Battle Royale",
        "imageBase": IMG_BASE,
        "rarities": catalog.get("rarities", {}),
        "classes": {**catalog.get("classes", {}), **cats},
        "lootPool": pool,
        "catalog": lines,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out} ({Path(args.out).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
