/*!
 * Fortnite Cosmetics Browser - web demo
 * (c) 248Tech - MIT License - https://github.com/248Tech/fortnite-cosmetics-browser
 * Data: fortnite-api.com. Not affiliated with Epic Games.
 */
(() => {
  'use strict';

  const API = 'https://fortnite-api.com/v2';
  const EPIC_SHOP = 'https://www.fortnite.com/item-shop';
  // fortnite.com item pages: /item-shop/<category>/<name-slug>-<md5("Backend:id")[-8:]>
  const EPIC_CATEGORIES = {
    AthenaCharacter: 'outfits', AthenaDance: 'emotes', AthenaItemWrap: 'wraps',
    CosmeticShoes: 'kicks', AthenaSkyDiveContrail: 'contrails',
  };
  const EPIC_ASSET_TYPES = { CosmeticShoes: 'Kicks' };

  const RARITY_COLORS = {
    common: '#7d838d', uncommon: '#4f9a33', rare: '#2f7fd6', epic: '#9645d6', legendary: '#d47a24',
    mythic: '#c9a52f', exotic: '#2fb4c6', transcendent: '#c33f62', marvel: '#c22f2c', dc: '#2a58ad',
    icon: '#279c94', gaminglegends: '#5243c9', starwars: '#26307f', dark: '#94208e', frozen: '#6fb0dc',
    lava: '#bd4a28', shadow: '#45454e', slurp: '#1fa9b9',
  };
  const RARITY_ORDER = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic', 'exotic', 'transcendent'];
  const SORTS = ['Newest', 'Oldest', 'Name A-Z', 'Name Z-A', 'Rarity (high-low)', 'Rarity (low-high)'];
  const TILE_SIZES = { S: 92, M: 116, L: 150 };
  const TEXT_H = 46, GAP = 12, HEADER_H = 54, MIN_CATEGORY = 20, OVERSCAN = 400;

  const $ = (s) => document.querySelector(s);
  const el = {
    app: $('#app'), sideList: $('#sideList'), sideHeading: $('#sideHeading'),
    browseCount: $('#browseCount'), shopCountdown: $('#shopCountdown'),
    search: $('#search'), rarity: $('#rarity'), sort: $('#sort'), browseTools: $('#browseTools'),
    sizeSeg: $('#sizeSeg'), wrap: $('#gridWrap'), inner: $('#gridInner'), empty: $('#empty'),
    status: $('#status'), detail: $('#detail'), detailBody: $('#detailBody'), about: $('#about'),
    toast: $('#toast'), spriteTools: $('#spriteTools'), spriteVariant: $('#spriteVariant'), spriteSort: $('#spriteSort'),
    weaponTools: $('#weaponTools'), weaponPool: $('#weaponPool'), weaponSort: $('#weaponSort'),
    mapWrap: $('#mapWrap'), mapTip: $('#mapTip'), mapEmpty: $('#mapEmpty'),
    hero: $('#spriteHero'), heroTitle: $('#heroTitle'), heroOwned: $('#heroOwned'), heroMastered: $('#heroMastered'), heroChips: $('#heroChips'),
  };

  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  const state = {
    mode: 'browse',
    items: [], byId: new Map(), cats: [], cat: 'All', rarity: 'All', sort: 'Newest',
    search: { browse: '', shop: '', sprites: '', weapons: '', map: '', news: '' },
    news: null, newsError: null,
    map: null, mapError: null, mapLayers: new Map(), mapOn: new Set(),
    weapons: null, weaponsError: null, weaponPool: 'Current loot pool', weaponSort: 'Class', weaponRarity: {},
    sprites: null, spritesError: null, spriteFilter: 'All', spriteSeason: null, spriteVariant: 'All', spriteSort: 'Default',
    shop: null, shopByItem: new Map(), shopError: null, cosmeticsError: null,
    size: TILE_SIZES[store.get('fcb.size', 'M')] ? store.get('fcb.size', 'M') : 'M',
    grid: {
      browse: { sections: [], flat: [], selected: null, scroll: 0 },
      shop: { sections: [], flat: [], selected: null, scroll: 0 },
      sprites: { sections: [], flat: [], selected: null, scroll: 0 },
      weapons: { sections: [], flat: [], selected: null, scroll: 0 },
      map: { sections: [], flat: [], selected: null, scroll: 0 },
      news: { sections: [], flat: [], selected: null, scroll: 0 },
    },
    layout: { rows: [], rowY: [], pos: [], cols: 1, x0: 0, tile: 116, total: 0 },
    rendered: new Map(),
  };

  // ------------------------------------------------------------------ utils
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (n) => Number(n || 0).toLocaleString('en-US');

  function hexRgb(h) { h = h.replace('#', '').slice(0, 6); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)); }
  function rgbHex(c) { return '#' + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join(''); }
  function shade(color, f) {
    const c = hexRgb(color);
    return rgbHex(f >= 0 ? c.map((v) => v + (255 - v) * f) : c.map((v) => v * (1 + f)));
  }
  const rarityColor = (k) => RARITY_COLORS[k] || '#5d6270';
  const rarityBg = (k) => { const c = rarityColor(k); return [shade(c, 0.22), shade(c, -0.5)]; };
  const gradient = ([a, b]) => `radial-gradient(circle at 50% 45%, ${a} 0%, ${b} 78%)`;
  const rarityRank = (k) => { const i = RARITY_ORDER.indexOf(k); return i < 0 ? RARITY_ORDER.length : i; };

  function fmtRemaining(sec) {
    sec = Math.max(0, Math.floor(sec));
    const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
    return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
  }

  // Compact MD5 (RFC 1321), used only to build fortnite.com item URLs.
  const MD5_K = Array.from({ length: 64 }, (_, i) => Math.floor(Math.abs(Math.sin(i + 1)) * 2 ** 32) >>> 0);
  const MD5_S = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
  function md5(str) {
    const bytes = new TextEncoder().encode(str);
    const n = bytes.length;
    const words = new Uint32Array((((n + 8) >>> 6) + 1) * 16);
    for (let i = 0; i < n; i++) words[i >> 2] |= bytes[i] << ((i % 4) * 8);
    words[n >> 2] |= 0x80 << ((n % 4) * 8);
    words[words.length - 2] = (n * 8) >>> 0;
    words[words.length - 1] = Math.floor(n / 0x20000000);
    let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
    for (let off = 0; off < words.length; off += 16) {
      let A = a0, B = b0, C = c0, D = d0;
      for (let i = 0; i < 64; i++) {
        let F, g;
        if (i < 16) { F = (B & C) | (~B & D); g = i; }
        else if (i < 32) { F = (D & B) | (~D & C); g = (5 * i + 1) % 16; }
        else if (i < 48) { F = B ^ C ^ D; g = (3 * i + 5) % 16; }
        else { F = C ^ (B | ~D); g = (7 * i) % 16; }
        F = ((F >>> 0) + A + MD5_K[i] + words[off + g]) >>> 0;
        const s = MD5_S[(i >> 4) * 4 + (i % 4)];
        A = D; D = C; C = B;
        B = (B + ((F << s) | (F >>> (32 - s)))) >>> 0;
      }
      a0 = (a0 + A) >>> 0; b0 = (b0 + B) >>> 0; c0 = (c0 + C) >>> 0; d0 = (d0 + D) >>> 0;
    }
    const hex = (x) => [0, 1, 2, 3].map((i) => ((x >>> (i * 8)) & 255).toString(16).padStart(2, '0')).join('');
    return hex(a0) + hex(b0) + hex(c0) + hex(d0);
  }

  function webSlug(name) {
    return name.toLowerCase().replace(/[^a-z0-9\s]/g, '').trim().replace(/\s+/g, '-');
  }

  function epicItemUrl(it) {
    const cat = EPIC_CATEGORIES[it.backend];
    if (cat && it.name !== it.id && webSlug(it.name)) {
      const h = md5(`${it.backend}:${it.id.toLowerCase()}`).slice(-8);
      return `${EPIC_SHOP}/${cat}/${webSlug(it.name)}-${h}?lang=en-US`;
    }
    const q = new URLSearchParams({ assetType: EPIC_ASSET_TYPES[it.backend] || it.type, itemNotAvailable: 'true', title: it.name, lang: 'en-US' });
    return `${EPIC_SHOP}?${q}`;
  }

  function offerStoreUrl(e) {
    if (e.contents.length === 1 && e.contents[0].kind === 'br' && state.byId.has(e.contents[0].id)) {
      return epicItemUrl(state.byId.get(e.contents[0].id));
    }
    return `${EPIC_SHOP}?lang=en-US`;
  }

  let toastTimer;
  function toast(msg) {
    el.toast.textContent = msg;
    el.toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.toast.classList.remove('show'), 1800);
  }
  async function copy(text, what) {
    try { await navigator.clipboard.writeText(text); toast(`Copied ${what}`); }
    catch { toast('Copy failed'); }
  }

  // ------------------------------------------------------------------ data
  function normalizeCosmetics(raw) {
    return raw.map((c) => {
      const t = c.type || {}, r = c.rarity || {}, imgs = c.images || {};
      let name = (c.name || '').trim();
      if (!name || ['null', 'tbd'].includes(name.toLowerCase())) name = c.id;
      let type = (t.displayValue || '').trim();
      if (!type || type.toLowerCase() === 'null') type = 'Unknown';
      let desc = (c.description || '').trim();
      if (desc.toLowerCase() === 'null') desc = '';
      const it = {
        key: c.id, id: c.id, name, description: desc, type, backend: t.backendValue || '',
        rarity: r.displayValue || 'Unknown', rarityKey: (r.value || '').toLowerCase(),
        set: (c.set && c.set.value) || '', intro: (c.introduction && c.introduction.text) || '',
        added: c.added || '',
        small: imgs.smallIcon || imgs.icon || '',
        icon: imgs.icon || imgs.featured || imgs.smallIcon || '',
        featured: imgs.featured || imgs.icon || '',
      };
      it.search = [name, c.id, it.set, type, it.rarity].join(' ').toLowerCase();
      return it;
    });
  }

  function normalizeShop(data) {
    const entries = (data.entries || []).map((e) => {
      const br = e.brItems || [], tracks = e.tracks || [], cars = e.cars || [], inst = e.instruments || [];
      const bundle = e.bundle || {};
      const renders = (e.newDisplayAsset && e.newDisplayAsset.renderImages) || [];
      const first = br[0] || cars[0] || inst[0] || {};
      const title = bundle.name || first.name || (tracks[0] && tracks[0].title) || 'Offer';
      let image = bundle.image || (renders[0] && renders[0].image) || '';
      if (!image && br[0]) { const im = br[0].images || {}; image = im.featured || im.icon || im.smallIcon || ''; }
      if (!image && (cars[0] || inst[0])) image = ((cars[0] || inst[0]).images || {}).large || '';
      if (!image && tracks[0]) image = tracks[0].albumArt || '';
      const rkey = ((first.rarity && first.rarity.value) || '').toLowerCase();
      const colors = e.colors || {};
      let bg;
      if (colors.color1) {
        const c3 = colors.color3 || colors.color2 || colors.color1;
        bg = [shade('#' + colors.color1.slice(0, 6), -0.1), shade('#' + c3.slice(0, 6), -0.35)];
      } else if (tracks.length) bg = ['#3a3150', '#17141f'];
      else bg = rarityBg(rkey);

      const contents = [
        ...br.map((x) => ({ kind: 'br', id: x.id, name: x.name && x.name.toLowerCase() !== 'null' ? x.name : x.id, type: (x.type && x.type.displayValue) || 'Item' })),
        ...cars.map((x) => ({ kind: 'car', id: x.id, name: x.name, type: (x.type && x.type.displayValue) || 'Car' })),
        ...inst.map((x) => ({ kind: 'instrument', id: x.id, name: x.name, type: (x.type && x.type.displayValue) || 'Instrument' })),
        ...tracks.map((x) => ({ kind: 'track', id: x.id, name: x.title, type: 'Jam Track', artist: x.artist, year: x.releaseYear, duration: x.duration })),
      ];
      let kind;
      if (bundle.name) kind = `Bundle · ${contents.length} items`;
      else if (tracks.length) kind = `Jam Track${tracks[0].artist ? ' · ' + tracks[0].artist : ''}`;
      else kind = contents[0] ? contents[0].type : 'Offer';
      const layout = e.layout || {};
      const banner = e.banner || {};
      const it = {
        key: e.offerId || e.devName, offerId: e.offerId || '', name: title, kind, image, bg, rarityKey: rkey,
        final: e.finalPrice || 0, regular: e.regularPrice || 0,
        banner: banner.value || '', bannerHot: banner.intensity === 'High',
        out: e.outDate ? new Date(e.outDate) : null, giftable: !!e.giftable,
        section: (layout.name || '').trim() || 'More Offers', sindex: layout.index ?? 999,
        sort: e.sortPriority || 0, contents,
      };
      it.search = [title, kind, it.section, ...contents.map((c) => c.name || '')].join(' ').toLowerCase();
      return it;
    });
    entries.sort((a, b) => a.sindex - b.sindex || a.section.localeCompare(b.section));
    const sections = new Map();
    for (const it of entries) {
      if (!sections.has(it.section)) sections.set(it.section, []);
      sections.get(it.section).push(it);
    }
    for (const list of sections.values()) list.sort((a, b) => b.sort - a.sort || b.final - a.final);
    const date = data.date ? new Date(data.date) : new Date();
    return { date, reset: new Date(date.getTime() + 86400000), vbuck: data.vbuckIcon || '', sections, entries };
  }

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    if (json.status !== 200) throw new Error(json.error || `API status ${json.status}`);
    return json.data;
  }

  async function loadCosmetics() {
    try {
      const data = await getJSON(`${API}/cosmetics/br?language=en`);
      const items = normalizeCosmetics(data || []);
      const counts = new Map();
      for (const it of items) counts.set(it.type, (counts.get(it.type) || 0) + 1);
      const main = [...counts.entries()].filter(([t, n]) => n >= MIN_CATEGORY && t !== 'Unknown')
        .sort((a, b) => b[1] - a[1]).map(([t]) => t);
      const mainSet = new Set(main);
      for (const it of items) it.cat = mainSet.has(it.type) ? it.type : 'Other';
      state.cats = main.concat(items.some((it) => it.cat === 'Other') ? ['Other'] : []);
      state.items = items;
      state.byId = new Map(items.map((it) => [it.id, it]));
      const keyOf = new Map(items.map((it) => [it.rarity, it.rarityKey]));
      const rarities = [...keyOf.keys()].sort((a, b) => rarityRank(keyOf.get(a)) - rarityRank(keyOf.get(b)) || a.localeCompare(b));
      el.rarity.innerHTML = ['All rarities', ...rarities].map((r) => `<option>${esc(r)}</option>`).join('');
      el.browseCount.textContent = fmt(items.length);
    } catch (err) {
      state.cosmeticsError = err;
    }
    if (state.mode === 'browse') buildSidebar();
    applyFilter('browse');
    routeFromHash(true);
  }

  async function loadShop() {
    try {
      state.shop = normalizeShop(await getJSON(`${API}/shop?language=en`));
      state.shopError = null;
      state.shopByItem = new Map();
      for (const e of state.shop.entries) {
        for (const c of e.contents) {
          if (c.kind !== 'br' || !c.id) continue;
          const cur = state.shopByItem.get(c.id);
          if (!cur || e.contents.length < cur.contents.length) state.shopByItem.set(c.id, e);
        }
      }
    } catch (err) {
      state.shopError = err;
    }
    if (state.mode === 'shop') buildSidebar();
    applyFilter('shop');
    if (state.mode === 'browse') render(true);
    tick();
    routeFromHash(true);
  }

  // ------------------------------------------------------------------ filtering
  function applyFilter(mode = state.mode) {
    if (mode === 'map') { if (state.mode === 'map') buildSidebar(); updateStatus(); return; }
    const g = state.grid[mode];
    const keepKey = g.selected != null && g.flat[g.selected] ? g.flat[g.selected].key : null;
    const terms = state.search[mode].toLowerCase().split(/\s+/).filter(Boolean);
    const match = (it) => terms.every((t) => it.search.includes(t));
    if (mode === 'browse') {
      const { cat, rarity, sort } = state;
      const view = state.items.filter((it) => (cat === 'All' || it.cat === cat) && (rarity === 'All' || it.rarity === rarity) && match(it));
      const byName = (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
      const sorters = {
        'Newest': (a, b) => (a.added < b.added ? 1 : a.added > b.added ? -1 : 0),
        'Oldest': (a, b) => (a.added < b.added ? -1 : a.added > b.added ? 1 : 0),
        'Name A-Z': byName,
        'Name Z-A': (a, b) => byName(b, a),
        'Rarity (high-low)': (a, b) => rarityRank(b.rarityKey) - rarityRank(a.rarityKey) || byName(a, b),
        'Rarity (low-high)': (a, b) => rarityRank(a.rarityKey) - rarityRank(b.rarityKey) || byName(a, b),
      };
      view.sort(sorters[sort]);
      g.sections = [{ title: null, items: view }];
    } else if (mode === 'sprites') {
      g.sections = spriteSections(match);
    } else if (mode === 'weapons') {
      g.sections = weaponSections(match);
      if (state.mode === 'weapons') buildSidebar();
    } else if (mode === 'news') {
      g.sections = newsSections(match);
      if (state.mode === 'news') buildSidebar();
    } else {
      g.sections = [];
      if (state.shop) {
        for (const [title, list] of state.shop.sections) {
          const its = list.filter(match);
          if (its.length) g.sections.push({ title, subtitle: `${its.length} offer${its.length === 1 ? '' : 's'}`, items: its });
        }
      }
    }
    g.flat = g.sections.flatMap((s) => s.items);
    g.selected = null;
    if (keepKey != null) {
      const i = g.flat.findIndex((it) => it.key === keepKey);
      if (i >= 0) g.selected = i;
    }
    if (mode === state.mode) {
      el.wrap.scrollTop = 0;
      layout();
    }
    updateStatus();
  }

  function emptyMessage() {
    if (state.mode === 'browse') {
      if (state.cosmeticsError) return `Couldn't load cosmetics.\n${state.cosmeticsError.message}\nRefresh the page to try again.`;
      if (!state.items.length) return null;
      return 'No cosmetics match your filters.';
    }
    if (state.mode === 'news') {
      if (state.newsError && !state.news) return `Couldn't load the news.\n${state.newsError.message}\nRefresh the page to try again.`;
      return state.news ? 'No stories match.' : null;
    }
    if (state.mode === 'weapons') {
      if (state.weaponsError && !state.weapons) return `Couldn't load weapon stats.\n${state.weaponsError.message}\nRefresh the page to try again.`;
      return state.weapons ? 'Nothing matches.' : null;
    }
    if (state.mode === 'sprites') {
      if (state.spritesError && !state.sprites) return `Couldn't load the Sprite list.\n${state.spritesError.message}\nRefresh the page to try again.`;
      return state.sprites ? 'No sprites match.' : null;
    }
    if (state.shopError) return `Couldn't load the Item Shop.\n${state.shopError.message}\nRefresh the page to try again.`;
    if (!state.shop) return null;
    return "Nothing in today's shop matches your search.";
  }

  // ------------------------------------------------------------------ virtual grid
  function tileSize(width) {
    let t = TILE_SIZES[state.size];
    const minCols = width < 520 ? 3 : 2;
    const fit = Math.floor((width - GAP * (minCols + 1)) / minCols);
    return Math.max(72, Math.min(t, fit));
  }

  function layout() {
    if (state.mode === 'map') return;
    const g = state.grid[state.mode];
    const w = Math.max(1, el.wrap.clientWidth);
    const tile = tileSize(w);
    const tw = state.mode === 'news' ? Math.min(w - 2 * GAP, tile * 2 + GAP) : tile;
    const ih = state.mode === 'news' ? Math.round(tw * 9 / 16) : tile;
    const th = ih + cardTextH();
    const cols = Math.max(1, Math.floor((w - GAP) / (tw + GAP)));
    const gridW = cols * (tw + GAP) - GAP;
    const x0 = Math.max(GAP, Math.floor((w - gridW) / 2));
    const rows = [], pos = new Array(g.flat.length);
    let y = GAP, idx = 0;
    for (const s of g.sections) {
      if (s.title) { rows.push({ y, h: HEADER_H, kind: 'header', s }); y += HEADER_H; }
      const n = s.items.length;
      for (let r = 0; r < Math.ceil(n / cols); r++) {
        const start = idx + r * cols, cnt = Math.min(cols, n - r * cols);
        rows.push({ y, h: th, kind: 'tiles', start, cnt });
        for (let k = 0; k < cnt; k++) pos[start + k] = [x0 + k * (tw + GAP), y];
        y += th + GAP;
      }
      idx += n;
    }
    Object.assign(state.layout, { rows, rowY: rows.map((r) => r.y), pos, cols, x0, tile, tw, ih, th, total: y + GAP });
    el.inner.style.height = `${y + GAP}px`;
    const msg = g.flat.length ? '' : emptyMessage();
    el.empty.hidden = !!g.flat.length;
    el.empty.innerHTML = g.flat.length ? '' : msg == null
      ? `<div class="spinner"></div><p>${{ browse: 'Loading 16,000+ Fortnite cosmetics...', shop: 'Loading the Item Shop...', sprites: 'Loading Sprites...', weapons: 'Loading weapons...', news: 'Loading Fortnite news...' }[state.mode]}</p>`
      : `<p>${esc(msg)}</p>`;
    render(true);
  }

  function firstRowAt(y) {
    const a = state.layout.rowY;
    let lo = 0, hi = a.length - 1, ans = 0;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (a[mid] <= y) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
    return ans;
  }

  function tileHTML(it, i) {
    const L = state.layout, tile = L.tile, [x, y] = L.pos[i];
    const sel = state.grid[state.mode].selected === i ? ' sel' : '';
    if (state.mode === 'weapons') return weaponTileHTML(it, i, sel);
    if (state.mode === 'news') return newsTileHTML(it, i, sel);
    if (state.mode === 'sprites') {
      const t = spriteCardHTML(it);
      return `<div class="tile scard${sel}" data-i="${i}" style="left:${x}px;top:${y}px;width:${tile}px;height:${tile + cardTextH()}px">` +
        `<div class="tile-img" style="height:${tile}px;background:${t.bg}">${t.art}${t.pill}</div>` +
        `<div class="tile-text"><div class="tile-name" title="${esc(it.name)}">${esc(it.name)}</div><div class="cboxes">${t.body}</div></div></div>`;
    }
    let img, bg, pill = '', sub, extra = '';
    if (state.mode === 'browse') {
      img = it.small; bg = rarityBg(it.rarityKey);
      if (state.shopByItem.has(it.id)) pill = '<span class="pill">IN SHOP</span>';
      sub = esc(it.type);
      extra = `<i class="rbar" style="background:${rarityColor(it.rarityKey)}"></i>`;
    } else {
      img = it.image; bg = it.bg;
      if (it.banner) pill = `<span class="pill ${it.bannerHot ? 'hot' : 'dark'}">${esc(it.banner.toUpperCase())}</span>`;
      const vb = state.shop && state.shop.vbuck ? `<img class="vb" src="${esc(state.shop.vbuck)}" alt="">` : '';
      sub = `${vb}<span>${fmt(it.final)}</span>${it.regular > it.final ? `<span class="strike">${fmt(it.regular)}</span>` : ''}`;
    }
    return `<div class="tile${sel}" data-i="${i}" style="left:${x}px;top:${y}px;width:${tile}px;height:${tile + TEXT_H}px">` +
      `<div class="tile-img" style="height:${tile}px;background:${gradient(bg)}">${pill}` +
      (img ? `<img src="${esc(img)}" alt="${esc(it.name)}" decoding="async" onload="this.classList.add('loaded')" onerror="this.remove()">` : '') +
      `${extra}</div><div class="tile-text"><div class="tile-name" title="${esc(it.name)}">${esc(it.name)}</div><div class="tile-sub">${sub}</div></div></div>`;
  }

  function render(full = false) {
    if (state.mode === 'map') return;
    const L = state.layout, g = state.grid[state.mode];
    if (full) { el.inner.innerHTML = ''; state.rendered.clear(); }
    const top = el.wrap.scrollTop - OVERSCAN, bottom = el.wrap.scrollTop + el.wrap.clientHeight + OVERSCAN;
    const want = new Set();
    let html = '';
    for (let r = firstRowAt(Math.max(0, top)); r < L.rows.length && L.rows[r].y < bottom; r++) {
      const row = L.rows[r];
      if (row.kind === 'header') {
        const key = 'h' + r;
        want.add(key);
        if (!state.rendered.has(key)) {
          html += `<div class="section-head" data-k="${key}" style="left:${L.x0}px;top:${row.y + HEADER_H - 38}px"><h2>${esc(row.s.title)}</h2><span>${esc(row.s.subtitle || '')}</span></div>`;
        }
      } else {
        for (let i = row.start; i < row.start + row.cnt; i++) {
          want.add(i);
          if (!state.rendered.has(i)) html += tileHTML(g.flat[i], i);
        }
      }
    }
    for (const [key, node] of state.rendered) {
      if (!want.has(key)) { node.remove(); state.rendered.delete(key); }
    }
    if (html) {
      const tpl = document.createElement('template');
      tpl.innerHTML = html;
      for (const node of [...tpl.content.children]) {
        const k = node.dataset.k || Number(node.dataset.i);
        state.rendered.set(k, node);
        el.inner.appendChild(node);
      }
    }
  }

  let scrollRaf = 0;
  el.wrap.addEventListener('scroll', () => {
    if (scrollRaf) return;
    scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; render(); });
  }, { passive: true });
  let resizeTimer;
  new ResizeObserver(() => { clearTimeout(resizeTimer); resizeTimer = setTimeout(layout, 60); }).observe(el.wrap);

  function select(i, { scroll = true, open = true, fromRoute = false } = {}) {
    const g = state.grid[state.mode];
    if (!g.flat.length || i == null) return;
    i = Math.max(0, Math.min(g.flat.length - 1, i));
    const prev = state.rendered.get(g.selected);
    if (prev) prev.classList.remove('sel');
    g.selected = i;
    if (scroll) ensureVisible(i);
    const node = state.rendered.get(i);
    if (node) node.classList.add('sel');
    const it = g.flat[i];
    showItem(it);
    if (open) document.body.classList.add('detail-open');
    if (!fromRoute) setHash(state.mode === 'browse' ? `item/${it.id}` : state.mode === 'shop' ? `shop/${it.offerId}` : state.mode === 'weapons' ? `weapons/${it.slug}` : state.mode === 'news' ? `news/${it.id}` : `sprites/${it.sp.id}${it.v ? '~' + it.v : ''}`);
  }

  function ensureVisible(i) {
    const [, y] = state.layout.pos[i];
    const th = state.layout.th;
    const top = el.wrap.scrollTop, h = el.wrap.clientHeight;
    if (y - GAP < top) el.wrap.scrollTop = Math.max(0, y - GAP - (state.mode === 'shop' ? HEADER_H : 0));
    else if (y + th + GAP > top + h) el.wrap.scrollTop = y + th + GAP - h;
    render();
  }

  el.inner.addEventListener('click', (e) => {
    const t = e.target.closest('.tile');
    if (!t) return;
    const cb = e.target.closest('[data-cw]');
    if (cb && state.mode === 'sprites') {
      const i = Number(t.dataset.i);
      if (state.grid.sprites.selected !== i) select(i, { scroll: false, open: false });
      toggleEntry(state.grid.sprites.flat[i], cb.dataset.cw);
      return;
    }
    select(Number(t.dataset.i), { scroll: false });
  });
  function showItem(it) {
    if (state.mode === 'browse') showCosmetic(it);
    else if (state.mode === 'shop') showOffer(it);
    else if (state.mode === 'weapons') showWeapon(it);
    else if (state.mode === 'news') showNews(it);
    else showSprite(it);
  }
  el.inner.addEventListener('dblclick', (e) => {
    const t = e.target.closest('.tile');
    if (!t) return;
    const it = state.grid[state.mode].flat[Number(t.dataset.i)];
    if (state.mode === 'sprites') { if (!e.target.closest('[data-cw]')) toggleEntry(it, 'owned'); return; }
    if (state.mode === 'weapons') { window.open(fggWeapon(it.slug), '_blank', 'noopener'); return; }
    if (state.mode === 'news') { window.open(it.imageLarge || it.image, '_blank', 'noopener'); return; }
    window.open(state.mode === 'browse' ? it.featured || it.icon : it.image, '_blank', 'noopener');
  });

  // ------------------------------------------------------------------ detail panel
  function showAbout() {
    el.detailBody.hidden = true;
    el.about.hidden = false;
  }

  function setDetail(html) {
    el.about.hidden = true;
    el.detailBody.hidden = false;
    el.detailBody.innerHTML = html;
    el.detail.scrollTop = 0;
  }

  function factsHTML(facts) {
    return `<dl class="facts">${facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`;
  }

  function showCosmetic(it) {
    const offer = state.shopByItem.get(it.id);
    const facts = [];
    if (it.set) facts.push(['Set', it.set]);
    if (it.intro) facts.push(['Introduced', it.intro.replace('Introduced in ', '').replace(/\.$/, '')]);
    if (it.added) facts.push(['Added', it.added.slice(0, 10)]);
    facts.push(['ID', it.id]);
    setDetail(
      `<a class="d-img" href="${esc(it.featured || it.icon)}" target="_blank" rel="noopener" style="background:${gradient(rarityBg(it.rarityKey))}">` +
      `<img src="${esc(it.icon)}" alt="${esc(it.name)} - Fortnite ${esc(it.type)}"></a>` +
      `<h2>${esc(it.name)}</h2>` +
      `<div class="badges"><span class="badge" style="background:${rarityColor(it.rarityKey)}">${esc(it.rarity)}</span><span class="badge">${esc(it.type)}</span></div>` +
      (offer ? `<button class="shop-link" data-act="goto-offer" data-key="${esc(offer.key)}"><span>● In the Item Shop now</span><span>${fmt(offer.final)} V-Bucks ›</span></button>` : '') +
      (it.description ? `<p class="desc">${esc(it.description)}</p>` : '') +
      factsHTML(facts) +
      `<div class="btn-row"><button class="btn" data-act="copy" data-v="${esc(it.id)}" data-w="ID">Copy ID</button>` +
      `<button class="btn" data-act="copy" data-v="${esc(it.name)}" data-w="name">Copy name</button>` +
      `<button class="btn" data-act="link">Share link</button></div>` +
      `<a class="btn btn-accent block" href="${esc(epicItemUrl(it))}" target="_blank" rel="noopener">↗ Open on fortnite.com</a>`,
    );
  }

  function showOffer(e) {
    const vb = state.shop && state.shop.vbuck ? `<img class="vb" src="${esc(state.shop.vbuck)}" alt="V-Bucks">` : '';
    const facts = [['Section', e.section]];
    if (e.out) {
      const rem = (e.out - Date.now()) / 1000;
      facts.push(['Leaves', `in ${fmtRemaining(rem)} (${e.out.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })})`]);
    }
    facts.push(['Giftable', e.giftable ? 'Yes' : 'No']);
    const badges = [];
    if (e.banner) badges.push(`<span class="badge" style="background:${e.bannerHot ? 'var(--gold);color:#1a1405' : '#3a3f52'}">${esc(e.banner)}</span>`);
    badges.push(`<span class="badge">${esc(e.kind)}</span>`);
    const inc = e.contents.map((c) => {
      if (c.kind === 'track') {
        const d = c.duration || 0;
        const sub = [c.artist, c.year, `${Math.floor(d / 60)}:${String(d % 60).padStart(2, '0')}`].filter(Boolean).join(' · ');
        return `<div class="inc"><span>${esc(c.name || 'Jam Track')}</span><span>${esc(sub)}</span></div>`;
      }
      const known = c.kind === 'br' && state.byId.has(c.id);
      return known
        ? `<button class="inc" data-act="goto-item" data-id="${esc(c.id)}"><span>${esc(c.name)}</span><span>${esc(c.type)} ›</span></button>`
        : `<div class="inc"><span>${esc(c.name || c.id)}</span><span>${esc(c.type)}</span></div>`;
    }).join('');
    setDetail(
      `<a class="d-img" href="${esc(e.image)}" target="_blank" rel="noopener" style="background:${gradient(e.bg)}">` +
      (e.image ? `<img src="${esc(e.image)}" alt="${esc(e.name)}">` : '') + '</a>' +
      `<h2>${esc(e.name)}</h2><div class="badges">${badges.join('')}</div>` +
      `<div class="price">${vb}<span>${fmt(e.final)}${vb ? '' : ' V-Bucks'}</span>` +
      (e.regular > e.final ? `<span class="was">${fmt(e.regular)}</span><span class="save">Save ${fmt(e.regular - e.final)}</span>` : '') + '</div>' +
      factsHTML(facts) +
      (e.contents.length ? `<div class="includes-h">Includes (${e.contents.length})</div>${inc}` : '') +
      `<div class="btn-row"><button class="btn" data-act="copy" data-v="${esc(e.name)}" data-w="name">Copy name</button>` +
      `<button class="btn" data-act="copy" data-v="${esc(e.offerId)}" data-w="offer ID">Copy offer ID</button>` +
      `<button class="btn" data-act="link">Share link</button></div>` +
      `<a class="btn btn-accent block" href="${esc(offerStoreUrl(e))}" target="_blank" rel="noopener">↗ Open on fortnite.com</a>`,
    );
  }

  el.detailBody.addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    if (act === 'copy') copy(b.dataset.v, b.dataset.w);
    else if (act === 'link') copy(location.href, 'link');
    else if (act === 'goto-offer') gotoOffer(b.dataset.key);
    else if (act === 'goto-item') gotoCosmetic(b.dataset.id);
    else if (act === 'sp' || act === 'sp-all') {
      const en = selectedEntry();
      if (!en) return;
      if (act === 'sp') toggleEntry(en, b.dataset.w); else markAll(en.sp, !!b.dataset.v);
    } else if (act === 'w-rar' || act === 'w-copy') {
      const g = state.grid.weapons, w = g.selected != null && g.flat[g.selected];
      if (!w) return;
      if (act === 'w-rar') setWeaponRarity(w, b.dataset.r); else copy(weaponStatsText(w), 'stats');
    } else if (act === 'map-only' || act === 'map-hide') {
      const id = b.dataset.layer;
      if (act === 'map-only') setMapLayers(state.mapLayers.get(id).kind === 'labels' ? [id] : [id, 'poi']);
      else { const on = new Set(state.mapOn); on.delete(id); setMapLayers(on); }
    } else if (act === 'map-zoom') {
      if (fmap && fmap.selected) fmap.flyTo(fmap.selected.pt, Math.max(fmap.view.z + 1, 5.5));
    } else if (act === 'map-fit') {
      if (fmap) fmap.fit();
    } else if (act === 'goto-entry') {
      gotoEntry(b.dataset.key);
    } else if (act === 'photo-paste') {
      navigator.clipboard?.read?.().then(async (items) => {
        for (const it of items) {
          const type = it.types.find((t) => t.startsWith('image/'));
          if (type) { setPhotoFromBlob(await it.getType(type)); return; }
        }
        toast('Clipboard has no image');
      }).catch(() => toast('Press Ctrl+V to paste'));
    } else if (act === 'photo-file') {
      const inp = document.createElement('input');
      inp.type = 'file'; inp.accept = 'image/*';
      inp.onchange = () => setPhotoFromBlob(inp.files[0]);
      inp.click();
    } else if (act === 'photo-remove') {
      const en = selectedEntry();
      if (en) { userPhotos.set(en.sp, en.v, ''); toast('Photo removed'); refreshSpriteViews(); }
    }
  });
  $('#detailClose').addEventListener('click', () => document.body.classList.remove('detail-open'));

  // ------------------------------------------------------------------ sprites
  // Epic has no public Sprite API: the catalog is our own data/sprites.json (edit it to add sprites,
  // variants or seasons). Every base sprite and every variant is its own card with Owned / Mastered,
  // like Fortnite.GG. Progress is keyed by variant id, so new variants need no code change.
  const SPRITE_RARITIES = ['rare', 'epic', 'legendary', 'mythic'];
  const SPRITE_FILTERS = ['All', 'Missing', 'Owned', 'Mastered', 'Not mastered'];
  const SPRITE_SORTS = ['Default', 'Name A-Z', 'Rarity (high-low)', 'Missing first', 'Owned first'];
  const SPRITE_THEMES = { common: '#3a3f45', rare: '#104273', epic: '#4d1566', legendary: '#743e0a', mythic: '#a89442' };
  const SPRITE_CHIPS = { common: ['#40464d', '#b7bfc5'], rare: ['#00458a', '#00fffb'], epic: ['#4c197b', '#ec27ff'], legendary: ['#8a3c1e', '#fbc363'], mythic: ['#7c5d26', '#fff0a6'] };
  const FGG_SPRITES = 'https://fortnite.gg/sprites';
  const fggIcon = (sp, v) => sp.fgg ? `https://fortnite.gg/img/x/sprites/icons/T_Icon_BR_Creature_Sprite_${sp.fgg}${v ? state.sprites.variants.get(v).fgg : ''}_L.webp` : '';
  const PROGRESS_KEY = 'fcb.sprites.v1';
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const isOut = (day) => !day || day <= today();
  const fmtDay = (day) => { const d = new Date(`${day}T12:00:00`); return isNaN(d) ? day : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); };
  const cardTextH = () => (state.mode === 'sprites' ? 84 : state.mode === 'weapons' ? 62 : state.mode === 'news' ? 92 : TEXT_H);

  function normalizeSprites(data) {
    if (!data || data.schema !== 1) throw new Error('unsupported sprite data');
    const variants = new Map();
    for (const v of data.variants || []) {
      if (v.id) variants.set(v.id, { id: v.id, name: v.name || v.id, color: v.color || '#fce51e', description: v.description || '', release: v.releaseDate || '', fgg: v.fgg || '', theme: v.theme || v.color || '#fce51e' });
    }
    const seasons = (data.seasons || []).map((se) => ({
      id: se.id, name: se.name || se.id, label: se.label || se.name || se.id, how: se.howToGet || '',
      sprites: (se.sprites || []).filter((sp) => sp.id).map((sp) => {
        const rk = (sp.rarity || 'rare').toLowerCase();
        const vids = (sp.variants || []).filter((v) => variants.has(v));
        const it = {
          key: `${se.id}:${sp.id}`, id: sp.id, season: se.id, name: sp.name || sp.id, rarityKey: rk,
          rarity: rk[0].toUpperCase() + rk.slice(1), color: sp.color || rarityColor(rk), ability: sp.ability || '',
          where: sp.where || '', release: sp.releaseDate || '', variants: vids,
          upcoming: (sp.upcoming || []).filter((v) => variants.has(v) && !vids.includes(v)),
          image: sp.image || '', images: sp.images || {}, wiki: sp.wiki || '', fgg: sp.fgg || '',
        };
        it.search = [it.name, it.id, it.rarity, it.ability, ...vids.map((v) => variants.get(v).name)].join(' ').toLowerCase();
        return it;
      }),
    }));
    if (!seasons.length) throw new Error('no seasons in sprite data');
    const ids = seasons.map((s) => s.id);
    return { seasons, variants, dust: data.dustCost || {}, updated: data.updated || '', current: ids.includes(data.current) ? data.current : ids[ids.length - 1] };
  }

  // One card per base sprite and per variant.
  function seasonEntries(se = seasonObj()) {
    if (!se) return [];
    const V = state.sprites.variants, out = [];
    se.sprites.forEach((sp, order) => {
      [null, ...sp.variants, ...sp.upcoming].forEach((v, vi) => {
        const vd = v ? V.get(v) : null, upcoming = sp.upcoming.includes(v);
        const e = {
          key: `${sp.key}|${v || ''}`, sp, v, name: vd ? `${vd.name} ${sp.name}` : sp.name, rarityKey: sp.rarityKey,
          theme: vd ? vd.theme : (SPRITE_THEMES[sp.rarityKey] || '#3a3f45'),
          out: !upcoming && isOut(sp.release) && (!vd || isOut(vd.release)), upcoming,
          release: !isOut(sp.release) ? sp.release : vd ? vd.release : '', order: order * 10 + vi,
        };
        e.search = `${sp.search} ${e.name.toLowerCase()}`;
        out.push(e);
      });
    });
    return out;
  }

  const progress = {
    data: {},
    load() {
      try { this.data = this.clean(JSON.parse(store.get(PROGRESS_KEY, '{}'))); } catch { this.data = {}; }
    },
    clean(obj) {
      const prog = obj && typeof obj === 'object' && 'progress' in obj ? obj.progress : obj;
      const out = {};
      for (const [season, sprites] of Object.entries(prog || {})) {
        if (!sprites || typeof sprites !== 'object') continue;
        for (const [id, rec] of Object.entries(sprites)) {
          if (!rec || typeof rec !== 'object') continue;
          const r = { captured: !!(rec.captured || rec.mastered), mastered: !!rec.mastered, variants: {}, vmastered: {} };
          for (const [v, on] of Object.entries(rec.vmastered || {})) if (on) { r.vmastered[v] = true; r.variants[v] = true; }
          for (const [v, on] of Object.entries(rec.variants || {})) if (on) r.variants[v] = true;
          if (r.captured || Object.keys(r.variants).length) (out[season] ||= {})[id] = r;
        }
      }
      return out;
    },
    get(sp) { return (this.data[sp.season] || {})[sp.id] || { captured: false, mastered: false, variants: {}, vmastered: {} }; },
    owned(sp, v) { const r = this.get(sp); return v ? !!r.variants[v] : r.captured; },
    mastered(sp, v) { const r = this.get(sp); return v ? !!(r.vmastered || {})[v] : r.mastered; },
    set(sp, v, what, value) {
      const cur = this.get(sp);
      const r = { captured: cur.captured, mastered: cur.mastered, variants: { ...cur.variants }, vmastered: { ...(cur.vmastered || {}) } };
      let own = this.owned(sp, v), mas = this.mastered(sp, v);
      if (what === 'owned') { own = value ?? !own; mas = mas && own; } // un-owning clears mastered
      else { mas = value ?? !mas; own = own || mas; } // can't master what you never caught
      if (v) {
        if (own) r.variants[v] = true; else delete r.variants[v];
        if (mas) r.vmastered[v] = true; else delete r.vmastered[v];
      } else { r.captured = own; r.mastered = mas; }
      const season = (this.data[sp.season] ||= {});
      if (r.captured || Object.keys(r.variants).length) season[sp.id] = r; else delete season[sp.id];
      this.save();
    },
    exportObj() { return { app: 'fortnite-cosmetics-browser', kind: 'sprite-progress', schema: 1, exported: new Date().toISOString(), progress: this.data }; },
    save() { store.set(PROGRESS_KEY, JSON.stringify(this.exportObj())); },
    merge(obj) {
      const inc = this.clean(obj);
      let n = 0;
      for (const [season, sprites] of Object.entries(inc)) {
        for (const [id, rec] of Object.entries(sprites)) {
          const cur = (this.data[season] || {})[id] || { captured: false, mastered: false, variants: {}, vmastered: {} };
          (this.data[season] ||= {})[id] = {
            captured: cur.captured || rec.captured, mastered: cur.mastered || rec.mastered,
            variants: { ...cur.variants, ...rec.variants }, vmastered: { ...(cur.vmastered || {}), ...rec.vmastered },
          };
          n++;
        }
      }
      this.save();
      return n;
    },
  };
  progress.load();

  async function loadSprites() {
    try {
      const res = await fetch('data/sprites.json', { cache: 'no-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.sprites = normalizeSprites(await res.json());
      state.spriteSeason = state.spriteSeason || state.sprites.current;
      state.spritesError = null;
      el.spriteVariant.innerHTML = ['All', 'Base', ...[...state.sprites.variants.values()].map((v) => v.name)]
        .map((n) => `<option value="${esc(n)}">${esc(n === 'All' ? 'All variants' : n)}</option>`).join('');
    } catch (err) {
      state.spritesError = err;
    }
    spriteCountsChanged();
    applyFilter('sprites');
    routeFromHash(true);
    if (state.sprites) { loadSpriteImages(); loadSpriteNews(); }
  }

  // Fortnite Wiki fallback for sprites without a Fortnite.GG name (CORS-enabled API), cached 6 h.
  const WIKI_API = 'https://fortnite.fandom.com/api.php';
  const IMG_KEY = 'fcb.spriteimg.v1';
  function wikiCandidates(sp, v) {
    const names = sp.wiki ? [sp.wiki] : [sp.name, `${sp.name} Sprite`];
    const pre = v ? `${state.sprites.variants.get(v).name} ` : '';
    return [...new Set(names)].map((n) => `File:${pre}${n} - Item - Fortnite.png`);
  }
  async function loadSpriteImages() {
    const need = state.sprites.seasons.flatMap((se) => se.sprites.filter((sp) => !sp.fgg && !sp.image));
    if (!need.length) return;
    const keys = need.map((sp) => `${sp.key}|`);
    try {
      const c = JSON.parse(store.get(IMG_KEY, 'null'));
      if (c && c.map) {
        state.spriteImgs = c.map;
        if (Date.now() - c.time < 6 * 3600e3 && keys.every((k) => k in c.map)) { refreshSpriteViews(); return; }
      }
    } catch { /* ignore */ }
    try {
      const want = {};
      for (const sp of need) for (const v of [null, ...sp.variants, ...sp.upcoming]) want[`${sp.key}|${v || ''}`] = wikiCandidates(sp, v);
      const titles = [...new Set(Object.values(want).flat())];
      const found = {};
      const norm = (t) => t.replace(/_/g, ' ');
      for (let i = 0; i < titles.length; i += 50) {
        const q = new URLSearchParams({ action: 'query', titles: titles.slice(i, i + 50).join('|'), prop: 'imageinfo', iiprop: 'url', iiurlwidth: '512', format: 'json', formatversion: '2', origin: '*' });
        const res = await fetch(`${WIKI_API}?${q}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        for (const pg of (await res.json()).query?.pages || []) {
          const info = (pg.imageinfo || [])[0];
          if (info) found[norm(pg.title)] = info.thumburl || info.url;
        }
      }
      const map = {};
      for (const [k, cands] of Object.entries(want)) {
        const hit = cands.map(norm).find((t) => found[t]);
        map[k] = hit ? found[hit] : '';
      }
      state.spriteImgs = map;
      store.set(IMG_KEY, JSON.stringify({ time: Date.now(), map }));
    } catch { /* offline or wiki down: keep cache / drawn art */ }
    refreshSpriteViews();
  }
  function refreshSpriteViews() {
    if (state.mode !== 'sprites') return;
    render(true);
    const g = state.grid.sprites;
    if (g.selected != null && g.flat[g.selected]) { const y = el.detail.scrollTop; showSprite(g.flat[g.selected]); el.detail.scrollTop = y; }
  }
  // Art for a card: your photo > URL in sprites.json > Fortnite.GG > Fortnite Wiki > drawn stand-in.
  const spriteImgURL = (sp, v) => userPhotos.get(sp, v) || (v ? sp.images[v] : sp.image) || fggIcon(sp, v) || (state.spriteImgs || {})[`${sp.key}|${v || ''}`] || '';
  // drawn stand-in first, real art on top once it loads (stand-in hidden), removed on error
  const spriteArt = (sp, v) => {
    const url = spriteImgURL(sp, v);
    return spriteSVG(sp, v) + (url ? `<img class="sprite-img" src="${esc(url)}" alt="${esc((v ? state.sprites.variants.get(v).name + ' ' : '') + sp.name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer" onload="this.classList.add('loaded');this.parentNode.classList.add('has-img')" onerror="this.remove()">` : '');
  };
  const cardBg = (e) => `linear-gradient(180deg, ${e.theme} 0%, var(--panel) 100%)`;

  // User photos (e.g. screenshots of the in-game collection), resized to 256 px and kept in localStorage.
  const PHOTO_KEY = 'fcb.spritephoto.v1';
  const userPhotos = {
    map: (() => { try { return JSON.parse(store.get(PHOTO_KEY, '{}')) || {}; } catch { return {}; } })(),
    key: (sp, v) => `${sp.key}|${v || ''}`,
    get(sp, v) { return this.map[this.key(sp, v)] || ''; },
    set(sp, v, url) {
      if (url) this.map[this.key(sp, v)] = url; else delete this.map[this.key(sp, v)];
      try { localStorage.setItem(PHOTO_KEY, JSON.stringify(this.map)); return true; }
      catch { if (url) delete this.map[this.key(sp, v)]; return false; }
    },
  };
  async function blobToPhoto(blob) {
    const bmp = await createImageBitmap(blob);
    const k = Math.min(1, 256 / Math.max(bmp.width, bmp.height));
    const c = document.createElement('canvas');
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    const webp = c.toDataURL('image/webp', 0.85);
    return webp.startsWith('data:image/webp') ? webp : c.toDataURL('image/png');
  }
  const selectedEntry = () => { const g = state.grid.sprites; return g.selected != null ? g.flat[g.selected] : null; };
  async function setPhotoFromBlob(blob) {
    const e = selectedEntry();
    if (!e || !blob) return;
    try {
      if (!userPhotos.set(e.sp, e.v, await blobToPhoto(blob))) { toast('Browser storage is full'); return; }
      toast('Photo set');
    } catch { toast('Not an image'); return; }
    refreshSpriteViews();
  }
  document.addEventListener('paste', (ev) => {
    if (state.mode !== 'sprites' || ev.target === el.search) return;
    const item = [...(ev.clipboardData?.items || [])].find((i) => i.type.startsWith('image/'));
    if (item) { ev.preventDefault(); setPhotoFromBlob(item.getAsFile()); }
    else toast('Clipboard has no image. Screenshot with Win+Shift+S, then Ctrl+V');
  });

  // Official Sprite art from Epic: BR news cards that mention Sprites (fortnite-api.com mirrors Epic's feed).
  async function loadSpriteNews() {
    try {
      const d = await getJSON(`${API}/news/br?language=en`);
      state.spriteNews = (d.motds || []).filter((m) => `${m.title} ${m.body}`.toLowerCase().includes('sprite'))
        .map((m) => ({ title: m.title || '', body: m.body || '', image: m.tileImage || m.image || '' })).filter((n) => n.image);
      refreshSpriteViews();
    } catch { /* optional */ }
  }

  const seasonObj = () => state.sprites && (state.sprites.seasons.find((s) => s.id === state.spriteSeason) || state.sprites.seasons[state.sprites.seasons.length - 1]);

  function spriteStats(se = seasonObj()) {
    const live = seasonEntries(se).filter((e) => e.out);
    return { total: live.length, owned: live.filter((e) => progress.owned(e.sp, e.v)).length, mastered: live.filter((e) => progress.mastered(e.sp, e.v)).length };
  }
  function entryMatches(e, f) {
    const own = progress.owned(e.sp, e.v), mas = progress.mastered(e.sp, e.v);
    return { Missing: !own, Owned: own, Mastered: mas, 'Not mastered': own && !mas }[f] ?? true;
  }
  function variantOk(e) {
    const vf = state.spriteVariant;
    if (vf === 'All') return true;
    if (vf === 'Base') return !e.v;
    return !!e.v && state.sprites.variants.get(e.v).name === vf;
  }
  const sectionSub = (its) => { const live = its.filter((e) => e.out); return `${live.filter((e) => progress.owned(e.sp, e.v)).length} / ${live.length} owned`; };

  function spriteSections(match) {
    if (!seasonObj()) return [];
    const es = seasonEntries().filter((e) => variantOk(e) && entryMatches(e, state.spriteFilter) && match(e));
    const rank = (e) => { const i = SPRITE_RARITIES.indexOf(e.rarityKey); return i < 0 ? 9 : i; };
    const sorters = {
      'Name A-Z': (a, b) => a.name.localeCompare(b.name),
      'Rarity (high-low)': (a, b) => rank(b) - rank(a) || a.order - b.order,
      'Missing first': (a, b) => progress.owned(a.sp, a.v) - progress.owned(b.sp, b.v) || a.order - b.order,
      'Owned first': (a, b) => progress.owned(b.sp, b.v) - progress.owned(a.sp, a.v) || a.order - b.order,
    };
    if (sorters[state.spriteSort]) return es.length ? [{ title: null, items: es.sort(sorters[state.spriteSort]) }] : [];
    const extra = [...new Set(es.map((e) => e.rarityKey))].filter((r) => !SPRITE_RARITIES.includes(r)).sort();
    const out = [];
    for (const rk of SPRITE_RARITIES.concat(extra)) {
      const its = es.filter((e) => e.rarityKey === rk);
      if (its.length) out.push({ title: its[0].sp.rarity, subtitle: sectionSub(its), items: its });
    }
    return out;
  }

  function spriteCountsChanged() {
    if (state.sprites) {
      const st = spriteStats(), se = seasonObj();
      $('#spriteCount').textContent = `${st.owned}/${st.total}`;
      el.heroTitle.textContent = `${se.name} Sprites`;
      el.heroOwned.textContent = `${st.owned} / ${st.total}`;
      el.heroMastered.textContent = `${st.mastered} / ${st.total}`;
      el.heroChips.innerHTML = state.sprites.seasons.map((s) => `<button class="chip${s.id === se.id ? ' on' : ''}" data-season="${esc(s.id)}">${esc(s.name)}</button>`).join('');
    }
    if (state.mode === 'sprites') buildSidebar();
    updateStatus();
  }

  // Stand-in art drawn as SVG, shown until an image loads (and for unreleased variants).
  let svgSeq = 0;
  function spriteSVG(sp, variant) {
    const vd = variant ? state.sprites.variants.get(variant) : null;
    let body = sp.color;
    if (variant === 'gold') body = '#f2c14e';
    else if (vd) { const a = hexRgb(sp.color), b = hexRgb(vd.color); body = rgbHex(a.map((x, i) => x * 0.45 + b[i] * 0.55)); }
    const glow = vd ? vd.color : shade(body, 0.3);
    const uid = `sg${++svgSeq}`;
    let front = '', back = '';
    if (variant === 'cursed') back = `<path d="M41.3 40.5 35.6 30.6 40.7 45ZM58.7 40.5 64.4 30.6 59.3 45Z" fill="${shade(vd.color, -0.35)}"/>`;
    if (variant === 'fortune') front = '<path d="M50 39.3 54 44.3 50 49.3 46 44.3Z" fill="#ff405c" stroke="#ffd6de" stroke-width="1"/>';
    if (variant === 'gold') {
      front = [[22, 30, 6], [80, 24, 4.5], [78, 78, 5]].map(([x, y, k]) =>
        `<path d="M${x} ${y - k}L${x + k * 0.28} ${y - k * 0.28}L${x + k} ${y}L${x + k * 0.28} ${y + k * 0.28}L${x} ${y + k}L${x - k * 0.28} ${y + k * 0.28}L${x - k} ${y}L${x - k * 0.28} ${y - k * 0.28}Z" fill="#fff4c8"/>`).join('');
    }
    const eye = (ex) => `<ellipse cx="${ex}" cy="61" rx="5" ry="6.5" fill="#fff"/><ellipse cx="${ex}" cy="64" rx="2.5" ry="3.5" fill="#181624"/><circle cx="${ex - 1}" cy="62" r=".9" fill="#fff"/>`;
    return `<svg class="sprite-art" viewBox="0 0 100 100" aria-hidden="true"><defs><filter id="${uid}" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7"/></filter></defs>` +
      `<ellipse cx="50" cy="54" rx="34" ry="34" fill="${glow}" opacity=".6" filter="url(#${uid})"/>${back}` +
      `<path d="M34.5 44.3 53 14.3 66.5 45.5Z" fill="${body}"/><circle cx="50" cy="58" r="25" fill="${body}"/>` +
      `<ellipse cx="40.6" cy="46.3" rx="8.1" ry="7.3" fill="#fff" opacity=".3"/>${eye(41)}${eye(59)}${front}</svg>`;
  }

  // Card body: name + Owned / Mastered checkboxes (or a lock for unreleased cards).
  function spriteCardHTML(e) {
    const own = progress.owned(e.sp, e.v), mas = progress.mastered(e.sp, e.v);
    const box = (w, on, label) => `<button class="cbox${on ? ' on' : ''} ${w}" data-cw="${w}" tabindex="-1"><i></i>${label}</button>`;
    return {
      art: spriteArt(e.sp, e.v), bg: cardBg(e), pill: mas ? '<span class="crown" title="Mastered">♛</span>' : '',
      body: e.out ? box('owned', own, 'Owned') + box('mastered', mas, 'Mastered')
        : `<div class="locked" title="Not released yet">🔒 ${e.release ? esc(fmtDay(e.release)) : 'Soon'}</div>`,
    };
  }

  function showSprite(e) {
    const sp = e.sp, v = e.v, V = state.sprites.variants, se = seasonObj();
    const own = progress.owned(sp, v), mas = progress.mastered(sp, v);
    const check = (w, on, label, sub, color) =>
      `<button class="check${on ? ' on' : ''}${e.out ? '' : ' soon'}" data-act="sp" data-w="${w}" style="--c:${color}">` +
      `<span class="box">${on ? '✓' : ''}</span><span class="lbl">${esc(label)}</span><span class="sub">${esc(sub)}</span></button>`;
    const versions = seasonEntries().filter((x) => x.sp === sp).map((x) => {
      const o = progress.owned(sp, x.v), m = progress.mastered(sp, x.v);
      const cls = !x.out ? 'lock' : m ? 'mas' : o ? 'own' : '';
      const mark = !x.out ? '🔒 ' : m ? '♛ ' : o ? '✓ ' : '';
      return `<button class="vprev ${cls}${x.key === e.key ? ' cur' : ''}" data-act="goto-entry" data-key="${esc(x.key)}"><div class="vimg" style="background:${cardBg(x)}">${spriteArt(sp, x.v)}</div><span>${mark}${esc(x.v ? V.get(x.v).name : 'Base')}</span></button>`;
    }).join('');
    const facts = [];
    const cost = state.sprites.dust[sp.rarityKey];
    if (cost) facts.push(['Resummon', `${fmt(v ? cost.variant : cost.base)} Dust (half when mastered)`]);
    facts.push(['Where', sp.where || se.how], ['Season', se.label]);
    const url = spriteImgURL(sp, v);
    facts.push(['Image', url.startsWith('data:') ? 'Your photo' : url.includes('fortnite.gg') ? 'Fortnite.GG' : url.includes('wikia') ? 'Fortnite Wiki' : url ? 'Sprite list' : 'Stand-in']);
    const [cbg, cfg] = SPRITE_CHIPS[sp.rarityKey] || ['#18191c', '#fff'];
    const badges = [`<span class="badge" style="background:${cbg};color:${cfg}">${esc(sp.rarity)}</span>`];
    if (v) badges.push(`<span class="badge" style="background:${V.get(v).theme}">${esc(V.get(v).name)}</span>`);
    badges.push('<span class="badge">Sprite</span>');
    if (!e.out) badges.push(`<span class="badge" style="background:var(--red)">${e.release ? `Coming ${esc(fmtDay(e.release))}` : 'Unreleased'}</span>`);
    const newsHTML = (state.spriteNews || []).length ? '<div class="includes-h">From Epic news</div>' + state.spriteNews.map((n) =>
      `<a class="news" href="${esc(n.image.split('?')[0])}" target="_blank" rel="noopener"><img src="${esc(n.image)}" alt="${esc(n.title)}" loading="lazy"><b>${esc(n.title)}</b><span>${esc(n.body)}</span></a>`).join('') : '';
    setDetail(
      `<div class="d-img sprite-big" style="background:${cardBg(e)}">${spriteArt(sp, v)}</div>` +
      `<h2 class="display">${esc(e.name)}</h2><div class="badges">${badges.join('')}</div>` +
      (sp.ability ? `<p class="desc">${esc(sp.ability)}</p>` : '') +
      (v && V.get(v).description ? `<p class="hint">${esc(V.get(v).description)}</p>` : '') +
      '<div class="includes-h">My progress</div>' +
      check('owned', own, 'Owned', 'Space', 'var(--green)') + check('mastered', mas, 'Mastered', 'M', 'var(--accent)') +
      `<div class="includes-h">Versions</div><div class="vstrip">${versions}</div>` +
      factsHTML(facts) +
      `<div class="btn-row"><button class="btn" data-act="copy" data-v="${esc(e.name)}" data-w="name">Copy name</button><button class="btn" data-act="sp-all" data-v="1">All versions</button><button class="btn" data-act="sp-all" data-v="">Clear all</button></div>` +
      `<a class="btn btn-accent block" href="${FGG_SPRITES}" target="_blank" rel="noopener">↗ View on Fortnite.GG</a>` +
      '<div class="includes-h">Your photo</div><div class="photo-row"><button class="btn" data-act="photo-paste">Paste</button><button class="btn" data-act="photo-file">File…</button><button class="btn" data-act="photo-remove">Remove</button></div>' +
      '<p class="hint">Optional: use your own screenshot (Win+Shift+S, then Ctrl+V) instead of the Fortnite.GG image. Saved in this browser.</p>' +
      newsHTML,
    );
  }

  function toggleEntry(e, w, value) {
    if (!e || !e.out) return;
    progress.set(e.sp, e.v, w, value);
    afterProgress(e);
  }

  function afterProgress(e) {
    const g = state.grid.sprites;
    if (state.spriteFilter !== 'All' || ['Missing first', 'Owned first'].includes(state.spriteSort)) {
      const top = el.wrap.scrollTop;
      applyFilter('sprites');
      if (state.mode === 'sprites') { el.wrap.scrollTop = top; render(); }
      if (g.selected == null) {
        if (state.mode === 'sprites') showAbout();
        spriteCountsChanged();
        return;
      }
    } else {
      for (const s of g.sections) if (s.title) s.subtitle = sectionSub(s.items);
      if (state.mode === 'sprites') { const top = el.wrap.scrollTop; render(true); el.wrap.scrollTop = top; }
    }
    spriteCountsChanged();
    if (e && state.mode === 'sprites' && g.selected != null && g.flat[g.selected].key === e.key) {
      const y = el.detail.scrollTop;
      showSprite(g.flat[g.selected]);
      el.detail.scrollTop = y;
    }
  }

  function markAll(sp, on) {
    for (const e of seasonEntries()) if (e.sp === sp && (e.out || !on)) progress.set(sp, e.v, on ? 'mastered' : 'owned', on);
    afterProgress(selectedEntry());
  }

  function gotoEntry(key) {
    let i = state.grid.sprites.flat.findIndex((x) => x.key === key);
    if (i < 0) {
      state.spriteFilter = 'All'; state.spriteVariant = 'All'; el.spriteVariant.value = 'All';
      state.search.sprites = ''; el.search.value = '';
      buildSidebar(); applyFilter('sprites');
      i = state.grid.sprites.flat.findIndex((x) => x.key === key);
    }
    if (i >= 0) select(i, { open: false });
  }

  function exportProgress() {
    const blob = new Blob([JSON.stringify(progress.exportObj(), null, 1)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'fortnite_sprite_progress.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast('Progress exported');
  }

  function importProgress() {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = '.json,application/json';
    inp.onchange = async () => {
      try {
        const n = progress.merge(JSON.parse((await inp.files[0].text()).replace(/^﻿/, '')));
        applyFilter('sprites');
        spriteCountsChanged();
        toast(`Imported ${n} sprites (merged)`);
      } catch { toast('Not a sprite progress file'); }
    };
    inp.click();
  }

  // ------------------------------------------------------------------ weapons & items
  // data/weapons.json is scraped from Fortnite.GG by tools/scrape_fortnitegg.py (refreshed daily by GitHub Actions).
  const WEAPON_POOLS = ['Current loot pool', 'All weapons'];
  const WEAPON_SORTS = ['Class', 'Name', 'Damage', 'DPS', 'Fire rate', 'Magazine', 'Reload', 'Chest chance'];
  const WEAPON_SORT_KEYS = { Damage: ['dmg', -1], DPS: ['dps', -1], 'Fire rate': ['rate', -1], Magazine: ['mag', -1], Reload: ['reload', 1] };
  // [key, label, unit, lowerIsBetter]
  const WEAPON_STATS = [['dmg', 'Damage', '', false], ['head', 'Headshot damage', '', false], ['dps', 'DPS', '', false],
    ['rate', 'Fire rate', '/s', false], ['mag', 'Magazine', '', false], ['reload', 'Reload', 's', true],
    ['struct', 'Structure damage', '', false], ['spread', 'Spread', '', true], ['vrecoil', 'Vertical recoil', '', true],
    ['hrecoil', 'Horizontal recoil', '', true], ['ads', 'Aim down sights', 's', true]];
  const fggWeapon = (slug) => `https://fortnite.gg/weapons/weapon/${encodeURIComponent(slug)}?mode=battle-royale`;
  const fmtStat = (v, u = '') => (v == null ? '-' : `${Math.round(v * 100) / 100}${u}`);

  function normalizeWeapons(data) {
    if (!data || data.schema !== 1) throw new Error('unsupported weapon data');
    const img = data.imageBase || 'https://fortnite.gg/img/weapons/';
    const classes = data.classes || {};
    const corder = Object.fromEntries(Object.keys(classes).map((c, i) => [c, i]));
    const item = (w, pool) => {
      const rar = w.rarities || (w.variants || []).map((v) => v.rarity);
      const stats = w.stats || Object.fromEntries((w.variants || []).map((v) => [v.rarity, { dmg: v.dmg, dps: v.dps }]));
      const it = {
        key: `${pool ? 'pool' : 'all'}:${w.slug}`, slug: w.slug, name: w.name || w.slug, cat: w.cat || '',
        catLabel: classes[w.cat] || (w.cat || 'Other'), image: w.icon ? img + w.icon : '', rarities: rar, stats,
        rates: w.rates || {}, desc: w.desc || w.blurb || '', ammo: w.ammo || '', falloff: w.falloff || [],
        where: w.where || {}, also: w.also || {}, modes: w.modes || [], special: w.loot === 'special', pool,
        headmult: w.headmult, corder: corder[w.cat] ?? 99,
      };
      it.search = [it.name, it.catLabel, it.ammo, ...rar].join(' ').toLowerCase();
      return it;
    };
    return { pool: (data.lootPool || []).map((w) => item(w, true)), all: (data.catalog || []).map((w) => item(w, false)), updated: data.updated || '', mode: data.mode || 'Battle Royale' };
  }

  async function loadWeapons() {
    try {
      const res = await fetch('data/weapons.json', { cache: 'no-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.weapons = normalizeWeapons(await res.json());
      state.weaponsError = null;
      $('#weaponCount').textContent = state.weapons.pool.length;
    } catch (err) {
      state.weaponsError = err;
    }
    if (state.mode === 'weapons') buildSidebar();
    applyFilter('weapons');
    routeFromHash(true);
  }

  const weaponRar = (w) => { const r = state.weaponRarity[w.key]; return w.rarities.includes(r) ? r : (w.rarities[0] || ''); };

  function weaponSections(match) {
    if (!state.weapons) return [];
    const pool = state.weaponPool === WEAPON_POOLS[0];
    const items = state.weapons[pool ? 'pool' : 'all'].filter(match);
    const sort = state.weaponSort;
    if (sort === 'Class') {
      const secs = new Map();
      items.slice().sort((a, b) => a.corder - b.corder || a.special - b.special || (pool ? 0 : a.name.localeCompare(b.name)))
        .forEach((w) => { if (!secs.has(w.catLabel)) secs.set(w.catLabel, []); secs.get(w.catLabel).push(w); });
      return [...secs].map(([title, its]) => ({ title, subtitle: String(its.length), items: its }));
    }
    if (sort === 'Name') items.sort((a, b) => a.name.localeCompare(b.name));
    else if (sort === 'Chest chance') items.sort((a, b) => (b.rates.chests || 0) - (a.rates.chests || 0));
    else {
      const [k, sign] = WEAPON_SORT_KEYS[sort];
      const val = (w) => (w.stats[weaponRar(w)] || {})[k];
      items.sort((a, b) => (val(a) == null) - (val(b) == null) || sign * ((val(a) || 0) - (val(b) || 0)));
    }
    return items.length ? [{ title: null, items }] : [];
  }

  function weaponStatsText(w) {
    const st = w.stats[weaponRar(w)] || {};
    const parts = WEAPON_STATS.filter(([k]) => st[k] != null).map(([k, l, u]) => `${l} ${fmtStat(st[k], u)}`);
    return parts.length ? `${w.name} (${weaponRar(w)}): ${parts.join(', ')}` : w.name;
  }

  function weaponTileHTML(w, i, sel) {
    const L = state.layout, tile = L.tile, [x, y] = L.pos[i];
    const r = weaponRar(w), st = w.stats[r] || {};
    const line = st.dmg != null ? `${fmtStat(st.dmg)} DMG · ${fmtStat(st.dps)} DPS` : esc(w.catLabel);
    const pips = w.rarities.map((rr) => `<i class="wpip${rr === r ? ' on' : ''}" style="background:${rarityColor(rr)}"></i>`).join('');
    return `<div class="tile wcard${sel}" data-i="${i}" style="left:${x}px;top:${y}px;width:${tile}px;height:${tile + cardTextH()}px">` +
      `<div class="tile-img" style="height:${tile}px;background:linear-gradient(180deg, ${shade(rarityColor(r), -0.35)} 0%, var(--panel) 100%)">` +
      (w.special ? '<span class="pill dark">SPECIAL</span>' : '') +
      (w.image ? `<img src="${esc(w.image)}" alt="${esc(w.name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer" onload="this.classList.add('loaded')" onerror="this.remove()">` : '') +
      `<span class="wpips">${pips}</span></div>` +
      `<div class="tile-text"><div class="tile-name" title="${esc(w.name)}">${esc(w.name)}</div><div class="tile-sub">${line}</div>` +
      (w.rates.chests != null ? `<div class="tile-sub muted2">Chests ${fmtStat(w.rates.chests)}%</div>` : '') + '</div></div>';
  }

  function falloffSVG(pts) {
    if (!pts || pts.length < 2) return '';
    const W = 300, H = 110, pad = 22, xmax = Math.max(...pts.map((p) => p[0])) || 1, ymax = Math.max(...pts.map((p) => p[1])) * 1.15 || 1;
    const X = (d) => pad + (W - pad - 22) * d / xmax, Y = (v) => H - 18 - (H - 30) * v / ymax;
    const path = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('');
    return `<svg class="falloff" viewBox="0 0 ${W} ${H}" role="img" aria-label="Damage by distance">` +
      `<line x1="${pad}" y1="${H - 18}" x2="${W - 8}" y2="${H - 18}" class="axis"/><path d="${path}" class="curve"/>` +
      pts.map(([d, v]) => `<circle cx="${X(d)}" cy="${Y(v)}" r="3"/><text x="${X(d)}" y="${Y(v) - 7}" class="val">${fmtStat(Math.round(v * 10) / 10)}</text><text x="${X(d)}" y="${H - 5}" class="dist">${fmtStat(d)}m</text>`).join('') + '</svg>';
  }

  function showWeapon(w) {
    const r = weaponRar(w), st = w.stats[r] || {};
    const badges = [`<span class="badge">${esc(w.catLabel)}</span>`];
    if (w.ammo) badges.push(`<span class="badge" style="background:#3a3c42">${esc(w.ammo)}</span>`);
    if (w.special) badges.push('<span class="badge" style="background:var(--accent);color:var(--accent-fg)">Special</span>');
    const rarBtns = w.rarities.map((rr) => `<button class="rbtn${rr === r ? ' on' : ''}" data-act="w-rar" data-r="${rr}" style="--c:${rarityColor(rr)}">${esc(rr)}</button>`).join('');
    let statsHTML = '';
    if (st.dmg != null) {
      const head = w.headmult ? `${fmtStat(w.headmult)}×` : (st.head && st.dmg ? `${fmtStat(st.head / st.dmg)}×` : '-');
      const tiles = [['Damage', fmtStat(st.dmg), st.head != null ? `${fmtStat(st.head)} headshot` : ''], ['DPS', fmtStat(st.dps), st.rate != null ? `${fmtStat(st.rate)} shots / s` : ''],
        ['Magazine', fmtStat(st.mag), 'per reload'], ['Reload', fmtStat(st.reload, 's'), ''], ['Structures', fmtStat(st.struct), 'damage to builds'], ['Headshot', head, 'multiplier']];
      statsHTML = `<div class="wtiles">${tiles.map(([l, v, sub]) => `<div class="wtile"><span>${l}</span><b>${v}</b><em>${esc(sub)}</em></div>`).join('')}</div>`;
      const idx = Math.max(0, w.rarities.indexOf(r));
      if (w.falloff.length) statsHTML += `<div class="includes-h">Damage by distance</div>${falloffSVG(w.falloff[Math.min(idx, w.falloff.length - 1)])}`;
      const rars = w.rarities.filter((rr) => w.stats[rr]);
      const rows = WEAPON_STATS.filter(([k]) => rars.some((rr) => w.stats[rr][k] != null));
      if (rars.length > 1 && rows.length) {
        statsHTML += '<div class="includes-h">All rarities</div><div class="wmatrix-wrap"><table class="wmatrix"><thead><tr><th></th>' +
          rars.map((rr) => `<th style="color:${rarityColor(rr)}">${esc(rr.slice(0, 4))}</th>`).join('') + '</tr></thead><tbody>' +
          rows.map(([k, l, u, low]) => {
            const vals = rars.map((rr) => w.stats[rr][k]), nums = vals.filter((v) => v != null);
            const best = nums.length && new Set(nums).size > 1 ? (low ? Math.min(...nums) : Math.max(...nums)) : null;
            return `<tr><th>${l}</th>${vals.map((v) => `<td${v != null && v === best ? ' class="best"' : ''}>${fmtStat(v, u)}</td>`).join('')}</tr>`;
          }).join('') + '</tbody></table></div>';
      }
    }
    const where = Object.keys(w.where).length ? w.where : Object.fromEntries(Object.entries(w.rates).map(([k, v]) => [k.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()), v]));
    const mx = Math.max(1, ...Object.values(where));
    const whereHTML = Object.keys(where).length ? `<div class="includes-h">Where to find it · ${esc(state.weapons.mode)}</div>` +
      Object.entries(where).map(([k, v]) => `<div class="wfind"><span>${esc(k)}</span><div class="wtrack"><i style="width:${(100 * v / mx).toFixed(1)}%"></i></div><b>${fmtStat(v)}%</b></div>`).join('') +
      (Object.keys(w.also).length ? `<p class="hint">Also from: ${Object.entries(w.also).map(([k, v]) => `${esc(k)} (${fmtStat(v)}%)`).join(', ')}</p>` : '') : '';
    const facts = [];
    if (w.modes.length) facts.push(['Modes', w.modes.join(', ')]);
    if (!w.pool) facts.push(['Pool', state.weapons.pool.some((p) => p.slug === w.slug) ? 'In the current loot pool' : 'Not in the current Battle Royale loot pool']);
    facts.push(['Data', `Fortnite.GG · updated ${state.weapons.updated}`]);
    setDetail(
      `<a class="d-img" href="${esc(fggWeapon(w.slug))}" target="_blank" rel="noopener" style="background:linear-gradient(180deg, ${shade(rarityColor(r), -0.35)} 0%, var(--panel) 100%)">` +
      (w.image ? `<img src="${esc(w.image)}" alt="${esc(w.name)}" referrerpolicy="no-referrer">` : '') + '</a>' +
      `<h2>${esc(w.name)}</h2><div class="badges">${badges.join('')}</div>` +
      (w.desc ? `<p class="desc">${esc(w.desc)}</p>` : '') +
      (rarBtns ? `<div class="rbtns">${rarBtns}</div>` : '') + statsHTML + whereHTML + factsHTML(facts) +
      `<div class="btn-row"><button class="btn" data-act="copy" data-v="${esc(w.name)}" data-w="name">Copy name</button><button class="btn" data-act="w-copy">Copy stats</button><button class="btn" data-act="link">Share link</button></div>` +
      `<a class="btn btn-accent block" href="${esc(fggWeapon(w.slug))}" target="_blank" rel="noopener">View on Fortnite.GG</a>`,
    );
  }

  function setWeaponRarity(w, r) {
    state.weaponRarity[w.key] = r;
    const top = el.wrap.scrollTop; render(true); el.wrap.scrollTop = top;
    const y = el.detail.scrollTop; showWeapon(w); el.detail.scrollTop = y;
  }

  // ------------------------------------------------------------------ news
  // fortnite.com/news blocks scripts (Cloudflare) and its /api/news route is switched off, so the archive comes from
  // Fortnite.GG's copy of Epic's official news (data/news.json, refreshed every 3 h by tools/scrape_fortnitegg.py),
  // merged with Epic's live in-game news from fortnite-api.com so the newest stories show up right away.
  const FN_NEWS = 'https://www.fortnite.com/news?lang=en-US';
  const FGG_NEWS = 'https://fortnite.gg/news';
  const normTitle = (t) => String(t || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const todayISO = () => new Date().toISOString().slice(0, 10);

  function normalizeNews(data, motds) {
    if (!data || data.schema !== 1 || !Array.isArray(data.items)) throw new Error('unsupported news data');
    const live = new Map((motds || []).filter((m) => m.title).map((m) => [normTitle(m.title), m]));
    const items = data.items.map((n, i) => ({
      key: n.id ? `fgg:${n.id}` : `n:${i}`, id: n.id || String(i), title: n.title || '', desc: n.desc || '', date: n.date || '',
      image: n.image || '', imageLarge: n.imageLarge || n.image || '', links: n.links || [], votes: n.votes || null,
      live: live.has(normTitle(n.title)),
    }));
    const known = new Set(items.map((n) => normTitle(n.title)));
    const fresh = [...live.values()].filter((m) => !known.has(normTitle(m.title))).map((m) => ({
      key: `epic:${m.id || normTitle(m.title)}`, id: `epic-${m.id || normTitle(m.title).replace(/ /g, '-')}`, title: m.title, desc: m.body || '',
      date: todayISO(), image: m.tileImage || m.image || '', imageLarge: m.image || m.tileImage || '', links: [], votes: null, live: true, epic: true,
    }));
    const all = [...fresh, ...items];
    all.forEach((n) => { n.search = `${n.title} ${n.desc}`.toLowerCase(); });
    return { items: all, updated: data.updated || '', liveCount: live.size };
  }

  async function loadNews() {
    try {
      const [res, motds] = await Promise.all([
        fetch('data/news.json', { cache: 'no-cache' }),
        getJSON(`${API}/news/br?language=en`).then((d) => d.motds || []).catch(() => []),
      ]);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.news = normalizeNews(await res.json(), motds);
      state.newsError = null;
      $('#newsCount').textContent = state.news.items.filter((n) => n.date >= daysAgo(7)).length || '';
    } catch (err) {
      state.newsError = err;
    }
    applyFilter('news');
    if (state.mode === 'news') buildSidebar();
    routeFromHash(true);
  }

  function daysAgo(n) { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); }
  const fmtNewsDate = (iso) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '');

  function newsSections(match) {
    if (!state.news) return [];
    const secs = new Map();
    const live = state.news.items.filter((n) => n.live && match(n));
    if (live.length) secs.set('In game now', live);
    for (const n of state.news.items) {
      if (n.live || !match(n)) continue;
      const t = n.date ? new Date(`${n.date}T12:00:00`).toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : 'Older';
      if (!secs.has(t)) secs.set(t, []);
      secs.get(t).push(n);
    }
    return [...secs].map(([title, items]) => ({ title, subtitle: `${items.length} ${items.length === 1 ? 'story' : 'stories'}`, items }));
  }

  function newsTileHTML(n, i, sel) {
    const L = state.layout, [x, y] = L.pos[i];
    return `<div class="tile ncard${sel}" data-i="${i}" style="left:${x}px;top:${y}px;width:${L.tw}px;height:${L.th}px">` +
      `<div class="tile-img" style="height:${L.ih}px;background:var(--panel-2)">` +
      (n.live ? '<span class="pill">IN GAME NOW</span>' : '') +
      (n.image ? `<img src="${esc(n.image)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onload="this.classList.add('loaded')" onerror="this.remove()">` : '') +
      `</div><div class="tile-text"><div class="ndate">${esc(fmtNewsDate(n.date))}${n.votes && n.votes.fire != null ? ` · <span title="Fortnite.GG votes">🔥 ${Math.round(n.votes.fire)}%</span>` : ''}</div>` +
      `<div class="ntitle" title="${esc(n.title)}">${esc(n.title)}</div><div class="ndesc">${esc(n.desc)}</div></div></div>`;
  }

  function showNews(n) {
    const badges = [`<span class="badge">${esc(fmtNewsDate(n.date))}</span>`];
    if (n.live) badges.unshift('<span class="badge" style="background:var(--accent);color:var(--accent-fg)">In game now</span>');
    const links = n.links.map((l) => {
      const cid = l.cosmetic && [...state.byId.keys()].find((k) => k.toLowerCase() === l.cosmetic.toLowerCase());
      return cid
        ? `<button class="inc" data-act="goto-item" data-id="${esc(cid)}"><span>${esc(l.label)}</span><span>${esc(state.byId.get(cid).name)} ›</span></button>`
        : `<a class="inc" href="${esc(l.url)}" target="_blank" rel="noopener"><span>${esc(l.label)}</span><span>${esc(l.island ? 'Island on Fortnite.GG' : 'Fortnite.GG')} ↗</span></a>`;
    }).join('');
    const facts = [['Published', fmtNewsDate(n.date) || '-'], ['Source', n.epic ? 'Epic in-game news (live)' : "Epic's Fortnite news, archived by Fortnite.GG"]];
    if (n.votes) facts.push(['Player votes', `${n.votes.fire != null ? `${Math.round(n.votes.fire)}% 🔥 · ` : ''}${fmt(n.votes.total)} votes on Fortnite.GG`]);
    setDetail(
      `<a class="d-img news-dimg" href="${esc(n.imageLarge || n.image)}" target="_blank" rel="noopener">` +
      (n.image ? `<img src="${esc(n.imageLarge || n.image)}" alt="${esc(n.title)}" referrerpolicy="no-referrer">` : '') + '</a>' +
      `<h2>${esc(n.title)}</h2><div class="badges">${badges.join('')}</div>` +
      (n.desc ? `<p class="desc">${esc(n.desc)}</p>` : '') +
      (links ? `<div class="includes-h">Links</div>${links}` : '') + factsHTML(facts) +
      `<div class="btn-row"><button class="btn" data-act="copy" data-v="${esc(n.title)}" data-w="headline">Copy headline</button><button class="btn" data-act="link">Share link</button></div>` +
      `<a class="btn btn-accent block" href="${FN_NEWS}" target="_blank" rel="noopener">Read Fortnite news on fortnite.com</a>` +
      `<a class="btn block" style="margin-top:8px" href="${FGG_NEWS}" target="_blank" rel="noopener">News archive on Fortnite.GG</a>`,
    );
  }

  // ------------------------------------------------------------------ interactive map
  // data/map.json is scraped from Fortnite.GG's map by tools/scrape_fortnitegg.py (refreshed daily). Tiles and icons
  // are hotlinked from fortnite.gg. Rendering lives in map.js (window.FcbMap); this block is the app glue.
  const MAP_KEY = 'fcb.map.layers.v1';
  let fmap = null;

  async function loadMap() {
    try {
      const res = await fetch('data/map.json', { cache: 'no-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.schema !== 1 || !Array.isArray(data.groups)) throw new Error('unsupported map data');
      state.map = data;
      state.mapLayers = new Map(data.groups.flatMap((g) => g.layers.map((l) => [l.id, { ...l, groupName: g.name }])));
      let saved = null;
      try { saved = JSON.parse(store.get(MAP_KEY, 'null')); } catch { /* ignore */ }
      state.mapOn = new Set((Array.isArray(saved) ? saved : data.defaultOn || []).filter((id) => state.mapLayers.has(id)));
      state.mapError = null;
      $('#mapCount').textContent = `S${data.season}`;
      if (fmap) { fmap.setData(data); fmap.setEnabled(state.mapOn); }
    } catch (err) {
      state.mapError = err;
    }
    if (state.mode === 'map') { ensureMap(); buildSidebar(); showMapInfo(); }
    updateStatus();
    routeFromHash(true);
  }

  function ensureMap() {
    el.mapEmpty.hidden = !!state.map;
    el.mapEmpty.innerHTML = state.map ? '' : state.mapError
      ? `<p>${esc(`Couldn't load the map.\n${state.mapError.message}\nRefresh the page to try again.`)}</p>`
      : '<div class="spinner"></div><p>Loading the map...</p>';
    if (!state.map || !window.FcbMap) return;
    if (!fmap) {
      fmap = new window.FcbMap(el.mapWrap, {
        onSelect: (h) => { if (h) { showMapHit(h); if (window.innerWidth <= 980) document.body.classList.add('detail-open'); } else showMapInfo(); },
        onView: (v) => { if (state.mode === 'map') setHash(`map/@${v.x.toFixed(1)},${v.y.toFixed(1)},${v.z.toFixed(2)}`); },
        onHover: (h, p) => {
          if (!h || !p) { el.mapTip.hidden = true; return; }
          el.mapTip.textContent = h.label ? h.name : h.count ? `${h.count} ${state.mapLayers.get(h.layer.id).name} (click to zoom)` : state.mapLayers.get(h.layer.id).name;
          el.mapTip.style.transform = `translate(${Math.round(p[0] + 14)}px, ${Math.round(p[1] + 12)}px)`;
          el.mapTip.hidden = false;
        },
      });
      fmap.setData(state.map);
      fmap.setEnabled(state.mapOn);
    } else fmap.resize();
  }

  function saveMapLayers() { store.set(MAP_KEY, JSON.stringify([...state.mapOn])); }

  function setMapLayers(ids) {
    state.mapOn = new Set(ids);
    saveMapLayers();
    if (fmap) fmap.setEnabled(state.mapOn);
    buildSidebar();
    if (!fmap || !fmap.selected) showMapInfo();
    else if (!state.mapOn.has(fmap.selected.layer.id)) { fmap.select(null); showMapInfo(); }
  }

  function toggleMapLayer(id) {
    const on = new Set(state.mapOn);
    if (on.has(id)) on.delete(id); else on.add(id);
    setMapLayers(on);
  }

  const mapIcon = (id) => (id != null && state.map ? `${state.map.iconBase}${id}.png` : '');

  function mapLocations() {
    return ['poi', 'landmarks'].flatMap((id) => (state.mapLayers.get(id)?.labels || []).map((b) => ({ ...b, major: id === 'poi' })));
  }

  function nearestLocation(pt) {
    let best = null, bd = Infinity;
    for (const b of mapLocations()) {
      const d = Math.hypot(b.pt[0] - pt[0], b.pt[1] - pt[1]) * (b.major ? 0.8 : 1);
      if (d < bd) { bd = d; best = b; }
    }
    return best && { ...best, d: bd };
  }

  function mapSidebarHTML() {
    if (!state.map) return state.mapError ? '<div class="side-note">Map unavailable</div>' : '<div class="side-note">Loading the map...</div>';
    const terms = state.search.map.toLowerCase().split(/\s+/).filter(Boolean);
    const hit = (txt) => terms.every((t) => txt.toLowerCase().includes(t));
    let html = '';
    if (terms.length) {
      const locs = mapLocations().filter((b) => hit(b.name)).slice(0, 12);
      if (locs.length) {
        html += '<div class="side-heading sub">Go to location</div>' + locs.map((b) =>
          `<button class="side-row" data-goto="${b.pt.join(',')}"><span>${esc(b.name)}</span><span>${b.major ? 'POI' : ''}</span></button>`).join('');
      }
    } else {
      html += '<div class="map-allrow"><button class="side-row" data-mapall="1"><span>Show all</span></button><button class="side-row" data-mapall="0"><span>Hide all</span></button><button class="side-row" data-mapall="d"><span>Default</span></button></div>';
    }
    for (const g of state.map.groups) {
      const ls = g.layers.filter((l) => !terms.length || hit(`${l.name} ${l.sub} ${g.name}`));
      if (!ls.length) continue;
      html += `<div class="side-heading sub">${esc(g.name)}</div>` + ls.map((l) => {
        const on = state.mapOn.has(l.id);
        const ic = mapIcon(l.icon) || (l.kind === 'labels' ? '' : '');
        return `<button class="side-row map-layer${on ? ' on' : ''}" data-layer="${esc(l.id)}" aria-pressed="${on}" title="${esc(l.sub || l.name)}">` +
          `<span class="ml-name">${ic ? `<img src="${esc(ic)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<i class="ml-dot">A</i>'}<span>${esc(l.name)}</span></span><span>${fmt(l.n)}</span></button>`;
      }).join('');
    }
    return html || '<div class="side-note">No layers match.</div>';
  }

  function showMapInfo() {
    if (state.mode !== 'map') return;
    if (!state.map) { showAbout(); return; }
    const on = [...state.mapOn].map((id) => state.mapLayers.get(id)).filter(Boolean);
    const total = on.reduce((n, l) => n + l.n, 0);
    const legend = on.filter((l) => l.kind !== 'labels').map((l) =>
      `<button class="inc" data-act="map-only" data-layer="${esc(l.id)}"><span class="ml-name">${mapIcon(l.icon) ? `<img src="${esc(mapIcon(l.icon))}" alt="" referrerpolicy="no-referrer">` : ''}<span>${esc(l.name)}</span></span><span>${fmt(l.n)}</span></button>`).join('');
    setDetail(
      `<h2>Fortnite Map</h2><div class="badges"><span class="badge" style="background:var(--accent);color:var(--accent-fg)">Season ${esc(state.map.season)}</span><span class="badge">Map ${esc(state.map.version)}</span></div>` +
      `<p class="desc">Drag to pan, scroll or pinch to zoom, click a marker for details. Numbers on icons are clusters, click one to zoom in. Pick layers on the left.</p>` +
      factsHTML([['Layers on', `${on.length} of ${state.mapLayers.size}`], ['Markers shown', fmt(total)], ['Data', `Fortnite.GG · updated ${state.map.updated}`]]) +
      (legend ? `<div class="includes-h">Showing (click to show only that layer)</div>${legend}` : '') +
      '<div class="btn-row"><button class="btn" data-act="map-fit">Reset view</button><button class="btn" data-act="link">Share link</button></div>' +
      '<a class="btn btn-accent block" href="https://fortnite.gg/" target="_blank" rel="noopener">Open the full map on Fortnite.GG</a>',
    );
  }

  function showMapHit(h) {
    const l = state.mapLayers.get(h.layer.id);
    const near = nearestLocation(h.pt);
    const coords = `${h.pt[0].toFixed(1)}, ${h.pt[1].toFixed(1)}`;
    const title = h.label ? h.name : l.name;
    const facts = [['Layer', `${l.name} · ${l.groupName}`]];
    if (!h.label && near) facts.push(['Nearest place', near.name]);
    if (l.sub) facts.push(['Note', l.sub]);
    if (h.to) facts.push(['Leads to', `${h.to[0].toFixed(1)}, ${h.to[1].toFixed(1)}`]);
    facts.push(['On this map', `${fmt(l.n)} ${l.kind === 'labels' ? 'places' : 'markers'}`], ['Map position', coords]);
    const icon = mapIcon(h.icon ?? l.icon);
    setDetail(
      (icon ? `<div class="d-img map-dimg"><img src="${esc(icon)}" alt="" referrerpolicy="no-referrer"></div>` : '') +
      `<h2>${esc(title)}</h2><div class="badges"><span class="badge">${esc(l.groupName)}</span>${h.label ? '' : `<span class="badge" style="background:#3a3c42">${esc(l.name)}</span>`}</div>` +
      factsHTML(facts) +
      `<div class="btn-row"><button class="btn" data-act="map-zoom">Zoom here</button><button class="btn" data-act="map-only" data-layer="${esc(l.id)}">Only this layer</button><button class="btn" data-act="map-hide" data-layer="${esc(l.id)}">Hide layer</button></div>` +
      `<div class="btn-row"><button class="btn" data-act="copy" data-v="${esc(title)}" data-w="name">Copy name</button><button class="btn" data-act="link">Share link</button></div>` +
      '<a class="btn btn-accent block" href="https://fortnite.gg/" target="_blank" rel="noopener">Open the full map on Fortnite.GG</a>',
    );
  }

  // ------------------------------------------------------------------ navigation
  function setMode(mode, { keepHash = false } = {}) {
    if (mode === state.mode) return;
    if (state.mode) state.grid[state.mode].scroll = el.wrap.scrollTop;
    state.mode = mode;
    document.querySelectorAll('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
    el.search.value = state.search[mode];
    el.search.placeholder = { browse: 'Search cosmetics, sets, IDs...', shop: 'Search the Item Shop...', sprites: 'Search sprites, abilities...', weapons: 'Search weapons & items...', map: 'Search layers & locations...', news: 'Search Fortnite news...' }[mode];
    el.browseTools.style.display = mode === 'browse' ? '' : 'none';
    el.spriteTools.style.display = mode === 'sprites' ? '' : 'none';
    el.weaponTools.style.display = mode === 'weapons' ? '' : 'none';
    el.hero.hidden = mode !== 'sprites';
    el.wrap.hidden = mode === 'map';
    el.mapWrap.hidden = mode !== 'map';
    el.sizeSeg.style.display = mode === 'map' ? 'none' : '';
    el.empty.hidden = true;
    if (mode === 'map') ensureMap(); else el.mapTip.hidden = true;
    buildSidebar();
    layout();
    el.wrap.scrollTop = state.grid[mode].scroll;
    render();
    const g = state.grid[mode];
    if (mode === 'map') {
      if (fmap && fmap.selected) showMapHit(fmap.selected); else showMapInfo();
    } else if (g.selected != null && g.flat[g.selected]) {
      showItem(g.flat[g.selected]);
    } else showAbout();
    if (!keepHash) setHash(mode === 'browse' ? '' : mode);
    updateStatus();
    document.body.classList.remove('menu-open');
  }

  function buildSidebar() {
    const rows = [];
    if (state.mode === 'browse') {
      el.sideHeading.textContent = 'Categories';
      const counts = new Map();
      for (const it of state.items) counts.set(it.cat, (counts.get(it.cat) || 0) + 1);
      rows.push(['All', state.items.length]);
      for (const c of state.cats) rows.push([c, counts.get(c) || 0]);
      el.sideList.innerHTML = rows.map(([c, n]) =>
        `<button class="side-row${c === state.cat ? ' active' : ''}" data-cat="${esc(c)}"><span>${esc(c)}</span><span>${n ? fmt(n) : ''}</span></button>`).join('');
    } else if (state.mode === 'sprites') {
      el.sideHeading.textContent = 'My collection';
      const es = state.sprites ? seasonEntries().filter(variantOk) : [];
      el.sideList.innerHTML = SPRITE_FILTERS.map((f) =>
        `<button class="side-row${f === state.spriteFilter ? ' active' : ''}" data-filter="${esc(f)}"><span>${esc(f)}</span><span>${state.sprites ? es.filter((e) => entryMatches(e, f)).length : ''}</span></button>`).join('') +
        '<div class="side-heading sub">Backup</div>' +
        '<button class="side-row" data-backup="export"><span>Export progress</span><span>.json</span></button>' +
        '<button class="side-row" data-backup="import"><span>Import progress</span><span>merge</span></button>';
    } else if (state.mode === 'news') {
      el.sideHeading.textContent = 'News';
      el.sideList.innerHTML = state.grid.news.sections.map((x) =>
        `<button class="side-row" data-section="${esc(x.title)}"><span>${esc(x.title)}</span><span>${x.items.length}</span></button>`).join('') +
        '<div class="side-heading sub">Official</div>' +
        `<a class="side-row" href="${FN_NEWS}" target="_blank" rel="noopener"><span>fortnite.com/news</span><span>↗</span></a>` +
        `<a class="side-row" href="${FGG_NEWS}" target="_blank" rel="noopener"><span>Fortnite.GG archive</span><span>↗</span></a>`;
    } else if (state.mode === 'map') {
      el.sideHeading.textContent = 'Map layers';
      el.sideList.innerHTML = mapSidebarHTML();
    } else if (state.mode === 'weapons') {
      el.sideHeading.textContent = 'Classes';
      el.sideList.innerHTML = state.grid.weapons.sections.filter((x) => x.title).map((x) =>
        `<button class="side-row" data-section="${esc(x.title)}"><span>${esc(x.title)}</span><span>${x.items.length}</span></button>`).join('');
    } else {
      el.sideHeading.textContent = 'Shop sections';
      el.sideList.innerHTML = state.shop ? [...state.shop.sections].map(([t, list]) =>
        `<button class="side-row" data-section="${esc(t)}"><span>${esc(t)}</span><span>${list.length}</span></button>`).join('') : '';
    }
  }

  el.sideList.addEventListener('click', (e) => {
    const b = e.target.closest('.side-row');
    if (!b) return;
    if (b.dataset.cat != null) {
      state.cat = b.dataset.cat;
      el.sideList.querySelectorAll('.side-row').forEach((r) => r.classList.toggle('active', r === b));
      applyFilter('browse');
    } else if (b.dataset.filter != null) {
      state.spriteFilter = b.dataset.filter;
      buildSidebar();
      applyFilter('sprites');
    } else if (b.dataset.backup) {
      if (b.dataset.backup === 'export') exportProgress(); else importProgress();
    } else if (b.dataset.layer) {
      toggleMapLayer(b.dataset.layer);
      return; // keep the drawer open while picking layers
    } else if (b.dataset.mapall) {
      const v = b.dataset.mapall;
      setMapLayers(v === '1' ? [...state.mapLayers.keys()] : v === '0' ? [] : (state.map.defaultOn || []).filter((id) => state.mapLayers.has(id)));
      return;
    } else if (b.dataset.goto) {
      const pt = b.dataset.goto.split(',').map(Number);
      if (fmap) {
        fmap.flyTo(pt, 4.6);
        const loc = mapLocations().find((x) => x.pt[0] === pt[0] && x.pt[1] === pt[1]);
        if (loc) {
          const layer = state.mapLayers.get(loc.major ? 'poi' : 'landmarks');
          if (!state.mapOn.has(layer.id)) toggleMapLayer(layer.id);
          const hit = { layer, pt, name: loc.name, label: true };
          fmap.select(hit); showMapHit(hit);
        }
      }
    } else {
      const r = state.layout.rows.find((row) => row.kind === 'header' && row.s.title === b.dataset.section);
      if (r) { el.wrap.scrollTop = r.y; render(); }
    }
    document.body.classList.remove('menu-open');
  });
  document.querySelectorAll('.nav-item').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));

  function gotoOffer(key) {
    setMode('shop', { keepHash: true });
    state.search.shop = ''; el.search.value = '';
    applyFilter('shop');
    const i = state.grid.shop.flat.findIndex((it) => it.key === key);
    if (i >= 0) select(i);
  }

  function gotoCosmetic(id, fromRoute = false) {
    setMode('browse', { keepHash: true });
    state.search.browse = ''; el.search.value = '';
    state.cat = 'All'; state.rarity = 'All'; el.rarity.selectedIndex = 0;
    buildSidebar();
    applyFilter('browse');
    const i = state.grid.browse.flat.findIndex((it) => it.id === id);
    if (i >= 0) select(i, { fromRoute, open: !fromRoute || window.innerWidth > 980 });
  }

  // hash routes: #item/<id>, #shop, #shop/<offerId>, #sprites, #sprites/<spriteId>
  let settingHash = false;
  function setHash(h) {
    settingHash = true;
    history.replaceState(null, '', h ? `#${h}` : location.pathname + location.search);
    settingHash = false;
  }
  function routeFromHash(onLoad = false) {
    const h = decodeURIComponent(location.hash.slice(1));
    if (h.startsWith('item/') && state.items.length) {
      if (!onLoad || state.grid.browse.selected == null) gotoCosmetic(h.slice(5), true);
    } else if (h.startsWith('news')) {
      if (state.mode !== 'news') setMode('news', { keepHash: true });
      const id = h.slice(5);
      if (id && state.news) {
        const i = state.grid.news.flat.findIndex((it) => it.id === id);
        if (i >= 0 && state.grid.news.selected !== i) select(i, { fromRoute: true, open: window.innerWidth > 980 });
      }
    } else if (h.startsWith('map')) {
      if (state.mode !== 'map') setMode('map', { keepHash: true });
      const m = /^map\/@(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)$/.exec(h);
      if (m && fmap && onLoad !== 'view') fmap.setView(+m[1], +m[2], +m[3]);
    } else if (h.startsWith('weapons')) {
      if (state.mode !== 'weapons') setMode('weapons', { keepHash: true });
      const slug = h.slice(8);
      if (slug && state.weapons) {
        const i = state.grid.weapons.flat.findIndex((it) => it.slug === slug);
        if (i >= 0 && state.grid.weapons.selected !== i) select(i, { fromRoute: true, open: window.innerWidth > 980 });
      }
    } else if (h.startsWith('sprites')) {
      if (state.mode !== 'sprites') setMode('sprites', { keepHash: true });
      const [id, v] = h.slice(8).split('~');
      if (id && state.sprites) {
        const i = state.grid.sprites.flat.findIndex((it) => it.sp.id === id && (it.v || '') === (v || ''));
        if (i >= 0 && state.grid.sprites.selected !== i) select(i, { fromRoute: true, open: window.innerWidth > 980 });
      }
    } else if (h.startsWith('shop')) {
      if (state.mode !== 'shop') setMode('shop', { keepHash: true });
      const offerId = h.slice(5);
      if (offerId && state.shop) {
        const i = state.grid.shop.flat.findIndex((it) => it.offerId === offerId);
        if (i >= 0 && state.grid.shop.selected !== i) select(i, { fromRoute: true, open: window.innerWidth > 980 });
      }
    }
  }
  window.addEventListener('hashchange', () => { if (!settingHash) routeFromHash(); });

  // ------------------------------------------------------------------ status / timers
  function updateStatus() {
    if (state.mode === 'browse') {
      el.status.textContent = state.items.length
        ? `Showing ${fmt(state.grid.browse.flat.length)} of ${fmt(state.items.length)} cosmetics`
        : state.cosmeticsError ? 'Cosmetics unavailable' : 'Downloading cosmetics from fortnite-api.com...';
    } else if (state.mode === 'news') {
      el.status.textContent = state.news ? `Fortnite news · ${fmt(state.grid.news.flat.length)} stories · ${state.news.liveCount} in game now · archive updated ${state.news.updated.replace('T', ' ')} · Epic news via Fortnite.GG & fortnite-api.com`
        : state.newsError ? 'News unavailable' : 'Loading Fortnite news...';
    } else if (state.mode === 'map') {
      el.status.textContent = state.map ? `Season ${state.map.season} map · ${state.mapOn.size} layers on · updated ${state.map.updated} · map & data: Fortnite.GG`
        : state.mapError ? 'Map unavailable' : 'Loading the map...';
    } else if (state.mode === 'weapons') {
      el.status.textContent = state.weapons ? `${state.weaponPool} · ${fmt(state.grid.weapons.flat.length)} shown · stats updated ${state.weapons.updated} · data: Fortnite.GG`
        : state.weaponsError ? 'Weapon stats unavailable' : 'Loading weapon stats...';
    } else if (state.mode === 'sprites') {
      if (!state.sprites) { el.status.textContent = state.spritesError ? 'Sprite list unavailable' : 'Loading Sprites...'; return; }
      const st = spriteStats(), se = seasonObj();
      el.status.textContent = `${se.name} · Owned ${st.owned}/${st.total} · Mastered ${st.mastered}/${st.total} · saved in this browser · sprite images: Fortnite.GG`;
    } else if (state.shop) {
      const n = state.grid.shop.flat.length;
      const rem = (state.shop.reset - Date.now()) / 1000;
      el.status.textContent = `Item Shop for ${state.shop.date.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' })} · ${n} offers · ${rem > 0 ? 'resets in ' + fmtRemaining(rem) : 'new shop available, refresh'}`;
    } else {
      el.status.textContent = state.shopError ? 'Item Shop unavailable' : 'Loading the Item Shop...';
    }
  }

  function tick() {
    if (state.shop) {
      const rem = (state.shop.reset - Date.now()) / 1000;
      el.shopCountdown.textContent = rem > 0 ? fmtRemaining(rem) : 'new';
    }
    if (state.mode === 'shop') updateStatus();
  }
  setInterval(tick, 30000);

  // ------------------------------------------------------------------ controls
  SORTS.forEach((s) => el.sort.insertAdjacentHTML('beforeend', `<option>${s}</option>`));
  let searchTimer;
  el.search.addEventListener('input', () => {
    state.search[state.mode] = el.search.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => applyFilter(), 140);
  });
  el.rarity.addEventListener('change', () => { state.rarity = el.rarity.selectedIndex ? el.rarity.value : 'All'; applyFilter('browse'); });
  el.sort.addEventListener('change', () => { state.sort = el.sort.value; applyFilter('browse'); });

  function paintSize() { el.sizeSeg.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.size === state.size)); }
  el.sizeSeg.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    state.size = b.dataset.size;
    store.set('fcb.size', state.size);
    paintSize();
    const g = state.grid[state.mode];
    layout();
    if (g.selected != null) ensureVisible(g.selected);
  });
  paintSize();

  $('#menuBtn').addEventListener('click', () => document.body.classList.toggle('menu-open'));
  $('#scrim').addEventListener('click', () => document.body.classList.remove('menu-open'));

  document.addEventListener('keydown', (e) => {
    const inField = e.target === el.search || e.target.tagName === 'SELECT';
    if ((e.key === '/' && !inField) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f')) {
      e.preventDefault(); el.search.focus(); el.search.select(); return;
    }
    if (e.key === 'Escape') {
      if (document.body.classList.contains('detail-open')) document.body.classList.remove('detail-open');
      else if (e.target === el.search && el.search.value) { el.search.value = ''; el.search.dispatchEvent(new Event('input')); }
      return;
    }
    if (state.mode === 'map') {
      if (e.target === el.search && e.key === 'Enter' && state.map) {
        const first = el.sideList.querySelector('[data-goto]');
        if (first) first.click();
        return;
      }
      if (!inField && fmap && e.target !== fmap.canvas && /^(Arrow\w+|[+=_0-]|-)$/.test(e.key)) {
        fmap.canvas.focus();
        fmap.canvas.dispatchEvent(new KeyboardEvent('keydown', { key: e.key }));
        e.preventDefault();
      }
      return;
    }
    if (inField && e.key !== 'ArrowDown') return;
    const g = state.grid[state.mode];
    if (!g.flat.length) return;
    const cur = g.selected ?? -1;
    const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -state.layout.cols, ArrowDown: state.layout.cols };
    if (e.key in moves) {
      e.preventDefault();
      if (inField) el.wrap.focus();
      select(cur < 0 ? 0 : cur + moves[e.key], { open: false });
    } else if (state.mode === 'sprites' && cur >= 0 && !inField && (e.key === ' ' || /^[mM]$/.test(e.key))) {
      e.preventDefault();
      toggleEntry(g.flat[cur], e.key === ' ' ? 'owned' : 'mastered');
    } else if (e.key === 'Enter' && cur >= 0) {
      const it = g.flat[cur];
      if (state.mode === 'sprites') { toggleEntry(it, 'owned'); return; }
      if (state.mode === 'weapons') { window.open(fggWeapon(it.slug), '_blank', 'noopener'); return; }
      if (state.mode === 'news') { window.open(it.imageLarge || it.image, '_blank', 'noopener'); return; }
      window.open(state.mode === 'browse' ? it.featured || it.icon : it.image, '_blank', 'noopener');
    }
  });

  WEAPON_POOLS.forEach((n) => el.weaponPool.insertAdjacentHTML('beforeend', `<option value="${n}">${n}</option>`));
  WEAPON_SORTS.forEach((n) => el.weaponSort.insertAdjacentHTML('beforeend', `<option value="${n}">${n === 'Class' ? 'Sort: class' : n}</option>`));
  el.weaponPool.addEventListener('change', () => { state.weaponPool = el.weaponPool.value; applyFilter('weapons'); });
  el.weaponSort.addEventListener('change', () => { state.weaponSort = el.weaponSort.value; applyFilter('weapons'); });
  SPRITE_SORTS.forEach((n) => el.spriteSort.insertAdjacentHTML('beforeend', `<option value="${n}">${n === 'Default' ? 'Sort: default' : n}</option>`));
  el.spriteVariant.addEventListener('change', () => { state.spriteVariant = el.spriteVariant.value; buildSidebar(); applyFilter('sprites'); });
  el.spriteSort.addEventListener('change', () => { state.spriteSort = el.spriteSort.value; applyFilter('sprites'); });
  el.heroChips.addEventListener('click', (e) => {
    const b = e.target.closest('[data-season]');
    if (!b) return;
    state.spriteSeason = b.dataset.season;
    spriteCountsChanged();
    applyFilter('sprites');
  });

  el.mapWrap.querySelector('.map-ctrl').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b || !fmap) return;
    const z = Number(b.dataset.z);
    if (z) fmap.zoomBy(z * 0.75); else fmap.fit();
  });

  // ------------------------------------------------------------------ boot
  state.mode = null;
  setMode(location.hash.startsWith('#shop') ? 'shop' : location.hash.startsWith('#sprites') ? 'sprites' : location.hash.startsWith('#weapons') ? 'weapons' : location.hash.startsWith('#map') ? 'map' : location.hash.startsWith('#news') ? 'news' : 'browse', { keepHash: true });
  loadCosmetics();
  loadShop();
  loadSprites();
  loadWeapons();
  loadMap();
  loadNews();

  // exposed for tests
  window.__fcb = { md5, webSlug, epicItemUrl, state, progress, toggleEntry, userPhotos, setPhotoFromBlob, seasonEntries, weaponStatsText, getMap: () => fmap, nearestLocation, normalizeNews };
})();
