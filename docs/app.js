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
    toast: $('#toast'),
  };

  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  const state = {
    mode: 'browse',
    items: [], byId: new Map(), cats: [], cat: 'All', rarity: 'All', sort: 'Newest',
    search: { browse: '', shop: '' },
    shop: null, shopByItem: new Map(), shopError: null, cosmeticsError: null,
    size: TILE_SIZES[store.get('fcb.size', 'M')] ? store.get('fcb.size', 'M') : 'M',
    grid: {
      browse: { sections: [], flat: [], selected: null, scroll: 0 },
      shop: { sections: [], flat: [], selected: null, scroll: 0 },
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
    const g = state.grid[state.mode];
    const w = Math.max(1, el.wrap.clientWidth);
    const tile = tileSize(w);
    const th = tile + TEXT_H;
    const cols = Math.max(1, Math.floor((w - GAP) / (tile + GAP)));
    const gridW = cols * (tile + GAP) - GAP;
    const x0 = Math.max(GAP, Math.floor((w - gridW) / 2));
    const rows = [], pos = new Array(g.flat.length);
    let y = GAP, idx = 0;
    for (const s of g.sections) {
      if (s.title) { rows.push({ y, h: HEADER_H, kind: 'header', s }); y += HEADER_H; }
      const n = s.items.length;
      for (let r = 0; r < Math.ceil(n / cols); r++) {
        const start = idx + r * cols, cnt = Math.min(cols, n - r * cols);
        rows.push({ y, h: th, kind: 'tiles', start, cnt });
        for (let k = 0; k < cnt; k++) pos[start + k] = [x0 + k * (tile + GAP), y];
        y += th + GAP;
      }
      idx += n;
    }
    Object.assign(state.layout, { rows, rowY: rows.map((r) => r.y), pos, cols, x0, tile, total: y + GAP });
    el.inner.style.height = `${y + GAP}px`;
    const msg = g.flat.length ? '' : emptyMessage();
    el.empty.hidden = !!g.flat.length;
    el.empty.innerHTML = g.flat.length ? '' : msg == null
      ? `<div class="spinner"></div><p>${state.mode === 'browse' ? 'Loading 16,000+ Fortnite cosmetics...' : 'Loading the Item Shop...'}</p>`
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
    if (state.mode === 'browse') showCosmetic(it); else showOffer(it);
    if (open) document.body.classList.add('detail-open');
    if (!fromRoute) setHash(state.mode === 'browse' ? `item/${it.id}` : `shop/${it.offerId}`);
  }

  function ensureVisible(i) {
    const [, y] = state.layout.pos[i];
    const th = state.layout.tile + TEXT_H;
    const top = el.wrap.scrollTop, h = el.wrap.clientHeight;
    if (y - GAP < top) el.wrap.scrollTop = Math.max(0, y - GAP - (state.mode === 'shop' ? HEADER_H : 0));
    else if (y + th + GAP > top + h) el.wrap.scrollTop = y + th + GAP - h;
    render();
  }

  el.inner.addEventListener('click', (e) => {
    const t = e.target.closest('.tile');
    if (t) select(Number(t.dataset.i), { scroll: false });
  });
  el.inner.addEventListener('dblclick', (e) => {
    const t = e.target.closest('.tile');
    if (!t) return;
    const it = state.grid[state.mode].flat[Number(t.dataset.i)];
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
  });
  $('#detailClose').addEventListener('click', () => document.body.classList.remove('detail-open'));

  // ------------------------------------------------------------------ navigation
  function setMode(mode, { keepHash = false } = {}) {
    if (mode === state.mode) return;
    if (state.mode) state.grid[state.mode].scroll = el.wrap.scrollTop;
    state.mode = mode;
    document.querySelectorAll('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
    el.search.value = state.search[mode];
    el.search.placeholder = mode === 'browse' ? 'Search cosmetics, sets, IDs...' : 'Search the Item Shop...';
    el.browseTools.style.display = mode === 'browse' ? '' : 'none';
    buildSidebar();
    layout();
    el.wrap.scrollTop = state.grid[mode].scroll;
    render();
    const g = state.grid[mode];
    if (g.selected != null && g.flat[g.selected]) {
      const it = g.flat[g.selected];
      if (mode === 'browse') showCosmetic(it); else showOffer(it);
    } else showAbout();
    if (!keepHash) setHash(mode === 'shop' ? 'shop' : '');
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

  // hash routes: #item/<id>, #shop, #shop/<offerId>
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
    if (inField && e.key !== 'ArrowDown') return;
    const g = state.grid[state.mode];
    if (!g.flat.length) return;
    const cur = g.selected ?? -1;
    const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -state.layout.cols, ArrowDown: state.layout.cols };
    if (e.key in moves) {
      e.preventDefault();
      if (inField) el.wrap.focus();
      select(cur < 0 ? 0 : cur + moves[e.key], { open: false });
    } else if (e.key === 'Enter' && cur >= 0) {
      const it = g.flat[cur];
      window.open(state.mode === 'browse' ? it.featured || it.icon : it.image, '_blank', 'noopener');
    }
  });

  // ------------------------------------------------------------------ boot
  state.mode = null;
  setMode(location.hash.startsWith('#shop') ? 'shop' : 'browse', { keepHash: true });
  loadCosmetics();
  loadShop();

  // exposed for tests
  window.__fcb = { md5, webSlug, epicItemUrl, state };
})();
