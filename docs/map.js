/*!
 * Fortnite Cosmetics Browser - interactive map engine (no dependencies)
 * (c) 248Tech - MIT License. Map tiles, icons and marker data: Fortnite.GG.
 *
 * World coordinates are 0..256 on both axes (x right, y down), matching data/map.json.
 * At zoom z one world unit is 2^z CSS pixels; Fortnite.GG serves 256 px tiles for z = 3..8.
 */
(() => {
  'use strict';

  const CLUSTER_CELL = 46;       // px; markers of one layer closer than this merge into a counted cluster
  const CLUSTER_UNTIL = 5.2;     // zoom from which clustering stops
  const HIT_PAD = 4;

  class FcbMap {
    constructor(host, { onSelect, onView, onHover } = {}) {
      this.host = host;
      this.canvas = document.createElement('canvas');
      this.canvas.className = 'map-canvas';
      this.canvas.tabIndex = 0;
      this.canvas.setAttribute('aria-label', 'Interactive Fortnite map');
      host.prepend(this.canvas);
      this.ctx = this.canvas.getContext('2d');
      this.onSelect = onSelect || (() => {});
      this.onView = onView || (() => {});
      this.onHover = onHover || (() => {});
      this.data = null;
      this.enabled = new Set();
      this.view = { x: 128, y: 128, z: 2 };
      this.tiles = new Map();
      this.icons = new Map();
      this.hits = [];
      this.selected = null;
      this.hover = null;
      this.raf = 0;
      this.ptrs = new Map();
      this._bind();
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(host);
    }

    // ------------------------------------------------------------- data / layers
    setData(data) {
      this.data = data;
      this.layers = new Map();
      for (const g of data.groups) for (const l of g.layers) this.layers.set(l.id, Object.assign(l, { group: g }));
      this.resize();
      this.fit();
    }

    setEnabled(ids) { this.enabled = new Set(ids); this.draw(); }

    bounds() {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      const add = ([x, y]) => { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; };
      for (const l of this.layers.values()) {
        if (l.kind === 'markers') l.markers.forEach((m) => m.pts.forEach(add));
        else if (l.kind === 'labels') l.labels.forEach((b) => add(b.pt));
      }
      if (!isFinite(x0)) return [0, 0, 256, 256];
      const pad = 10;
      return [Math.max(0, x0 - pad), Math.max(0, y0 - pad), Math.min(256, x1 + pad), Math.min(256, y1 + pad)];
    }

    fit() {
      if (!this.data || !this.w) return;
      const [x0, y0, x1, y1] = this.bounds();
      const z = Math.log2(Math.min(this.w / (x1 - x0), this.h / (y1 - y0)));
      this.minZ = Math.max(0.5, z - 0.6);
      this.setView((x0 + x1) / 2, (y0 + y1) / 2, z);
    }

    // ------------------------------------------------------------- view
    resize() {
      const r = this.host.getBoundingClientRect();
      if (!r.width || !r.height) return;
      this.dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.w = r.width; this.h = r.height;
      this.canvas.width = Math.round(r.width * this.dpr);
      this.canvas.height = Math.round(r.height * this.dpr);
      this.canvas.style.width = `${r.width}px`;
      this.canvas.style.height = `${r.height}px`;
      if (this.data && this.minZ == null) this.fit();
      this.draw();
    }

    setView(x, y, z) {
      z = Math.max(this.minZ ?? 0.5, Math.min(7.5, z));
      this.view = { x: Math.max(0, Math.min(256, x)), y: Math.max(0, Math.min(256, y)), z };
      this.draw();
      clearTimeout(this._viewT);
      this._viewT = setTimeout(() => this.onView(this.view), 350);
    }

    scale() { return 2 ** this.view.z; }
    toScreen(x, y) { const s = this.scale(); return [(x - this.view.x) * s + this.w / 2, (y - this.view.y) * s + this.h / 2]; }
    toWorld(sx, sy) { const s = this.scale(); return [(sx - this.w / 2) / s + this.view.x, (sy - this.h / 2) / s + this.view.y]; }

    zoomAt(sx, sy, dz) {
      const [wx, wy] = this.toWorld(sx, sy);
      const z = Math.max(this.minZ ?? 0.5, Math.min(7.5, this.view.z + dz));
      const s = 2 ** z;
      this.setView(wx - (sx - this.w / 2) / s, wy - (sy - this.h / 2) / s, z);
    }
    zoomBy(dz) { this.zoomAt(this.w / 2, this.h / 2, dz); }
    pan(dx, dy) { const s = this.scale(); this.setView(this.view.x - dx / s, this.view.y - dy / s, this.view.z); }

    flyTo(pt, z) {
      const from = { ...this.view }, to = { x: pt[0], y: pt[1], z: z ?? Math.max(this.view.z, 4.5) };
      const t0 = performance.now(), dur = 420;
      const step = (t) => {
        const k = Math.min(1, (t - t0) / dur), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
        this.setView(from.x + (to.x - from.x) * e, from.y + (to.y - from.y) * e, from.z + (to.z - from.z) * e);
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }

    // ------------------------------------------------------------- images
    tile(z, x, y) {
      const k = `${z}/${x}/${y}`;
      let t = this.tiles.get(k);
      if (!t) {
        t = new Image();
        t.decoding = 'async';
        t.referrerPolicy = 'no-referrer';
        t.onload = () => { t.ok = true; this.draw(); };
        t.onerror = () => { t.bad = true; };
        t.src = this.data.tiles.replace('{z}', z).replace('{x}', x).replace('{y}', y);
        this.tiles.set(k, t);
        if (this.tiles.size > 600) { // drop the oldest
          const first = this.tiles.keys().next().value;
          this.tiles.delete(first);
        }
      }
      return t;
    }

    icon(id) {
      if (id == null) return null;
      let im = this.icons.get(id);
      if (!im) {
        im = new Image();
        im.referrerPolicy = 'no-referrer';
        im.onload = () => { im.ok = true; this.draw(); };
        im.src = `${this.data.iconBase}${id}.png`;
        this.icons.set(id, im);
      }
      return im.ok ? im : null;
    }

    // ------------------------------------------------------------- drawing
    draw() { if (!this.raf) this.raf = requestAnimationFrame(() => { this.raf = 0; this._draw(); }); }

    _draw() {
      const { ctx, data } = this;
      if (!data || !this.w) return;
      ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      ctx.fillStyle = '#0f3b57';
      ctx.fillRect(0, 0, this.w, this.h);
      this._drawTiles();
      this.hits = [];
      const z = this.view.z;
      // order: lines, tunnels, markers, labels on top
      const on = [...this.layers.values()].filter((l) => this.enabled.has(l.id));
      on.filter((l) => l.kind === 'lines').forEach((l) => this._drawLines(l));
      on.filter((l) => l.kind === 'tunnels').forEach((l) => this._drawTunnels(l));
      on.filter((l) => l.kind === 'markers').forEach((l) => this._drawMarkers(l, z));
      on.filter((l) => l.kind === 'labels').forEach((l) => this._drawLabels(l, z));
      if (this.selected && !this.selected.label) {
        const [sx, sy] = this.toScreen(...this.selected.pt);
        ctx.beginPath(); ctx.arc(sx, sy, 17, 0, Math.PI * 2);
        ctx.lineWidth = 3; ctx.strokeStyle = '#fce51e'; ctx.stroke();
      }
    }

    _drawTiles() {
      const { ctx, data } = this;
      const zt = Math.max(data.tileMinZoom, Math.min(data.tileMaxZoom, Math.round(this.view.z + Math.log2(this.dpr))));
      const n = 2 ** zt, unit = data.worldSize / n, s = this.scale();
      const [wx0, wy0] = this.toWorld(0, 0), [wx1, wy1] = this.toWorld(this.w, this.h);
      const tx0 = Math.max(0, Math.floor(wx0 / unit)), ty0 = Math.max(0, Math.floor(wy0 / unit));
      const tx1 = Math.min(n - 1, Math.floor(wx1 / unit)), ty1 = Math.min(n - 1, Math.floor(wy1 / unit));
      ctx.imageSmoothingEnabled = true;
      for (let ty = ty0; ty <= ty1; ty++) {
        for (let tx = tx0; tx <= tx1; tx++) {
          const [sx, sy] = this.toScreen(tx * unit, ty * unit);
          const size = unit * s;
          const t = this.tile(zt, tx, ty);
          if (t.ok) { ctx.drawImage(t, sx, sy, size + 0.5, size + 0.5); continue; }
          // parent tile as a placeholder while this one loads
          for (let pz = zt - 1; pz >= data.tileMinZoom; pz--) {
            const f = 2 ** (zt - pz), p = this.tiles.get(`${pz}/${Math.floor(tx / f)}/${Math.floor(ty / f)}`);
            if (p && p.ok) {
              const sub = 256 / f;
              ctx.drawImage(p, (tx % f) * sub, (ty % f) * sub, sub, sub, sx, sy, size + 0.5, size + 0.5);
              break;
            }
          }
        }
      }
    }

    _visible(sx, sy, m = 30) { return sx > -m && sy > -m && sx < this.w + m && sy < this.h + m; }

    _drawMarkers(l, z) {
      const { ctx } = this;
      const base = z < 3.5 ? 20 : z < 5 ? 24 : 30;
      const cluster = l.cluster && z < CLUSTER_UNTIL;
      for (const m of l.markers) {
        const im = this.icon(m.icon ?? l.icon);
        const size = base * ((m.size || 40) / 40);
        const cells = new Map();
        for (const pt of m.pts) {
          const [sx, sy] = this.toScreen(pt[0], pt[1]);
          if (!this._visible(sx, sy)) continue;
          if (cluster) {
            const k = `${Math.floor(sx / CLUSTER_CELL)},${Math.floor(sy / CLUSTER_CELL)}`;
            const c = cells.get(k);
            if (c) { c.n++; c.x += pt[0]; c.y += pt[1]; } else cells.set(k, { n: 1, x: pt[0], y: pt[1], pt });
          } else this._marker(im, sx, sy, size, { layer: l, pt, icon: m.icon ?? l.icon });
        }
        for (const c of cells.values()) {
          const pt = c.n > 1 ? [c.x / c.n, c.y / c.n] : c.pt;
          const [sx, sy] = this.toScreen(pt[0], pt[1]);
          this._marker(im, sx, sy, size, { layer: l, pt, icon: m.icon ?? l.icon, count: c.n > 1 ? c.n : 0 });
          if (c.n > 1) {
            const label = String(c.n);
            ctx.font = '700 10px Bahnschrift, "Segoe UI", system-ui, sans-serif';
            const w = Math.max(16, ctx.measureText(label).width + 8);
            const bx = sx + size / 2 - 4, by = sy - size / 2 - 2;
            ctx.fillStyle = '#fce51e';
            ctx.beginPath(); ctx.roundRect(bx - w / 2, by - 8, w, 16, 8); ctx.fill();
            ctx.fillStyle = '#111'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(label, bx, by + 0.5);
          }
        }
      }
    }

    _marker(im, sx, sy, size, hit) {
      const { ctx } = this;
      if (im) ctx.drawImage(im, sx - size / 2, sy - size / 2, size, size);
      else { ctx.fillStyle = '#fce51e'; ctx.beginPath(); ctx.arc(sx, sy, 5, 0, Math.PI * 2); ctx.fill(); }
      if (this.hover && this.hover.layer === hit.layer && this.hover.pt === hit.pt) {
        ctx.lineWidth = 2; ctx.strokeStyle = '#fff'; ctx.beginPath(); ctx.arc(sx, sy, size / 2 + 3, 0, Math.PI * 2); ctx.stroke();
      }
      this.hits.push({ ...hit, sx, sy, r: size / 2 + HIT_PAD });
    }

    _drawLines(l) {
      const { ctx } = this;
      const col = l.color || '#ffcc7b';
      for (const [a, b] of l.lines) {
        const [ax, ay] = this.toScreen(...a), [bx, by] = this.toScreen(...b);
        if (!this._visible(ax, ay, 200) && !this._visible(bx, by, 200)) continue;
        ctx.lineCap = 'round';
        ctx.strokeStyle = col; ctx.lineWidth = 7; ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
        ctx.strokeStyle = '#222'; ctx.lineWidth = 3; ctx.stroke();
        for (const [x, y, pt] of [[ax, ay, a], [bx, by, b]]) {
          ctx.fillStyle = '#222'; ctx.strokeStyle = col; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
          this.hits.push({ layer: l, pt, icon: l.icon, sx: x, sy: y, r: 9 });
        }
      }
    }

    _drawTunnels(l) {
      const { ctx } = this;
      for (const t of l.tunnels) {
        const col = t.color || '#7fd1ff';
        const im = this.icon(t.icon ?? l.icon);
        for (const [a, b] of t.pairs) {
          const [ax, ay] = this.toScreen(...a), [bx, by] = this.toScreen(...b);
          if (!this._visible(ax, ay, 200) && !this._visible(bx, by, 200)) continue;
          ctx.setLineDash([6, 5]); ctx.strokeStyle = col; ctx.lineWidth = 2.5;
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); ctx.setLineDash([]);
          this._marker(im, ax, ay, 24, { layer: l, pt: a, icon: t.icon ?? l.icon, to: b });
        }
      }
    }

    _drawLabels(l, z) {
      const { ctx } = this;
      const major = l.id === 'poi';
      if (!major && z < 3.4) return;
      const px = major ? Math.round(Math.max(11, Math.min(18, 7 + z * 2.2))) : Math.round(Math.max(9, Math.min(13, 4 + z * 1.6)));
      ctx.font = `${major ? 700 : 600} ${px}px Bahnschrift, "Segoe UI", system-ui, sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
      for (const b of l.labels) {
        const [sx, sy] = this.toScreen(...b.pt);
        if (!this._visible(sx, sy, 120)) continue;
        const txt = major ? b.name.toUpperCase() : b.name;
        ctx.lineWidth = major ? 4 : 3; ctx.strokeStyle = 'rgba(0,0,0,.85)'; ctx.strokeText(txt, sx, sy);
        ctx.fillStyle = major ? '#fff' : '#e6e6e6'; ctx.fillText(txt, sx, sy);
        const w = ctx.measureText(txt).width;
        this.hits.push({ layer: l, pt: b.pt, name: b.name, sx, sy, r: Math.max(10, w / 2), label: true });
      }
    }

    // ------------------------------------------------------------- hit testing
    hitAt(sx, sy) {
      for (let i = this.hits.length - 1; i >= 0; i--) {
        const h = this.hits[i];
        if (h.label ? Math.abs(sx - h.sx) <= h.r && Math.abs(sy - h.sy) <= 10 : (sx - h.sx) ** 2 + (sy - h.sy) ** 2 <= h.r ** 2) return h;
      }
      return null;
    }

    select(hit) { this.selected = hit; this.draw(); }

    // ------------------------------------------------------------- input
    _bind() {
      const c = this.canvas;
      const pos = (e) => { const r = c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
      c.addEventListener('wheel', (e) => {
        e.preventDefault();
        const [x, y] = pos(e);
        const dy = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY;
        this.zoomAt(x, y, -dy / 320);
      }, { passive: false });
      c.addEventListener('pointerdown', (e) => {
        c.setPointerCapture(e.pointerId);
        this.ptrs.set(e.pointerId, pos(e));
        this.drag = { start: pos(e), moved: false, view: { ...this.view } };
        if (this.ptrs.size === 2) {
          const [a, b] = [...this.ptrs.values()];
          this.pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), z: this.view.z };
        }
      });
      c.addEventListener('pointermove', (e) => {
        const p = pos(e);
        if (this.ptrs.has(e.pointerId)) {
          const prev = this.ptrs.get(e.pointerId);
          this.ptrs.set(e.pointerId, p);
          if (this.ptrs.size === 2 && this.pinch) {
            const [a, b] = [...this.ptrs.values()];
            const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
            this.zoomAt((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, this.pinch.z + Math.log2(d / this.pinch.d) - this.view.z);
            this.drag.moved = true;
            return;
          }
          if (this.drag && (this.drag.moved || Math.hypot(p[0] - this.drag.start[0], p[1] - this.drag.start[1]) > 4)) {
            this.drag.moved = true;
            c.style.cursor = 'grabbing';
            this.pan(p[0] - prev[0], p[1] - prev[1]);
          }
          return;
        }
        const h = this.hitAt(...p);
        if ((h && h.pt) !== (this.hover && this.hover.pt)) {
          this.hover = h; this.draw();
          c.style.cursor = h ? 'pointer' : 'grab';
          this.onHover(h, p);
        } else if (h) this.onHover(h, p);
      });
      const up = (e) => {
        const was = this.ptrs.has(e.pointerId);
        this.ptrs.delete(e.pointerId);
        if (this.ptrs.size < 2) this.pinch = null;
        c.style.cursor = 'grab';
        if (!was || !this.drag || this.drag.moved || e.type === 'pointercancel') { if (!this.ptrs.size) this.drag = null; return; }
        const h = this.hitAt(...pos(e));
        this.drag = null;
        if (h && h.count) { this.flyTo(h.pt, Math.min(7.5, this.view.z + 1.5)); return; }
        this.selected = h && !h.count ? h : null;
        this.draw();
        this.onSelect(this.selected);
      };
      c.addEventListener('pointerup', up);
      c.addEventListener('pointercancel', up);
      c.addEventListener('pointerleave', () => { if (this.hover) { this.hover = null; this.draw(); this.onHover(null); } });
      c.addEventListener('dblclick', (e) => { const [x, y] = pos(e); this.zoomAt(x, y, 1); });
      c.addEventListener('keydown', (e) => {
        const k = e.key, step = 80;
        if (k === '+' || k === '=') this.zoomBy(0.5);
        else if (k === '-' || k === '_') this.zoomBy(-0.5);
        else if (k === 'ArrowLeft') this.pan(step, 0);
        else if (k === 'ArrowRight') this.pan(-step, 0);
        else if (k === 'ArrowUp') this.pan(0, step);
        else if (k === 'ArrowDown') this.pan(0, -step);
        else if (k === '0') this.fit();
        else return;
        e.preventDefault();
        e.stopPropagation();
      });
      c.style.cursor = 'grab';
      c.style.touchAction = 'none';
    }
  }

  window.FcbMap = FcbMap;
})();
