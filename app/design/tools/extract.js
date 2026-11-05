(function () {
  try {
    document.body.classList.add('ov'); buildOverview();
    document.getElementById('ovboard').style.zoom = 1;
    const px = v => parseFloat(v) || 0;
    const col = v => { const m = /rgba?\(([^)]+)\)/.exec(v); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); const a = p.length > 3 ? p[3] : 1; if (a === 0) return null; const h = n => Math.round(n).toString(16).padStart(2, '0'); return { hex: '#' + h(p[0]) + h(p[1]) + h(p[2]), a }; };
    const WS = { 100: 'Thin', 200: 'ExtraLight', 300: 'Light', 400: 'Regular', 500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold', 900: 'Black' };
    const MAIN = { 'flex-start': 'min', start: 'min', center: 'center', 'flex-end': 'max', end: 'max', 'space-between': 'spaceBetween', 'space-around': 'spaceAround', 'space-evenly': 'spaceEvenly' };
    const CROSS = { 'flex-start': 'min', start: 'min', center: 'center', 'flex-end': 'max', end: 'max', baseline: 'baseline', stretch: 'min', normal: 'min' };
    let count = 0;
    function textOf(node, o, cs, rect) {
      const f = col(cs.color) || { hex: '#ffffff', a: 1 };
      let t = node.textContent.replace(/\s+/g, ' ').trim();
      if (cs.textTransform === 'uppercase') t = t.toUpperCase();
      return { k: 'text', name: t.slice(0, 24), text: t, x: rect.left - o.x, y: rect.top - o.y, w: rect.width, h: rect.height,
        fs: px(cs.fontSize), fw: WS[Math.round(px(cs.fontWeight) / 100) * 100] || 'Regular', color: f.hex, a: f.a,
        ls: cs.letterSpacing === 'normal' ? 0 : px(cs.letterSpacing), lh: cs.lineHeight === 'normal' ? null : px(cs.lineHeight),
        ta: cs.textAlign === 'end' || cs.textAlign === 'right' ? 'right' : cs.textAlign === 'center' ? 'center' : 'left',
        tnum: /tabular/.test(cs.fontVariantNumeric) };
    }
    function walk(el, o) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || el.hidden) return null;
      const r = el.getBoundingClientRect();
      if (r.width < 0.5 || r.height < 0.5) return null;
      if (el.tagName.toLowerCase() === 'svg') {
        const c = col(cs.color) || { hex: '#ffffff', a: 1 };
        return { k: 'icon', name: 'icon/' + (el.dataset.icon || 'svg'), icon: el.dataset.icon || null, x: r.left - o.x, y: r.top - o.y, w: r.width, h: r.height, color: c.hex };
      }
      count++;
      const n = { k: 'frame', name: (el.className && typeof el.className === 'string' ? el.className.split(' ')[0] : el.tagName.toLowerCase()) || 'box', x: r.left - o.x, y: r.top - o.y, w: r.width, h: r.height, kids: [] };
      const bg = col(cs.backgroundColor); if (bg) { n.fill = bg.hex; n.fa = bg.a; }
      const bw = px(cs.borderTopWidth), bc = col(cs.borderTopColor);
      if (bw > 0 && bc && cs.borderTopStyle !== 'none') { n.stroke = bc.hex; n.sw = bw; }
      n.radius = Math.min(px(cs.borderTopLeftRadius), Math.min(r.width, r.height) / 2);
      const op = parseFloat(cs.opacity); if (op < 1) n.opacity = op;
      if (cs.overflow !== 'visible' || cs.overflowX !== 'visible') n.clip = true;
      if (/flex/.test(cs.display)) {
        n.layout = cs.flexDirection.startsWith('column') ? 'vertical' : 'horizontal';
        n.gap = n.layout === 'horizontal' ? px(cs.columnGap) : px(cs.rowGap);
        n.pad = [px(cs.paddingTop), px(cs.paddingRight), px(cs.paddingBottom), px(cs.paddingLeft)];
        n.main = MAIN[cs.justifyContent] || 'min'; n.cross = CROSS[cs.alignItems] || 'min'; n.wrap = cs.flexWrap === 'wrap';
      }
      const kids = [...el.childNodes];
      const hasEl = kids.some(k => k.nodeType === 1);
      if (!hasEl) {
        const t = el.textContent.replace(/\s+/g, ' ').trim();
        if (t) { const rg = document.createRange(); rg.selectNodeContents(el); const rr = rg.getBoundingClientRect(); n.kids.push(textOf(el, o, cs, rr.width ? rr : r)); }
        else if (el.tagName === 'INPUT' && (el.value || el.placeholder)) { n.kids.push(textOf({ textContent: el.value || el.placeholder }, o, cs, r)); }
      } else {
        for (const k of kids) {
          if (k.nodeType === 1) { const c = walk(k, o); if (c) n.kids.push(c); }
          else if (k.nodeType === 3 && k.textContent.trim()) {
            const rg = document.createRange(); rg.selectNodeContents(k); const rr = rg.getBoundingClientRect();
            if (rr.width > 0) n.kids.push(textOf(k, o, cs, rr));
          }
        }
      }
      if (n.layout) { // child sizing inside auto layout: grow = fill
        kids.forEach(k => { if (k.nodeType === 1) { const kc = getComputedStyle(k); if (px(kc.flexGrow) > 0) { const c = n.kids.find(x => x.__el === k); } } });
      }
      return n;
    }
    const out = [];
    document.querySelectorAll('#ovboard figure.fr').forEach(fig => {
      const name = fig.querySelector('.fr-n').textContent.trim();
      const group = fig.closest('.ov-g').querySelector('.ov-gh').textContent.trim();
      const dev = [...fig.children].find(c => !c.classList.contains('fr-n') && !c.classList.contains('fr-flow'));
      if (!dev) return;
      const r = dev.getBoundingClientRect();
      const tree = walk(dev, { x: r.left, y: r.top });
      out.push({ group, name, w: r.width, h: r.height, tree });
    });
    const pre = document.createElement('pre'); pre.id = '__out'; pre.textContent = JSON.stringify({ frames: out, nodes: count }); document.body.appendChild(pre);
  } catch (e) { const pre = document.createElement('pre'); pre.id = '__err'; pre.textContent = String(e && e.stack || e); document.body.appendChild(pre); }
})();
