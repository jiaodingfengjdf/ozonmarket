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
  ['fav', ''], ['img', ''], ['sku', 'SKU'], ['title', '商品标题'],
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
  ['opportunity', '机会分'],
  ['net_profit', '净利₽'], ['net_margin', '真毛利%'], ['breakeven', '保本价₽'], ['suggested', '建议售价₽'],
  ['link', '']
];
/* 率 / 占比 / 折扣类字段：数值后追加 % */
const PCT_KEYS = new Set(['discount', 'gross_margin', 'return_cancellation_rate',
  'conv_to_cart_search', 'conv_to_cart_pdp', 'conv_view_to_order',
  'order_conversion_rate', 'drr', 'promo_revenue_share', 'net_margin']);
/* 表格列 → 官方排序字段：能映射的走服务端排序（全量），映射不到的只排当前已加载行 */
const SORTMAP = {
  price: 'price', sales: 'sales', revenue: 'revenue', review_count: 'reviewCount',
  review_rating: 'reviewRating', gross_margin: 'grossMargin', views: 'views',
  session_count_search: 'sessionCountSearch', session_count: 'sessionCount',
  conv_to_cart_pdp: 'convToCartPdp', order_conversion_rate: 'orderConversionRate',
  drr: 'drr', return_cancellation_rate: 'returnCancellationRate', variants: 'variants',
  weight: 'weight', volume: 'volume', qa: 'questionsAndAnswers', up_time_date: 'upTime',
  search_volume: 'searchVolume', growth30: 'count30GrowthRate', avg_price: 'avgPrice',
  competing_products: 'competingProducts', sellers: 'sellers', market_space: 'marketSpace',
  conversion_sharing: 'conversionSharing', title_density: 'titleDensity',
  word_count: 'wordCount', relevancy: 'relevancy', exposure: 'exposure',
  conversion: 'conversion', natural_rank: 'naturalRank', ad_rank: 'adRank',
  opportunity: 'opportunity', net_margin: 'net_margin', net_profit: 'net_profit'
};
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
  viewMode: localStorage.getItem('sf_view') || 'table', lastCols: null,
  sortDir: 'desc', lastPageInfo: null, autoConfirm: false
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
  let timer = null;
  if (opts.timeoutMs) {
    const ctl = new AbortController();
    o.signal = ctl.signal;
    timer = setTimeout(() => ctl.abort(), opts.timeoutMs);
  }
  try {
    const r = await fetch(path, o);
    let j; try { j = await r.json(); } catch (e) { throw new Error('服务返回非 JSON（HTTP ' + r.status + '）'); }
    if (!j.ok) { const e = new Error(j.error || '请求失败'); e.type = j.type; throw e; }
    return j;
  } catch (e) {
    if (e && e.name === 'AbortError') throw new Error('请求超时（' + Math.round(opts.timeoutMs / 1000) + ' 秒）');
    throw e;
  } finally { if (timer) clearTimeout(timer); }
}
/* POST：后端要求二次确认（多页按页计费）时，弹一次确认再带 confirm 重发 */
async function postTool(path, body) {
  let j = await api(path, { method: 'POST', body });
  if (j.data && j.data.need_confirm && !state.autoConfirm) {
    const d = j.data;
    const est = d.estimated_credit != null ? d.estimated_credit : '?';
    if (!confirm(`${d.tip || '该操作会消耗积分'}（预估 ${est} 积分）\n\n确认继续？`)) {
      const e = new Error('已取消（原预估 ' + est + ' 积分）');
      e.cancelled = true; throw e;
    }
    j = await api(path, { method: 'POST', body: Object.assign({}, body, { confirm: true }) });
  }
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
  // 同名字段的复选框（如「词类型」自然/广告）需要收集成数组，不能只留最后一个
  const cbCount = {};
  $$('[data-f]', form).forEach(el => {
    if (el.type === 'checkbox' && el.dataset.f) cbCount[el.dataset.f] = (cbCount[el.dataset.f] || 0) + 1;
  });
  $$('[data-f]', form).forEach(el => {
    const k = el.dataset.f; let v;
    if (el.type === 'radio') { if (!el.checked) return; v = el.value; }
    else if (el.type === 'checkbox') {
      if (!el.checked) return;
      if (cbCount[k] > 1) { (f[k] = f[k] || []).push(el.value); return; }
      v = true;
    }
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
  // 市场热词接口的类目参数叫 categories（之前这里的勾选没送到后端，等于白勾）
  if (tool === 'hotwords' && state.selectedCats.size) {
    f.categories = [...state.selectedCats].slice(0, 20);
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
  types: '词类型',
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
    if (k === 'types') text = '词类型 ' + (Array.isArray(v) ? v : [v]).map(x => ({ 0: '自然搜索词', 1: '广告搜索词' }[x] || x)).join(',');
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
    else if (k === 'fav') {
      const on = favSet.has(String(r.sku));
      v = `<button type="button" class="favbtn${on ? ' on' : ''}" data-fav="${esc(r.sku)}" title="${on ? '取消收藏' : '收藏'}">${on ? '★' : '☆'}</button>`;
    }
    else if (k === 'img') v = r.image_url ? `<img class="thumb" src="${esc(r.image_url)}" loading="lazy">` : '<div class="thumb" style="background:#eef2fb"></div>';
    else if (k === 'link') v = r.product_url ? `<a href="${esc(r.product_url)}" target="_blank" rel="noopener">打开 ↗</a>` : '';
    else if (k === 'title') { extra = ` title="${esc(v)}"`; v = `<span class="pname">${esc(String(v || '').slice(0, 58))}</span>`; }
    else if (k === 'opportunity') {
      const s = Number(v || 0), lvl = s >= 60 ? 'high' : s >= 40 ? 'mid' : 'low';
      v = `<span class="score ${lvl}">${fmt(s)}</span>`;
    } else if (k === 'net_profit' || k === 'breakeven' || k === 'suggested') {
      const n = Number(v);
      cls = 'num';
      v = (v == null || !isFinite(n)) ? '—'
        : `<span class="${k === 'net_profit' && n < 0 ? 'delta-down' : ''}">${money(n)}</span>`;
    }
    else if (k === 'sales_rate' || k === 'growth30' || k === 'revenue_rate') {
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
    const key = th.dataset.k;
    const form = $(`form[data-tool="${state.tool}"]`);
    const sel = form && $('[data-f="sort"]', form);
    const dsel = form && $('[data-f="direction"]', form);
    const sf = SORTMAP[key];
    // 能映射到官方排序字段 → 改表单里的排序条件并重新查询（全量排序）
    if (sel && sf && [...sel.options].some(o => o.value === sf)) {
      const dir = state.sortDir === 'desc' ? 'ASC' : 'DESC';
      state.sortDir = dir.toLowerCase();
      sel.value = sf;
      if (dsel) dsel.value = dir;
      const label = (th.textContent || key).trim();
      state.page[state.tool] = 1;
      toast(`按「${label}」${dir === 'DESC' ? '降序' : '升序'}重新查询（服务端排序）`);
      runTool(state.tool);
      return;
    }
    // 官方无此排序字段 → 仅对当前已加载行排序，并明确提示
    const dir = state.sort === 'desc' ? 'asc' : 'desc';
    state.sort = dir;
    renderTable(box, rows.slice().sort((a, b) => {
      let x = a[key], y = b[key];
      if (x == null) return 1; if (y == null) return -1;
      const c = (typeof x === 'number' && typeof y === 'number') ? x - y : String(x).localeCompare(String(y), 'zh-CN');
      return dir === 'desc' ? -c : c;
    }), cols);
    const ind = $(`th[data-k="${key}"] .sortind`, box); if (ind) ind.textContent = dir === 'desc' ? ' ↓' : ' ↑';
    toast('该列官方接口不支持排序，仅对当前 ' + rows.length + ' 行排序', true);
  }));
}
document.addEventListener('click', e => {
  const so = e.target.closest('[data-sku-open]'); if (so && so.dataset.skuOpen) { openDrawer(so.dataset.skuOpen); return; }
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
      const j = await postTool(cfg.api, { filters: f });
      d = j.data; rows = d.rows || []; state.lastApplied = d.applied || {};
      note = `共命中 <b>${fmt(d.total ?? 0)}</b> 条 · ${j.meta.cached ? '命中缓存 0 积分' : '消耗 <b>' + j.meta.cost + ' 积分</b>'}`
        + (d.fetched_pages > 1 ? ` · 已抓取 ${d.fetched_pages} 页` : '');
      const lf = d.local_filter;
      if (lf && lf.fields.length) {
        note += `<br><span class="warn">${esc(lf.fields.join(' / '))} 只能本地过滤：本次 ${lf.before} 行中剔除 ${lf.filtered_out} 行，仅作用于${esc(lf.scope)}，不是全站</span>`;
      }
      renderSummary(tool, d, rows);
    } else if (tool === 'category') {
      if (!f.category_id) throw new Error('请填类目 ID（可点左侧类目树）');
      f.page = page;
      const j = await postTool(cfg.api, { category_id: f.category_id, filters: f });
      d = j.data; rows = d.rows || [];
      renderSummary(tool, { total: (d.overview || {}).products, overview: d.overview }, rows);
      note = (d.hint ? esc(d.hint) + ' · ' : '') + `商品 ${rows.length} 行 · ${j.meta.cached ? '缓存 0 积分' : '消耗 ' + j.meta.cost + ' 积分'}`
        + (d.fetched_pages > 1 ? ` · 已抓取 ${d.fetched_pages} 页` : '');
    } else if (tool === 'shop') {
      if (!f.id) throw new Error('请填店铺 ID');
      f.page = page;
      const j = await postTool(cfg.api, { id: Number(f.id), filters: f });
      d = j.data; rows = d.rows || [];
      renderSummary(tool, { total: (d.summary || {}).productCount }, rows);
      note = `店铺商品 ${rows.length} 行 · ${j.meta.cached ? '缓存 0 积分' : '消耗 ' + j.meta.cost + ' 积分'}`
        + (d.fetched_pages > 1 ? ` · 已抓取 ${d.fetched_pages} 页` : '');
    } else if (tool === 'hotwords' || tool === 'mining' || tool === 'backsearch') {
      if (tool === 'mining' && !f.keyword) throw new Error('请填种子词');
      if (tool === 'backsearch' && !(f.skus || []).length) throw new Error('请填竞品 SKU');
      f.page = page;
      const body = tool === 'mining' ? { keyword: f.keyword, filters: f }
        : tool === 'backsearch' ? { skus: f.skus, filters: f } : { filters: f };
      const j = await postTool(cfg.api, body);
      d = j.data; rows = d.rows || [];
      note = `${rows.length} 行 · ${j.meta.cached ? '缓存 0 积分' : '消耗 ' + j.meta.cost + ' 积分'}${d.total ? ' · 共 ' + fmt(d.total) : ''}`
        + (d.fetched_pages > 1 ? ` · 已抓取 ${d.fetched_pages} 页` : '');
    } else if (tool === 'product') {
      if (!f.sku) throw new Error('请填商品 SKU');
      const q = `/api/product?sku=${encodeURIComponent(f.sku)}&date_range=${encodeURIComponent(f.date_range || 'past_30_days')}` + (f.similar ? '&similar=1' : '');
      const j = await api(q);
      renderProductDetail($('[data-table]', panelOf('product')), j.data);
      note = `竞品 ${esc(f.sku)} · 消耗约 20 积分`;
      setMeta(tool, note); refreshStatus(); busy(b, false, '查竞品'); return;
    } else if (tool === 'local_products' || tool === 'local_keywords') {
      const size = Number(f.limit || 200) || 200;
      f.limit = size;
      f.offset = (page - 1) * size;
      const qs = new URLSearchParams();
      Object.entries(f).forEach(([k, v]) => {
        if (v === '' || v == null || k === 'force') return;
        qs.set(k, Array.isArray(v) ? v.join(',') : v);
      });
      const j = await api(`${cfg.api}?${qs.toString()}`);
      const d0 = j.data || {};
      rows = d0.rows || [];
      d = { total: d0.total || 0, pages: Math.max(1, Math.ceil((d0.total || 0) / size)) };
      note = `${rows.length} / ${fmt(d0.total || 0)} 行 · <b>本地查询，0 积分</b>`;
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
    state.lastPageInfo = d || null;
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
    if (e.cancelled) {
      setMeta(tool, '<span class="muted">' + esc(e.message) + '</span>');
      renderAppliedTags(tool);
      return;
    }
    setMeta(tool, '请求失败：' + esc(e.message) + (e.type ? '（' + esc(e.type) + '）' : ''), true);
    toast(e.message, true);
    renderAppliedTags(tool);
  } finally { busy(b, false); }
  }
function renderPager(tool, meta) {
  const box = $('[data-pager]', panelOf(tool)); if (!box) return;
  const page = state.page[tool] || 1;
  const pages = meta && meta.pages ? Number(meta.pages) : null;
  // 部分接口只给 hasNextPage（查类目 / 查店铺），没有总页数
  const hasNext = meta && meta.has_next_page != null ? !!meta.has_next_page : null;
  const off = pages ? page >= pages : (hasNext === false);
  box.innerHTML = `<button class="btn ghost sm" data-d="-1" ${page <= 1 ? 'disabled' : ''}>← 上一页</button>
    <span>第 ${page} 页${pages ? ' / 共 ' + fmt(pages) + ' 页' : (hasNext === false ? ' / 已到末页' : '')}</span>
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
  if (exp) exp.addEventListener('click', () => exportFlow(tool, exp));
  const ap = $('[data-applied]', panelOf(tool));
  if (ap) ap.addEventListener('click', () => {
    $('#drawerTitle').textContent = '本次请求参数（官方 Body）';
    $('#drawerBody').innerHTML = `<div class="tiny">实际提交给官方接口的参数：</div>
      <pre class="json">${esc(JSON.stringify(state.lastApplied || {}, null, 2))}</pre>`;
    $('#drawer').classList.remove('hidden');
  });
});

/* 导出：当前页只有 N 行时会主动提示「抓全量再导」，并给出积分预估 */
async function exportFlow(tool, btn) {
  if (!state.rows.length) return toast('请先查询出结果', true);
  const info = state.lastPageInfo || {};
  const total = Number(info.total || 0);
  const form = $(`form[data-tool="${tool}"]`);
  const sizeEl = form && $('[data-f="size"]', form);
  const pagesEl = form && $('[data-f="pages"]', form);
  const size = Number((sizeEl && sizeEl.value) || state.rows.length || 20) || 20;
  if (pagesEl && total > state.rows.length) {
    const maxPages = Math.min(10, Math.max(1, Math.ceil(total / size)));
    const est = Math.round(maxPages * 10);
    if (confirm(`当前只有 ${state.rows.length} 行，官方共命中 ${total} 行。\n\n是否抓取 ${maxPages} 页（最多约 ${est} 积分，命中缓存不扣费）后再导出？\n\n取消 = 只导出当前 ${state.rows.length} 行`)) {
      pagesEl.value = maxPages;
      state.autoConfirm = true;
      try { await runTool(tool, btn); } finally { state.autoConfirm = false; }
      if (!state.rows.length) return toast('抓取失败，未导出', true);
    }
  }
  doExport(state.rows, TOOL_CFG[tool].kind, btn);
}

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
    const j = await api('/api/product?sku=' + encodeURIComponent(sku) + '&trend=0');
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
        <div>重量</div><div>${p.weight == null ? '—' : fmt(p.weight) + ' g'}</div>
        <div>体积</div><div>${p.volume == null ? '—' : fmt(p.volume) + ' L'}</div>
        <div>尺寸</div><div>${esc(p.dimension || '—')}</div>
        <div>毛利率</div><div>${fmt(p.gross_margin)} %</div>
        <div>广告份额 DRR</div><div>${fmt(p.drr)} %</div>
        <div>加购率</div><div>${fmt(p.conv_to_cart_pdp)} %</div>
        <div>曝光量</div><div>${fmt(p.session_count_search)}</div>
        <div>上架天数</div><div>${fmt(p.up_days)}</div>
        <div>店铺类型</div><div>${esc(p.seller_type_text || '—')}</div>
        <div>配送</div><div>${esc(p.fulfillment_text || '—')}</div></div>
      <h4 style="margin:16px 0 8px;font-size:12.5px">日销量趋势（${t.length} 天）</h4>
      ${t.length ? sparkline(t, 'sales', '#2563eb', '日销量') : '<div class="empty">未查询趋势（抽屉默认省积分，需要看趋势请在「竞品详情」页查）</div>'}
      <div data-drawer-content class="drawer-content"><div class="empty">正在读取商品内容（属性/描述/图片）…</div></div>`;
    refreshStatus();
    loadDrawerContent(sku);
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

/* ================= 阶段 2：店铺品牌/类目结构 + 变体分析 + 评论分析 ================= */
function curSku() { const el = $('form[data-tool="product"] [data-f="sku"]'); return el ? el.value.trim() : ''; }
function curShopId() { const el = $('form[data-tool="shop"] [data-f="id"]'); return el ? el.value.trim() : ''; }

/* 简易表格：cols = [表头, 数据键, 类型(money|pct|text|num)] */
function miniTable(box, cols, rows, emptyText) {
  if (!box) return;
  if (!rows || !rows.length) {
    box.innerHTML = `<div class="placeholder"><div class="ph-title">没有数据</div><div class="ph-desc">${esc(emptyText || '')}</div></div>`;
    return;
  }
  const head = cols.map(([l]) => `<th>${esc(l)}</th>`).join('');
  const body = rows.map(r => '<tr>' + cols.map(([, k, kind]) => {
    const v = r[k];
    if (kind === 'text') return `<td>${esc(v == null || v === '' ? '—' : String(v))}</td>`;
    if (kind === 'money') return `<td class="num">${v == null ? '—' : money(v)}</td>`;
    if (kind === 'pct') return `<td class="num">${v == null ? '—' : fmt(v) + '%'}</td>`;
    return `<td class="num">${v == null ? '—' : fmt(v)}</td>`;
  }).join('') + '</tr>').join('');
  box.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

const BRAND_COLS = [['品牌', 'name', 'text'], ['销售额 ₽', 'revenue', 'money'], ['占本页%', 'page_share', 'pct'],
  ['Top10份额%', 'sharing', 'pct'], ['销量', 'sales'], ['商品数', 'products'], ['有销量商品', 'products_with_sales'],
  ['均价 ₽', 'avg_price', 'money'], ['均销', 'avg_sales'], ['均评分', 'avg_rating'], ['均评论', 'avg_reviews'],
  ['卖家数', 'sellers'], ['退货率%', 'return_rate', 'pct']];
const CAT_COLS = [['类目', 'cn_path', 'text'], ['销售额 ₽', 'revenue', 'money'], ['占本页%', 'page_share', 'pct'],
  ['销量', 'sales'], ['商品数', 'products'], ['均价 ₽', 'avg_price', 'money'],
  ['销额增长%', 'revenue_rate', 'pct'], ['销量增长%', 'sales_rate', 'pct']];
const VAR_COLS = [['SKU', 'sku', 'text'], ['变体特征', 'variation_text', 'text'], ['价格 ₽', 'price', 'money'],
  ['月销量', 'sales'], ['月销额 ₽', 'revenue', 'money'], ['评论数', 'review_count'],
  ['评分', 'review_rating'], ['上架', 'up_time_date', 'text']];

async function loadShopBrands(btn) {
  const id = curShopId(); if (!id) return toast('先填店铺 ID', true);
  busy(btn, true, '加载中');
  try {
    const j = await api('/api/shop/brands?id=' + encodeURIComponent(id) + '&size=50');
    const d = j.data || {}, t = d.top || {};
    miniTable($('[data-brand-table]'), BRAND_COLS, d.rows, '该店铺没有品牌数据（或该接口无权限）');
    $('[data-brand-count]').textContent = fmt((d.rows || []).length);
    $('[data-brand-meta]').innerHTML =
      `品牌总数 <b>${fmt(t.total)}</b> · 店铺总销额 <b>${money(t.total_revenue)}</b> ₽ · 总销量 <b>${fmt(t.total_sales)}</b>`
      + ` · Top10 销售额占比 <b>${t.revenue_share_top10 == null ? '—' : t.revenue_share_top10 + '%'}</b>`
      + ` · ${j.meta && j.meta.cached ? '命中缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分'}`;
    refreshStatus();
  } catch (e) { toast(e.message, true); $('[data-brand-meta]').textContent = '加载失败：' + e.message; }
  finally { busy(btn, false); }
}

async function loadShopCats(btn) {
  const id = curShopId(); if (!id) return toast('先填店铺 ID', true);
  busy(btn, true, '加载中');
  try {
    const j = await api('/api/shop/categories?id=' + encodeURIComponent(id) + '&size=50');
    const d = j.data || {};
    miniTable($('[data-cat-table]'), CAT_COLS, d.rows, '该店铺没有类目数据');
    $('[data-cat-count]').textContent = fmt((d.rows || []).length);
    $('[data-cat-meta]').innerHTML = `类目 ${(d.rows || []).length} 行 · 共 ${fmt(d.total)} 个`
      + ` · ${j.meta && j.meta.cached ? '命中缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分'}`;
    refreshStatus();
  } catch (e) { toast(e.message, true); $('[data-cat-meta]').textContent = '加载失败：' + e.message; }
  finally { busy(btn, false); }
}

async function loadVarList(btn) {
  const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
  busy(btn, true, '加载中');
  try {
    const j = await api('/api/variations?sku=' + encodeURIComponent(sku) + '&size=50');
    const rows = (j.data && j.data.rows) || [];
    miniTable($('[data-var-table]'), VAR_COLS, rows, '没有变体数据');
    $('[data-var-count]').textContent = fmt(rows.length);
    $('[data-var-meta]').innerHTML = `变体 <b>${rows.length}</b> 个 · 共 ${fmt(j.data.total)}`
      + ` · ${j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分'}`;
    refreshStatus();
  } catch (e) { toast(e.message, true); $('[data-var-meta]').textContent = '加载失败：' + e.message; }
  finally { busy(btn, false); }
}

async function loadVarChars(btn) {
  const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
  const box = $('[data-var-chars]');
  busy(btn, true, '加载中');
  try {
    const j = await api('/api/varchars?sku=' + encodeURIComponent(sku));
    const rows = (j.data && j.data.rows) || [];
    box.innerHTML = rows.length
      ? '<span class="muted">点维度看 Top10：</span>' + rows.map(c =>
        `<button class="chipbtn" data-char="${esc(c.sourceName || '')}">${esc(c.name || c.sourceName || '')}` +
        `<i>${esc(c.sourceName || '')}</i></button>`).join('')
      : '<span class="muted">该商品没有可用变体维度（或未返回）</span>';
    $('[data-var-meta]').innerHTML = `维度 ${rows.length} 个 · ${j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分'}`;
    refreshStatus();
  } catch (e) { toast(e.message, true); box.innerHTML = `<span class="muted">${esc(e.message)}</span>`; }
  finally { busy(btn, false); }
}

async function loadVarTop(char, btn) {
  const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
  busy(btn, true, '加载中');
  try {
    const j = await api('/api/vartop?sku=' + encodeURIComponent(sku) + '&characteristic=' + encodeURIComponent(char));
    const d = j.data || {}, rev = d.revenues || [], sal = d.sales || [];
    const map = new Map();
    rev.forEach((x, i) => map.set(x.name, { name: x.name, rank: i + 1, revenue: x.quantity }));
    sal.forEach((x, i) => { const o = map.get(x.name) || { name: x.name }; o.sales = x.quantity; o.salesRank = i + 1; map.set(x.name, o); });
    miniTable($('[data-var-table]'),
      [['特征值', 'name', 'text'], ['销额排名', 'rank'], ['销售额', 'revenue', 'money'], ['销量排名', 'salesRank'], ['销量', 'sales']],
      [...map.values()], '该维度没有数据');
    $('[data-var-meta]').innerHTML = `维度「<b>${esc(char)}</b>」Top10 · ${j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分'}`;
    refreshStatus();
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
}

const SIM_COLS = [['SKU', 'sku', 'text'], ['标题', 'title', 'text'], ['价格 ₽', 'price', 'money'],
  ['月销量', 'sales'], ['月销额 ₽', 'revenue', 'money'], ['库存', 'stock'], ['评论数', 'review_count'],
  ['评分', 'review_rating'], ['毛利率%', 'gross_margin', 'pct'], ['卖家', 'seller', 'text']];

async function loadSimilar(btn) {
  const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
  busy(btn, true, '加载中');
  try {
    const j = await api('/api/similar?sku=' + encodeURIComponent(sku));
    const rows = (j.data && j.data.rows) || [];
    miniTable($('[data-sim-table]'), SIM_COLS, rows, '没有相似商品');
    $('[data-sim-count]').textContent = fmt(rows.length);
    $('[data-sim-meta]').innerHTML = `相似 ${rows.length} 条（含目标商品）`
      + ` · ${j.meta && j.meta.cached ? '命中缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分'}`;
    refreshStatus();
  } catch (e) { toast(e.message, true); $('[data-sim-meta]').textContent = '加载失败：' + e.message; }
  finally { busy(btn, false); }
}

/* ---------- 评论分析 ---------- */
function revLang() { const s = $('[data-rev-lang]'); return s ? s.value : 'CN'; }

function renderRevStat(box, d) {
  const s = d.statistic || {};
  if (!s || s.reviewCount == null) {
    box.innerHTML = '<div class="empty">还没有该 SKU 的评论统计（可能未创建分析任务）</div>'; return;
  }
  const bars = [5, 4, 3, 2, 1].map(n => {
    const cn = { 5: 'fiveStarCount', 4: 'fourStarCount', 3: 'threeStarCount', 2: 'twoStarCount', 1: 'oneStarCount' }[n];
    const cp = { 5: 'fiveStarPercent', 4: 'fourStarPercent', 3: 'threeStarPercent', 2: 'twoStarPercent', 1: 'oneStarPercent' }[n];
    const c = s[cn] || 0, p = s[cp] || 0;
    return `<div class="barrow"><span class="barlab">${n}★</span>
      <span class="bar"><i style="width:${Math.min(100, p)}%"></i></span>
      <span class="barval">${fmt(c)} · ${fmt(p)}%</span></div>`;
  }).join('');
  box.innerHTML = `<div class="card-grid">
      <div class="card"><b>${fmt(s.reviewCount)}</b><span>评论总数</span></div>
      <div class="card"><b>${fmt(s.reviewRating)}</b><span>商品评分</span></div>
      <div class="card"><b>${s.avgRating == null ? '—' : fmt(s.avgRating)}</b><span>平均评分</span></div>
    </div>
    <div class="stars">${bars}</div>`;
}

function renderRevWords(box, d) {
  const chips = arr => (arr || []).slice(0, 150).map(w => `<span class="wchip">${esc(w)}</span>`).join('');
  const o = d.origin || [], c = d.sinicized || [];
  if (!o.length && !c.length) { box.innerHTML = '<div class="empty">没有词频数据（需先创建分析任务）</div>'; return; }
  box.innerHTML = `${c.length ? `<h4>中文词频（${c.length}）</h4><div class="wchips">${chips(c)}</div>` : ''}
    ${o.length ? `<h4>原文词频（${o.length}）</h4><div class="wchips">${chips(o)}</div>` : ''}`;
}

function renderRevOriginal(box, d) {
  const rows = (d.rows || []).slice(0, 60);
  if (!rows.length) { box.innerHTML = '<div class="empty">没有原始评论</div>'; return; }
  box.innerHTML = `<div class="revlist">` + rows.map(r => `
    <div class="revitem">
      <div class="revhead"><b>${'★'.repeat(Math.max(0, Math.min(5, Number(r.star) || 0)))}</b>
        <span class="muted">${esc(r.date || r.ruDate || '')} · ${esc(r.author || '匿名')}${r.skus ? ' · SKU ' + esc(r.skus) : ''}</span></div>
      <div class="revtext">${esc(r.text || '（无正文）')}</div>
      ${(r.photos && r.photos.length) ? `<div class="revphotos">${r.photos.slice(0, 6).map(u => `<img src="${esc(u)}" loading="lazy">`).join('')}</div>` : ''}
    </div>`).join('') + `</div>`;
}

const DIM_KEYS = ['advantages', 'disadvantages', 'usageScenarios', 'userCharacteristics', 'unmetNeeds',
  'timePoints', 'usageLocations', 'userBehavior', 'purchaseMotivations'];
const DIM_LABEL = { advantages: '优点', disadvantages: '缺点', usageScenarios: '使用场景', userCharacteristics: '用户特征',
  unmetNeeds: '未满足需求', timePoints: '使用时刻', usageLocations: '使用地点', userBehavior: '用户行为', purchaseMotivations: '购买动机' };

function renderRevReport(box, d) {
  const has = DIM_KEYS.some(k => (d[k] || []).length) || d.optSugges || d.qaAnalysis;
  if (!has) { box.innerHTML = '<div class="empty">没有报表数据（需先创建分析任务，再回来查报表）</div>'; return; }
  const dims = DIM_KEYS.map(k => {
    const arr = d[k] || [];
    if (!arr.length) return '';
    return `<h4>${DIM_LABEL[k]}（${arr.length}）</h4><div class="wchips">` + arr.map(x =>
      `<span class="wchip">${esc(x.dimensionCn || x.dimensionRu || '')}${x.count != null ? ` · ${fmt(x.count)}条` : ''}${x.proportion != null ? ` · ${(Number(x.proportion) * (Number(x.proportion) <= 1 ? 100 : 1)).toFixed(1)}%` : ''}</span>`).join('') + '</div>';
  }).join('');
  const kv = obj => obj ? Object.entries(obj).map(([k, v]) => `<div>${esc(k)}</div><div>${esc(v)}</div>`).join('') : '';
  box.innerHTML = dims
    + (d.optSugges ? `<h4>运营建议</h4><div class="kv">${kv(d.optSugges)}</div>` : '')
    + (d.qaAnalysis ? `<h4>问答分析</h4><div class="kv">${kv(d.qaAnalysis)}</div>` : '');
}

async function loadReview(kind, btn) {
  const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
  const box = $('[data-rev-box]');
  const label = { stat: '星级分布', words: '词频', original: '原始评论', report: 'AI 报表' }[kind];
  busy(btn, true, '加载中');
  try {
    const j = await api(`/api/reviews?sku=${encodeURIComponent(sku)}&type=${kind}&language=${revLang()}`);
    const d = j.data || {};
    if (kind === 'stat') renderRevStat(box, d);
    else if (kind === 'words') renderRevWords(box, d);
    else if (kind === 'original') renderRevOriginal(box, d);
    else renderRevReport(box, d);
    $('[data-rev-meta]').innerHTML = `${label} · 语言 ${esc(revLang())}`
      + ` · ${j.meta && j.meta.cached ? '命中缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分'}`;
    $('[data-rev-count]').textContent = kind === 'original' ? fmt(((d.rows) || []).length) : '';
    refreshStatus();
  } catch (e) {
    toast(e.message, true);
    box.innerHTML = `<div class="empty" style="color:var(--bad)">${esc(e.message)}</div>`;
    $('[data-rev-meta]').textContent = '加载失败：' + e.message;
  } finally { busy(btn, false); }
}

async function createRevTask(btn) {
  const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
  if (!confirm(`创建评论分析任务：官方按 200 积分/SKU 计费，且需要一段时间才出报表。\n\nSKU ${sku} · 语言 ${revLang()}\n\n确认创建？`)) return;
  busy(btn, true, '创建中');
  try {
    const j = await api('/api/reviews/task', { method: 'POST', body: { skus: [sku], confirm: true } });
    toast('任务已创建：' + JSON.stringify(j.data || {}).slice(0, 100));
    $('[data-rev-meta]').innerHTML = '任务已提交，稍后点「AI 报表 / 词频」查看结果（同一 SKU 已创建过就不必重复付费）。';
    refreshStatus();
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
}

document.addEventListener('click', e => {
  const b = e.target.closest('[data-act]');
  if (b) {
    const act = b.dataset.act;
    const fn = {
      'shop-brands': () => loadShopBrands(b), 'shop-cats': () => loadShopCats(b),
      'var-list': () => loadVarList(b), 'var-chars': () => loadVarChars(b),
      'rev-stat': () => loadReview('stat', b), 'rev-words': () => loadReview('words', b),
      'rev-original': () => loadReview('original', b), 'rev-report': () => loadReview('report', b),
      'rev-task': () => createRevTask(b), 'similar': () => loadSimilar(b),
      'profit': () => runProfit(b), 'export-report': () => exportReport(b),
      'content': () => loadContent(b)
    }[act];
    if (fn) { fn(); return; }
  }
  const ch = e.target.closest('[data-char]');
  if (ch) loadVarTop(ch.dataset.char, ch);
});

/* ================= 阶段 3：收藏 / 利润模型 / 本地库筛选 / 选品报告 ================= */
const favSet = new Set();

async function loadFavorites() {
  try {
    const j = await api('/api/favorites?limit=2000');
    (j.data.rows || []).forEach(r => favSet.add(String(r.sku)));
  } catch (e) { /* 收藏是增强功能，失败不影响主流程 */ }
}

document.addEventListener('click', async e => {
  const b = e.target.closest('[data-fav]');
  if (!b) return;
  e.preventDefault();
  const sku = b.dataset.fav;
  try {
    const j = await api('/api/favorites/toggle', { method: 'POST', body: { sku } });
    const on = !!(j.data && j.data.favorite);
    on ? favSet.add(sku) : favSet.delete(sku);
    b.classList.toggle('on', on);
    b.textContent = on ? '★' : '☆';
    toast(on ? `已收藏 ${sku}` : `已取消收藏 ${sku}`);
  } catch (err) { toast(err.message, true); }
});

/* 利润参数：界面输入 → 参数对象，并在 localStorage 记忆 */
const PROFIT_KEYS = ['cost_cny', 'rate_cny_rub', 'shipping_cny_per_kg', 'commission_pct',
  'payment_pct', 'drr_pct', 'return_pct', 'target_margin_pct', 'volumetric_divisor'];
const PROFIT_DEFAULTS = { cost_cny: '', rate_cny_rub: 12.5, shipping_cny_per_kg: 35,
  commission_pct: 15, payment_pct: 2, drr_pct: '', return_pct: 0,
  target_margin_pct: 20, volumetric_divisor: 5000 };

function profitParams() {
  const p = {};
  PROFIT_KEYS.forEach(k => {
    const el = $(`[data-profit="${k}"]`);
    if (!el) return;
    const v = String(el.value == null ? '' : el.value).trim();
    p[k] = v === '' ? null : Number(v);
  });
  return p;
}

function saveProfitParams() {
  const p = profitParams();
  try { localStorage.setItem('sf_profit', JSON.stringify(p)); } catch (e) { }
}

function restoreProfitParams() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('sf_profit') || '{}') || {}; } catch (e) { }
  PROFIT_KEYS.forEach(k => {
    const el = $(`[data-profit="${k}"]`);
    if (!el) return;
    const v = saved[k] != null ? saved[k] : PROFIT_DEFAULTS[k];
    if (v != null) el.value = v;
  });
}

async function runProfit(btn) {
  if (!state.rows.length) return toast('先查询出商品', true);
  if (!curToolHasProfit()) return toast('当前页面不支持利润计算', true);
  saveProfitParams();
  busy(btn, true, '计算中');
  try {
    const rows = state.rows.map(r => {
      const o = {}; for (const k in r) if (k !== 'raw' && k !== 'opportunity_parts') o[k] = r[k];
      return o;
    });
    const j = await api('/api/profit', { method: 'POST', body: { rows, params: profitParams() } });
    const d = j.data || {};
    state.profitRows = d.rows || [];
    state.profitSummary = d.summary || null;
    const onlyProfit = $('[data-profit-only]');
    state.rows = (onlyProfit && onlyProfit.checked)
      ? state.profitRows.filter(r => (Number(r.net_profit) || 0) > 0)
      : state.profitRows;
    state.lastCols = RESULT_COLS;
    const tbox = $('[data-table]', panelOf(state.tool));
    if (tbox && state.viewMode === 'card') renderCards(tbox, state.rows);
    else renderTable(tbox, state.rows, RESULT_COLS);
    const cnt = $('[data-count]', panelOf(state.tool)); if (cnt) cnt.textContent = fmt(state.rows.length);
    const s = state.profitSummary || {};
    const meta = $('[data-profit-meta]');
    if (meta) meta.innerHTML = `已按你的成本模型重算 <b>${fmt(s.rows)}</b> 行`
      + ` · 平均真毛利率 <b>${s.avg_net_margin == null ? '—' : s.avg_net_margin + '%'}</b>`
      + ` · 平均净利 <b>${s.avg_net_profit == null ? '—' : money(s.avg_net_profit) + ' ₽'}</b>`
      + ` · 亏损行 <b class="${(s.loss_rows || 0) ? 'warn' : ''}">${fmt(s.loss_rows)}</b>`
      + ` · 平均计费重 ${s.avg_chargeable_kg == null ? '—' : s.avg_chargeable_kg + ' kg'}`
      + `（0 积分，本地计算）`;
    toast('利润已计算：' + (onlyProfit && onlyProfit.checked ? '已过滤为盈利行' : '全部行'));
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
}

function curToolHasProfit() {
  return ['select', 'category', 'shop', 'local_products'].includes(state.tool)
    && !!$('#profitCard');
}

/* 选品报告：结论/参数 + 商品 + 收藏（多 sheet） */
async function exportReport(btn) {
  if (!state.rows.length) return toast('先查询出商品', true);
  busy(btn, true, '导出中');
  try {
    const fav = await api('/api/favorites?limit=2000').catch(() => ({ data: { rows: [] } }));
    const s = state.profitSummary || {};
    const meta = {
      '导出时间': new Date().toLocaleString('zh-CN'),
      '页面': state.tool,
      '筛选条件': JSON.stringify(collectForm(state.tool)),
      '利润参数': JSON.stringify(profitParams()),
      '命中总数': state.lastPageInfo && state.lastPageInfo.total != null ? state.lastPageInfo.total : '',
      '本表行数': state.rows.length,
      '平均真毛利率%': s.avg_net_margin == null ? '' : s.avg_net_margin,
      '平均净利₽': s.avg_net_profit == null ? '' : s.avg_net_profit,
      '亏损行数': s.loss_rows == null ? '' : s.loss_rows,
    };
    const rows = state.rows.map(r => {
      const o = {}; for (const k in r) if (k !== 'raw' && k !== 'opportunity_parts') o[k] = r[k];
      return o;
    });
    const body = { kind: 'report', rows, meta, favorites: (fav.data.rows || []),
      filename: 'seerfar_report_' + new Date().toISOString().slice(0, 10) };
    if (state.tool === 'hotwords' || state.tool === 'mining' || state.tool === 'backsearch') {
      body.keywords = rows; body.rows = [];
    }
    const j = await api('/api/export', { method: 'POST', body });
    const a = document.createElement('a'); a.href = j.data.url; a.download = j.data.file;
    document.body.appendChild(a); a.click(); a.remove();
    toast('报告已导出：' + j.data.file);
  } catch (e) { toast(e.message, true); }
  finally { busy(btn, false); }
}

/* ---------- 商品内容（Ozon composer：属性/描述/变体/图片/标签） ---------- */
function renderContent(box, d) {
  if (!box) return;
  const attrs = d.attributes || [], aspects = d.aspects || [], images = d.images || [], tags = d.tags || [];
  const kv = attrs.length
    ? `<h4>商品属性（${attrs.length}）</h4><div class="attrgrid">` +
      attrs.map(a => `<div class="akey">${esc(a.name || '—')}</div><div class="aval">${esc((a.values || []).join(' / ') || '—')}</div>`).join('') + '</div>'
    : '<div class="empty">没有属性数据</div>';
  const asp = aspects.length
    ? `<h4>变体维度（${aspects.length}）</h4>` + aspects.map(a => `
        <div class="aspectrow"><span class="aspectname">${esc(a.name)}</span>
        <span class="wchips">${(a.values || []).slice(0, 40).map(v =>
          `<a class="wchip" href="javascript:;" data-sku-open="${esc(v.sku || '')}" title="SKU ${esc(v.sku || '')}">${esc(v.value)}${v.price ? ' · ' + fmt(v.price) + '₽' : ''}</a>`).join('')}</span></div>`).join('')
    : '<div class="empty">没有变体维度</div>';
  const desc = d.description
    ? `<h4>描述（${d.description.length} 字）</h4><div class="descbox">${esc(d.description)}</div>`
    : '<h4>描述</h4><div class="empty">该商品没有文本描述</div>';
  const imgs = images.length
    ? `<h4>图片（${images.length}）</h4><div class="thumbs">` + images.slice(0, 24).map(u =>
        `<a href="${esc(u)}" target="_blank" rel="noopener"><img src="${esc(u)}" loading="lazy"></a>`).join('') + '</div>'
    : '';
  const tagbox = tags.length
    ? `<h4>标签（${tags.length}）</h4><div class="wchips">${tags.map(t => `<span class="wchip">${esc(t)}</span>`).join('')}</div>`
    : '';
  const rich = d.rich
    ? (typeof d.rich === 'string'
      ? `<h4>富文本</h4><div class="richdesc">${d.rich}</div>`
      : `<h4>富文本（${(d.rich.content || []).length} 个块）</h4><pre class="json">${esc(JSON.stringify(d.rich, null, 2)).slice(0, 6000)}</pre>`)
    : `<h4>富文本</h4><div class="empty">该商品没有富文本块（只有纯文本描述）。</div>`;
  const ex = d.extra || {};
  const exRows = [
    ['卖家', ex.seller], ['公司', ex.seller_company], ['工商注册号', ex.seller_psrn],
    ['店铺评分', ex.seller_rating], ['店铺评价/订单', ex.seller_reviews],
    ['卖家地址', ex.seller_address], ['诚信标志', ex.honest_sign],
    ['库存', ex.stock], ['提问数', ex.questions], ['产地', ex.country],
    ['类目路径', ex.category], ['货号', ex.offer_code], ['折扣%', ex.discount],
    ['图片数', ex.image_count],
  ].filter(([, v]) => v !== null && v !== undefined && v !== '');
  const extra = exRows.length
    ? `<h4>卖家与库存</h4><div class="attrgrid">` +
      exRows.map(([k, v]) => `<div class="akey">${esc(k)}</div><div class="aval">${esc(String(v))}</div>`).join('') + '</div>'
    : '';
  box.innerHTML = `<div class="contenthead">
      <b>${esc(d.title || '')}</b>
      <span class="muted">${esc(d.brand || '')}${d.rating ? ' · ★' + fmt(d.rating) : ''}${d.review_count ? ' · ' + fmt(d.review_count) + ' 条评论' : ''}${d.price ? ' · ' + money(d.price) + '₽' + (d.original_price ? '（原价 ' + money(d.original_price) + '₽）' : '') : ''}</span>
    </div>${extra}${kv}${asp}${desc}${tagbox}${imgs}${rich}`;
}

async function loadContent(btn) {
  const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
  const refresh = $('[data-content-refresh]');
  const box = $('[data-content-box]');
  busy(btn, true, '抓取中');
  $('[data-content-meta]').innerHTML = '正在用本机浏览器打开 Ozon 前台抓取（首次约 8~15 秒）…';
  try {
    const url = '/api/content?sku=' + encodeURIComponent(sku) + (refresh && refresh.checked ? '&refresh=1' : '');
    const j = await api(url);
    const d = j.data || {};
    renderContent(box, d);
    $('[data-content-count]').textContent = (d.attributes || []).length + '/' + (d.aspects || []).length;
    $('[data-content-note]').textContent = d.cached ? '缓存' : '刚抓取';
    const t = d.fetched_at ? new Date(d.fetched_at * 1000).toLocaleString('zh-CN') : '';
    $('[data-content-meta]').innerHTML = `SKU <b>${esc(d.sku || sku)}</b> · 来源 ${esc(d.source || 'ozon-composer')}`
      + ` · ${d.cached ? '命中本地缓存（0 请求）' : '实时抓取'} · 抓取时间 ${esc(t)} · <b>0 积分</b>`;
    toast(d.cached ? '已从缓存读取' : '内容抓取成功');
  } catch (e) {
    $('[data-content-meta]').innerHTML = '抓取失败：' + esc(e.message);
    box.innerHTML = `<div class="empty" style="color:var(--bad)">${esc(e.message)}</div>`;
    toast(e.message, true);
  } finally { busy(btn, false); }
}

/* ---------- 抽屉里的商品内容：打开即自动加载（有缓存秒出，没有就现抓） ---------- */
const _contentBusy = new Set();
async function loadDrawerContent(sku) {
  const box = $('[data-drawer-content]');
  if (!box) return;
  if (_contentBusy.has(sku)) return;      // 同一 SKU 正在抓取时不重复触发
  _contentBusy.add(sku);
  box.innerHTML = `<div class="drawer-loading">正在加载商品内容（属性 / 描述 / 变体维度 / 图片）…
    <div class="tiny" style="margin-top:6px">首次需要本机浏览器渲染 Ozon 前台，约 5~15 秒；之后缓存 72 小时，秒出。0 积分。</div></div>`;
  try {
    const j = await api('/api/content?sku=' + encodeURIComponent(sku), { timeoutMs: 180000 });
    const d = j.data || {};
    box.innerHTML = '';
    if (!d.sku && !d.title) {
      box.innerHTML = '<div class="empty">这个 SKU 没有拿到任何内容（可能已下架）</div>';
      return;
    }
    renderContent(box, d);
  } catch (e) {
    box.innerHTML = `<div class="empty" style="color:var(--bad)">商品内容加载失败：${esc(e.message)}
      <div class="tiny" style="margin-top:6px">关闭抽屉重开可重试；或到「竞品详情」页手动抓取。</div></div>`;
  } finally { _contentBusy.delete(sku); }
}

/* ---------- 启动（多页面：只初始化当前页） ---------- */

const _q = new URLSearchParams(location.search);
$$('[data-viewmode]').forEach(b => b.classList.toggle('on', b.dataset.viewmode === state.viewMode));
refreshStatus();
loadFavorites();
restoreProfitParams();
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
