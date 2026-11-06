'use strict';

const state = {
  cats: [],
  sorts: [],
  cat: null,
  catZh: '',
  catRu: '',
  sort: 'new',
  page: 1,
  depth: 4,
  filters: {},      // key -> [values]
  ranges: {},       // currency_price -> "min;max"
  filterSchema: [],
  attrs: {},
  selected: new Map(),
  showFull: true,
  detailMap: new Map(),
  df: {},        // 详情列筛选
  rows: [],         // 原始抓取结果
  view: [],         // 本地过滤/排序后的视图
  localSort: 'default',
  localDays: 0,
  localMinRev: 0,
  loading: false,
};

const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (s) => String(s ?? '');
const fmtNum = (n) => (n == null || n === '' ? '-' : Number(n).toLocaleString('ru-RU'));

async function api(path) {
  const r = await fetch(path, { cache: 'no-store' });
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}

function setStat(txt) { $('#stat').textContent = txt || ''; }
function setBusy(b) {
  state.loading = b;
  document.body.style.cursor = b ? 'progress' : '';
}

// ---------------------------------------------------------------- 类目树（Seller API 全量）
async function initCategories() {
  const data = await api('/api/categories');
  state.sorts = data.sorts;
  state.cats = data.items;              // 35 个一级类目的兜底映射（slug/zh/ru）
  renderSorts();

  $('#mktCompile') && ($('#mktCompile').textContent = '');
  let tree = { tree: [] };
  try { tree = await api('/api/tree'); } catch (e) { /* 无树时兜底 */ }

  if (tree.tree && tree.tree.length) {
    state.tree = tree.tree;
    renderTreeFromApi(tree.tree);
    $('#treeMeta').textContent = `${tree.tree.length} 个一级 · ${tree.total} 个节点 · 已映射 ${tree.mapped || 0}`;
    // 默认把第一个一级类目的第一个二级也展开，直接露出三级类型
    setTimeout(() => {
      const first = document.querySelector('#catTree .cat-children.open > .cat-group > .cat-item > .caret.has');
      if (first) first.click();
    }, 300);
  } else {
    renderTreeFallback(data.items);
    $('#treeMeta').textContent = '35 个一级类目（网页口径）';
  }

  $('#catSearch').addEventListener('input', (e) => filterTree(e.target.value.trim().toLowerCase()));

  const first = state.tree && state.tree[0];
  if (first) {
    openNode(first, true);
  } else if (state.cats.length) {
    const c = state.cats[0];
    selectCat(c.slug, c.zh, c.ru);
  }
}

function renderTreeFromApi(tree) {
  const nav = $('#catTree');
  nav.innerHTML = '';
  tree.forEach((node) => {
    nav.appendChild(catNodeEl(node, 0, [node]));
  });
}

function catNodeEl(node, depth, path) {
  const wrap = el('div', 'cat-group');
  const item = el('div', 'cat-item');
  item.dataset.depth = depth;
  item.dataset.title = (node.zh || node.n || '');
  item.dataset.ru = node.n || '';
  if (node.slug) item.dataset.slug = node.slug;

  const hasKids = node.c && node.c.length;
  const zh = node.zh || node.n;
  const ru = node.zh ? node.n : '';
  const tag = node.type ? '<span class="tleaf">类型</span>' : '';
  const inherited = !node.slug && (path || []).slice(0, -1).some((a) => a && a.slug);
  const dot = node.slug
    ? '<span class="dot ok" title="已映射前台类目"></span>'
    : (inherited
        ? '<span class="dot inh" title="无独立类目页，点击会用上级类目"></span>'
        : '<span class="dot" title="点击时解析"></span>');
  const zhTxt = node.zh || node.n;
  const ruTxt = node.zh ? node.n : '';
  const cnt = hasKids ? `<span class="tcnt">${node.c.length}</span>` : '';
  item.innerHTML =
    `<input type="checkbox" class="cbox">` +
    `<span class="caret${hasKids ? ' has' : ''}">${hasKids ? '▶' : ''}</span>` +
    `<span class="t" style="padding-left:${depth * 4}px">${dot}<span class="zh">${esc(zhTxt)}</span>${tag}${cnt}` +
    `<span class="ru" data-ru="${esc(node.n)}">${ruTxt ? esc(ruTxt) : ''}</span></span>`;

  const box = item.querySelector('.cbox');
  box.checked = state.selected.has(keyOf(node));
  box.onclick = (e) => {
    e.stopPropagation();
    toggleSelect(node, box.checked);
  };

  const kids = el('div', 'cat-children');
  item.onclick = (e) => {
    if (e.target === box) return;
    if (e.target.classList.contains('caret') && hasKids) {
      e.stopPropagation();
      expandNode();
      return;
    }
    // 点类目名：选中并加载商品；有子节点就顺带展开，不用再去点小三角
    if (hasKids && !kids.classList.contains('open')) expandNode();
    openNode(node, false, path);
  };

  function expandNode() {
    if (!kids.dataset.loaded) {
      node.c.forEach((k) => kids.appendChild(catNodeEl(k, depth + 1, [...path, k])));
      kids.dataset.loaded = '1';
    }
    kids.classList.toggle('open');
    item.querySelector('.caret').classList.toggle('open');
  }

  wrap.append(item, kids);
  if (depth === 0 && hasKids) {
    setTimeout(scheduleTreeZh, 600);
    node.c.forEach((k) => kids.appendChild(catNodeEl(k, 1, [...path, k])));
    kids.dataset.loaded = '1';
    kids.classList.add('open');    item.querySelector('.caret').classList.add('open');
  }
  return wrap;
}

// ---------- 多选 ----------
const keyOf = (node) => node.slug || ('n:' + node.n);

function toggleSelect(node, on) {
  const k = keyOf(node);
  if (on) {
    if (state.selected.size >= 10) { setStat('最多选 10 个类目'); syncCheckbox(); return; }
    state.selected.set(k, { zh: node.zh || node.n, ru: node.zh ? node.n : '', node });
  } else {
    state.selected.delete(k);
  }
  // 子节点跟随
  (function cascade(n, val) {
    (n.c || []).forEach((c) => {
      const ck = keyOf(c);
      if (val) { if (state.selected.size < 10) state.selected.set(ck, { zh: c.zh || c.n, ru: c.zh ? c.n : '', node: c }); }
      else state.selected.delete(ck);
      cascade(c, val);
    });
  })(node, on);

  syncCheckbox();
  updateSelBar();
}

function syncCheckbox() {
  document.querySelectorAll('.cat-item').forEach((it) => {
    const box = it.querySelector('.cbox');
    if (!box) return;
    const slug = it.dataset.slug;
    const ru = it.dataset.ru;
    const on = slug ? state.selected.has(slug) : state.selected.has('n:' + ru);
    box.checked = on;
  });
}

function updateSelBar() {
  const n = state.selected.size;
  const el2 = $('#selCount');
  if (el2) el2.textContent = n;
  if (n) setStat(`已选 ${n} 个类目`);
}

function clearSelection() {
  state.selected.clear();
  syncCheckbox();
  updateSelBar();
  setStat('');
}

async function openNode(node, silent, path) {
  const zh = node.zh || node.n || '';
  const ru = node.zh ? (node.n || '') : '';
  let slug = node.slug;

  if (!slug) {
    if (!silent) setStat('解析 web 类目…');
    try {
      const r = await api('/api/resolve?name=' + encodeURIComponent(node.n));
      slug = r.slug;
      if (slug) node.slug = slug;
    } catch (e) { slug = null; }
  }

  // 兜底：这个类型在前台没有独立类目页 → 用最近的、已映射的上级类目
  let fallenBack = null;
  if (!slug) {
    const chain = (path || [node]).slice(0, -1).reverse();
    for (const anc of chain) {
      let s = anc.slug;
      if (!s) {
        try {
          const r2 = await api('/api/resolve?name=' + encodeURIComponent(anc.n) + '&online=0');
          s = r2.slug;
          if (s) anc.slug = s;
        } catch (e) { s = null; }
      }
      if (s) { slug = s; fallenBack = anc; break; }
    }
  }

  if (!slug) {
    if (!silent) setStat(`「${node.n}」及其上级在前台都没有对应类目页`);
    return;
  }

  const crumb = (path || [node]).map((x) => x.zh || x.n).join(' › ');
  state.pathZh = crumb;
  if (fallenBack) {
    setStat(`「${node.zh || node.n}」无独立类目页，已打开上级「${fallenBack.zh || fallenBack.n}」`);
    selectCat(slug, fallenBack.zh || fallenBack.n, fallenBack.n);
    return;
  }
  selectCat(slug, zh, ru);
}

function renderTreeFallback(items) {
  const nav = $('#catTree');
  nav.innerHTML = '';
  items.forEach((c) => {
    const group = el('div', 'cat-group');
    const item = el('div', 'cat-item');
    item.dataset.title = c.zh;
    item.dataset.ru = c.ru;
    item.dataset.slug = c.slug;
    item.innerHTML = `<span class="caret">▶</span><span class="t">${esc(c.zh)}<span class="ru">${esc(c.ru)}</span></span>`;
    item.onclick = () => selectCat(c.slug, c.zh, c.ru);
    item.querySelector('.caret').onclick = (e) => { e.stopPropagation(); lazyChildren(group, c, item); };
    group.append(item, el('div', 'cat-children'));
    nav.appendChild(group);
  });
}

async function lazyChildren(group, c, item) {
  const kids = group.querySelector('.cat-children');
  const caret = item.querySelector('.caret');
  if (kids.dataset.loaded === '1') {
    kids.classList.toggle('open');
    caret.classList.toggle('open');
    return;
  }
  caret.classList.add('open');
  kids.classList.add('open');
  try {
    const data = await api('/api/filters?cat=' + encodeURIComponent(c.slug) + '&sort=' + state.sort);
    const sub = (data.filters || []).find((f) => f.type === 'subcat');
    kids.innerHTML = '';
    (sub ? sub.values : []).forEach((v) => {
      const k = el('div', 'cat-item child');
      k.dataset.title = v.zh;
      k.dataset.ru = v.title;
      k.innerHTML = `<span class="t">${esc(v.zh)}<span class="ru">${esc(v.title)}</span></span>`;
      k.onclick = (e) => { e.stopPropagation(); selectCat(v.slug, v.zh, v.title); };
      kids.appendChild(k);
    });
    kids.dataset.loaded = '1';
  } catch (err) { kids.innerHTML = ''; }
}

function filterTree(kw) {
  document.querySelectorAll('.cat-group').forEach((g) => {
    // 只过滤顶层容器
  });
  const nav = $('#catTree');
  [...nav.children].forEach((group) => {
    const item = group.querySelector('.cat-item');
    const hay = ((item.dataset.title || '') + ' ' + (item.dataset.ru || '')).toLowerCase();
    group.style.display = !kw || hay.includes(kw) ? '' : 'none';
  });
}

function renderSorts() {
  const seg = $('#sortSeg');
  seg.innerHTML = '';
  state.sorts.forEach((s) => {
    const b = el('button', s.key === state.sort ? 'on' : '', s.name);
    b.title = s.desc;
    b.onclick = () => {
      state.sort = s.key;
      state.page = 1;
      renderSorts();
      loadAll();
    };
    seg.appendChild(b);
  });
}

function markActive(slug) {
  document.querySelectorAll('.cat-item').forEach((n) => {
    n.classList.toggle('on', n.dataset.slug === slug);
  });
}

function selectCat(slug, zh, ru) {
  state.cat = slug;
  state.catZh = zh || slug;
  state.catRu = ru || '';
  state.page = 1;
  state.filters = {};
  state.ranges = {};
  document.querySelectorAll('.cat-item').forEach((n) => {
    if (n.dataset.slug === slug) n.classList.add('on');
  });
  loadAll();
}

// ---------------------------------------------------------------- 筛选面板
async function loadFilters() {
  const [f, a] = await Promise.all([
    api('/api/filters?cat=' + encodeURIComponent(state.cat) + '&sort=' + state.sort).catch((e) => ({ filters: [], src: 'blocked', error: String(e.message || e) })),
    api('/api/attrs?cat=' + encodeURIComponent(state.cat)).catch(() => ({ attrs: [] })),
  ]);
  state.filterSchema = f.filters || [];
  state.filterSrc = f.src || '';
  state.filterErr = f.error || '';
  state.attrs = a || { attrs: [] };
  renderFilters();
}

function renderFilters() {
  const srcTag = state.filterSrc === 'allFilters' ? '· 含类目属性' :
                 state.filterSrc === 'category' ? '· 侧边栏' : '';
  $('#filterCat').textContent = `${state.catZh} · ${state.catRu} ${srcTag}`;

  const fill = (sel, list, placeholder) => {
    const n = $(sel);
    if (!n) return;
    const cur = n.value;
    n.innerHTML = `<option value="">${esc(placeholder)}</option>` +
      list.map((v) => `<option value="${esc(v.key)}">${esc(v.zh || v.title)}</option>`).join('');
    if (cur) n.value = cur;
  };
  const fs = state.filterSchema || [];
  const pick = (k) => (fs.find((f) => f.key === k) || {}).values || [];
  fill('#fBrand', pick('brand'), '全部品牌');
  fill('#fShop', pick('seller'), '全部店铺');
  fill('#fColor', pick('color'), '全部颜色');
  fill('#fType', pick('type'), '全部类型');
  fill('#fDelivery', pick('delivery'), '不限');

  // 类目属性（Seller API）作为下拉槽位
  const host = $('#fAttrs');
  if (host) {
    const attrs = ((state.attrs || {}).attrs || []).filter((a) => a.dict && (a.values || []).length).slice(0, 3);
    host.innerHTML = attrs.map((a, i) =>
      `<select data-attr="${esc(a.id)}"><option value="">${esc(a.name)}（全部）</option>` +
      a.values.slice(0, 60).map((v) => `<option value="${esc(v.value)}">${esc(v.value)}</option>`).join('') +
      '</select>').join('');
  }
}
function group(zh, ru, open) {
  const root = el('div', 'fgroup');
  const head = el('div', 'fgroup-head' + (open ? ' open' : ''));
  head.innerHTML = `<span><span class="tt">${esc(zh)}</span>${ru ? `<span class="ru">${esc(ru)}</span>` : ''}</span><span class="caret">▶</span>`;
  const body = el('div', 'fgroup-body' + (open ? ' open' : ''));
  body.appendChild(el('div', 'chips'));
  head.onclick = () => { head.classList.toggle('open'); body.classList.toggle('open'); };
  root.append(head, body);
  return { root, body, head };
}

// ---------------------------------------------------------------- 中文补译（树）
let _zhTimer = null;
function scheduleTreeZh() {
  clearTimeout(_zhTimer);
  _zhTimer = setTimeout(patchTreeZh, 350);
}

async function patchTreeZh() {
  const nodes = [...document.querySelectorAll('#catTree .cat-item .t')].filter((t) => {
    const ru = t.querySelector('.ru');
    return ru && !ru.textContent.trim();     // 只有俄文、没有中文的
  }).slice(0, 60);
  if (!nodes.length) return;
  const texts = [...new Set(nodes.map((t) => t.querySelector('.ru').dataset.ru).filter(Boolean))];
  if (!texts.length) return;
  try {
    const d = await api('/api/zh?texts=' + encodeURIComponent(texts.join('|')));
    const map = d.results || {};
    nodes.forEach((t) => {
      const ru = t.querySelector('.ru');
      const zh = map[ru.dataset.ru];
      if (zh) {
        t.querySelector('.zh').textContent = zh;
        ru.textContent = ru.dataset.ru;
      }
    });
  } catch (e) { /* 忽略 */ }
}

// ---------------------------------------------------------------- 搜索
function buildFilterParam() {
  const out = {};
  const take = (sel, key) => {
    const n = document.querySelector(sel);
    if (n && n.value) out[key] = n.value;
  };
  take('#fBrand', 'brand');
  take('#fShop', 'seller');
  take('#fColor', 'color');
  take('#fType', 'type');
  take('#fDelivery', 'delivery');
  const pmin = Number((document.querySelector('#fPriceMin') || {}).value || 0);
  const pmax = Number((document.querySelector('#fPriceMax') || {}).value || 0);
  if (pmin || pmax) out.currency_price = (pmin || 1) + '.000;' + (pmax || 9999999) + '.000';
  return out;
}

/** 本地（详情列）条件 */
function buildLocalDf() {
  const df = Object.assign({}, state.df || {});
  const g = (sel) => { const n = document.querySelector(sel); return n ? String(n.value || '').trim() : ''; };
  const t = g('#fTitle'), s = g('#fSku'), sid = g('#fSellerId');
  if (t) df.title = t;
  if (s) df.sku = s;
  if (sid) df.seller_id = sid;
  return Object.fromEntries(Object.entries(df).filter(([, v]) => v !== '' && v != null));
}

async function search() {
  if (state.loading) return;
  setBusy(true);
  setStat('抓取中…');
  const t0 = Date.now();
  try {
    const cats = await resolveSelectedCats();
    const q = new URLSearchParams({
      cat: cats[0] || state.cat,
      cats: cats.join(','),
      sort: state.sort, page: String(state.page),
      pages: String(state.depth),
      filters: JSON.stringify(buildFilterParam()),
    });
    const data = await api('/api/search?' + q.toString());
    state.rows = data.items || [];
    state.perCat = data.perCat || {};
    applyLocalView();
    $('#pageInfo').textContent = `第 ${state.page}–${state.page + state.depth - 1} 页`;
    setStat(`${state.rows.length} 条 · ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  } catch (e) {
    const msg = String(e.message || e);
    const blocked = /限流|incident|403|冷却/.test(msg);
    setStat(blocked ? 'Ozon 限流中' : '失败: ' + msg);
    $('#empty').textContent = blocked
      ? '⚠ Ozon 临时限流（按 IP 计速），选品和类目请求都会被挡。等 30–60 分钟再试；左栏类目树与类目属性不受影响。'
      : '加载失败：' + msg;
    state.rows = [];
    applyLocalView();
  } finally {
    setBusy(false);
  }
}

/** 把勾选的类目解析成 web slug；没勾选就用当前类目 */
async function resolveSelectedCats() {
  if (!state.selected.size) return state.cat ? [state.cat] : [];
  const out = [];
  for (const v of state.selected.values()) {
    let slug = v.node.slug;
    if (!slug) {
      try {
        const r = await api('/api/resolve?name=' + encodeURIComponent(v.node.n));
        if (r.slug) { slug = r.slug; v.node.slug = r.slug; }
      } catch (e) { /* 忽略 */ }
    }
    if (slug && !out.includes(slug)) out.push(slug);
  }
  return out.slice(0, 10);
}

async function loadAll() {
  markActive(state.cat);
  await loadFilters();
  await search();
}

// ---------------------------------------------------------------- 本地视图
function daysAgo(d) {
  const t = Date.parse(d + 'T00:00:00Z');
  if (isNaN(t)) return 1e9;
  return (Date.now() - t) / 86400000;
}

function applyLocalView() {
  let rows = state.rows.slice();

  if (state.localDays > 0) {
    rows = rows.filter((r) => r.listed_date && daysAgo(r.listed_date) <= state.localDays);
  }
  if (state.localMinRev > 0) {
    rows = rows.filter((r) => (r.reviews || 0) >= state.localMinRev);
  }

  // 详情列筛选（依赖已抓到的 PDP 详情）
  const df = state.df || {};
  const hasDf = Object.values(df).some((v) => v !== '' && v != null);
  if (hasDf) {
    rows = rows.filter((r) => {
      const m = mergeRow(r);
      if (!m._full) return false;                    // 没抓详情的先排除
      if (df.title && !s(m.name).includes(s(df.title))) return false;
      if (df.sku && !s(m.sku).includes(s(df.sku))) return false;
      if (df.seller_id && !s(m.seller_id).includes(s(df.seller_id))) return false;
      const s = (v) => String(v ?? '').toLowerCase();
      if (df.brand && !s(m.brand).includes(s(df.brand))) return false;
      if (df.seller && !s(m.seller).includes(s(df.seller))) return false;
      if (df.country && !s(m.country).includes(s(df.country))) return false;
      if (df.offer_code && !s(m.offer_code).includes(s(df.offer_code))) return false;
      if (df.psrn && !s(m.seller_psrn).includes(s(df.psrn))) return false;
      if (df.honest && s(m.honest_sign) !== s(df.honest)) return false;
      const ge = (v, lim) => (lim === '' || lim == null ? true : v != null && Number(v) >= Number(lim));
      const le = (v, lim) => (lim === '' || lim == null ? true : v != null && Number(v) <= Number(lim));
      if (!ge(m.seller_rating, df.seller_rating_min)) return false;
      if (!le(m.seller_rating, df.seller_rating_max)) return false;
      if (!ge(m.rating, df.rating_min)) return false;
      if (!le(m.rating, df.rating_max)) return false;
      if (!ge(m.reviews, df.reviews_min)) return false;
      if (!le(m.reviews, df.reviews_max)) return false;
      if (!ge(m.questions, df.questions_min)) return false;
      if (!le(m.questions, df.questions_max)) return false;
      if (!ge(m.stock, df.stock_min)) return false;
      if (!le(m.stock, df.stock_max)) return false;
      if (!ge(m.image_count, df.images_min)) return false;
      if (!le(m.image_count, df.images_max)) return false;
      if (!ge(m.weight, df.weight_min)) return false;
      if (!le(m.weight, df.weight_max)) return false;
      if (!ge(m.length, df.length_min)) return false;
      if (!le(m.length, df.length_max)) return false;
      if (state.discountMin) {
        const dv = Math.abs(parseFloat(String(m.discount || '').replace('%','')) || 0);
        if (dv < state.discountMin) return false;
      }
      if (!ge(m.width, df.width_min)) return false;
      if (!le(m.width, df.width_max)) return false;
      return true;
    });
  }

  const s = state.localSort;
  const by = (f) => (a, b) => f(a) - f(b);
  if (s === 'listed_desc') rows.sort((a, b) => String(b.listed_date || '').localeCompare(String(a.listed_date || '')));
  else if (s === 'listed_asc') rows.sort((a, b) => String(a.listed_date || '9999').localeCompare(String(b.listed_date || '9999')));
  else if (s === 'price_asc') rows.sort(by((r) => r.price ?? 1e12));
  else if (s === 'price_desc') rows.sort(by((r) => -(r.price ?? -1)));
  else if (s === 'discount_desc') rows.sort(by((r) => -Math.abs(parseFloat(String(r.discount || '0').replace('%', '')) || 0)));
  else if (s === 'rating_desc') rows.sort(by((r) => -(r.rating ?? -1)));
  else if (s === 'reviews_desc') rows.sort(by((r) => -(r.reviews ?? -1)));
  else if (s === 'seller_rating_desc') rows.sort(by((r) => -(mergeRow(r).seller_rating ?? -1)));
  else if (s === 'stock_desc') rows.sort(by((r) => -(mergeRow(r).stock ?? -1)));
  else if (s.startsWith('k:')) {
    const key = s.slice(2);
    const dir = state.sortDir || -1;
    rows.sort((a, b) => {
      const va = mergeRow(a)[key];
      const vb = mergeRow(b)[key];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      const na = Number(va), nb = Number(vb);
      if (!isNaN(na) && !isNaN(nb)) return dir * (na - nb);
      return dir * String(va).localeCompare(String(vb));
    });
  }

  state.view = rows;
  renderProducts();
  renderStats();
}

function renderStats() {
  const rows = state.view;
  const bar = $('#statbar');
  bar.innerHTML = '';
  $('#rowCount').textContent = `显示 ${rows.length} / 抓取 ${state.rows.length} 条`;
  $('#empty').hidden = rows.length > 0;
  if (!rows.length) return;

  const prices = rows.map((r) => r.price).filter((n) => n != null);
  const discs = rows.map((r) => Math.abs(parseFloat(String(r.discount || '').replace('%', '')))).filter((n) => !isNaN(n));
  const rates = rows.map((r) => r.rating).filter((n) => n != null);
  const revs = rows.map((r) => r.reviews).filter((n) => n != null);
  const avg = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  const median = (a) => {
    if (!a.length) return null;
    const s = [...a].sort((x, y) => x - y);
    return s[Math.floor(s.length / 2)];
  };
  const recent = rows.filter((r) => r.listed_date && daysAgo(r.listed_date) <= 30).length;

  const kpi = (k, v, unit) => {
    const n = el('div', 'kpi');
    n.innerHTML = `<div class="k">${k}</div><div class="v">${v}${unit ? `<small> ${unit}</small>` : ''}</div>`;
    return n;
  };
  bar.appendChild(kpi('商品数', rows.length, '条'));
  bar.appendChild(kpi('均价', fmtNum(Math.round(avg(prices) || 0)), '₽'));
  bar.appendChild(kpi('中位价', fmtNum(median(prices)), '₽'));
  bar.appendChild(kpi('平均折扣', (avg(discs) || 0).toFixed(1), '%'));
  bar.appendChild(kpi('平均评分', (avg(rates) || 0).toFixed(2), '★'));
  bar.appendChild(kpi('评论中位', fmtNum(median(revs)), '条'));
  bar.appendChild(kpi('30天内上架', Math.round((recent / rows.length) * 100), '%'));

  const bands = [
    ['<500', 0, 500], ['500-1k', 500, 1000], ['1-2k', 1000, 2000],
    ['2-5k', 2000, 5000], ['5-10k', 5000, 10000], ['>10k', 10000, Infinity],
  ];
  const counts = bands.map(([, lo, hi]) => prices.filter((p) => p >= lo && p < hi).length);
  const max = Math.max(...counts, 1);
  const k = el('div', 'kpi band');
  k.innerHTML = `<div class="k">价格带分布（₽）</div><div class="bands">${
    bands.map(([label], i) => `<div class="band-col" title="${label} ₽：${counts[i]} 条">
        <i style="height:${Math.max(2, (counts[i] / max) * 24)}px"></i><span>${label}</span></div>`).join('')
  }</div>`;
  bar.appendChild(k);
}

// ---------------------------------------------------------------- 表格
function renderProducts() {
  const grid = $('#grid');
  if (state.showFull) return renderWideTable();
  grid.classList.remove('wide');
  grid.innerHTML = '';
  const rows = state.view;
  const multi = state.selected.size > 0;
  const crumbMain = multi
    ? `<b>已选 ${state.selected.size} 个类目</b>`
    : `<b>${esc(state.catZh)}</b> <span style="color:#9aa8ba">${esc(state.catRu)}</span>`;
  $('#crumb').innerHTML = `${crumbMain} · ${esc(sortName(state.sort))}`;
  $('#empty').hidden = rows.length > 0;

  const head = el('div', 'trow thead');
  head.innerHTML = `<div>图片</div><div>标题</div>
    <div>价格<span class="ru">₽</span></div>
    <div>折扣</div><div>评分</div><div>评论数</div>
    <div>上架日期<span class="ru">推算</span></div>`;
  grid.appendChild(head);

  rows.forEach((r) => {
    const row = el('div', 'trow');

    const th = el('div', 'tthumb');
    if (r.image) {
      const img = el('img');
      img.referrerPolicy = 'no-referrer';
      img.loading = 'lazy';
      img.src = r.image;
      th.appendChild(img);
    }

    const name = el('div', 'tname');
    name.textContent = r.name || '(无标题)';
    if (r.listed_date && daysAgo(r.listed_date) <= 30) {
      name.insertAdjacentHTML('beforeend', '<span class="tagnew">NEW</span>');
    }
    if (multi && r.cat) {
      const c = catLabel(r.cat);
      if (c) name.insertAdjacentHTML('beforeend', `<span class="tagcat">${esc(c)}</span>`);
    }

    const price = el('div', 'tprice');
    price.innerHTML = r.price != null ? `${fmtNum(r.price)}<small style="font-size:11px;color:#9aa8ba"> ₽</small>` : '—';
    if (r.old_price) price.insertAdjacentHTML('beforeend', `<s>${fmtNum(r.old_price)} ₽</s>`);

    const disc = el('div', 'tdisc', esc(r.discount || ''));
    const rate = el('div', 'trate');
    rate.innerHTML = r.rating != null ? `<span class="star">★</span> ${r.rating}` : '—';
    const rev = el('div', 'trate');
    rev.innerHTML = r.reviews != null ? `${fmtNum(r.reviews)}<small>条</small>` : '—';

    const date = el('div', 'tdate');
    if (r.listed_date) {
      const days = Math.round(daysAgo(r.listed_date));
      const rel = days <= 1 ? '今天' : days < 30 ? `${days} 天前`
        : days < 365 ? `${Math.round(days / 30)} 个月前` : `${(days / 365).toFixed(1)} 年前`;
      date.innerHTML = `<b>${r.listed_date}</b><span>${rel}</span>`;
    } else {
      date.textContent = '—';
    }

    row.append(th, name, price, disc, rate, rev, date);
    row.title = (r.stock ? `库存 ${r.stock} · ` : '') + `SKU ${r.sku}`;
    row.onclick = () => openDetail(r);
    grid.appendChild(row);
  });
  grid.scrollTop = 0;
}

function sortName(k) {
  const s = state.sorts.find((x) => x.key === k);
  return s ? s.name : k;
}

function catLabel(slug) {
  for (const v of state.selected.values()) {
    if (v.node && v.node.slug === slug) return v.zh;
  }
  const c = state.cats.find((x) => x.slug === slug);
  return c ? c.zh : '';
}

// ---------------------------------------------------------------- 详情
async function openDetail(r) {
  const drawer = $('#drawer');
  const box = $('#drawerContent');
  drawer.hidden = false;
  box.innerHTML = '<p style="color:#6c7a8c">加载详情…</p>';
  try {
    const d = await api('/api/product?sku=' + encodeURIComponent(r.sku));
    const imgs = (d.images && d.images.length ? d.images : r.images) || [];
    box.innerHTML = `
      <div class="detail-imgs">${imgs.map((u) => `<img referrerpolicy="no-referrer" src="${esc(u)}">`).join('')}</div>
      <h2 class="detail-title">${esc(d.name || r.name)}</h2>
      <dl class="detail-kv">
        <dt>SKU</dt><dd>${esc(r.sku)}</dd>
        <dt>现价 / 原价</dt><dd>${r.price != null ? fmtNum(r.price) + ' ₽' : '—'} ${r.old_price ? `<s style="color:#a7b3c2">${fmtNum(r.old_price)} ₽</s> <b style="color:#e5484d">${esc(r.discount)}</b>` : ''}</dd>
        <dt>评分 / 评论</dt><dd>${r.rating != null ? '<span style="color:#f5a524">★</span> ' + r.rating : '—'} ${r.reviews_text ? '· ' + esc(r.reviews_text) : ''}</dd>
        <dt>上架日期</dt><dd>${d.listed_date || '—'} <span style="color:#9aa8ba">（由 SKU 推算）</span></dd>
        <dt>库存提示</dt><dd>${esc(r.stock || '—')}</dd>
        <dt>商品链接</dt><dd><a style="color:#005bff" target="_blank" href="${esc(r.url)}">打开 Ozon 商品页 ↗</a></dd>
      </dl>
      ${d.chars && d.chars.length ? `<h3 style="font-size:13px;margin:18px 0 8px;color:#2b3644">商品属性（俄文原文）</h3>
        <dl class="detail-kv">${d.chars.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
    `;
  } catch (e) {
    box.innerHTML = `<p style="color:#e5484d">详情加载失败: ${esc(e.message)}</p>`;
  }
}

// ---------------------------------------------------------------- 导出
async function doExport() {
  const rows = state.fullRows && state.fullRows.length ? state.fullRows : state.view;
  if (!rows.length) { setStat('没有可导出的数据'); return; }
  setStat('导出中…');
  try {
    const r = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rows),
    });
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    setStat('已导出 ' + j.name);
  } catch (e) {
    setStat('导出失败: ' + e.message);
  }
}

// ---------------------------------------------------------------- 类目大盘
const mkt = { rows: [], sortKey: 'opportunity', sortDir: -1, jobId: null, timer: null };

function switchView(v) {
  document.querySelectorAll('#viewSeg button').forEach((b) => b.classList.toggle('on', b.dataset.view === v));
  $('#pickerView').hidden = v !== 'picker';
  $('#marketView').hidden = v !== 'market';
  $('#sortSeg').style.display = v === 'picker' ? '' : 'none';
  $('#btnExport').style.display = v === 'picker' ? '' : 'none';
  if (v === 'market' && !mkt.rows.length) loadLastMarket();
}

async function loadLastMarket() {
  try {
    const d = await api('/api/market/last');
    if (d.rows && d.rows.length) {
      mkt.rows = d.rows;
      renderMarket();
      $('#mktEmpty').hidden = true;
      if (d.built_at) $('#mktProgressText').textContent = '上次分析：' + d.built_at;
    }
  } catch (e) { /* 忽略 */ }
}

async function runMarket() {
  const cats = $('#mktCats').value;
  const pages = $('#mktPages').value;
  const sorts = $('#mktSorts').value;
  const detail = $('#mktDetail').value;
  const df = Object.fromEntries(Object.entries(state.df || {}).filter(([, v]) => v !== '' && v != null));
  $('#btnMktRun').disabled = true;
  $('#mktProgress').hidden = false;
  $('#mktBar').style.width = '0%';
  $('#mktProgressText').textContent = '正在启动…';
  $('#mktEmpty').hidden = true;
  try {
    const r = await api(`/api/market/start?cats=${encodeURIComponent(cats)}&pages=${pages}&sorts=${encodeURIComponent(sorts)}&detail=${detail}&df=${encodeURIComponent(JSON.stringify(df))}`);
    mkt.jobId = r.id;
    pollMarket();
  } catch (e) {
    $('#mktProgressText').textContent = '启动失败: ' + e.message;
    $('#btnMktRun').disabled = false;
  }
}

function pollMarket() {
  clearInterval(mkt.timer);
  mkt.timer = setInterval(async () => {
    try {
      const s = await api('/api/market/status?id=' + encodeURIComponent(mkt.jobId));
      const pct = Math.round((s.progress || 0) * 100);
      $('#mktBar').style.width = pct + '%';
      $('#mktProgressText').textContent = s.done ? '完成' : `分析中 ${pct}%（${s.label || ''}）`;
      if (s.result && s.result.length) { mkt.rows = s.result; renderMarket(); }
      if (s.done) {
        clearInterval(mkt.timer);
        $('#btnMktRun').disabled = false;
        $('#mktBar').style.width = '100%';
        $('#mktProgressText').textContent = s.error ? ('失败: ' + s.error) : `完成 · ${s.result.length} 个类目`;
        setTimeout(() => { $('#mktProgress').hidden = true; }, 1500);
      }
    } catch (e) {
      clearInterval(mkt.timer);
      $('#btnMktRun').disabled = false;
      $('#mktProgressText').textContent = '轮询失败: ' + e.message;
    }
  }, 1200);
}

const MKT_COLS = [
  { k: 'zh', t: '类目', cls: 'mcat' },
  { k: 'n', t: '样本数' },
  { k: 'detail_n', t: '详情数' },
  { k: 'price_median', t: '中位价 ₽' },
  { k: 'price_avg', t: '均价 ₽' },
  { k: 'discount_avg', t: '折扣 %' },
  { k: 'rating_avg', t: '均分' },
  { k: 'reviews_median', t: '评论中位' },
  { k: 'new30_pct', t: '30天新品 %' },
  { k: 'cr5', t: '评论CR5 %' },
  { k: 'seller_n', t: '卖家数' },
  { k: 'seller_cr1', t: '卖家CR1 %' },
  { k: 'seller_cr5', t: '卖家CR5 %' },
  { k: 'seller_rating_avg', t: '卖家均分' },
  { k: 'seller_low_pct', t: '低分卖家 %' },
  { k: 'opportunity', t: '机会分' },
  { k: 'bands', t: '价格带分布' },
];
function renderMarket() {
  const rows = mkt.rows.filter((r) => r && r.n);
  if (!rows.length) return;
  $('#mktEmpty').hidden = true;

  // KPI
  const kpi = $('#mktKpi');
  kpi.innerHTML = '';
  const best = [...rows].sort((a, b) => b.opportunity - a.opportunity)[0];
  const newest = [...rows].sort((a, b) => b.new30_pct - a.new30_pct)[0];
  const cheapest = [...rows].filter((r) => r.price_median).sort((a, b) => a.price_median - b.price_median)[0];
  const add = (k, v, s) => {
    const n = el('div', 'kpi');
    n.innerHTML = `<div class="k">${k}</div><div class="v">${v}<small> ${s || ''}</small></div>`;
    kpi.appendChild(n);
  };
  add('已分析类目', rows.length, '个');
  add('平均机会分', (rows.reduce((x, r) => x + (r.opportunity || 0), 0) / rows.length).toFixed(1), '分');
  add('最有机会', esc(best.zh), `(${best.opportunity})`);
  add('新品最活跃', esc(newest.zh), `${newest.new30_pct}%`);
  add('价格门槛最低', esc(cheapest.zh), `${fmtNum(Math.round(cheapest.price_median))} ₽`);

  const sorted = [...rows].sort((a, b) => {
    const k = mkt.sortKey;
    let x = a[k], y = b[k];
    if (x == null) x = -1e12;
    if (y == null) y = -1e12;
    if (typeof x === 'string') return mkt.sortDir * x.localeCompare(y);
    return mkt.sortDir * (x - y);
  });

  const box = $('#mktTable');
  box.innerHTML = '';
  const head = el('div', 'mrow mhead');
  MKT_COLS.forEach((c) => {
    const d = el('div', mkt.sortKey === c.k ? 'sorted' : '',
      c.t + (mkt.sortKey === c.k ? (mkt.sortDir < 0 ? ' ↓' : ' ↑') : ''));
    d.onclick = () => {
      if (mkt.sortKey === c.k) mkt.sortDir *= -1;
      else { mkt.sortKey = c.k; mkt.sortDir = c.k === 'zh' ? 1 : -1; }
      renderMarket();
    };
    head.appendChild(d);
  });
  box.appendChild(head);

  const maxBand = Math.max(1, ...rows.map((r) => Math.max(...(r.bands || [0]))));
  const maxOp = Math.max(...rows.map((r) => r.opportunity), 1);

  sorted.forEach((r) => {
    const row = el('div', 'mrow');
    const lowTag = r.low_confidence ? ' <span style="color:#e5484d;font-size:10px">样本少</span>' : '';
    row.appendChild(el('div', 'mcat', `<b>${esc(r.zh)}${lowTag}</b><span>${esc(r.ru)}</span>`));
    const cellv = (v, cls, suffix) => {
      if (v == null || v === '') return el('div', 'mnum ' + (cls || ''), '<span style="color:#a7b3c2">—</span>');
      return el('div', 'mnum ' + (cls || ''), (typeof v === 'number' ? fmtNum(v) : esc(v)) + (suffix || ''));
    };
    row.appendChild(cellv(r.n));
    row.appendChild(cellv(r.detail_n));
    row.appendChild(cellv(r.price_median, 'hl'));
    row.appendChild(cellv(r.price_avg));
    row.appendChild(cellv(r.discount_avg, '', '%'));
    row.appendChild(cellv(r.rating_avg == null ? null : Number(r.rating_avg).toFixed(1)));
    row.appendChild(cellv(r.reviews_median));
    row.appendChild(cellv(r.new30_pct, '', '%'));
    row.appendChild(cellv(r.cr5, '', '%'));
    row.appendChild(cellv(r.seller_n));
    row.appendChild(cellv(r.seller_cr1, '', '%'));
    row.appendChild(cellv(r.seller_cr5, '', '%'));
    row.appendChild(cellv(r.seller_rating_avg == null ? null : Number(r.seller_rating_avg).toFixed(2)));
    row.appendChild(cellv(r.seller_low_pct, '', '%'));

    const op = r.opportunity ?? 0;
    const hue = 205 - Math.min(205, (op / 100) * 205);
    const cell = el('div', 'mop', op.toFixed(1));
    cell.style.background = `hsl(${hue}, ${35 + (op / 100) * 45}%, ${94 - (op / maxOp) * 22}%)`;
    row.appendChild(cell);

    const bars = el('div', 'mbars');
    (r.bands || []).forEach((c) => {
      const i = el('i');
      i.style.height = Math.max(2, (c / maxBand) * 22) + 'px';
      i.title = c + ' 条';
      bars.appendChild(i);
    });
    row.appendChild(bars);

    row.onclick = () => {
      switchView('picker');
      const c = state.cats.find((x) => x.slug === r.slug);
      if (c) selectCat(c.slug, c.zh, c.ru);
    };
    box.appendChild(row);
  });
}

// ---------------------------------------------------------------- 全量列宽表
// 只放「短值 / 数值」列，能排序能筛选；长文本（描述、富文本、图片库、地址、链接）留在右侧抽屉
const WCOLS = [
  ['图', 42, null],
  ['SKU', 98, 'sku'],
  ['卖家货号', 88, 'offer_code'],
  ['品牌', 84, 'brand'],
  ['名称', 240, 'name'],
  ['类目', 200, 'category'],
  ['特价', 62, 'special_price'],
  ['价格', 62, 'price'],
  ['原价', 62, 'original_price'],
  ['折扣 %', 58, 'discount'],
  ['卖家', 116, 'seller'],
  ['卖家 ID', 74, 'seller_id'],
  ['卖家评分', 66, 'seller_rating'],
  ['卖家评价/订单', 84, 'seller_reviews'],
  ['店龄', 66, 'seller_age'],
  ['公司名称', 160, 'seller_company'],
  ['工商注册号', 104, 'seller_psrn'],
  ['诚信标志', 62, 'honest_sign'],
  ['评分', 46, 'rating'],
  ['评价数', 68, 'reviews'],
  ['提问数', 60, 'questions'],
  ['数量', 60, 'stock'],
  ['图片数', 52, 'image_count'],
  ['产地', 72, 'country'],
  ['长 mm', 56, 'length'],
  ['宽 mm', 56, 'width'],
  ['高 mm', 56, 'height'],
  ['重量 g', 60, 'weight'],
  ['上架日期', 92, 'listed_date'],
];

function mergeRow(r) {
  const d = (state.detailMap && state.detailMap.get(String(r.sku))) || {};
  return {
    sku: r.sku, name: d.name || r.name, name_zh: d.name_zh || r.name_zh, image: r.image,
    offer_code: d.offer_code, brand: d.brand, category: d.category,
    special_price: d.special_price, price: d.price ?? r.price,
    original_price: d.original_price ?? r.old_price, discount: d.discount ?? r.discount,
    seller: d.seller, seller_id: d.seller_id, seller_rating: d.seller_rating,
    seller_reviews: d.seller_reviews, seller_age: d.seller_age,
    seller_company: d.seller_company, seller_psrn: d.seller_psrn,
    seller_address: d.seller_address, honest_sign: d.honest_sign, seller_url: d.seller_url,
    rating: d.rating ?? r.rating, reviews: d.reviews ?? r.reviews, questions: d.questions,
    stock: d.stock ?? r.stock, image_count: d.image_count,
    url: d.url || r.url, thumbnail: d.thumbnail || r.image, gallery: d.gallery,
    description: d.description, rich_description: d.rich_description,
    country: d.country, country_zh: d.country_zh, category_zh: d.category_zh, length: d.length, width: d.width, height: d.height,
    weight: d.weight, listed_date: r.listed_date, _full: !!d.seller,
  };
}

function renderWideTable() {
  const grid = $('#grid');
  grid.classList.add('wide');
  grid.innerHTML = '';
  const rows = state.view.map(mergeRow);
  $('#empty').hidden = rows.length > 0;
  const multi = state.selected.size > 0;
  const crumbMain = multi ? `<b>已选 ${state.selected.size} 个类目</b>`
    : `<b>${esc(state.catZh)}</b> <span style="color:#9aa8ba">${esc(state.catRu)}</span>`;
  $('#crumb').innerHTML = `${crumbMain} · ${esc(sortName(state.sort))} · 全量列`;

  const tmpl = WCOLS.map((c) => c[1] + 'px').join(' ');
  const box = el('div', 'wt');
  const head = el('div', 'wrow whead');
  head.style.gridTemplateColumns = tmpl;
  const curKey = (state.localSort || '').startsWith('k:') ? state.localSort.slice(2) : '';
  head.innerHTML = WCOLS.map((c) => {
    if (!c[2]) return `<div class="wcell">${esc(c[0])}</div>`;
    const on = c[2] === curKey;
    const arrow = on ? (state.sortDir < 0 ? ' ↓' : ' ↑') : '';
    return `<div class="wcell" data-sort="${c[2]}" style="cursor:pointer${on ? ';color:var(--accent)' : ''}">${esc(c[0])}${arrow}</div>`;
  }).join('');
  head.querySelectorAll('[data-sort]').forEach((d) => {
    d.onclick = () => {
      const k = d.dataset.sort;
      if (curKey === k) state.sortDir = -state.sortDir;
      else { state.sortDir = -1; }
      state.localSort = 'k:' + k;
      applyLocalView();
    };
  });
  box.appendChild(head);

  rows.forEach((r) => {
    const row = el('div', 'wrow');
    row.style.gridTemplateColumns = tmpl;

    const th = el('div', 'wthumb');
    if (r.image) { const im = el('img'); im.referrerPolicy = 'no-referrer'; im.loading = 'lazy'; im.src = r.image; th.appendChild(im); }

    const txt = (v, cls) => el('div', 'wcell ' + (cls || ''), v == null || v === '' ? '<span class="wmut">—</span>' : esc(v));
    const num = (v, cls) => el('div', 'wcell ' + (cls || ''), v == null || v === '' ? '<span class="wmut">—</span>' : fmtNum(v));
    const bi = (zh, ru) => {
      if (!zh) return el('div', 'wcell', ru ? esc(ru) : '<span class="wmut">—</span>');
      return el('div', 'wcell', `${esc(zh)}<span class="ru2">${esc(ru || '')}</span>`);
    };
    const disc = (dv) => {
      const dn = parseFloat(String(dv ?? '').replace('%', '').replace('−', '-'));
      if (dv == null || dv === '' || isNaN(dn)) return el('div', 'wcell', '<span class="wmut">—</span>');
      return el('div', 'wcell tdisc', esc(dn + '%'));
    };

    row.append(
      th,
      txt(r.sku, 'mnum'),
      txt(r.offer_code),
      txt(r.brand),
      bi(r.name_zh, r.name),
      bi(r.category_zh, r.category),
      num(r.special_price, 'mnum'),
      num(r.price, 'mnum'),
      num(r.original_price, 'mnum'),
      disc(r.discount),
      txt(r.seller),
      txt(r.seller_id, 'mnum'),
      txt(r.seller_rating, 'mnum'),
      txt(r.seller_reviews, 'mnum'),
      txt(r.seller_age),
      txt(r.seller_company),
      txt(r.seller_psrn, 'mnum'),
      txt(r.honest_sign),
      txt(r.rating, 'mnum'),
      num(r.reviews, 'mnum'),
      num(r.questions, 'mnum'),
      num(r.stock, 'mnum'),
      num(r.image_count, 'mnum'),
      txt(r.country_zh && r.country_zh !== r.country ? r.country_zh : r.country),
      num(r.length, 'mnum'),
      num(r.width, 'mnum'),
      num(r.height, 'mnum'),
      num(r.weight, 'mnum'),
      el('div', 'wcell', r.listed_date ? esc(r.listed_date) : '<span class="wmut">—</span>'),
    );
    row.title = r._full ? '点击查看全部字段（含描述/图片库/卖家地址/链接）'
                       : '还没抓详情，点「抓详情」补全卖家/产地/长宽高列';
    row.onclick = () => openFullDetail(r, r);
    box.appendChild(row);
  });
  grid.appendChild(box);
  grid.scrollTop = 0;
}

// ---------------------------------------------------------------- 全量详情
async function loadFullDetails() {
  if (!state.view.length) { setStat('没有可抓的商品'); return; }
  const rows = state.view.slice(0, 30);
  setBusy(true);
  setStat(`抓详情 0/${rows.length}…`);
  if (!state.detailMap) state.detailMap = new Map();
  try {
    for (let i = 0; i < rows.length; i += 6) {
      const batch = rows.slice(i, i + 6).map((r) => r.sku);
      const d = await api('/api/product/full?skus=' + encodeURIComponent(batch.join(',')));
      (d.items || []).forEach((it) => state.detailMap.set(String(it.sku), it));
      setStat(`抓详情 ${Math.min(i + 6, rows.length)}/${rows.length}…`);
      if (state.showFull) renderWideTable();
    }
    state.fullRows = [...state.detailMap.values()];
    setStat(`详情已补全 ${state.detailMap.size} 条`);
  } catch (e) {
    setStat('抓详情失败: ' + e.message);
  } finally {
    setBusy(false);
  }
}

function openFullDetail(r) {
  const box = $('#drawerContent');
  $('#drawer').hidden = false;
  const kv = [
    ['SKU', r.sku], ['卖家货号', r.offer_code], ['品牌', r.brand], ['名称', r.name],
    ['类目', r.category_zh ? r.category_zh + ' / ' + r.category : r.category], ['特价', r.special_price], ['价格', r.price], ['原价', r.original_price],
    ['折扣', r.discount != null ? r.discount + '%' : ''], ['上架日期', r.listed_date],
    ['卖家', r.seller], ['卖家ID', r.seller_id], ['卖家评分', r.seller_rating],
    ['卖家评价/订单', r.seller_reviews], ['店龄', r.seller_age], ['公司名称', r.seller_company],
    ['工商注册号', r.seller_psrn], ['卖家地址', r.seller_address], ['诚信标志', r.honest_sign],
    ['评分', r.rating], ['评价数', r.reviews], ['提问数', r.questions], ['库存', r.stock],
    ['图片数', r.image_count], ['产地', r.country_zh && r.country_zh !== r.country ? r.country_zh + ' / ' + r.country : r.country],
    ['长度/宽度/高度/深度', [r.length, r.width, r.height, r.depth].map((x) => (x == null ? '-' : x)).join(' / ')],
    ['重量', r.weight],
  ];
  box.innerHTML = `
    <div class="detail-imgs">${String(r.gallery || '').split(';').filter(Boolean).slice(0, 8)
      .map((u) => `<img referrerpolicy="no-referrer" src="${esc(u)}">`).join('')}</div>
    <h2 class="detail-title">${esc(r.name || '')}</h2>
    <dl class="detail-kv">${kv.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v == null ? '—' : v)}</dd>`).join('')}</dl>
    <h3 style="font-size:13px;margin:18px 0 8px;color:#2b3644">完整属性（${(r.attributes || []).length}）</h3>
    <dl class="detail-kv">${(r.attributes || []).map((a) => `<dt>${esc(a.name_zh || a.name)}<span class="ru">${a.name_zh ? esc(a.name) : ""}</span></dt><dd>${esc(a.value)}</dd>`).join('')}</dl>
    <h3 style="font-size:13px;margin:18px 0 8px;color:#2b3644">描述</h3>
    <p style="font-size:13px;line-height:1.7;color:#33404f;white-space:pre-wrap">${esc(r.description || '')}</p>
  `;
}

// ---------------------------------------------------------------- 绑定
$('#prevPage').onclick = () => {
  if (state.page > 1) { state.page = Math.max(1, state.page - state.depth); search(); }
};
$('#nextPage').onclick = () => {
  if (state.rows.length) { state.page += state.depth; search(); }
};
$('#btnReset').onclick = () => {
  state.filters = {}; state.ranges = {}; state.page = 1;
  state.localSort = 'default'; state.localDays = 0; state.localMinRev = 0;
  $('#selSort').value = 'default'; $('#selDays').value = '0'; $('#inpMinRev').value = '';
  renderFilters(); search();
};
$('#btnExport').onclick = doExport;
$('#selPages').onchange = (e) => { state.depth = Number(e.target.value); state.page = 1; search(); };
$('#selSort').onchange = (e) => { state.localSort = e.target.value; applyLocalView(); };
$('#selDays').onchange = (e) => { state.localDays = Number(e.target.value); };
$('#inpMinRev').oninput = (e) => { state.localMinRev = Number(e.target.value) || 0; };
$('#drawerMask').onclick = () => { $('#drawer').hidden = true; };
$('#drawerClose').onclick = () => { $('#drawer').hidden = true; };

document.querySelectorAll('#viewSeg button').forEach((b) => {
  b.onclick = () => switchView(b.dataset.view);
});
$('#btnMktRun').onclick = runMarket;
// ---------------- 筛选方案（保存/载入） ----------------
const SCHEME_KEY = 'ozon.filterSchemes.v1';

function loadSchemes() {
  try { return JSON.parse(localStorage.getItem(SCHEME_KEY) || '[]'); } catch { return []; }
}
function storeSchemes(list) {
  try { localStorage.setItem(SCHEME_KEY, JSON.stringify(list)); } catch { /* 忽略 */ }
}
function renderSchemeList(selectName) {
  const sel = $('#fSchemeList');
  if (!sel) return;
  const list = loadSchemes();
  sel.innerHTML = '<option value="">— 筛选方案（' + list.length + '）—</option>' +
    list.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  if (selectName) {
    const hit = list.find((s) => s.name === selectName);
    if (hit) sel.value = hit.id;
  }
}

/** 抓取表单当前状态 */
function captureScheme() {
  return {
    sel: {
      brand: ($('#fBrand') || {}).value || '',
      shop: ($('#fShop') || {}).value || '',
      color: ($('#fColor') || {}).value || '',
      type: ($('#fType') || {}).value || '',
      delivery: ($('#fDelivery') || {}).value || '',
      priceMin: ($('#fPriceMin') || {}).value || '',
      priceMax: ($('#fPriceMax') || {}).value || '',
      title: ($('#fTitle') || {}).value || '',
      sku: ($('#fSku') || {}).value || '',
      sellerId: ($('#fSellerId') || {}).value || '',
    },
    df: Object.assign({}, state.df || {}),
    days: state.localDays || 0,
    discountMin: state.discountMin || 0,
    tab: (document.querySelector('#fTabs button.on') || {}).dataset?.tab || 'all',
    sort: state.localSort || 'default',
    depth: state.depth,
  };
}

/** 把方案写回表单（不触发查询） */
function applyScheme(s) {
  if (!s) return;
  const d = s.sel || {};
  const set = (id, v) => { const n = $(id); if (n) n.value = v || ''; };
  set('#fBrand', d.brand); set('#fShop', d.shop); set('#fColor', d.color);
  set('#fType', d.type); set('#fDelivery', d.delivery);
  set('#fPriceMin', d.priceMin); set('#fPriceMax', d.priceMax);
  set('#fTitle', d.title); set('#fSku', d.sku); set('#fSellerId', d.sellerId);

  state.df = Object.assign({}, s.df || {});
  document.querySelectorAll('[data-df]').forEach((i) => {
    const k = i.dataset.df;
    i.value = state.df[k] != null ? state.df[k] : '';
  });

  state.localDays = s.days || 0;
  document.querySelectorAll('#fDays button').forEach((x) =>
    x.classList.toggle('on', Number(x.dataset.days) === Number(state.localDays)));

  state.discountMin = s.discountMin || 0;

  const honest = (s.df || {}).honest || '';
  document.querySelectorAll('#fHonest button').forEach((x) =>
    x.classList.toggle('on', (x.dataset.honest || '') === honest));

  document.querySelectorAll('#fTabs button').forEach((x) =>
    x.classList.toggle('on', x.dataset.tab === (s.tab || 'all')));

  if (s.sort) { state.localSort = s.sort; const n = $('#selSort'); if (n) n.value = s.sort; }
  if (s.depth) { state.depth = s.depth; const n = $('#selPages'); if (n) n.value = String(s.depth); }

  setStat('方案已载入，点「查询」生效');
}

function saveScheme() {
  const name = (($('#fSchemeName') || {}).value || '').trim();
  const list = loadSchemes();
  if (!name) { setStat('先填方案名再保存'); return; }
  const data = captureScheme();
  const idx = list.findIndex((s) => s.name === name);
  if (idx >= 0) {
    list[idx] = { id: list[idx].id, name, data, ts: Date.now() };
    setStat(`已覆盖方案「${name}」`);
  } else {
    list.push({ id: 's' + Date.now(), name, data, ts: Date.now() });
    setStat(`已保存方案「${name}」`);
  }
  storeSchemes(list);
  renderSchemeList(name);
}

function deleteScheme() {
  const id = ($('#fSchemeList') || {}).value;
  if (!id) { setStat('先在下拉里选一个方案'); return; }
  const list = loadSchemes().filter((s) => s.id !== id);
  storeSchemes(list);
  renderSchemeList();
  setStat('方案已删除');
}

// ---------------- 筛选表单 ----------------
// 数字/文本条件
document.querySelectorAll('[data-df]').forEach((inp) => {
  const key = inp.dataset.df;
  inp.value = state.df[key] || '';
  inp.addEventListener('change', () => {
    state.df[key] = String(inp.value).trim();   // 只记录，点「查询」才生效
  });
});

// 上架天数快捷
document.querySelectorAll('#fDays button').forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll('#fDays button').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    state.localDays = Number(b.dataset.days) || 0;   // 只记录
  };
});

// 诚信标志
document.querySelectorAll('#fHonest button').forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll('#fHonest button').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    if (b.dataset.honest) state.df.honest = b.dataset.honest;
    else delete state.df.honest;
  };
});

// 顶部分段预设
document.querySelectorAll('#fTabs button').forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll('#fTabs button').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    const t = b.dataset.tab;
    state.df = {};
    state.localDays = 0;
    document.querySelectorAll('[data-df]').forEach((i) => { i.value = ''; });
    document.querySelectorAll('#fDays button').forEach((x) => x.classList.toggle('on', x.dataset.days === '0'));
    document.querySelectorAll('#fHonest button').forEach((x) => x.classList.toggle('on', x.dataset.honest === ''));
    if (t === 'new') {
      state.localDays = 30;
      document.querySelectorAll('#fDays button').forEach((x) => x.classList.toggle('on', x.dataset.days === '30'));
    } else if (t === 'highrate') {
      state.df.rating_min = '4.8';
    } else if (t === 'discount') {
      state.discountMin = 50;
    } else if (t === 'seller') {
      state.df.seller_rating_min = '4.5';
    } else if (t === 'hot') {
      state.df.reviews_min = '1000';
    }
    state.discountMin = t === 'discount' ? 50 : 0;
    state.page = 1;
    setStat('条件已设置，点「查询」生效');
  };
});

// 重置 / 查询
$('#btnReset').onclick = () => {
  state.filters = {}; state.ranges = {}; state.df = {};
  state.localDays = 0; state.discountMin = 0; state.page = 1;
  document.querySelectorAll('[data-df],#fTitle,#fSku,#fSellerId,#fPriceMin,#fPriceMax').forEach((i) => { i.value = ''; });
  ['#fBrand', '#fShop', '#fColor', '#fType', '#fDelivery'].forEach((s) => { const n = $(s); if (n) n.value = ''; });
  document.querySelectorAll('#fTabs button').forEach((x) => x.classList.toggle('on', x.dataset.tab === 'all'));
  document.querySelectorAll('#fDays button').forEach((x) => x.classList.toggle('on', x.dataset.days === '0'));
  document.querySelectorAll('#fHonest button').forEach((x) => x.classList.toggle('on', x.dataset.honest === ''));
  search();
};
$('#btnQuery').onclick = () => { state.page = 1; search(); };

// 方案
$('#btnSchemeSave').onclick = saveScheme;
$('#btnSchemeDel').onclick = deleteScheme;
$('#fSchemeList').onchange = (e) => {
  const s = loadSchemes().find((x) => x.id === e.target.value);
  if (!s) return;
  $('#fSchemeName').value = s.name;
  applyScheme(s.data);
};
renderSchemeList();
$('#btnClearSel').onclick = () => { clearSelection(); state.page = 1; search(); };

if (location.hash === '#market') {
  switchView('market');
}

initCategories().catch((e) => setStat('初始化失败: ' + e.message));













