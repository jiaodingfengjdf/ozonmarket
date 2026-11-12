/* ==========================================================================
   Seerfar Ozon 选品台 · Vue 3 SPA（无构建，Vue 全局版 + 预生成 schema）
   - 表单：由 tools/gen_vue_schema.py 从原页面生成，字段与旧版 1:1
   - 表格列：由原 app.js 抽出（cols.js）
   - 抽屉：只加载 0 积分的 Ozon 商品内容
   ========================================================================== */
(function () {
  const { createApp, ref, reactive, computed, watch, nextTick, onMounted } = Vue;
  const SCHEMA = window.__SCHEMA__ || { pages: [], nav: [] };
  const COLS = window.__COLS__ || { RESULT_COLS: [], KEYWORD_COLS: [], LOG_COLS: [], SORTMAP: {}, PCT_KEYS: [] };

  const PRESETS = {
    all: {}, soaring: { monthlySalesRate_min: 20, sort: 'sales' },
    potential: { monthlySales_min: 30, monthlySalesRate_min: 10, reviewCount_max: 200, sort: 'sales' },
    hot: { monthlySales_min: 100, sort: 'revenue' }, fbs: { fulfillment: 'FBS' },
    boutique: { reviewRating_min: 4.7, reviewCount_min: 50 },
    new: { labels: '0', _quickDays: 30 }, cross: { cross_border: '1' }
  };

  const TOOL_CFG = {
    select: { api: '/api/top', cols: COLS.RESULT_COLS, kind: 'products', post: true },
    hotwords: { api: '/api/hotwords', cols: COLS.KEYWORD_COLS, kind: 'keywords', post: true },
    mining: { api: '/api/mining', cols: COLS.KEYWORD_COLS, kind: 'keywords', post: true },
    backsearch: { api: '/api/backsearch', cols: COLS.KEYWORD_COLS, kind: 'keywords', post: true },
    category: { api: '/api/category', cols: COLS.RESULT_COLS, kind: 'products', post: true },
    shop: { api: '/api/shop', cols: COLS.RESULT_COLS, kind: 'products', post: true },
    local_products: { api: '/api/local/products', cols: COLS.RESULT_COLS, kind: 'products', get: true },
    local_keywords: { api: '/api/local/keywords', cols: COLS.KEYWORD_COLS, kind: 'keywords', get: true },
    logs: { api: '/api/logs', cols: COLS.LOG_COLS, kind: 'logs', get: true },
    product: { api: '/api/product', cols: COLS.RESULT_COLS, kind: 'product', get: true }
  };

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = n => (n === null || n === undefined || n === '' || Number.isNaN(Number(n))) ? '—'
    : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  const money = n => (n === null || n === undefined || n === '') ? '—' : fmt(n);

  async function api(path, opts) {
    opts = opts || {};
    const o = { method: opts.method || 'GET', headers: { 'Content-Type': 'application/json' } };
    if (opts.body) o.body = JSON.stringify(opts.body);
    let timer = null;
    if (opts.timeoutMs) {
      const ctl = new AbortController(); o.signal = ctl.signal;
      timer = setTimeout(() => ctl.abort(), opts.timeoutMs);
    }
    try {
      const r = await fetch(path, o);
      let j; try { j = await r.json(); } catch (e) { throw new Error('服务返回非 JSON（HTTP ' + r.status + '）'); }
      if (!j.ok) { const e = new Error(j.error || '请求失败'); e.type = j.type; throw e; }
      return j;
    } catch (e) {
      if (e && e.name === 'AbortError') throw new Error('请求超时');
      throw e;
    } finally { if (timer) clearTimeout(timer); }
  }
  async function postTool(path, body, autoConfirm) {
    let j = await api(path, { method: 'POST', body });
    if (j.data && j.data.need_confirm && !autoConfirm) {
      const d = j.data, est = d.estimated_credit != null ? d.estimated_credit : '?';
      if (!confirm((d.tip || '该操作会消耗积分') + '（预估 ' + est + ' 积分）\n\n确认继续？')) {
        const e = new Error('已取消（原预估 ' + est + ' 积分）'); e.cancelled = true; throw e;
      }
      j = await api(path, { method: 'POST', body: Object.assign({}, body, { confirm: true }) });
    }
    return j;
  }

  const App = {
    setup() {
      const pages = SCHEMA.pages;
      const byPath = {};
      pages.forEach(p => byPath[p.path] = p);
      const nav = SCHEMA.nav;

      const route = ref((location.hash || '#/select').replace(/^#/, ''));
      if (!byPath[route.value]) route.value = '/select';
      const page = computed(() => byPath[route.value] || byPath['/select']);
      const cfg = computed(() => TOOL_CFG[page.value.tool] || TOOL_CFG.select);

      const status = ref(null);
      const toastMsg = ref(''), toastBad = ref(false);
      const loading = ref(false);
      const rows = ref([]);
      const note = ref('');
      const pageNo = ref(1);
      const pageMeta = ref({});
      const viewMode = ref(localStorage.getItem('sf_view') || 'table');
      const formEl = ref(null);
      const quickDays = ref(0);
      const activePreset = ref('all');

      // 类目树
      const cats = ref([]);
      const catExpanded = reactive({});
      const selectedCats = ref([]);          // [{id,name,level}]
      const catSearch = ref('');
      const catPanelOpen = ref(false);

      // 竞品详情
      const product = ref(null);
      const content = ref(null);
      const contentLoading = ref(false);

      // 抽屉
      const drawerOpen = ref(false);
      const drawerSku = ref('');
      const drawerContent = ref(null);
      const drawerLoading = ref(false);
      const _busy = new Set();

      function toast(m, bad) {
        toastMsg.value = (bad ? '⚠ ' : '✓ ') + m; toastBad.value = !!bad;
        clearTimeout(toast._t); toast._t = setTimeout(() => { toastMsg.value = ''; }, 4200);
      }

      async function refreshStatus() {
        try {
          const d = (await api('/api/status')).data || {};
          const q = d.quota || {}, ca = d.cache || {}, c = d.categories || {};
          status.value = {
            used: q.creditUsed, limit: q.creditLimit,
            left: (q.creditUsed == null || q.creditLimit == null) ? null : (q.creditLimit - q.creditUsed),
            today: d.today_spent_local, hits: ca.hits || 0, products: d.products || 0,
            fused: !!d.fused, cats: c.total || 0
          };
        } catch (e) { toast('状态读取失败：' + e.message, true); }
      }

      /* ---------- 表单收集（与旧版逻辑一致） ---------- */
      function collectForm(tool) {
        const root = formEl.value; const f = {};
        if (!root) return f;
        const els = Array.from(root.querySelectorAll('[data-f]'));
        const cbCount = {};
        els.forEach(el => { if (el.type === 'checkbox') cbCount[el.dataset.f] = (cbCount[el.dataset.f] || 0) + 1; });
        els.forEach(el => {
          const k = el.dataset.f; let v;
          if (el.type === 'radio') { if (!el.checked) return; v = el.value; }
          else if (el.type === 'checkbox') {
            if (!el.checked) return;
            if (cbCount[k] > 1) { (f[k] = f[k] || []).push(el.value); return; }
            v = true;
          } else v = String(el.value || '').trim();
          if (v === '' || v === false) return;
          if (el.type === 'number' && v !== '') v = Number(v);
          f[k] = v;
        });
        if (f.weight_kg_min !== undefined) f.weight_min = Number(f.weight_kg_min) * 1000;
        if (f.weight_kg_max !== undefined) f.weight_max = Number(f.weight_kg_max) * 1000;
        delete f.weight_kg_min; delete f.weight_kg_max;
        ['keywords', 'include_keywords', 'exclude_keywords', 'seller_names', 'brands', 'skus', 'category_ids', 'labels']
          .forEach(k => { if (typeof f[k] === 'string') f[k] = f[k].split(/[,，\s]+/).filter(Boolean); });

        if (tool === 'select') {
          const st = f.search_type || 'keywords', sv = f.search_value;
          delete f.search_type; delete f.search_value;
          if (sv) f[st] = f[st] ? [].concat(f[st], sv.split(/[,，\s]+/).filter(Boolean)) : sv.split(/[,，\s]+/).filter(Boolean);
          const extra = [f.skus_extra, f.product_url].filter(Boolean).join(',');
          delete f.skus_extra; delete f.product_url;
          if (extra) f.skus = (f.skus || []).concat(extra.split(/[,，\s]+/).filter(Boolean));
          const d1 = f.date_from, d2 = f.date_to;
          delete f.date_from; delete f.date_to;
          if (d1) f.up_time_from = Date.parse(d1 + 'T00:00:00');
          if (d2) f.up_time_to = Date.parse(d2 + 'T23:59:59');
          if (quickDays.value && !d1 && !d2) {
            f.up_time_from = Date.now() - quickDays.value * 86400000;
            f.creation_date = quickDays.value <= 30 ? 1 : quickDays.value <= 90 ? 3
              : quickDays.value <= 180 ? 6 : quickDays.value <= 365 ? 12 : 24;
          }
          if (selectedCats.value.length) f.category_ids = selectedCats.value.slice(0, 20).map(c => c.id);
        }
        if (tool === 'category' && !f.category_id && selectedCats.value.length) f.category_id = selectedCats.value[0].id;
        if (tool === 'hotwords' && selectedCats.value.length) f.categories = selectedCats.value.slice(0, 20).map(c => c.id);
        if (f.brand_type === '0') f.brand_type = 0;
        return f;
      }

      function setField(k, v) {
        const root = formEl.value; if (!root) return;
        root.querySelectorAll('[data-f="' + k + '"]').forEach(el => {
          if (el.type === 'radio') el.checked = (el.value === String(v));
          else if (el.type === 'checkbox') el.checked = !!v;
          else el.value = v;
        });
      }

      function applyPreset(key) {
        activePreset.value = key;
        if (formEl.value) formEl.value.reset();
        quickDays.value = 0;
        const p = PRESETS[key] || {};
        Object.entries(p).forEach(([k, v]) => {
          if (k === '_quickDays') { quickDays.value = Number(v) || 0; return; }
          setField(k, v);
        });
        wireQuickdates();
        toast('已应用预设');
      }
      function wireQuickdates() {
        if (!formEl.value) return;
        formEl.value.querySelectorAll('[data-quickdate] button').forEach(b => {
          b.classList.toggle('on', Number(b.dataset.days) === quickDays.value);
        });
      }
      function formClick(e) {
        const q = e.target.closest('[data-quickdate] button[data-days]');
        if (q) {
          quickDays.value = Number(q.dataset.days) || 0;
          setField('date_from', ''); setField('date_to', '');
          wireQuickdates();
          e.preventDefault();
          return;
        }
        const rst = e.target.closest('[data-reset]');
        if (rst) { e.preventDefault(); resetForm(); }
      }
      function onPresetClick(e) {
        const b = e.target.closest('.preset[data-preset]');
        if (b) applyPreset(b.dataset.preset);
      }

      /* ---------- 查询 ---------- */
      async function run() {
        const tool = page.value.tool;
        if (tool === 'product') return runProduct();
        const c = TOOL_CFG[tool];
        const f = collectForm(tool);
        loading.value = true; note.value = '请求中…（首次约 9 积分，命中缓存不扣费）';
        try {
          let list = [], meta = {}, text = '';
          if (tool === 'select' || tool === 'category' || tool === 'shop') {
            f.page = pageNo.value;
            let body;
            if (tool === 'select') body = { filters: f };
            else if (tool === 'category') {
              if (!f.category_id) throw new Error('请填类目 ID（可点左侧类目树）');
              body = { category_id: f.category_id, filters: f };
            } else {
              if (!f.id) throw new Error('请填店铺 ID');
              body = { id: Number(f.id), filters: f };
            }
            const j = await postTool(c.api, body);
            const d = j.data || {};
            list = d.rows || [];
            meta = { total: d.total || (d.overview || {}).products, pages: d.pages, has_next_page: d.has_next_page };
            const cached = j.meta && j.meta.cached;
            text = '共 <b>' + fmt(meta.total || list.length) + '</b> 条 · ' + (cached ? '命中缓存 0 积分' : '消耗 <b>' + (j.meta ? j.meta.cost : '?') + ' 积分</b>');
            if (d.local_filter && d.local_filter.fields && d.local_filter.fields.length) {
              text += '<br><span class="warn">' + esc(d.local_filter.fields.join(' / ')) + ' 只能本地过滤</span>';
            }
          } else if (tool === 'hotwords' || tool === 'mining' || tool === 'backsearch') {
            f.page = pageNo.value;
            if (tool === 'mining' && !f.keyword) throw new Error('请填种子词');
            if (tool === 'backsearch' && !(f.skus || []).length) throw new Error('请填竞品 SKU');
            const body = tool === 'mining' ? { keyword: f.keyword, filters: f }
              : tool === 'backsearch' ? { skus: f.skus, filters: f } : { filters: f };
            const j = await postTool(c.api, body);
            const d = j.data || {}; list = d.rows || [];
            meta = { total: d.total, pages: d.pages, has_next_page: d.has_next_page };
            text = list.length + ' 行 · ' + (j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta ? j.meta.cost : '?') + ' 积分');
          } else if (tool === 'local_products' || tool === 'local_keywords') {
            const size = Number(f.limit || 200) || 200;
            f.limit = size; f.offset = (pageNo.value - 1) * size;
            const qs = new URLSearchParams();
            Object.entries(f).forEach(([k, v]) => { if (v === '' || v == null) return; qs.set(k, Array.isArray(v) ? v.join(',') : v); });
            const j = await api(c.api + '?' + qs.toString());
            const d0 = j.data || {}; list = d0.rows || [];
            meta = { total: d0.total || 0, pages: Math.max(1, Math.ceil((d0.total || 0) / size)) };
            text = list.length + ' / ' + fmt(d0.total || 0) + ' 行 · <b>本地查询，0 积分</b>';
          } else if (tool === 'logs') {
            const j = await api('/api/logs?limit=' + (f.limit || 50));
            list = ((j.data || {}).recent || []).map(l => ({
              query: String(l.path || '').replace('/open-api/', ''), query_cn: l.ok ? 'OK' : (l.err || 'FAIL'),
              search_volume: l.elapsed_ms, growth30: l.cost, competing_products: l.cached ? 1 : 0
            }));
            meta = {}; text = list.length + ' 条记录 · 本地查询';
          }
          rows.value = list; pageMeta.value = meta; note.value = text;
          localStorage.setItem('sf_rows_' + tool, '1');
          await nextTick();
        } catch (e) {
          if (e.cancelled) { note.value = '<span class="muted">' + esc(e.message) + '</span>'; }
          else { note.value = '请求失败：' + esc(e.message); toast(e.message, true); }
        } finally { loading.value = false; refreshStatus(); }
      }

      async function runProduct() {
        const f = collectForm('product');
        if (!f.sku) return toast('请填商品 SKU', true);
        loading.value = true; product.value = null; content.value = null;
        try {
          const q = '/api/product?sku=' + encodeURIComponent(f.sku) + '&date_range=' + encodeURIComponent(f.date_range || 'past_30_days');
          const j = await api(q, { timeoutMs: 120000 });
          product.value = j.data;
          note.value = '竞品 ' + esc(f.sku) + ' · 消耗约 20 积分';
          loadContent(f.sku);
          refreshStatus();
        } catch (e) { note.value = '查询失败：' + esc(e.message); toast(e.message, true); }
        finally { loading.value = false; }
      }

      async function loadContent(sku, force) {
        contentLoading.value = true;
        try {
          const j = await api('/api/content?sku=' + encodeURIComponent(sku) + (force ? '&refresh=1' : ''), { timeoutMs: 180000 });
          content.value = j.data || {};
        } catch (e) { content.value = { error: e.message }; toast('商品内容加载失败：' + e.message, true); }
        finally { contentLoading.value = false; }
      }

      async function openDrawer(sku) {
        drawerSku.value = sku; drawerOpen.value = true; drawerContent.value = null;
        if (_busy.has(sku)) return;
        _busy.add(sku); drawerLoading.value = true;
        try {
          const j = await api('/api/content?sku=' + encodeURIComponent(sku), { timeoutMs: 180000 });
          drawerContent.value = j.data || {};
        } catch (e) { drawerContent.value = { error: e.message }; }
        finally { drawerLoading.value = false; _busy.delete(sku); }
      }
      function closeDrawer() { drawerOpen.value = false; }

      async function toggleFav(row) {
        try {
          const sku = row.sku || row.product_id || row.id;
          const j = await api('/api/favorites/toggle', { method: 'POST', body: { sku } });
          row._fav = !!(j.data && j.data.fav);
          toast(row._fav ? '已收藏' : '已取消收藏');
        } catch (e) { toast(e.message, true); }
      }

      function resetForm() {
        if (formEl.value) formEl.value.reset();
        quickDays.value = 0; activePreset.value = 'all';
        rows.value = []; note.value = ''; pageNo.value = 1; pageMeta.value = {};
        product.value = null; content.value = null;
        wireQuickdates();
        toast('已重置');
      }

      async function exportXlsx() {
        if (!rows.value.length) return toast('没有可导出的数据', true);
        const kind = cfg.value.kind === 'keywords' ? 'keywords' : 'products';
        const clean = rows.value.map(r => { const o = {}; for (const k in r) if (k !== 'raw' && k !== 'opportunity_parts') o[k] = r[k]; return o; });
        try {
          const j = await api('/api/export', { method: 'POST', body: { kind, rows: clean } });
          const a = document.createElement('a'); a.href = j.data.url; a.download = j.data.file;
          document.body.appendChild(a); a.click(); a.remove();
          toast('已导出 ' + j.data.rows + ' 行');
        } catch (e) { toast(e.message, true); }
      }

      function go(delta) {
        pageNo.value = Math.max(1, pageNo.value + delta);
        run();
      }

      /* ---------- 单元格渲染 ---------- */
      const RATE_KEYS = new Set(['sales_rate', 'revenue_rate', 'ratings_rate', 'growth30']);
      function cell(row, key) {
        const v = row[key];
        if (key === 'fav') return row._fav ? '★' : '☆';
        if (key === 'img') return '';
        if (key === 'link') return row.url || row.product_url || '';
        if (key === 'sku') return row.sku || row.id || '';
        if (RATE_KEYS.has(key) && v != null) return (Number(v) >= 0 ? '+' : '') + fmt(v) + '%';
        if (COLS.PCT_KEYS.indexOf(key) >= 0 && v != null) return fmt(v) + '%';
        if (typeof v === 'number') return fmt(v);
        return v == null ? '—' : String(v);
      }
      function rateClass(row, key) {
        if (!RATE_KEYS.has(key)) return '';
        const v = Number(row[key]);
        return v > 0 ? 'delta-up' : v < 0 ? 'delta-down' : '';
      }

      /* ---------- 类目树 ---------- */
      async function loadCats(level, parent, into) {
        const q = '/api/categories?level=' + level + (parent ? '&parent=' + encodeURIComponent(parent) : '');
        const j = await api(q);
        const list = (j.data || []).map(n => ({
          id: n.id, name: n.cn || n.id, path: n.cn_path || '', kids: n.children || 0,
          named: n.named !== undefined ? n.named : !!(n.cn && n.cn !== n.id), level, open: false, children: null
        }));
        if (into) into.children = list; else cats.value = list;
      }
      async function toggleCatNode(n) {
        if (!n.kids) { toggleCat(n); return; }
        if (!n.children) await loadCats(n.level + 1, n.id, n);
        n.open = !n.open;
      }
      async function toggleCat(n) {
        const i = selectedCats.value.findIndex(c => c.id === n.id);
        if (i >= 0) { selectedCats.value.splice(i, 1); saveCats(); return; }
        if (n.level >= 3) { selectedCats.value.push({ id: n.id, name: n.name }); }
        else {
          const j = await api('/api/category/leaves?parent=' + encodeURIComponent(n.id) + '&limit=20');
          (j.data || []).forEach(l => { if (!selectedCats.value.some(c => c.id === l.id)) selectedCats.value.push({ id: l.id, name: l.cn || l.id }); });
        }
        saveCats();
      }
      function saveCats() { try { sessionStorage.setItem('sf_cats_vue', JSON.stringify(selectedCats.value)); } catch (e) { } }

      const catFiltered = computed(() => {
        const q = catSearch.value.trim().toLowerCase();
        return q ? cats.value.filter(n => n.name.toLowerCase().includes(q) || String(n.id).includes(q)) : cats.value;
      });

      /* ---------- 路由 ---------- */
      function onHash() {
        route.value = (location.hash || '#/select').replace(/^#/, '');
        if (!byPath[route.value]) route.value = '/select';
        pageNo.value = 1; rows.value = []; note.value = ''; product.value = null; content.value = null;
        nextTick(wireQuickdates);
      }
      watch(page, () => { nextTick(() => { wireQuickdates(); }); });

      onMounted(async () => {
        window.addEventListener('hashchange', onHash);
        refreshStatus();
        try {
          const saved = JSON.parse(sessionStorage.getItem('sf_cats_vue') || '[]');
          if (Array.isArray(saved)) selectedCats.value = saved;
        } catch (e) { }
        loadCats(1).catch(() => { });
        nextTick(wireQuickdates);
      });

      /* ---------- 商品内容渲染（顺序：图片→标题→描述→属性→变体→卖家→富文本） ---------- */
      function richParts(rich) {
        if (!rich) return { texts: [], imgs: [] };
        if (typeof rich === 'string') return { texts: [rich], imgs: [] };
        const texts = [], imgs = [];
        (rich.content || []).forEach(b => {
          if (b.text && Array.isArray(b.text.content)) {
            const t = b.text.content.join(' ').trim(); if (t) texts.push(t);
          }
          (b.blocks || []).forEach(blk => { if (blk && blk.img && blk.img.src) imgs.push(blk.img.src); });
        });
        return { texts, imgs };
      }
      const rich = computed(() => richParts(content.value && content.value.rich));
      const extraRows = computed(() => {
        const ex = (content.value || {}).extra || {};
        return [['卖家', ex.seller], ['公司', ex.seller_company], ['工商注册号', ex.seller_psrn],
          ['店铺评分', ex.seller_rating], ['店铺评价/订单', ex.seller_reviews], ['卖家地址', ex.seller_address],
          ['诚信标志', ex.honest_sign], ['库存', ex.stock], ['提问数', ex.questions], ['产地', ex.country],
          ['类目路径', ex.category], ['货号', ex.offer_code], ['折扣%', ex.discount], ['图片数', ex.image_count]]
          .filter(([, v]) => v !== null && v !== undefined && v !== '');
      });

      return {
        nav, page, cfg, route, status, loading, rows, note, pageNo, pageMeta, viewMode,
        formEl, quickDays, activePreset, cats, catFiltered, catSearch, catPanelOpen, selectedCats,
        product, content, contentLoading, rich, extraRows,
        drawerOpen, drawerSku, drawerContent, drawerLoading,
        toastMsg, toastBad,
        fmt, money, esc, cell, rateClass, run, resetForm, exportXlsx, go, openDrawer, closeDrawer,
        toggleFav, onPresetClick, applyPreset, toggleCatNode, toggleCat, loadContent, formClick, saveCats, refreshStatus
      };
    },

    template: `
<div>
  <div class="topbar">
    <div class="brand">
      <div class="brandmark">S</div>
      <div class="brandtext">
        <div class="brandname">Ozon 数据选品台</div>
        <div class="brandsub">Seerfar Open API · 数据口径近 30 天 · Vue 版</div>
      </div>
    </div>
    <div class="stats" v-if="status">
      <div class="stat"><b>{{ fmt(status.used) }}</b><span>已用积分</span></div>
      <div class="stat"><b>{{ fmt(status.left) }}</b><span>剩余积分</span></div>
      <div class="stat"><b>{{ fmt(status.today) }}</b><span>今日消耗</span></div>
      <div class="stat"><b>{{ fmt(status.hits) }}</b><span>缓存命中</span></div>
      <div class="stat"><b>{{ fmt(status.products) }}</b><span>落库商品</span></div>
      <div class="stat" :class="{danger: status.fused}"><b>{{ status.fused ? '熔断' : '正常' }}</b><span>数据源</span></div>
    </div>
    <div class="topactions"><button class="iconbtn" @click="refreshStatusSafe">刷新</button></div>
  </div>

  <div class="pagenav"><div class="pagenav-inner">
    <a v-for="n in nav" :key="n.href" class="pnav" :class="{active: route === n.href.replace('/app/#','')}" :href="n.href">{{ n.label }}</a>
  </div></div>

  <div class="layout" :class="{'no-sidebar': page.tool !== 'select'}">
    <aside class="sidebar" v-if="page.tool === 'select'">
      <div class="side-top">
        <div class="side-title">已选类目 <b>{{ selectedCats.length }}</b>
          <button class="linkbtn" @click="catPanelOpen = !catPanelOpen">{{ catPanelOpen ? '收起' : '展开' }}</button>
          <button class="linkbtn" @click="selectedCats.splice(0); saveCats()" v-if="selectedCats.length">清空</button>
        </div>
        <div class="selchips" v-if="catPanelOpen && selectedCats.length">
          <span class="selchip" v-for="c in selectedCats" :key="c.id"><span>{{ c.name }}</span>
            <i title="移除" @click="selectedCats = selectedCats.filter(x => x.id !== c.id); saveCats()">×</i></span>
        </div>
        <div class="side-search">
          <svg class="magnifier" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
          <input v-model="catSearch" placeholder="搜索中文 / 俄文 / 类目 ID">
        </div>
      </div>
      <div class="tree">
        <template v-for="n in catFiltered" :key="n.id">
          <div class="cnode" :class="{selected: selectedCats.some(c => c.id === n.id)}">
            <span class="arrow" @click="toggleCatNode(n)">{{ n.kids ? (n.open ? '▾' : '▸') : '·' }}</span>
            <input type="checkbox" class="catck" :checked="selectedCats.some(c => c.id === n.id)" @change="toggleCat(n)">
            <span class="node-name" :class="{unnamed: !n.named}" :title="n.path || n.id">{{ n.name }}</span>
            <span class="node-id">{{ n.kids || '' }}</span>
          </div>
          <div class="kids" v-if="n.open && n.children">
            <div class="cnode" v-for="k in n.children" :key="k.id" :class="{selected: selectedCats.some(c => c.id === k.id)}">
              <span class="arrow" @click="toggleCatNode(k)">{{ k.kids ? (k.open ? '▾' : '▸') : '·' }}</span>
              <input type="checkbox" class="catck" :checked="selectedCats.some(c => c.id === k.id)" @change="toggleCat(k)">
              <span class="node-name" :class="{unnamed: !k.named}">{{ k.name }}</span>
              <span class="node-id">{{ k.kids || '' }}</span>
            </div>
            <div class="kids" v-for="k in n.children.filter(x => x.open && x.children)" :key="'g' + k.id">
              <div class="cnode" v-for="g in k.children" :key="g.id" :class="{selected: selectedCats.some(c => c.id === g.id)}">
                <span class="arrow">·</span>
                <input type="checkbox" class="catck" :checked="selectedCats.some(c => c.id === g.id)" @change="toggleCat(g)">
                <span class="node-name">{{ g.name }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>
      <div class="side-foot"><span class="tiny">勾选父类目会自动带入前 20 个三级类目（上限 20 个）</span></div>
    </aside>

    <main class="main">
      <div class="pagehead">
        <div><h1>{{ page.title }}</h1><p class="muted">{{ page.sub }}</p></div>
        <div class="head-badges">
          <span class="badge soft">站点 <b>Ozon 俄罗斯 ₽</b></span>
          <span class="badge soft" v-if="status">积分 <b>{{ fmt(status.left) }}</b></span>
        </div>
      </div>

      <div class="presets" v-if="page.presets && page.presets.length" @click="onPresetClick">
        <button v-for="p in page.presets" :key="p.key" class="preset" :class="{active: activePreset === p.key}" :data-preset="p.key">
          <span class="pname"><i class="pico">◆</i>{{ p.name }}</span>
          <span class="pdesc">{{ p.desc }}</span>
        </button>
      </div>

      <form class="filtercard" v-if="page.tool !== 'product'" :data-tool="page.tool" ref="formEl"
            autocomplete="off" @submit.prevent="run" @click="formClick">
        <div v-html="page.formHtml"></div>
      </form>

      <form class="filtercard" v-else ref="formEl" @submit.prevent="run">
        <div class="fall">
          <div class="field"><label class="flab">商品 SKU</label><div class="fctl"><input data-f="sku" placeholder="例如 149710140"></div></div>
          <div class="field"><label class="flab">时间口径</label><div class="fctl">
            <select data-f="date_range"><option value="past_30_days">近 30 天</option><option value="past_7_days">近 7 天</option><option value="past_90_days">近 90 天</option></select>
          </div></div>
        </div>
        <div class="formfoot">
          <div class="foot-left"><span class="tiny">查竞品约 20 积分；商品内容（属性/描述/富文本）0 积分</span></div>
          <div class="foot-right">
            <button type="button" class="btn ghost" @click="resetForm">重置</button>
            <button type="submit" class="btn primary"><span class="btnlabel">查竞品</span></button>
          </div>
        </div>
      </form>

      <section class="resultcard" v-if="page.tool !== 'product'">
        <div class="resulthead">
          <div class="resultr"><h3>{{ page.resultTitle }}</h3><span class="badge solid">{{ rows.length }}</span></div>
          <div class="resultbar-actions">
            <div class="viewtoggle"><button class="vt" :class="{on: viewMode==='table'}" @click="viewMode='table'; localStorage.setItem('sf_view','table')">☰ 列表</button>
              <button class="vt" :class="{on: viewMode==='card'}" @click="viewMode='card'; localStorage.setItem('sf_view','card')">▦ 卡片</button></div>
            <button class="btn ghost sm" @click="exportXlsx">导出 XLSX</button>
          </div>
        </div>
        <div class="statusline" v-html="note || page.resultHint"></div>
        <div class="tablewrap" v-if="viewMode==='table'">
          <div class="placeholder" v-if="!rows.length && !loading">
            <div class="ph-icon">◈</div><div class="ph-title">还没有查询结果</div>
            <div class="ph-desc">设置条件后点查询；首次约 9 积分，命中缓存不扣费</div>
          </div>
          <table v-else>
            <thead><tr><th v-for="c in cfg.cols" :key="c[0]">{{ c[1] }}</th></tr></thead>
            <tbody>
              <tr v-for="(r, i) in rows" :key="i">
                <td v-for="c in cfg.cols" :key="c[0]" :class="{num: typeof r[c[0]]==='number'}">
                  <template v-if="c[0]==='fav'"><button class="favbtn" :class="{on: r._fav}" @click="toggleFav(r)">{{ r._fav ? '★' : '☆' }}</button></template>
                  <template v-else-if="c[0]==='img'"><img class="thumb" :src="r.image_url || r.img || ''" loading="lazy" v-if="r.image_url || r.img"></template>
                  <template v-else-if="c[0]==='sku'"><a class="sku-link" href="javascript:;" @click="openDrawer(r.sku || r.id)">{{ r.sku || r.id }}</a></template>
                  <template v-else-if="c[0]==='link'"><a v-if="r.url || r.product_url" :href="r.url || r.product_url" target="_blank" rel="noopener">打开 ↗</a></template>
                  <template v-else-if="c[0]==='title' || c[0]==='dim' || c[0]==='seller' || c[0]==='brand'"><span class="ttl" :title="String(r[c[0]]||'')" :class="rateClass(r, c[0])">{{ cell(r, c[0]) }}</span></template>
                  <template v-else><span :class="rateClass(r, c[0])">{{ cell(r, c[0]) }}</span></template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="cardgrid" v-else>
          <div class="pcard" v-for="(r, i) in rows" :key="i" @click="openDrawer(r.sku || r.id)">
            <img class="c-img" :src="r.image_url || r.img || ''" loading="lazy" v-if="r.image_url || r.img">
            <div class="c-body">
              <div class="c-title">{{ r.title || r.query || r.sku }}</div>
              <div class="c-price" v-if="r.price != null">{{ money(r.price) }} ₽</div>
              <div class="c-sales" v-if="r.sales != null">月销 {{ fmt(r.sales) }}</div>
              <div class="c-rate" v-if="r.review_rating != null">★ {{ fmt(r.review_rating) }} · {{ fmt(r.review_count) }} 评</div>
            </div>
            <div class="c-foot"><span class="tiny">{{ r.seller || r.brand || '' }}</span><span class="score" v-if="r.opportunity != null">{{ fmt(r.opportunity) }}</span></div>
          </div>
        </div>
        <div class="pager" v-if="rows.length">
          <button class="btn ghost sm" @click="go(-1)" :disabled="pageNo<=1">← 上一页</button>
          <span>第 {{ pageNo }} 页{{ pageMeta.pages ? ' / 共 ' + fmt(pageMeta.pages) + ' 页' : '' }}</span>
          <button class="btn ghost sm" @click="go(1)" :disabled="pageMeta.pages ? pageNo >= pageMeta.pages : pageMeta.has_next_page === false">下一页 →</button>
        </div>
      </section>

      <!-- 竞品详情 -->
      <template v-if="page.tool === 'product'">
        <section class="resultcard" v-if="product">
          <div class="resulthead"><div class="resultr"><h3>竞品数据</h3></div></div>
          <div class="card-grid" style="padding-top:12px">
            <div class="card"><b>{{ money((product.product||{}).price) }} ₽</b><span>价格</span></div>
            <div class="card"><b>{{ fmt((product.summary||{}).total_sales) }}</b><span>月销量</span></div>
            <div class="card"><b>{{ money((product.summary||{}).total_revenue) }}</b><span>月销售额 ₽</span></div>
            <div class="card"><b>{{ fmt((product.product||{}).review_rating) }}</b><span>评分</span></div>
            <div class="card"><b>{{ fmt((product.product||{}).review_count) }}</b><span>评论数</span></div>
            <div class="card"><b>{{ fmt((product.summary||{}).stock) }}</b><span>库存</span></div>
          </div>
          <div class="kv">
            <div>中文类目</div><div>{{ (product.product||{}).category_cn || '—' }}</div>
            <div>重量</div><div>{{ (product.product||{}).weight == null ? '—' : fmt((product.product||{}).weight) + ' g' }}</div>
            <div>体积</div><div>{{ (product.product||{}).volume == null ? '—' : fmt((product.product||{}).volume) + ' L' }}</div>
            <div>尺寸</div><div>{{ (product.product||{}).dimension || '—' }}</div>
            <div>毛利率</div><div>{{ fmt((product.product||{}).gross_margin) }} %</div>
            <div>广告份额 DRR</div><div>{{ fmt((product.product||{}).drr) }} %</div>
          </div>
        </section>

        <section class="resultcard">
          <div class="resulthead"><div class="resultr"><h3>商品内容（Ozon 前台 · 0 积分）</h3>
            <span class="badge solid" v-if="content && content.attributes">{{ (content.attributes||[]).length }}</span>
            <span class="muted" v-if="content">{{ content.cached ? '缓存' : '刚抓取' }}</span></div>
            <div class="resultbar-actions"><button class="btn ghost sm" @click="loadContent((content||{}).sku || '', true)">重新抓取</button></div>
          </div>
          <div class="contentblock">
            <div class="drawer-loading" v-if="contentLoading">正在加载商品内容（图片 / 标题 / 描述 / 属性 / 变体 / 卖家 / 富文本）…</div>
            <div class="empty" v-else-if="!content">填 SKU 查竞品后自动加载</div>
            <div class="empty" style="color:var(--bad)" v-else-if="content.error">{{ content.error }}</div>
            <template v-else>
              <h4>图片（{{ (content.images||[]).length }}）</h4>
              <div class="thumbs"><a v-for="u in (content.images||[]).slice(0,24)" :key="u" :href="u" target="_blank" rel="noopener"><img :src="u" loading="lazy"></a></div>
              <div class="contenthead"><b>{{ content.title }}</b>
                <span class="muted">{{ content.brand }}<template v-if="content.rating"> · ★{{ fmt(content.rating) }}</template><template v-if="content.review_count"> · {{ fmt(content.review_count) }} 条评论</template><template v-if="content.price"> · {{ money(content.price) }}₽</template></span>
              </div>
              <h4>描述（{{ (content.description||'').length }} 字）</h4>
              <div class="descbox">{{ content.description || '该商品没有文本描述' }}</div>
              <h4>产品属性（{{ (content.attributes||[]).length }}）</h4>
              <div class="attrgrid"><template v-for="a in (content.attributes||[])" :key="a.name">
                <div class="akey">{{ a.name }}</div><div class="aval">{{ (a.values||[]).join(' / ') }}</div></template></div>
              <h4>变体维度（{{ (content.aspects||[]).length }}）</h4>
              <div class="aspectrow" v-for="a in (content.aspects||[])" :key="a.name">
                <span class="aspectname">{{ a.name }}</span>
                <span class="wchips"><a class="wchip" href="javascript:;" v-for="v in a.values.slice(0,40)" :key="v.sku" @click="openDrawer(v.sku)">{{ v.value }}<template v-if="v.price"> · {{ fmt(v.price) }}₽</template></a></span>
              </div>
              <h4>卖家与库存</h4>
              <div class="attrgrid"><template v-for="row in extraRows" :key="row[0]">
                <div class="akey">{{ row[0] }}</div><div class="aval">{{ row[1] }}</div></template></div>
              <h4>富文本</h4>
              <div class="richdesc" v-if="rich.texts.length || rich.imgs.length">
                <p v-for="(t, i) in rich.texts" :key="'t'+i">{{ t }}</p>
                <div class="richimgs"><a v-for="u in rich.imgs" :key="u" :href="u" target="_blank" rel="noopener"><img :src="u" loading="lazy"></a></div>
              </div>
              <div class="empty" v-else>该商品没有富文本块</div>
            </template>
          </div>
        </section>
      </template>
    </main>
  </div>

  <!-- 抽屉：仅 0 积分内容 -->
  <div class="drawer" :class="{open: drawerOpen}" v-show="drawerOpen">
    <div class="drawer-head"><span>商品 {{ drawerSku }}</span><button @click="closeDrawer">×</button></div>
    <div class="drawer-body">
      <div class="drawer-loading" v-if="drawerLoading">正在加载商品内容…</div>
      <div class="empty" style="color:var(--bad)" v-else-if="drawerContent && drawerContent.error">{{ drawerContent.error }}</div>
      <template v-else-if="drawerContent">
        <h4>图片（{{ (drawerContent.images||[]).length }}）</h4>
        <div class="thumbs"><a v-for="u in (drawerContent.images||[]).slice(0,24)" :key="u" :href="u" target="_blank" rel="noopener"><img :src="u" loading="lazy"></a></div>
        <div class="contenthead"><b>{{ drawerContent.title }}</b>
          <span class="muted">{{ drawerContent.brand }}<template v-if="drawerContent.price"> · {{ money(drawerContent.price) }}₽</template></span></div>
        <h4>描述（{{ (drawerContent.description||'').length }} 字）</h4>
        <div class="descbox">{{ drawerContent.description || '无' }}</div>
        <h4>产品属性（{{ (drawerContent.attributes||[]).length }}）</h4>
        <div class="attrgrid"><template v-for="a in (drawerContent.attributes||[])" :key="a.name">
          <div class="akey">{{ a.name }}</div><div class="aval">{{ (a.values||[]).join(' / ') }}</div></template></div>
        <h4>变体维度（{{ (drawerContent.aspects||[]).length }}）</h4>
        <div class="aspectrow" v-for="a in (drawerContent.aspects||[])" :key="a.name">
          <span class="aspectname">{{ a.name }}</span>
          <span class="wchips"><a class="wchip" href="javascript:;" v-for="v in a.values.slice(0,40)" :key="v.sku" @click="openDrawer(v.sku)">{{ v.value }}</a></span>
        </div>
        <h4>卖家与库存</h4>
        <div class="attrgrid"><template v-for="k in ['seller','seller_company','seller_psrn','stock','questions','country']" :key="k">
          <template v-if="(drawerContent.extra||{})[k] != null">
            <div class="akey">{{ k }}</div><div class="aval">{{ (drawerContent.extra||{})[k] }}</div></template></template></div>
        <h4>富文本</h4>
        <div class="empty">见竞品详情页</div>
      </template>
    </div>
    <div class="drawer-foot">抽屉只展示 0 积分内容；Seerfar 指标请到「竞品详情」查询（约 20 积分/次）。</div>
  </div>

  <div class="toast" :class="{bad: toastBad}" v-show="toastMsg">{{ toastMsg }}</div>
</div>`
  };

  // 供模板使用的小工具
  App.setup = (function (orig) {
    return function () {
      const s = orig.call(this);
      s.refreshStatusSafe = () => s.refreshStatus();
      return s;
    };
  })(App.setup);

  createApp(App).mount('#app');
})();
