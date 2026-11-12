/* Ozon 数据选品台 · 多页面交互逻辑 */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v, d) => {
  if (v == null || v === '' || (typeof v === 'number' && !isFinite(v))) return '—';
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { maximumFractionDigits: d ?? (Number.isInteger(v) ? 0 : 2) });
  return String(v);
};
const money = v => v == null ? '—' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 });

/* ---------- 列定义（顺序 = 展示顺序：基础+产品数据 → 价格销售 → 口碑售后 → 流量转化漏斗 → 广告促销 → 上架/变体 → 综合） ---------- */
const RESULT_COLS = [
  ['img', ''], ['sku', 'SKU'], ['title', '商品标题'],
  ['weight', '重量g'], ['volume', '体积L'], ['dimension', '尺寸'],
  ['category_cn', '类目'], ['brand', '品牌'], ['seller', '店铺'],
  ['seller_type_text', '卖家类型'], ['fulfillment_text', '配送'],
  ['price', '价格 ₽'], ['discount', '平均折扣%'], ['sales', '月销量'], ['sales_rate', '销量环比%'],
  ['revenue', '月销售额 ₽'], ['revenue_rate', '销售额增长%'], ['gross_margin', '毛利率%'],
  ['review_count', '评论数'], ['review_rating', '评分'], ['qa', '问答数'], ['return_cancellation_rate', '退货取消率%'],
  ['views', '展示总量'], ['session_count_search', '曝光量'], ['session_count', '产品卡浏览'],
  ['conv_to_cart_search', '搜索加购率%'], ['conv_to_cart_pdp', '购物车转化率%'],
  ['conv_view_to_order', '展示转化%'], ['order_conversion_rate', '订单转化%'],
  ['drr', '广告费用份额%'], ['promo_revenue_share', '促销销售占比%'],
  ['up_time_date', '上架时间'], ['up_days', '上架天数'], ['variants', '变体数'],
  ['opportunity', '机会分'], ['link', '']
];
/* 率 / 占比 / 折扣类字段：数值后追加 % */
const PCT_KEYS = new Set(['discount', 'gross_margin', 'return_cancellation_rate',
  'conv_to_cart_search', 'conv_to_cart_pdp', 'conv_view_to_order',
  'order_conversion_rate', 'drr', 'promo_revenue_share']);
const KEYWORD_COLS = [
  ['query', '关键词'], ['query_cn', '中文'], ['search_volume', '月搜索量'],
  ['growth30', '30天增长'], ['competing_products', '竞品数'], ['sellers', '卖家数'],
  ['avg_price', '均价 ₽'], ['conversion_sharing', '转化份额'], ['market_space', '市场空间'],
  ['opportunity', '机会分']
];
const LOG_COLS = [
  ['query', '接口'], ['query_cn', '结果'], ['search_volume', '耗时 ms'],
  ['growth30', '积分'], ['competing_products', '缓存命中']
];

/* ---------- 各页面配置 ---------- */
const TOOL_CFG = {
  select: { api: '/api/top', cols: RESULT_COLS, kind: 'products', withCat: true, summary: true, applied: true },
  hotwords: { api: '/api/hotwords', cols: KEYWORD_COLS, kind: 'keywords', withCat: true },
  mining: { api: '/api/mining', cols: KEYWORD_COLS, kind: 'keywords' },
  backsearch: { api: '/api/backsearch', cols: KEYWORD_COLS, kind: 'keywords' },
  product: { api: '/api/product', cols: RESULT_COLS, kind: 'products', detail: true },
  category: { api: '/api/category', cols: RESULT_COLS, kind: 'products', withCat: true, summary: true },
  shop: { api: '/api/shop', cols: RESULT_COLS, kind: 'products', summary: true },
  local_products: { api: '/api/local/products', cols: RESULT_COLS, kind: 'products', get: true },
  local_keywords: { api: '/api/local/keywords', cols: KEYWORD_COLS, kind: 'keywords', get: true },
  logs: { api: '/api/logs', cols: LOG_COLS, kind: 'keywords', get: true }
};

/* ---------- 多页面：当前页由 body[data-page] 决定，导航栏跳转真实页面 ---------- */
const state = {
  rows: [], page: {}, selectedCats: new Set(), catNames: new Map(),
  catsExpanded: false, quickDays: 0, tool: document.body.dataset.page || 'select', lastApplied: null,
  viewMode: localStorage.getItem('sf_view') || 'table', lastCols: null
};

/* 已选类目跨页面保留（sessionStorage） */
function saveCats() {
  try { sessionStorage.setItem('sf_selected_cats', JSON.stringify([...state.selectedCats])); } catch (e) { }
}
function loadCats() {
  try {
    (JSON.parse(sessionStorage.getItem('sf_selected_cats') || '[]') || []).forEach(id => state.selectedCats.add(id));
  } catch (e) { }
}

/* ---------- 基础 ---------- */
async function api(path, opts = {}) {
  const o = { method: opts.method || 'GET', headers: { 'Content-Type': 'application/json' } };
  if (opts.body) o.body = JSON.stringify(opts.body);
  const r = await fetch(path, o);
  let j; try { j = await r.json(); } catch (e) { throw new Error('服务返回非 JSON（HTTP ' + r.status + '）'); }
  if (!j.ok) { const e = new Error(j.error || '请求失败'); e.type = j.type; throw e; }
  return j;
}
let toastTimer;
function toast(msg, bad = false) {
  const t = $('#toast');
  t.innerHTML = (bad ? '⚠ ' : '✓ ') + esc(msg);
  t.className = 'toast' + (bad ? ' bad' : '');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add('hidden'), 4200);
}
function busy(b, on, text) {
  if (!b) return;
  if (on) { b.dataset.old = b.textContent; b.classList.add('loading'); b.disabled = true; if (text) b.textContent = text; }
  else { b.classList.remove('loading'); b.textContent = b.dataset.old || b.textContent; b.disabled = false; }
}
/* ---------- 页面定位（多页面：每个功能是独立 HTML 页面） ---------- */
function panelOf(tool) { return $(`.panel[data-panel="${tool}"]`) || $('.panel'); }
function setMeta(tool, text, bad) {
  const el = $('[data-meta]', panelOf(tool)); if (el) { el.innerHTML = text; el.classList.toggle('bad', !!bad); }
}

/* ---------- 状态条 ---------- */
async function refreshStatus() {
  try {
    const d = (await api('/api/status')).data, q = d.quota || {}, c = d.categories || {}, ca = d.cache || {};
    const used = q.creditUsed ?? '?', limit = q.creditLimit ?? '?';
    const left = (limit === '?' || used === '?') ? '?' : (limit - used);
    $('#statsBar').innerHTML = `
      <div class="stat"><b>${fmt(used)}</b><span>已用积分</span></div>
      <div class="stat"><b>${fmt(left)}</b><span>剩余积分</span></div>
      <div class="stat"><b>${fmt(d.today_spent_local)}</b><span>今日消耗</span></div>
      <div class="stat"><b>${fmt(ca.hits || 0)}</b><span>缓存命中</span></div>
      <div class="stat"><b>${fmt(d.products || 0)}</b><span>落库商品</span></div>
      <div class="stat ${d.fused ? 'danger' : ''}"><b>${d.fused ? '熔断' : '正常'}</b><span>数据源</span></div>`;
    const hq = $('#headQuota'); if (hq) hq.textContent = '积分 ' + fmt(left);
    const ct = $('#catTotal'); if (ct) ct.textContent = fmt(c.total || 0);
  } catch (e) {
    $('#statsBar').innerHTML = `<span class="stat danger"><b>状态失败</b><span>${esc(e.message)}</span></span>`;
  }
}

/* 页面切换 = 导航栏跳转真实页面（index.html / hotwords.html / ...），无单页切换逻辑 */

/* ---------- 类目树 ---------- */
function catLabel(n) { return n.cn && n.cn !== n.id ? n.cn : (n.id || ''); }
function renderTree(container, nodes, level) {
  if (!nodes || !nodes.length) { container.innerHTML = '<div class="placeholder"><div class="ph-title">没有子类目</div></div>'; return; }
  container.innerHTML = nodes.map(n => {
    const id = esc(n.id), kids = n.children || 0;
    const named = n.named !== undefined ? n.named : !!(n.cn && n.cn !== n.id);
    const on = state.selectedCats.has(n.id) ? 'checked' : '';
    return `<div class="cnode ${on ? 'selected' : ''}" data-id="${id}" data-level="${level}" data-kids="${kids}" data-name="${esc(catLabel(n))}">
      <span class="arrow">${kids ? '▸' : '·'}</span>
      <input type="checkbox" class="catck" ${on}>
      <span class="node-name ${named ? '' : 'unnamed'}" title="${esc(n.cn_path || n.id)}">${esc(catLabel(n))}</span>
      <span class="node-id">${kids || ''}</span></div><div class="kids hidden"></div>`;
  }).join('');
}
async function loadTree() {
  try { renderTree($('#catTree'), (await api('/api/categories?level=1')).data, 1); }
  catch (e) { $('#catTree').innerHTML = `<div class="placeholder"><div class="ph-title">加载失败</div><div class="ph-desc">${esc(e.message)}</div></div>`; }
}
function renderSelChips() {
  const box = $('#selChips'), n = state.selectedCats.size;
  $('#catSelCount').textContent = n;
  if (state.catsExpanded) {
    box.classList.remove('hidden'); $('#catToggle').textContent = '收起';
    box.innerHTML = n ? [...state.selectedCats].map(id =>
      `<span class="selchip" data-id="${esc(id)}"><span>${esc(state.catNames.get(id) || id)}</span><i title="移除">×</i></span>`).join('')
      : '<span class="muted">未选择（默认全站）</span>';
  } else {
    box.classList.add('hidden'); box.innerHTML = '';
    $('#catToggle').textContent = n ? `展开 (${n})` : '展开';
  }
}
async function toggleCat(node, checked) {
  const id = node.dataset.id, level = Number(node.dataset.level), name = node.dataset.name || id;
  state.catNames.set(id, name);
  if (level >= 3) {
    checked ? state.selectedCats.add(id) : state.selectedCats.delete(id);
  } else {
    try {
      const leaves = (await api('/api/category/leaves?parent=' + encodeURIComponent(id) + '&limit=20')).data || [];
      leaves.forEach(l => {
        checked ? state.selectedCats.add(l.id) : state.selectedCats.delete(l.id);
        state.catNames.set(l.id, l.cn && l.cn !== l.id ? l.cn : l.id);
      });
      toast(checked ? `已选「${name}」下 ${leaves.length} 个三级类目（官方单次上限 20）` : `已取消「${name}」下 ${leaves.length} 个类目`);
    } catch (e) { toast(e.message, true); }
  }
  node.classList.toggle('selected', checked);
  renderSelChips();
  saveCats();
}
/* ---------- 类目树（仅带侧栏的页面：在线选品 / 市场热词 / 类目大盘） ---------- */
function bindSidebar() {
  if (!$('#catTree')) return;   // 当前页面没有类目树，跳过
$('#catTree').addEventListener('click', async e => {
  const node = e.target.closest('.cnode'); if (!node) return;
  const kids = node.nextElementSibling;
  if (e.target.classList.contains('arrow') && node.dataset.kids !== '0') {
    if (!kids.classList.contains('hidden')) { kids.classList.add('hidden'); node.querySelector('.arrow').textContent = '▸'; return; }
    kids.innerHTML = '<div class="empty">加载中…</div>'; kids.classList.remove('hidden');
    node.querySelector('.arrow').textContent = '▾';
    try {
      const j = await api('/api/categories?parent=' + encodeURIComponent(node.dataset.id));
      renderTree(kids, j.data, Number(node.dataset.level) + 1);
    } catch (err) { kids.innerHTML = `<div class="empty">${esc(err.message)}</div>`; }
    return;
  }
  if (e.target.classList.contains('catck')) { await toggleCat(node, e.target.checked); return; }
  const ck = node.querySelector('.catck'); ck.checked = !ck.checked; await toggleCat(node, ck.checked);
  // 点类目名时，同步填到当前需要类目 ID 的页面
  const cur = state.tool;
  if (cur === 'category') {
    const inp = $('[data-f="category_id"]', panelOf('category'));
    if (inp) { inp.value = node.dataset.id; toast('已填入类目 ID，点「查大盘」'); }
  } else if (cur === 'hotwords') {
    // 热词页类目走 category_ids
  }
});
$('#selChips').addEventListener('click', e => {
  if (!e.target.matches('i')) return;
  const chip = e.target.closest('.selchip'); const id = chip.dataset.id;
  state.selectedCats.delete(id); renderSelChips(); saveCats();
  $$('#catTree .cnode').forEach(n => {
    if (n.dataset.id === id) { const ck = n.querySelector('.catck'); if (ck) ck.checked = false; n.classList.remove('selected'); }
  });
});
$('#catSearch').addEventListener('keydown', async e => {
  if (e.key !== 'Enter') return;
  const q = e.target.value.trim(); if (!q) return loadTree();
  try {
    const j = await api('/api/categories?q=' + encodeURIComponent(q));
    renderTree($('#catTree'), j.data.map(n => ({ ...n, children: 0, named: !!n.cn })), 3);
  } catch (err) { toast(err.message, true); }
});
$('#catSearchClear').addEventListener('click', () => { $('#catSearch').value = ''; loadTree(); });
$('#catToggle').addEventListener('click', () => { state.catsExpanded = !state.catsExpanded; renderSelChips(); });
$('#catClear').addEventListener('click', () => {
  state.selectedCats.clear(); state.catNames.clear();
  $$('.catck', $('#catTree')).forEach(c => { c.checked = false; c.closest('.cnode').classList.remove('selected'); });
  renderSelChips(); saveCats(); toast('已清空类目选择');
});
}   // end bindSidebar

/* ---------- 预设（仅在线选品） ---------- */
const PRESETS = {
  all: {}, soaring: { monthlySalesRate_min: 20, sort: 'sales' },
  potential: { monthlySales_min: 30, monthlySalesRate_min: 10, reviewCount_max: 200, sort: 'sales' },
  hot: { monthlySales_min: 100, sort: 'revenue' }, fbs: { fulfillment: 'FBS' },
  boutique: { reviewRating_min: 4.7, reviewCount_min: 50 },
  new: { labels: '0', _quickDays: 30 }, cross: { cross_border: '1' }
};
const quickTabsEl = $('#quickTabs');
if (quickTabsEl) quickTabsEl.addEventListener('click', e => {
  const b = e.target.closest('.preset[data-preset]'); if (!b) return;
  $$('.preset').forEach(x => x.classList.remove('active')); b.classList.add('active');
  const form = $('form[data-tool="select"]'); if (form) form.reset();
  setQuickDays(0);
  const p = PRESETS[b.dataset.preset] || {};
  Object.entries(p).forEach(([k, v]) => {
    if (k === '_quickDays') return setQuickDays(v);
    $$(`[data-f="${k}"]`, panelOf('select')).forEach(el => {
      if (el.type === 'radio') el.checked = (el.value === String(v));
      else if (el.type === 'checkbox') el.checked = !!v;
      else el.value = v;
    });
  });
  renderAppliedTags('select');
  toast('已应用预设「' + b.querySelector('.pname').textContent + '」');
});
function setQuickDays(days) {
  state.quickDays = Number(days) || 0;
  $$('[data-quickdate] button').forEach(b => b.classList.toggle('on', Number(b.dataset.days) === state.quickDays));
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-quickdate] button[data-days]'); if (!b) return;
  setQuickDays(b.dataset.days);
  const form = b.closest('form');
  if (form) { const f = $('[data-f="date_from"]', form), t = $('[data-f="date_to"]', form); if (f) f.value = ''; if (t) t.value = ''; }
  renderAppliedTags('select');
});

/* ---------- 表单收集（通用） ---------- */
function collectForm(tool) {
  const form = $(`form[data-tool="${tool}"]`);
  const f = {};
  if (!form) return f;
  $$('[data-f]', form).forEach(el => {
    const k = el.dataset.f; let v;
    if (el.type === 'radio') { if (!el.checked) return; v = el.value; }
    else if (el.type === 'checkbox') { if (!el.checked) return; v = true; }
    else v = el.value.trim();
    if (v === '' || v === false) return;
    if (el.type === 'number' && v !== '') v = Number(v);
    f[k] = v;
  });
  // 重量：界面 kg → 官方 g
  if (f.weight_kg_min !== undefined) f.weight_min = Number(f.weight_kg_min) * 1000;
  if (f.weight_kg_max !== undefined) f.weight_max = Number(f.weight_kg_max) * 1000;
  delete f.weight_kg_min; delete f.weight_kg_max;
  // 列表类字段统一成数组（后端 as_list 也能吃逗号串，这里显式处理更稳）
  ['keywords', 'include_keywords', 'exclude_keywords', 'seller_names', 'brands',
    'skus', 'category_ids', 'labels'].forEach(k => {
    if (typeof f[k] === 'string') f[k] = f[k].split(/[,，\s]+/).filter(Boolean);
  });
  // 在线选品：搜索类型分流 + 商品链接提 SKU + 日期 + 类目
  if (tool === 'select') {
    const st = f.search_type || 'keywords', sv = f.search_value;
    delete f.search_type; delete f.search_value;
    if (sv) f[st] = (f[st] ? [].concat(f[st], sv.split(/[,，\s]+/).filter(Boolean)) : sv.split(/[,，\s]+/).filter(Boolean));
    const extra = [f.skus_extra, f.product_url].filter(Boolean).join(',');
    delete f.skus_extra; delete f.product_url;
    if (extra) f.skus = (f.skus || []).concat(extra.split(/[,，\s]+/).filter(Boolean));
    const d1 = f.date_from, d2 = f.date_to;
    delete f.date_from; delete f.date_to;
    if (d1) f.up_time_from = Date.parse(d1 + 'T00:00:00');
    if (d2) f.up_time_to = Date.parse(d2 + 'T23:59:59');
    if (state.quickDays && !d1 && !d2) {
      f.up_time_from = Date.now() - state.quickDays * 86400000;
      f.creation_date = state.quickDays <= 30 ? 1 : state.quickDays <= 90 ? 3
        : state.quickDays <= 180 ? 6 : state.quickDays <= 365 ? 12 : 24;
      f._date_label = '近' + (state.quickDays > 365 ? '2年' : state.quickDays + '天');
    } else if (d1 || d2) f._date_label = (d1 || '…') + ' ~ ' + (d2 || '…');
    if (state.selectedCats.size) f.category_ids = [...state.selectedCats].slice(0, 20);
    if (f.brand_type === 0 || f.brand_type === '0') f.brand_type = 0;
  }
  if (tool === 'category' && !f.category_id && state.selectedCats.size) {
    f.category_id = [...state.selectedCats][0];
  }
  return f;
}

/* ---------- 已选条件标签 ---------- */
const LAB = {
  price_min: '价格 ≥', price_max: '价格 ≤', monthlySales_min: '月销 ≥', monthlySales_max: '月销 ≤',
  monthlyRevenue_min: '月GMV ≥', monthlyRevenue_max: '月GMV ≤', monthlySalesRate_min: '环比 ≥', monthlySalesRate_max: '环比 ≤',
  reviewCount_min: '评论 ≥', reviewCount_max: '评论 ≤', reviewRating_min: '评分 ≥', reviewRating_max: '评分 ≤',
  grossMargin_min: '毛利率 ≥', grossMargin_max: '毛利率 ≤', convToCartPdp_min: '加购率 ≥', convToCartPdp_max: '加购率 ≤',
  drr_min: 'DRR ≥', drr_max: 'DRR ≤', returnCancellationRate_min: '退货率 ≥', returnCancellationRate_max: '退货率 ≤',
  questionsAndAnswers_min: '问答 ≥', questionsAndAnswers_max: '问答 ≤', ratingsRate_min: '评分增长 ≥', ratingsRate_max: '评分增长 ≤',
  weight_min: '重量 ≥', weight_max: '重量 ≤', volume_min: '体积 ≥', volume_max: '体积 ≤',
  variants_min: '变体 ≥', variants_max: '变体 ≤', sellers_min: '卖家 ≥', sellers_max: '卖家 ≤',
  searchVolume_min: '搜索量 ≥', searchVolume_max: '搜索量 ≤', searchChange30_min: '增长 ≥', searchChange30_max: '增长 ≤',
  products_min: '竞品 ≥', products_max: '竞品 ≤', marketSpace_min: '空间 ≥', marketSpace_max: '空间 ≤',
  productViews_min: '浏览 ≥', productViews_max: '浏览 ≤', conversionSharing_min: '转化 ≥', conversionSharing_max: '转化 ≤',
  reviews_min: '评论 ≥', reviews_max: '评论 ≤', ratings_min: '评分 ≥', ratings_max: '评分 ≤',
  relevancy_min: '相关度 ≥', relevancy_max: '相关度 ≤', titleDensity_min: '密度 ≥', titleDensity_max: '密度 ≤',
  wordCount_min: '词数 ≥', wordCount_max: '词数 ≤', adRivalCount_min: '广告对手 ≥', adRivalCount_max: '广告对手 ≤',
  uniqQueriesWCa_min: '唯一搜索 ≥', uniqQueriesWCa_max: '唯一搜索 ≤', ca_min: 'CA ≥', ca_max: 'CA ≤',
  exposure_min: '曝光 ≥', exposure_max: '曝光 ≤', conversion_min: '转化 ≥', conversion_max: '转化 ≤',
  naturalRank_min: '自然排名 ≥', naturalRank_max: '自然排名 ≤', adRank_min: '广告排名 ≥', adRank_max: '广告排名 ≤',
  keywords: '关键词', keyword: '种子词', skus: 'SKU', seller_names: '店铺', brands: '品牌',
  include_keywords: '包含词', exclude_keywords: '排除词', category_ids: '类目',
  fulfillment: '配送', labels: '标签', creation_date: '上架时间', search_date: '历史月',
  match_type: '匹配', has_variant: '剔除变体', date: '月份', tag: '标签词', sku: 'SKU',
  date_range: '区间', cross_border: '跨境', seller_type: '店铺类型', include_removed: '含下架',
  variations_merge: '变体合并', category_id: '类目ID', id: '店铺ID', limit: '条数'
};
function renderAppliedTags(tool) {
  const box = $('[data-tags]', panelOf(tool)); if (!box) return;
  const f = collectForm(tool), tags = [];
  Object.entries(f).forEach(([k, v]) => {
    if (k.startsWith('_') || k === 'force' || k === 'size' || k === 'sort' || k === 'direction') return;
    const lab = LAB[k]; if (!lab) return;
    let text = lab;
    if (Array.isArray(v)) { if (v.length) text += ' ' + v.slice(0, 3).join(',') + (v.length > 3 ? '…' : ''); else return; }
    else if (v !== true && v !== '') text += ' ' + v;
    if (k === 'cross_border') text = '跨境 ' + (v === '1' ? '是' : '否');
    if (k === 'seller_type') text = '店铺 ' + (v === '0' ? '本土' : '跨境');
    if (k === 'labels') text = Array.isArray(v) ? (v.map(x => ({ 0: '新品', 1: '正品', 2: '畅销品' }[x] || x)).join(',')) : ({ 0: '新品', 1: '正品', 2: '畅销品' }[v] || v);
    if (k === 'include_removed') text = '含已下架';
    if (k === 'variations_merge') text = v === '1' ? '合并变体' : '不合并变体';
    tags.push(`<span class="atag" data-k="${esc(k)}" data-tool="${esc(tool)}">${esc(text)}<i title="移除">×</i></span>`);
  });
  if (f._date_label) tags.push(`<span class="atag" data-k="_date" data-tool="${esc(tool)}">${esc(f._date_label)}<i title="移除">×</i></span>`);
  box.innerHTML = tags.length ? tags.join('') : '<span class="muted">无</span>';
}
document.addEventListener('click', e => {
  if (!e.target.matches('.atag i')) return;
  const tag = e.target.closest('.atag'), k = tag.dataset.k, tool = tag.dataset.tool;
  const form = $(`form[data-tool="${tool}"]`); if (!form) return;
  if (k === '_date') {
    setQuickDays(0);
    const f = $('[data-f="date_from"]', form), t = $('[data-f="date_to"]', form);
    if (f) f.value = ''; if (t) t.value = '';
  } else {
    $$(`[data-f="${k}"]`, form).forEach(el => {
      if (el.type === 'radio') { const first = $$(`[data-f="${k}"]`, form)[0]; if (first) first.checked = true; }
      else if (el.type === 'checkbox') el.checked = false;
      else el.value = '';
    });
  }
  renderAppliedTags(tool);
});
document.addEventListener('input', e => { const f = e.target.closest('form[data-tool]'); if (f) renderAppliedTags(f.dataset.tool); });
document.addEventListener('change', e => { const f = e.target.closest('form[data-tool]'); if (f) renderAppliedTags(f.dataset.tool); });

/* ---------- 表格渲染 ---------- */
function renderTable(sel, rows, cols) {
  const box = typeof sel === 'string' ? $(sel) : sel; if (!box) return;
  if (!rows || !rows.length) {
    box.innerHTML = `<div class="placeholder"><div class="ph-icon">◌</div><div class="ph-title">没有匹配的数据</div>
      <div class="ph-desc">试试放宽条件，或清空部分筛选项</div></div>`;
    return;
  }
  const isKw = cols.some(c => c[0] === 'query');
  const head = cols.map(([k, l]) => `<th data-k="${k}">${esc(l)}<span class="sortind"></span></th>`).join('');
  const body = rows.map(r => '<tr>' + cols.map(([k]) => {
    let v = r[k], cls = '', extra = '';
    if (k === 'sku' && !isKw) v = `<a href="javascript:;" class="sku-link" data-sku="${esc(r.sku)}">${esc(r.sku)}</a>`;
    else if (k === 'img') v = r.image_url ? `<img class="thumb" src="${esc(r.image_url)}" loading="lazy">` : '<div class="thumb" style="background:#eef2fb"></div>';
    else if (k === 'link') v = r.product_url ? `<a href="${esc(r.product_url)}" target="_blank" rel="noopener">打开 ↗</a>` : '';
    else if (k === 'title') { extra = ` title="${esc(v)}"`; v = `<span class="pname">${esc(String(v || '').slice(0, 58))}</span>`; }
    else if (k === 'opportunity') {
      const s = Number(v || 0), lvl = s >= 60 ? 'high' : s >= 40 ? 'mid' : 'low';
      v = `<span class="score ${lvl}">${fmt(s)}</span>`;
    } else if (k === 'sales_rate' || k === 'growth30' || k === 'revenue_rate') {
      const s = Number(v);
      if (isFinite(s)) v = `<span class="${s > 0 ? 'delta-up' : s < 0 ? 'delta-down' : ''}">${s > 0 ? '+' : ''}${fmt(s)}%</span>`;
      cls = 'num';
    } else if (k === 'up_time_date') {
      cls = 'dim';
    } else if (k === 'category_cn') {
      cls = 'dim'; v = esc(String(v || '—').slice(-22)); extra = ` title="${esc(r[k] || '')}"`;
    } else if (typeof v === 'number' || (v && !isNaN(v) && typeof v !== 'boolean')) {
      cls = 'num'; v = fmt(v) + (PCT_KEYS.has(k) ? '%' : '');
    }
    else v = esc(v);
    return `<td class="${cls}"${extra}>${v}</td>`;
  }).join('') + '</tr>').join('');
  box.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  $$('th', box).forEach(th => th.addEventListener('click', () => {
    const key = th.dataset.k, dir = state.sort === 'desc' ? 'asc' : 'desc';
    state.sort = dir;
    renderTable(box, rows.slice().sort((a, b) => {
      let x = a[key], y = b[key];
      if (x == null) return 1; if (y == null) return -1;
      const c = (typeof x === 'number' && typeof y === 'number') ? x - y : String(x).localeCompare(String(y), 'zh-CN');
      return dir === 'desc' ? -c : c;
    }), cols);
    const ind = $(`th[data-k="${key}"] .sortind`, box); if (ind) ind.textContent = dir === 'desc' ? ' ↓' : ' ↑';
  }));
}
document.addEventListener('click', e => {
  const a = e.target.closest('.sku-link'); if (a) { openDrawer(a.dataset.sku); return; }
  const card = e.target.closest('.pcard'); if (card && card.dataset.sku) openDrawer(card.dataset.sku);
});

/* ---------- 卡片视图（商品表专用，列表/卡片双模式） ---------- */
function agoText(days) {
  if (days == null) return '';
  if (days < 30) return `${days} 天前上架`;
  const m = Math.floor(days / 30);
  return m < 12 ? `${m} 个月前上架` : `${Math.floor(days / 365)} 年前上架`;
}
function renderCards(sel, rows) {
  const box = typeof sel === 'string' ? $(sel) : sel; if (!box) return;
  if (!rows || !rows.length) {
    box.innerHTML = `<div class="placeholder"><div class="ph-icon">◌</div><div class="ph-title">没有匹配的数据</div>
      <div class="ph-desc">试试放宽条件，或清空部分筛选项</div></div>`;
    return;
  }
  box.innerHTML = '<div class="cardgrid">' + rows.map(r => {
    const disc = Number(r.discount) || 0;
    const badge = disc > 0 ? `<span class="disc-badge">-${Math.round(disc)}%</span>` : '';
    const img = r.image_url ? `<img src="${esc(r.image_url)}" loading="lazy">` : '<div class="noimg">无图</div>';
    const rating = (r.review_rating != null)
      ? `<span class="c-star">★</span>${fmt(r.review_rating)} · ${fmt(r.review_count)} 条评论` : '';
    const ago = agoText(r.up_days);
    const rate = (rating || ago) ? `<div class="c-rate">${rating}${ago ? `<span class="c-ago">${esc(ago)}</span>` : ''}</div>` : '';
    const priceLine = `<div class="c-price"><b>${money(r.price)}</b> ₽` +
      (disc > 0 ? `<span class="c-disc">-${Math.round(disc)}%</span>` : '') +
      (r.sales != null ? `<span class="c-sales">月销 ${fmt(r.sales)}</span>` : '') + '</div>';
    return `<div class="pcard" data-sku="${esc(r.sku)}">
      <div class="c-img">${img}${badge}</div>
      <div class="c-body">
        <a class="c-title sku-link" data-sku="${esc(r.sku)}" title="${esc(r.title || '')}">${esc(String(r.title || '').slice(0, 64))}</a>
        ${rate}${priceLine}
        <div class="c-foot">SKU ${esc(r.sku)} · ${esc(String(r.category_cn || '—').slice(-18))}</div>
      </div></div>`;
  }).join('') + '</div>';
}

/* 视图切换：列表 ⇄ 卡片（商品表） */
function applyView() {
  if (!state.lastCols) return;
  const isProduct = state.lastCols.some(c => c[0] === 'title');
  const box = $('[data-table]', panelOf(state.tool));
  $$('[data-viewmode]').forEach(b => b.classList.toggle('on', b.dataset.viewmode === state.viewMode));
  if (box && isProduct && state.viewMode === 'card') renderCards(box, state.rows);
  else if (box) renderTable(box, state.rows, state.lastCols);
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-viewmode]'); if (!b) return;
  state.viewMode = b.dataset.viewmode;
  localStorage.setItem('sf_view', state.viewMode);
  applyView();
});

/* ---------- 汇总洞察 ---------- */
function renderSummary(tool, d, rows) {
  const box = $('[data-summary]', panelOf(tool)); if (!box) return;
  const n = rows.length;
  const avg = k => { const v = rows.map(r => Number(r[k])).filter(x => isFinite(x)); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const sum = k => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);
  const cards = [
    ['命中商品', fmt(d.total ?? n), (d.total ? '官方总数' : '本页 ' + n + ' 行')],
    ['平均价格', money(avg('price')) + ' ₽', '本页 ' + n + ' 行'],
    ['平均月销量', fmt(avg('sales')), '近 30 天'],
    ['平均月销售额', money(avg('revenue')) + ' ₽', '合计 ' + money(sum('revenue'))],
    ['平均评分', avg('review_rating') ? avg('review_rating').toFixed(2) : '—', '满分 5'],
    ['平均毛利率', avg('gross_margin') != null ? avg('gross_margin').toFixed(1) + '%' : '—', '官方估算']
  ];
  box.innerHTML = cards.map(([lab, val, sub]) =>
    `<div class="scard"><div class="sval">${esc(val)}</div><div class="slab">${esc(lab)}<br><span class="tiny">${esc(sub)}</span></div></div>`).join('');
}

/* ---------- 竞品详情渲染 ---------- */
function sparkline(data, key, color, label) {
  const vals = data.map(d => Number(d[key] || 0)), w = 620, h = 158, pad = 28;
  const max = Math.max(...vals, 1), min = Math.min(...vals, 0), rng = (max - min) || 1;
  const pts = vals.map((v, i) => `${pad + i * (w - 2 * pad) / Math.max(1, vals.length - 1)},${h - pad - (v - min) / rng * (h - 2 * pad)}`);
  const line = pts.length > 1 ? ` L${pts.slice(1).join(' L')}` : '';
  const area = `M${pts[0]}${line} L${w - pad},${h - pad} L${pad},${h - pad} Z`;
  return `<svg viewBox="0 0 ${w} ${h}" class="spark" preserveAspectRatio="none">
    <path d="${area}" fill="${color}" opacity=".12"/>
    <polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linejoin="round"/>
    <text x="${pad}" y="15" fill="#7c8aa5" font-size="11">${esc(label)} · 最高 ${fmt(max)}</text></svg>`;
}
function renderProductDetail(box, d) {
  const p = d.product || {}, s = d.summary || {}, t = d.trend || [], m = d.monthly || [];
  box.innerHTML = `<div class="pdetail">
    <div class="phead">${p.image_url ? `<img src="${esc(p.image_url)}" class="pimg">` : ''}
      <div><h3>${esc(p.title || p.sku)}</h3>
        <div class="tiny">${esc(p.brand || '')} · ${esc(p.seller || '')} · ${esc(p.category_cn || '')}</div>
        <div style="margin-top:8px">${p.product_url ? `<a class="btn primary sm" href="${esc(p.product_url)}" target="_blank" rel="noopener">在 Ozon 打开</a>` : ''}</div>
      </div></div>
    <div class="card-grid">
      <div class="card"><b>${fmt(p.price)} ₽</b><span>价格</span></div>
      <div class="card"><b>${fmt(s.total_sales)}</b><span>区间销量</span></div>
      <div class="card"><b>${money(s.total_revenue)}</b><span>区间销售额 ₽</span></div>
      <div class="card"><b>${fmt(s.daily_sales)}</b><span>日均销量</span></div>
      <div class="card"><b>${fmt(s.stock)}</b><span>库存</span></div>
      <div class="card"><b>${fmt(p.review_rating)}</b><span>评分</span></div>
      <div class="card"><b>${fmt(p.review_count)}</b><span>评论数</span></div>
      <div class="card"><b>${fmt(p.gross_margin)}%</b><span>毛利率</span></div>
      <div class="card"><b>${fmt(p.session_count_search)}</b><span>曝光量</span></div>
    </div>
    <h4>日销量趋势（${t.length} 天）</h4>${t.length ? sparkline(t, 'sales', '#2563eb', '日销量') : '<div class="empty">无趋势数据</div>'}
    <h4>日价格趋势</h4>${t.length ? sparkline(t, 'price', '#f59e0b', '价格 ₽') : ''}
    <h4>月度销量 / 销售额（${m.length} 个月）</h4>
    ${m.length ? `<table class="mini"><thead><tr><th>月份</th><th>销量</th><th>销售额 ₽</th></tr></thead><tbody>` +
      m.map(x => `<tr><td>${esc(x.date)}</td><td class="num">${fmt(x.sale)}</td><td class="num">${fmt(x.revenue)}</td></tr>`).join('') + '</tbody></table>' : '<div class="empty">无月度数据</div>'}
    <h4>类目排名</h4>
    ${(d.ranks || []).length ? `<div class="tiny">${d.ranks.map(r => `${esc(r.date)} 第 ${fmt(r.rank)} 名 / ${fmt(r.count)} 商品`).join(' · ')}</div>` : '<div class="empty">无排名数据</div>'}
    ${d.similar && d.similar.length ? `<h4>相似商品（${d.similar.length}）</h4><div class="tablewrap" id="similarTable"></div>` : ''}
  </div>`;
  if (d.similar && d.similar.length) {
    const sb = $('#similarTable');
    if (sb) renderTable(sb, d.similar, RESULT_COLS.slice(0, 10));
  }
}

/* ---------- 各页面查询 ---------- */
async function runTool(tool, btn) {
  const cfg = TOOL_CFG[tool]; if (!cfg) return;
  const b = btn || $(`form[data-tool="${tool}"] button[type="submit"]`);
  const f = collectForm(tool);
  const page = state.page[tool] || 1;
  busy(b, true, '查询中');
  setMeta(tool, '<span class="muted">请求中…（首次约 9 积分，命中缓存不扣费）</span>');
  try {
    let rows = [], note = '', d = {};
    if (tool === 'select') {
      f.page = page;
      const j = await api(cfg.api, { method: 'POST', body: { filters: f } });
      d = j.data; rows = d.rows || []; state.lastApplied = d.applied || {};
      note = `共命中 <b>${fmt(d.total ?? 0)}</b> 条 · ${j.meta.cached ? '命中缓存 0 积分' : '消耗 <b>' + j.meta.cost + ' 积分</b>'}`;
      renderSummary(tool, d, rows);
    } else if (tool === 'category') {
      if (!f.category_id) throw new Error('请填类目 ID（可点左侧类目树）');
      f.page = page;
      const j = await api(cfg.api, { method: 'POST', body: { category_id: f.category_id, filters: f } });
      d = j.data; rows = d.rows || [];
      renderSummary(tool, { total: (d.overview || {}).products, overview: d.overview }, rows);
      note = (d.hint ? esc(d.hint) + ' · ' : '') + `商品 ${rows.length} 行 · ${j.meta.cached ? '缓存 0 积分' : '消耗 ' + j.meta.cost + ' 积分'}`;
    } else if (tool === 'shop') {
      if (!f.id) throw new Error('请填店铺 ID');
      f.page = page;
      const j = await api(cfg.api, { method: 'POST', body: { id: Number(f.id), filters: f } });
      d = j.data; rows = d.rows || [];
      renderSummary(tool, { total: (d.summary || {}).productCount }, rows);
      note = `店铺商品 ${rows.length} 行 · ${j.meta.cached ? '缓存 0 积分' : '消耗 ' + j.meta.cost + ' 积分'}`;
    } else if (tool === 'hotwords' || tool === 'mining' || tool === 'backsearch') {
      if (tool === 'mining' && !f.keyword) throw new Error('请填种子词');
      if (tool === 'backsearch' && !(f.skus || []).length) throw new Error('请填竞品 SKU');
      f.page = page;
      const body = tool === 'mining' ? { keyword: f.keyword, filters: f }
        : tool === 'backsearch' ? { skus: f.skus, filters: f } : { filters: f };
      const j = await api(cfg.api, { method: 'POST', body });
      d = j.data; rows = d.rows || [];
      note = `${rows.length} 行 · ${j.meta.cached ? '缓存 0 积分' : '消耗 ' + j.meta.cost + ' 积分'}${d.total ? ' · 共 ' + fmt(d.total) : ''}`;
    } else if (tool === 'product') {
      if (!f.sku) throw new Error('请填商品 SKU');
      const q = `/api/product?sku=${encodeURIComponent(f.sku)}&date_range=${encodeURIComponent(f.date_range || 'past_30_days')}` + (f.similar ? '&similar=1' : '');
      const j = await api(q);
      renderProductDetail($('[data-table]', panelOf('product')), j.data);
      note = `竞品 ${esc(f.sku)} · 消耗约 20 积分`;
      setMeta(tool, note); refreshStatus(); busy(b, false, '查竞品'); return;
    } else if (tool === 'local_products' || tool === 'local_keywords') {
      const j = await api(`${cfg.api}?limit=${f.limit || 200}&sort=${f.sort || ''}`);
      rows = j.data || [];
      note = `${rows.length} 行 · <b>本地查询，0 积分</b>`;
    } else if (tool === 'logs') {
      const j = await api(`/api/logs?limit=${f.limit || 50}`);
      rows = (j.data.recent || []).map(l => ({
        query: (l.path || '').replace('/open-api/', ''), query_cn: l.ok ? 'OK' : (l.err || 'FAIL'),
        search_volume: l.elapsed_ms, growth30: l.cost, competing_products: l.cached ? 1 : 0
      }));
      note = `${rows.length} 条记录 · 本地查询`;
    }
    state.rows = rows;
    state.lastCols = cfg.cols;
    const tbox = $('[data-table]', panelOf(tool));
    if (tbox && cfg.cols.some(c => c[0] === 'title') && state.viewMode === 'card') renderCards(tbox, rows);
    else renderTable(tbox, rows, cfg.cols);
    const cnt = $('[data-count]', panelOf(tool)); if (cnt) cnt.textContent = fmt(rows.length);
    const nt = $('[data-note]', panelOf(tool)); if (nt) nt.textContent = '';
    renderPager(tool, d);
    setMeta(tool, note);
    renderAppliedTags(tool);
    refreshStatus();
  } catch (e) {
    setMeta(tool, '请求失败：' + esc(e.message) + (e.type ? '（' + esc(e.type) + '）' : ''), true);
    toast(e.message, true);
    renderAppliedTags(tool);
  } finally { busy(b, false); }
}
function renderPager(tool, meta) {
  const box = $('[data-pager]', panelOf(tool)); if (!box) return;
  const page = state.page[tool] || 1, pages = meta && meta.pages;
  const off = pages ? page >= pages : false;
  box.innerHTML = `<button class="btn ghost sm" data-d="-1" ${page <= 1 ? 'disabled' : ''}>← 上一页</button>
    <span>第 ${page} 页${pages ? ' / 共 ' + fmt(pages) + ' 页' : ''}</span>
    <button class="btn ghost sm" data-d="1" ${off ? 'disabled' : ''}>下一页 →</button>`;
  $$('button', box).forEach(b => b.onclick = () => {
    state.page[tool] = Math.max(1, page + Number(b.dataset.d)); runTool(tool);
  });
}

/* ---------- 通用绑定：每个页面的表单 / 重置 / 导出 / 请求参数 ---------- */
$$('form[data-tool]').forEach(form => {
  const tool = form.dataset.tool;
  form.addEventListener('submit', e => {
    e.preventDefault(); state.page[tool] = 1; runTool(tool);
  });
  const rst = $('[data-reset]', form);
  if (rst) rst.addEventListener('click', () => {
    form.reset();
    if (tool === 'select') { setQuickDays(0); $$('.preset').forEach((x, i) => x.classList.toggle('active', i === 0)); }
    state.page[tool] = 1;
    const cnt = $('[data-count]', panelOf(tool)); if (cnt) cnt.textContent = '0';
    renderTable($('[data-table]', panelOf(tool)), [], TOOL_CFG[tool].cols);
    const sum = $('[data-summary]', panelOf(tool)); if (sum) sum.innerHTML = '';
    setMeta(tool, '条件已重置。'); renderAppliedTags(tool); toast('已重置');
  });
  const exp = $('[data-export]', panelOf(tool));
  if (exp) exp.addEventListener('click', () => {
    if (!state.rows.length) return toast('请先查询出结果', true);
    doExport(state.rows, TOOL_CFG[tool].kind, exp);
  });
  const ap = $('[data-applied]', panelOf(tool));
  if (ap) ap.addEventListener('click', () => {
    $('#drawerTitle').textContent = '本次请求参数（官方 Body）';
    $('#drawerBody').innerHTML = `<div class="tiny">实际提交给官方接口的参数：</div>
      <pre class="json">${esc(JSON.stringify(state.lastApplied || {}, null, 2))}</pre>`;
    $('#drawer').classList.remove('hidden');
  });
});

async function doExport(rows, kind, btn) {
  const clean = rows.map(r => { const o = {}; for (const k in r) if (k !== 'raw' && k !== 'opportunity_parts') o[k] = r[k]; return o; });
  busy(btn, true, '导出中');
  try {
    const j = await api('/api/export', { method: 'POST', body: { kind, rows: clean } });
    const a = document.createElement('a'); a.href = j.data.url; a.download = j.data.file;
    document.body.appendChild(a); a.click(); a.remove();
    toast('已导出 ' + j.data.rows + ' 行 → ' + j.data.file);
  } catch (e) { toast(e.message, true); } finally { busy(btn, false, '导出 XLSX'); }
}

/* ---------- 商品抽屉（表格点 SKU） ---------- */
async function openDrawer(sku) {
  $('#drawer').classList.remove('hidden'); $('#drawerTitle').textContent = '商品 ' + sku;
  $('#drawerBody').innerHTML = '<div class="empty">加载中…</div>';
  try {
    const j = await api('/api/product?sku=' + encodeURIComponent(sku));
    const p = j.data.product || {}, s = j.data.summary || {}, t = j.data.trend || [];
    $('#drawerBody').innerHTML = `
      <div class="phead">${p.image_url ? `<img src="${esc(p.image_url)}" class="pimg">` : ''}
        <div><h3>${esc(p.title || sku)}</h3><div class="tiny">${esc(p.brand || '')} · ${esc(p.seller || '')}</div>
          <div style="margin-top:7px">${p.product_url ? `<a class="btn primary sm" href="${esc(p.product_url)}" target="_blank" rel="noopener">在 Ozon 打开</a>` : ''}</div></div></div>
      <div class="card-grid">
        <div class="card"><b>${fmt(p.price)} ₽</b><span>价格</span></div>
        <div class="card"><b>${fmt(s.total_sales)}</b><span>月销量</span></div>
        <div class="card"><b>${money(s.total_revenue)}</b><span>月销售额 ₽</span></div>
        <div class="card"><b>${fmt(p.review_rating)}</b><span>评分</span></div>
        <div class="card"><b>${fmt(p.review_count)}</b><span>评论数</span></div>
        <div class="card"><b>${fmt(s.stock)}</b><span>库存</span></div>
      </div>
      <div class="kv">
        <div>中文类目</div><div>${esc(p.category_cn || '—')}</div>
        <div>类目 ID</div><div>${esc(p.category_id || '—')}</div>
        <div>毛利率</div><div>${fmt(p.gross_margin)} %</div>
        <div>广告份额 DRR</div><div>${fmt(p.drr)} %</div>
        <div>加购率</div><div>${fmt(p.conv_to_cart_pdp)} %</div>
        <div>曝光量</div><div>${fmt(p.session_count_search)}</div>
        <div>上架天数</div><div>${fmt(p.up_days)}</div>
        <div>店铺类型</div><div>${esc(p.seller_type_text || '—')}</div>
        <div>配送</div><div>${esc(p.fulfillment_text || '—')}</div></div>
      <h4 style="margin:16px 0 8px;font-size:12.5px">日销量趋势（${t.length} 天）</h4>
      ${t.length ? sparkline(t, 'sales', '#2563eb', '日销量') : '<div class="empty">无趋势数据</div>'}`;
    refreshStatus();
  } catch (e) { $('#drawerBody').innerHTML = `<div class="empty" style="color:var(--bad)">${esc(e.message)}</div>`; }
}
$('#drawerClose').addEventListener('click', () => $('#drawer').classList.add('hidden'));
$('#drawer').addEventListener('click', e => { if (e.target.id === 'drawer') e.currentTarget.classList.add('hidden'); });
$('#btnRefresh').addEventListener('click', refreshStatus);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') $('#drawer').classList.add('hidden');
  if (e.key === 'Enter' && e.target.closest('form[data-tool]') && e.target.tagName !== 'BUTTON') {
    e.preventDefault();
    const form = e.target.closest('form[data-tool]'), tool = form.dataset.tool;
    state.page[tool] = 1; runTool(tool);
  }
});

/* ---------- 启动（多页面：只初始化当前页） ---------- */
const _q = new URLSearchParams(location.search);
$$('[data-viewmode]').forEach(b => b.classList.toggle('on', b.dataset.viewmode === state.viewMode));
refreshStatus();
bindSidebar();
if ($('#catTree')) {
  loadCats();
  loadTree();
  renderSelChips();
  const _cat = _q.get('cat');
  if (_cat) setTimeout(() => {
    state.selectedCats.add(_cat.trim()); state.catNames.set(_cat.trim(), _cat.trim());
    renderSelChips(); saveCats(); toast('已带入类目 ' + _cat.trim());
  }, 350);
  const _parent = _q.get('parent');
  if (_parent) setTimeout(async () => {
    try {
      const j = await api('/api/categories?parent=' + encodeURIComponent(_parent.trim()));
      renderTree($('#catTree'), j.data, _parent.split('_').length + 1);
    } catch (e) { toast(e.message, true); }
  }, 350);
}
if (_q.get('auto') === '1') setTimeout(() => runTool(state.tool), 800);
