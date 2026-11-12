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

  window.__FMT = { fmt, money, esc };
  const MiniTable = {
    props: { cols: Array, rows: Array, empty: { type: String, default: '没有数据' } },
    setup(props) {
      const F = window.__FMT;
      const isNum = v => typeof v === 'number';
      return { F, isNum };
    },
    template: `<div class="tablewrap" v-if="rows && rows.length">
      <table><thead><tr><th v-for="c in cols" :key="c[1]">{{ c[0] }}</th></tr></thead>
      <tbody><tr v-for="(r,i) in rows" :key="i">
        <td v-for="c in cols" :key="c[1]" :class="{num: isNum(r[c[1]])}">
          <span v-if="c[2]==='money'">{{ F.money(r[c[1]]) }}</span>
          <span v-else-if="c[2]==='pct'">{{ r[c[1]] == null ? '—' : F.fmt(r[c[1]]) + '%' }}</span>
          <span v-else :class="{ttl: c[2]==='text'}" :title="String(r[c[1]]||'')">{{ r[c[1]] == null ? '—' : (isNum(r[c[1]]) ? F.fmt(r[c[1]]) : r[c[1]]) }}</span>
        </td></tr></tbody></table></div>
      <div class="empty" v-else>{{ empty }}</div>`
  };

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
      const viewMode = ref((() => { try { const v = new URLSearchParams(location.search).get('view'); if (v === 'card' || v === 'table') return v; } catch (e) { } return localStorage.getItem('sf_view') || 'table'; })());
      const thumbSize = ref(localStorage.getItem('sf_thumb') || 'l');
      function setThumb(s) { thumbSize.value = s; localStorage.setItem('sf_thumb', s); }
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
            // 官方 creationDate：null 不筛选 / 1 近30天 / 3 近90天 / 6 近180天 / 12 近一年 / 24 近2年
            const CREATE_DATE_MAP = { 30: 1, 90: 3, 180: 6, 365: 12, 730: 24 };
            const cd = CREATE_DATE_MAP[Number(quickDays.value)];
            if (cd) f.creation_date = cd;   // 0（全部）→ 不传，官方按 null 处理
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
          splitDims(list);
          fillDates(list);
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
          row._fav = !!(j.data && j.data.favorite);
          loadFavorites();
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
      /* upTime 是毫秒时间戳，本地库不返回格式化字段：这里补成 YYYY-MM-DD */
      function fillDates(list) {
        (list || []).forEach(r => {
          if (r.up_time_date) return;
          const ts = Number(r.up_time);
          if (!isFinite(ts) || ts <= 0) return;
          const d = new Date(ts);
          if (isNaN(d.getTime())) return;
          try { r.up_time_date = d.toLocaleDateString('sv-SE'); }        // sv-SE 即 YYYY-MM-DD
          catch (e) { r.up_time_date = d.toISOString().slice(0, 10); }
        });
        return list;
      }
      /* 把 "340×240×120" 这类尺寸串拆成长/宽/高（mm），数字便于排序 */
      function splitDims(list) {
        (list || []).forEach(r => {
          if (r.length != null || r.width != null || r.height != null) return;
          const s = String(r.dimension || '').replace(/\s/g, '');
          if (!s) return;
          const parts = s.split(/[×xX*хХ,]/).map(v => Number(v)).filter(v => isFinite(v) && v > 0);
          if (parts.length >= 3) { r.length = parts[0]; r.width = parts[1]; r.height = parts[2]; }
        });
        return list;
      }
      function cell(row, key) {
        let v = row[key];
        const tag = String(row.sku || row.id || '') + ':' + key;
        if (Object.prototype.hasOwnProperty.call(tweenVals, tag)) v = tweenVals[tag];
        const tweening = Object.prototype.hasOwnProperty.call(tweenVals, tag);
        if (key === 'fav') return row._fav ? '★' : '☆';
        if (key === 'img') return '';
        if (key === 'link') return row.url || row.product_url || '';
        if (key === 'sku') return row.sku || row.id || '';
        if (RATE_KEYS.has(key) && v != null) return (Number(v) >= 0 ? '+' : '') + fmt(v) + '%';
        if (COLS.PCT_KEYS.indexOf(key) >= 0 && v != null) return fmt(v) + '%';
        if (typeof v === 'number') return fmt(v);
        return v == null ? '—' : String(v);
      }
      function isTweening(row, key) {
        return Object.prototype.hasOwnProperty.call(tweenVals, String(row.sku || row.id || '') + ':' + key);
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
        if (i >= 0) {
          // 取消：连同这个父类目自动带入的叶子一起移除
          selectedCats.value.splice(i, 1);
          selectedCats.value = selectedCats.value.filter(c => c.auto !== n.id);
          saveCats(); return;
        }
        if (n.level >= 3) {
          selectedCats.value.push({ id: n.id, name: n.name });
        } else {
          // 父类目：记自身；按开关决定是否补三级（Ozon 只认三级，不补通常查不到商品）
          selectedCats.value.push({ id: n.id, name: n.name });
          {
            const j = await api('/api/category/leaves?parent=' + encodeURIComponent(n.id) + '&limit=20');
            const leaves = (j.data || []);
            leaves.forEach(l => {
              if (!selectedCats.value.some(c => c.id === l.id)) {
                selectedCats.value.push({ id: l.id, name: l.cn || l.id, auto: n.id });
              }
            });
            // 把补进来的三级展开显示，让用户看得见
            n.children = leaves.map(l => ({
              id: l.id, name: l.cn || l.id, path: l.cn_path || '', level: 3,
              kids: 0, named: true, open: false, children: null
            }));
            n.open = true;
          }
        }
        saveCats();
      }
      function saveCats() { try { sessionStorage.setItem('sf_cats_vue', JSON.stringify(selectedCats.value)); } catch (e) { } }

      const selectedIds = computed(() => new Set(selectedCats.value.filter(c => !c.auto).map(c => c.id)));
      /* 搜索结果展示父级路径（去掉末尾自身名，避免重复） */
      function parentPath(p) {
        const parts = String(p || '').split(' > ').filter(Boolean);
        if (parts.length <= 1) return '';
        return parts.slice(0, -1).join('  ›  ');
      }
      /* 可见节点展平：深度优先、保序、带 depth 用于缩进 */
      const flatCat = computed(() => {
        const out = [];
        const walk = (list, depth) => {
          (list || []).forEach(n => {
            n._depth = depth;              // 直接挂原对象，保证点击改的是同一份状态
            out.push(n);
            if (n.open && n.children && n.children.length) walk(n.children, depth + 1);
          });
        };
        walk(catFiltered.value, 0);
        return out;
      });
      /* 搜索：走后端全库检索（10k 类目），而不是只过滤已加载的一级节点 */
      /* 卡片视图展示的商品明细字段（与表格列同一套 key） */
      /* 卡片只展示售卖/流量相关字段（按运营给的列顺序） */
      const CARD_FIELDS = [
        ['discount', '平均折扣', 'pct'],
        ['sales', '月销量', 'num'], ['sales_rate', '销量环比', 'pct'],
        ['revenue', '月销售额 ₽', 'money'], ['revenue_rate', '销售额增长', 'pct'],
        ['gross_margin', '毛利率', 'pct'],
        ['review_count', '评论数', 'num'], ['review_rating', '评分', 'num'], ['qa', '问答数', 'num'],
        ['return_cancellation_rate', '退货取消率', 'pct'],
        ['views', '展示总量', 'num'], ['session_count_search', '曝光量', 'num'],
        ['session_count', '产品卡浏览', 'num'],
        ['conv_to_cart_search', '搜索加购率', 'pct'], ['conv_to_cart_pdp', '购物车转化率', 'pct'],
        ['conv_view_to_order', '展示转化', 'pct'], ['order_conversion_rate', '订单转化', 'pct'],
        ['drr', '广告份额', 'pct'], ['promo_revenue_share', '促销占比', 'pct'],
        ['up_time_date', '上架时间', 'text']
      ];
      const catHits = ref([]), catSearching = ref(false);
      const autoIds = computed(() => new Set(selectedCats.value.filter(c => c.auto).map(c => c.id)));
      let catTimer = null;
      watch(catSearch, (v) => {
        const q = (v || '').trim();
        if (catTimer) clearTimeout(catTimer);
        if (!q) { catHits.value = []; catSearching.value = false; return; }
        catSearching.value = true;
        catTimer = setTimeout(async () => {
          try {
            const j = await api('/api/categories?q=' + encodeURIComponent(q));
            catHits.value = (j.data || []).map(n => ({
              id: n.id, name: n.cn || n.id, path: n.cn_path || '', level: n.level,
              leaf: !!n.leaf, named: n.named !== undefined ? n.named : !!(n.cn && n.cn !== n.id),
              kids: 0, open: false, children: null, _depth: 0
            }));
          } catch (e) { catHits.value = []; }
          finally { catSearching.value = false; }
        }, 260);
      });
      const displayList = computed(() => (catSearch.value.trim() ? catHits.value : flatCat.value));
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
      watch(page, () => { nextTick(() => { wireQuickdates(); updateHScroll(); }); });
      watch([rows, thumbSize, viewMode], () => { nextTick(updateHScroll); });

      onMounted(async () => {
        window.addEventListener('hashchange', onHash);
        const bar = document.querySelector('.topbar');
        const onScroll = () => {
          if (bar) bar.classList.toggle('scrolled', window.scrollY > 6);
          heroY.value = Math.min(90, window.scrollY * 0.16);
        };
        window.addEventListener('scroll', onScroll, { passive: true });
        window.addEventListener('resize', () => updateHScroll());
        onScroll();
        refreshStatus();
        try {
          const saved = JSON.parse(sessionStorage.getItem('sf_cats_vue') || '[]');
          if (Array.isArray(saved)) selectedCats.value = saved;
        } catch (e) { }
        try { const cq = new URLSearchParams(location.search).get('catq'); if (cq) catSearch.value = cq; } catch (e) { }
        loadCats(1).catch(() => { });
        try { if (new URLSearchParams(location.search).get('run') === '1') setTimeout(() => run().catch(() => { }), 400); } catch (e) { }
        loadFavorites();
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
      const drawerRich = computed(() => richParts(drawerContent.value && drawerContent.value.rich));
      const EXTRA_LABEL = {
        seller: '卖家', seller_company: '公司', seller_psrn: '工商注册号', seller_rating: '店铺评分',
        seller_reviews: '店铺评价/订单', seller_address: '卖家地址', honest_sign: '诚信标志',
        stock: '库存', questions: '提问数', country: '产地', category: '类目路径',
        offer_code: '货号', discount: '折扣%', image_count: '图片数'
      };
      const drawerExtra = computed(() => {
        const ex = (drawerContent.value || {}).extra || {};
        return Object.keys(EXTRA_LABEL)
          .filter(k => ex[k] !== null && ex[k] !== undefined && ex[k] !== '')
          .map(k => [EXTRA_LABEL[k], ex[k]]);
      });
      const extraRows = computed(() => {
        const ex = (content.value || {}).extra || {};
        return [['卖家', ex.seller], ['公司', ex.seller_company], ['工商注册号', ex.seller_psrn],
          ['店铺评分', ex.seller_rating], ['店铺评价/订单', ex.seller_reviews], ['卖家地址', ex.seller_address],
          ['诚信标志', ex.honest_sign], ['库存', ex.stock], ['提问数', ex.questions], ['产地', ex.country],
          ['类目路径', ex.category], ['货号', ex.offer_code], ['折扣%', ex.discount], ['图片数', ex.image_count]]
          .filter(([, v]) => v !== null && v !== undefined && v !== '');
      });

      /* ===== 深水区：变体 / 评论 / 相似 / 店铺结构 / 利润 / 报告 / 收藏 ===== */
      const VAR_COLS = [['SKU','sku','text'],['变体特征','variation_text','text'],['价格 ₽','price','money'],
        ['月销量','sales'],['月销额 ₽','revenue','money'],['评论数','review_count'],['评分','review_rating'],['上架','up_time_date','text']];
      const SIM_COLS = [['SKU','sku','text'],['标题','title','text'],['价格 ₽','price','money'],['月销量','sales'],
        ['月销额 ₽','revenue','money'],['库存','stock'],['评论数','review_count'],['评分','review_rating'],
        ['毛利率%','gross_margin','pct'],['卖家','seller','text']];
      const BRAND_COLS = [['品牌','name','text'],['销售额 ₽','revenue','money'],['占本页%','page_share','pct'],
        ['Top10份额%','sharing','pct'],['销量','sales'],['商品数','products'],['有销量商品','products_with_sales'],
        ['均价 ₽','avg_price','money'],['均销','avg_sales'],['均评分','avg_rating'],['均评论','avg_reviews'],
        ['卖家数','sellers'],['退货率%','return_rate','pct']];
      const CAT_COLS = [['类目','cn_path','text'],['销售额 ₽','revenue','money'],['占本页%','page_share','pct'],
        ['销量','sales'],['商品数','products'],['均价 ₽','avg_price','money'],['销额增长%','revenue_rate','pct'],['销量增长%','sales_rate','pct']];
      const PROFIT_KEYS = ['cost_cny','rate_cny_rub','shipping_cny_per_kg','commission_pct','payment_pct',
        'drr_pct','return_pct','target_margin_pct','volumetric_divisor'];
      const PROFIT_DEFAULTS = { cost_cny:'', rate_cny_rub:12.5, shipping_cny_per_kg:35, commission_pct:15,
        payment_pct:2, drr_pct:'', return_pct:0, target_margin_pct:20, volumetric_divisor:5000 };
      const PROFIT_LABEL = { cost_cny:'采购价 CNY', rate_cny_rub:'汇率 CNY→₽', shipping_cny_per_kg:'头程 CNY/kg',
        commission_pct:'佣金%', payment_pct:'支付/结算%', drr_pct:'广告 DRR%（留空=用商品自带）',
        return_pct:'退货损耗%', target_margin_pct:'目标毛利%', volumetric_divisor:'体积重系数' };
      const DIM_KEYS = ['advantages','disadvantages','usageScenarios','userCharacteristics','unmetNeeds',
        'timePoints','usageLocations','userBehavior','purchaseMotivations'];
      const DIM_LABEL = { advantages:'优点', disadvantages:'缺点', usageScenarios:'使用场景', userCharacteristics:'用户特征',
        unmetNeeds:'未满足需求', timePoints:'使用时刻', usageLocations:'使用地点', userBehavior:'用户行为', purchaseMotivations:'购买动机' };

      const STAR_PCT = { 5: 'fiveStarPercent', 4: 'fourStarPercent', 3: 'threeStarPercent', 2: 'twoStarPercent', 1: 'oneStarPercent' };
      const STAR_CNT = { 5: 'fiveStarCount', 4: 'fourStarCount', 3: 'threeStarCount', 2: 'twoStarCount', 1: 'oneStarCount' };
      const starPct = n => Number(((revData.value || {}).statistic || {})[STAR_PCT[n]] || 0);
      const starCnt = n => ((revData.value || {}).statistic || {})[STAR_CNT[n]];
      /* 利润计算后的数字滚动：按 sku:key 存中间值，cell() 优先取它 */
      const tweenVals = reactive({});
      const TWEEN_KEYS = ['net_profit', 'net_margin', 'breakeven', 'suggested', 'roi', 'chargeable_kg'];
      function tweenRow(fromRow, toRow) {
        const key = String(toRow.sku || toRow.id || '');
        TWEEN_KEYS.forEach(k => {
          const a = fromRow ? Number(fromRow[k]) : NaN;
          const b = Number(toRow[k]);
          if (!isFinite(b)) return;
          const tag = key + ':' + k;
          if (!fromRow || !isFinite(a) || a === b) { tweenVals[tag] = b; setTimeout(() => { delete tweenVals[tag]; }, 900); return; }
          const t0 = performance.now(), dur = 620;
          const step = (now) => {
            const pr = Math.min((now - t0) / dur, 1);
            const e = 1 - Math.pow(1 - pr, 3);
            tweenVals[tag] = a + (b - a) * e;
            if (pr < 1) requestAnimationFrame(step);
            else setTimeout(() => { delete tweenVals[tag]; }, 320);
          };
          requestAnimationFrame(step);
        });
      }

      const sortKey = ref(''), sortDir = ref('desc');
      function sortBy(key) {
        if (!key) return;
        if (sortKey.value === key) sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc';
        else { sortKey.value = key; sortDir.value = 'desc'; }
      }
      const sortedRows = computed(() => {
        const list = rows.value || [];
        if (!sortKey.value) return list;
        const k = sortKey.value, dir = sortDir.value === 'asc' ? 1 : -1;
        return list.slice().sort((a, b) => {
          const av = a[k], bv = b[k];
          const an = typeof av === 'number', bn = typeof bv === 'number';
          if (an && bn) return (av - bv) * dir;
          if (an !== bn) return (an ? -1 : 1) * dir;
          return String(av == null ? '' : av).localeCompare(String(bv == null ? '' : bv), 'zh-CN') * dir;
        });
      });
      /* ---------- 表格横向滚动：页面底部浮动条 ---------- */
      const tableWrap = ref(null), hTrack = ref(null);
      const hOn = ref(false), hThumbW = ref(80), hThumbX = ref(0), hOverflow = ref(0);
      function updateHScroll() {
        const el = tableWrap.value, tr = hTrack.value;
        if (!el || !tr) { hOn.value = false; return; }
        const overflow = el.scrollWidth - el.clientWidth;
        hOverflow.value = overflow;
        if (overflow <= 4) { hOn.value = false; return; }
        hOn.value = true;
        const trackW = tr.clientWidth || 1;
        const ratio = el.clientWidth / el.scrollWidth;
        hThumbW.value = Math.max(36, Math.round(trackW * ratio));
        const maxX = Math.max(0, trackW - hThumbW.value);
        hThumbX.value = overflow ? (el.scrollLeft / overflow) * maxX : 0;
      }
      function onTableScroll() { updateHScroll(); }
      function syncFromTable() {
        const el = tableWrap.value; if (!el) return;
        const tr = hTrack.value; if (!tr) return;
        const maxX = Math.max(1, tr.clientWidth - hThumbW.value);
        el.scrollLeft = (hThumbX.value / maxX) * hOverflow.value;
      }
      let _drag = null;
      function thumbDown(e) {
        e.preventDefault();
        _drag = { x: e.clientX, left: hThumbX.value };
        window.addEventListener('pointermove', thumbMove);
        window.addEventListener('pointerup', thumbUp, { once: true });
      }
      function thumbMove(e) {
        if (!_drag) return;
        const tr = hTrack.value; if (!tr) return;
        const maxX = Math.max(1, tr.clientWidth - hThumbW.value);
        hThumbX.value = Math.min(maxX, Math.max(0, _drag.left + (e.clientX - _drag.x)));
        syncFromTable();
      }
      function thumbUp() {
        _drag = null;
        window.removeEventListener('pointermove', thumbMove);
      }
      function trackDown(e) {
        const tr = hTrack.value; if (!tr) return;
        const rect = tr.getBoundingClientRect();
        const x = e.clientX - rect.left - hThumbW.value / 2;
        const maxX = Math.max(1, tr.clientWidth - hThumbW.value);
        hThumbX.value = Math.min(maxX, Math.max(0, x));
        syncFromTable();
      }
      const heroY = ref(0);
      const heroImg = computed(() => {
        const imgs = (content.value || {}).images || [];
        return imgs[0] || ((product.value || {}).product || {}).image_url || '';
      });
      const heroTitle = computed(() => (content.value || {}).title || ((product.value || {}).product || {}).title || '');
      const heroBrand = computed(() => (content.value || {}).brand || ((product.value || {}).product || {}).brand || '');
      const heroPrice = computed(() => (content.value || {}).price || ((product.value || {}).product || {}).price);
      const heroSku = computed(() => (content.value || {}).sku || ((product.value || {}).product || {}).sku || '');
      const imgLoaded = reactive({});
      function imgCls(u) { return 'phimg' + (imgLoaded[u] ? ' loaded' : ''); }
      function onImgLoad(e) {
        const s = e && e.target && (e.target.currentSrc || e.target.src);
        if (s) imgLoaded[s] = true;
      }
      const varChars = ref([]), varRows = ref([]), varTopRows = ref([]), varMeta = ref('');
      const simRows = ref([]), simMeta = ref('');
      const revKind = ref('stat'), revData = ref(null), revMeta = ref(''), revLang = ref('CN');
      const shopBrands = ref(null), shopCats = ref(null), shopBrandMeta = ref(''), shopCatMeta = ref('');
      const profit = ref(Object.assign({}, PROFIT_DEFAULTS));
      const profitOnly = ref(false), profitSummary = ref(null), profitMeta = ref('');
      const favList = ref([]), favOpen = ref(false);

      function formValue(key) {
        const el = formEl.value && formEl.value.querySelector('[data-f="' + key + '"]');
        return el ? String(el.value || '').trim() : '';
      }
      const curSku = () => formValue('sku');
      const curShopId = () => formValue('id');

      async function loadVarChars() {
        const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
        try {
          const j = await api('/api/varchars?sku=' + encodeURIComponent(sku));
          varChars.value = (j.data && j.data.rows) || [];
          varMeta.value = '维度 ' + varChars.value.length + ' 个 · ' + (j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分');
          refreshStatus();
        } catch (e) { toast(e.message, true); }
      }
      async function loadVarList() {
        const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
        try {
          const j = await api('/api/variations?sku=' + encodeURIComponent(sku) + '&size=50');
          varRows.value = (j.data && j.data.rows) || [];
          varTopRows.value = [];
          varMeta.value = '变体 ' + varRows.value.length + ' 个 · 共 ' + fmt((j.data || {}).total) + ' · ' + (j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分');
          refreshStatus();
        } catch (e) { toast(e.message, true); }
      }
      async function loadVarTop(char) {
        const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
        try {
          const j = await api('/api/vartop?sku=' + encodeURIComponent(sku) + '&characteristic=' + encodeURIComponent(char));
          const d = j.data || {}, rev = d.revenues || [], sal = d.sales || [];
          const map = new Map();
          rev.forEach((x, i) => map.set(x.name, { name: x.name, rank: i + 1, revenue: x.quantity }));
          sal.forEach((x, i) => { const o = map.get(x.name) || { name: x.name }; o.sales = x.quantity; o.salesRank = i + 1; map.set(x.name, o); });
          varTopRows.value = [...map.values()].sort((a, b) => (a.rank || 99) - (b.rank || 99));
          varMeta.value = '维度「' + esc(char) + '」Top' + varTopRows.value.length + ' · ' + (j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分');
          await nextTick();
          refreshStatus();
        } catch (e) { toast(e.message, true); }
      }
      async function loadSimilar() {
        const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
        try {
          const j = await api('/api/similar?sku=' + encodeURIComponent(sku));
          simRows.value = (j.data && j.data.rows) || [];
          simMeta.value = '相似 ' + simRows.value.length + ' 条（含目标商品）· ' + (j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分');
          refreshStatus();
        } catch (e) { toast(e.message, true); }
      }
      async function loadReview(kind) {
        const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
        revKind.value = kind;
        try {
          const j = await api('/api/reviews?sku=' + encodeURIComponent(sku) + '&type=' + kind + '&language=' + revLang.value);
          revData.value = j.data || {};
          const label = { stat: '星级分布', words: '词频', original: '原始评论', report: 'AI 报表' }[kind];
          revMeta.value = label + ' · 语言 ' + revLang.value + ' · ' + (j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分');
          refreshStatus();
        } catch (e) { toast(e.message, true); }
      }
      async function createRevTask() {
        const sku = curSku(); if (!sku) return toast('先填商品 SKU', true);
        if (!confirm('创建评论分析任务：官方按 200 积分/SKU 计费。\n\nSKU ' + sku + ' · 语言 ' + revLang.value + '\n\n确认创建？')) return;
        try {
          const j = await api('/api/reviews/task', { method: 'POST', body: { skus: [sku], confirm: true } });
          toast('任务已创建');
          revMeta.value = '任务已提交，稍后查「AI 报表 / 词频」（同一 SKU 已创建过无需重复付费）';
          refreshStatus();
        } catch (e) { toast(e.message, true); }
      }
      async function loadShopBrands() {
        const id = curShopId(); if (!id) return toast('先填店铺 ID', true);
        try {
          const j = await api('/api/shop/brands?id=' + encodeURIComponent(id) + '&size=50');
          const d = j.data || {}, t = d.top || {};
          shopBrands.value = { rows: d.rows || [], top: t };
          shopBrandMeta.value = '品牌 ' + fmt(t.total) + ' · 店铺销额 ' + money(t.total_revenue) + '₽ · Top10 份额 ' +
            (t.revenue_share_top10 == null ? '—' : fmt(t.revenue_share_top10) + '%') + ' · ' +
            (j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分');
          refreshStatus();
        } catch (e) { toast(e.message, true); }
      }
      async function loadShopCats() {
        const id = curShopId(); if (!id) return toast('先填店铺 ID', true);
        try {
          const j = await api('/api/shop/categories?id=' + encodeURIComponent(id) + '&size=50');
          const d = j.data || {};
          shopCats.value = { rows: d.rows || [], total: d.total };
          shopCatMeta.value = '类目 ' + (d.rows || []).length + ' 行 · 共 ' + fmt(d.total) + ' · ' +
            (j.meta && j.meta.cached ? '缓存 0 积分' : '消耗 ' + (j.meta && j.meta.cost) + ' 积分');
          refreshStatus();
        } catch (e) { toast(e.message, true); }
      }
      function profitParamsNow() {
        const p = {};
        PROFIT_KEYS.forEach(k => { const v = profit.value[k]; p[k] = (v === '' || v == null) ? null : Number(v); });
        return p;
      }
      async function runProfit() {
        if (!rows.value.length) return toast('先查询出商品', true);
        try { localStorage.setItem('sf_profit', JSON.stringify(profit.value)); } catch (e) { }
        const clean = rows.value.map(r => { const o = {}; for (const k in r) if (k !== 'raw' && k !== 'opportunity_parts') o[k] = r[k]; return o; });
        try {
          const j = await api('/api/profit', { method: 'POST', body: { rows: clean, params: profitParamsNow() } });
          const d = j.data || {};
          profitSummary.value = d.summary || null;
          const list = d.rows || [];
          const prev = new Map((rows.value || []).map(r => [String(r.sku || r.id || ''), r]));
          list.forEach(r => tweenRow(prev.get(String(r.sku || r.id || '')), r));
          rows.value = profitOnly.value ? list.filter(r => (Number(r.net_profit) || 0) > 0) : list;
          profitMeta.value = '已计算 ' + list.length + ' 行 · 平均真毛利 ' +
            (profitSummary.value && profitSummary.value.avg_net_margin != null ? fmt(profitSummary.value.avg_net_margin) + '%' : '—');
          toast('利润已计算');
        } catch (e) { toast(e.message, true); }
      }
      async function exportReport() {
        if (!rows.value.length) return toast('先查询出商品', true);
        const fav = await api('/api/favorites?limit=2000').catch(() => ({ data: { rows: [] } }));
        const clean = rows.value.map(r => { const o = {}; for (const k in r) if (k !== 'raw' && k !== 'opportunity_parts') o[k] = r[k]; return o; });
        const s = profitSummary.value || {};
        const body = {
          kind: 'report', rows: clean, favorites: ((fav.data || {}).rows || []),
          filename: 'seerfar_report_' + new Date().toISOString().slice(0, 10),
          meta: { '导出时间': new Date().toLocaleString('zh-CN'), '页面': page.value.tool,
            '命中总数': pageMeta.value.total == null ? '' : pageMeta.value.total, '本表行数': clean.length,
            '平均真毛利率%': s.avg_net_margin == null ? '' : s.avg_net_margin,
            '平均净利₽': s.avg_net_profit == null ? '' : s.avg_net_profit,
            '亏损行数': s.loss_rows == null ? '' : s.loss_rows }
        };
        if (['hotwords','mining','backsearch'].indexOf(page.value.tool) >= 0) { body.keywords = clean; body.rows = []; }
        try {
          const j = await api('/api/export', { method: 'POST', body });
          const a = document.createElement('a'); a.href = j.data.url; a.download = j.data.file;
          document.body.appendChild(a); a.click(); a.remove();
          toast('报告已导出：' + j.data.file);
        } catch (e) { toast(e.message, true); }
      }
      async function loadFavorites() {
        try {
          const j = await api('/api/favorites?limit=2000');
          favList.value = (j.data && j.data.rows) || [];
        } catch (e) { /* 增强功能 */ }
      }
      return {
        nav, page, cfg, route, status, loading, rows, note, pageNo, pageMeta, viewMode,
        formEl, quickDays, activePreset, cats, flatCat, selectedIds, displayList, catHits, catSearching, autoIds, parentPath, CARD_FIELDS,
        thumbSize, setThumb,
        tableWrap, hTrack, hOn, hThumbW, hThumbX, thumbDown, trackDown, onTableScroll, imgCls, catFiltered, catSearch, catPanelOpen, selectedCats,
        product, content, contentLoading, rich, extraRows, drawerRich, drawerExtra,
        drawerOpen, drawerSku, drawerContent, drawerLoading,
        toastMsg, toastBad,
        fmt, money, esc, cell, rateClass, run, resetForm, exportXlsx, go, openDrawer, closeDrawer,
        toggleFav, onPresetClick, applyPreset, toggleCatNode, toggleCat, loadContent, formClick, saveCats, refreshStatus,
        sortKey, sortDir, sortBy, sortedRows, onImgLoad, isTweening, heroY, heroImg, heroTitle, heroBrand, heroPrice, heroSku,
        // 深水区
        VAR_COLS, SIM_COLS, BRAND_COLS, CAT_COLS, PROFIT_KEYS, PROFIT_LABEL, DIM_KEYS, DIM_LABEL,
        varChars, varRows, varTopRows, varMeta, simRows, simMeta,
        revKind, revData, revMeta, revLang, shopBrands, shopCats, shopBrandMeta, shopCatMeta,
        profit, profitOnly, profitSummary, profitMeta, favList, favOpen, starPct, starCnt,
        loadVarChars, loadVarList, loadVarTop, loadSimilar, loadReview, createRevTask,
        loadShopBrands, loadShopCats, runProfit, exportReport, loadFavorites
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
    <div class="topactions">
      <button class="iconbtn" @click="favOpen = !favOpen">收藏 {{ favList.length }}</button>
      <button class="iconbtn" @click="refreshStatusSafe">刷新</button></div>
  </div>

  <div class="pagenav"><div class="pagenav-inner">
    <a v-for="n in nav" :key="n.href" class="pnav" :class="{active: route === n.href.replace('/app/#','')}" :href="'#' + n.href.replace('/app/#','')">{{ n.label }}</a>
  </div></div>

  <div class="layout" :class="{'no-sidebar': page.tool !== 'select'}">
    <aside class="sidebar" v-if="page.tool === 'select'">
      <div class="side-top">
        <div class="side-title">已选类目 <b>{{ selectedCats.length }}</b>
          <button class="linkbtn" @click="catPanelOpen = !catPanelOpen">{{ catPanelOpen ? '收起' : '展开' }}</button>
          <button class="linkbtn" @click="selectedCats.splice(0); saveCats()" v-if="selectedCats.length">清空</button>
        </div>
        <div class="selchips" v-if="catPanelOpen && selectedCats.length">
          <span class="selchip" :class="{auto: c.auto}" v-for="c in selectedCats" :key="c.id"><span>{{ c.name }}</span>
            <i title="移除" @click="selectedCats = selectedCats.filter(x => x.id !== c.id); saveCats()">×</i></span>
        </div>
        <div class="side-search">
          <svg class="magnifier" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
          <input v-model="catSearch" placeholder="搜索中文 / 俄文 / 类目 ID">
        </div>
      </div>
      <div class="tree">
        <div class="cnode" v-for="n in displayList" :key="n.id"
             :class="{selected: selectedIds.has(n.id), auto: autoIds.has(n.id)}"
             :style="{ paddingLeft: (6 + (n._depth || 0) * 14) + 'px' }">
          <span class="arrow" @click.stop="toggleCatNode(n)">{{ n.kids ? (n.open ? '▾' : '▸') : '·' }}</span>
          <input type="checkbox" class="catck" :checked="selectedIds.has(n.id)" @change="toggleCat(n)">
          <span class="node-name" :class="{unnamed: !n.named, clickable: n.kids, search: !!catSearch.trim()}"
                  :title="n.path || n.id"
                  @click.stop="n.kids ? toggleCatNode(n) : toggleCat(n)">
            <b>{{ n.name }}</b>
            <em class="node-path" v-if="catSearch.trim()">{{ parentPath(n.path) || ("ID " + n.id) }}</em>
          </span>
          <span class="node-id">{{ n.kids || '' }}</span>
          <span class="auto-tag" v-if="autoIds.has(n.id)">自动</span>
        </div>
        <div class="empty tiny" v-if="catSearch.trim() && !catSearching && !displayList.length">没有匹配的类目</div>
      </div>
            <div class="side-foot"><span class="tiny">勾选父类目会自动带上它前 20 个三级类目（Ozon 只认三级），带上的显示为灰色「自动」标签，可单独移除</span></div>
    </aside>

    <main class="main" :key="route">
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
            <div class="viewtoggle" title="缩略图尺寸">
              <button class="vt" :class="{on: thumbSize==='s'}" @click="setThumb('s')">小图</button>
              <button class="vt" :class="{on: thumbSize==='m'}" @click="setThumb('m')">中图</button>
              <button class="vt" :class="{on: thumbSize==='l'}" @click="setThumb('l')">大图</button>
            </div>
            <div class="viewtoggle"><button class="vt" :class="{on: viewMode==='table'}" @click="viewMode='table'; localStorage.setItem('sf_view','table')">☰ 列表</button>
              <button class="vt" :class="{on: viewMode==='card'}" @click="viewMode='card'; localStorage.setItem('sf_view','card')">▦ 卡片</button></div>
            <button class="btn ghost sm" @click="exportXlsx">导出 XLSX</button>
          </div>
        </div>
        <div class="statusline" v-html="note || page.resultHint"></div>
        <div class="tablewrap" ref="tableWrap" v-if="viewMode==='table'" @scroll.passive="onTableScroll">
          <table v-if="loading && !rows.length">
            <thead><tr><th v-for="c in cfg.cols.slice(0, 7)" :key="c[0]">{{ c[1] }}</th></tr></thead>
            <tbody>
              <tr class="skelrow" v-for="n in 7" :key="n">
                <td v-for="c in cfg.cols.slice(0, 7)" :key="c[0]">
                  <div class="skel" :class="{ 'w40': c[0]==='title', 'w20': c[0]!=='title' }"></div>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="placeholder" v-else-if="!rows.length">
            <div class="ph-icon">◈</div><div class="ph-title">还没有查询结果</div>
            <div class="ph-desc">设置条件后点查询；首次约 9 积分，命中缓存不扣费</div>
          </div>
          <table v-else>
            <thead><tr>
              <th v-for="c in cfg.cols" :key="c[0]" :class="{sorted: sortKey === c[0]}"
                  @click="sortBy(c[0])" style="cursor:pointer">
                {{ c[1] }}<span class="sortind" v-if="sortKey === c[0]">{{ sortDir === 'asc' ? '▲' : '▼' }}</span>
              </th>
            </tr></thead>
            <tbody>
              <tr v-for="(r, i) in sortedRows" :key="i">
                <td v-for="c in cfg.cols" :key="c[0]" :class="{num: typeof r[c[0]]==='number', 'num-tween': isTweening(r, c[0])}">
                  <template v-if="c[0]==='fav'"><button class="favbtn" :class="{on: r._fav}" @click="toggleFav(r)">{{ r._fav ? '★' : '☆' }}</button></template>
                  <template v-else-if="c[0]==='img'"><img :class="['thumb', 'sz-' + thumbSize, imgCls(r.image_url || r.img)]" :src="r.image_url || r.img || ''" loading="lazy" @load="onImgLoad" v-if="r.image_url || r.img"></template>
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
            <img :class="['c-img', imgCls(r.image_url || r.img)]" :src="r.image_url || r.img || ''" loading="lazy" @load="onImgLoad" v-if="r.image_url || r.img">
            <div class="c-body">
              <div class="c-title">{{ r.title || r.query || r.sku }}</div>
              <div class="c-price" v-if="r.price != null">{{ money(r.price) }} ₽</div>
              <div class="c-meta">
                <template v-for="f in CARD_FIELDS" :key="f[0]">
                  <div class="c-kv" v-if="r[f[0]] !== null && r[f[0]] !== undefined && r[f[0]] !== ''">
                    <span class="c-k">{{ f[1] }}</span>
                    <span class="c-v" :class="{num: f[2] !== 'text', txt: f[2] === 'text'}">
                      {{ f[2] === 'money' ? money(r[f[0]])
                         : f[2] === 'pct' ? fmt(r[f[0]]) + '%'
                         : f[2] === 'num' ? fmt(r[f[0]]) : r[f[0]] }}
                    </span>
                  </div>
                </template>
              </div>
            </div>
            <div class="c-foot"><span class="tiny">机会分</span><span class="score" v-if="r.opportunity != null">{{ fmt(r.opportunity) }}</span></div>
          </div>
        </div>
      </section>

      <!-- 竞品详情 -->
      <template v-if="page.tool === 'product'">
        <section class="hero" v-if="heroImg">
          <img :class="['hero-img', imgCls(heroImg)]" :src="heroImg" :style="{ transform: 'translate3d(0,' + heroY + 'px,0) scale(1.12)' }" @load="onImgLoad" alt="">
          <div class="hero-veil"></div>
          <div class="hero-actions">
            <button class="btn sm" v-if="heroSku" @click="openDrawer(heroSku)">快速查看</button>
          </div>
          <div class="hero-meta">
            <div class="hero-eyebrow">OZON · SKU {{ heroSku || '—' }}</div>
            <h2>{{ heroTitle || '商品详情' }}</h2>
            <div class="hero-sub">
              <span v-if="heroBrand">{{ heroBrand }}</span>
              <span class="hp" v-if="heroPrice">{{ money(heroPrice) }} ₽</span>
              <span v-if="content && content.review_count">· ★ {{ fmt(content.rating) }}（{{ fmt(content.review_count) }} 条评论）</span>
            </div>
          </div>
        </section>
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
              <div class="thumbs"><a v-for="u in (content.images||[]).slice(0,24)" :key="u" :href="u" target="_blank" rel="noopener"><img :class="imgCls(u)" :src="u" loading="lazy" @load="onImgLoad"></a></div>
              <div class="contenthead"><b>{{ content.title }}</b>
                <span class="muted">{{ content.brand }}<template v-if="content.rating"> · ★{{ fmt(content.rating) }}</template><template v-if="content.review_count"> · {{ fmt(content.review_count) }} 条评论</template><template v-if="content.price"> · {{ money(content.price) }}₽</template></span>
              </div>
              <h4>描述（{{ (content.description||'').length }} 字）</h4>
              <div class="descbox">{{ content.description || '该商品没有文本描述' }}</div>
              <h4>产品属性（{{ (content.attributes||[]).length }}）</h4>
              <div class="attrgrid"><template v-for="a in (content.attributes||[])" :key="a.name">
                <div class="akey">{{ a.name }}</div><div class="aval"><template v-if="a.name === '主题标签'"><span class="tagchip" v-for="v in a.values" :key="v">{{ v }}</span></template><template v-else>{{ (a.values||[]).join(' / ') }}</template></div></template></div>
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
      <!-- 店铺结构 -->
      <template v-if="page.tool === 'shop'">
        <section class="resultcard">
          <div class="resulthead">
            <div class="resultr"><h3>品牌结构</h3><span class="badge solid" v-if="shopBrands">{{ (shopBrands.rows||[]).length }}</span></div>
            <div class="resultbar-actions"><button class="btn ghost sm" @click="loadShopBrands">查店铺品牌</button></div>
          </div>
          <div class="statusline" v-html="shopBrandMeta || '品牌集中度、Top10 份额、各品牌均价与评分（约 10 积分/次）'"></div>
          <div class="contentblock"><mini-table :cols="BRAND_COLS" :rows="shopBrands ? shopBrands.rows : []" empty="该店铺没有品牌数据（或接口无权限）"></mini-table></div>
        </section>
        <section class="resultcard">
          <div class="resulthead">
            <div class="resultr"><h3>类目结构</h3><span class="badge solid" v-if="shopCats">{{ (shopCats.rows||[]).length }}</span></div>
            <div class="resultbar-actions"><button class="btn ghost sm" @click="loadShopCats">查店铺类目</button></div>
          </div>
          <div class="statusline" v-html="shopCatMeta || '该店铺在各三级类目的销额/销量/商品数/均价（约 10 积分/次）'"></div>
          <div class="contentblock"><mini-table :cols="CAT_COLS" :rows="shopCats ? shopCats.rows : []" empty="该店铺没有类目数据"></mini-table></div>
        </section>
      </template>

      <!-- 变体 / 评论 / 相似（竞品详情页） -->
      <template v-if="page.tool === 'product'">
        <section class="resultcard">
          <div class="resulthead">
            <div class="resultr"><h3>变体分析</h3>
              <span class="badge solid">{{ varRows.length || varTopRows.length }}</span></div>
            <div class="resultbar-actions">
              <button class="btn ghost sm" @click="loadVarChars">特征维度</button>
              <button class="btn ghost sm" @click="loadVarList">变体列表</button>
            </div>
          </div>
          <div class="statusline" v-html="varMeta || '先点「特征维度」，再点某个维度看 Top10（每次约 10 积分）'"></div>
          <div class="contentblock">
            <div class="wchips" v-if="varChars.length">
              <button class="chipbtn" v-for="c in varChars" :key="c.sourceName" @click="loadVarTop(c.sourceName)">
                {{ c.name || c.sourceName }}<i>{{ c.sourceName }}</i>
              </button>
            </div>
            <mini-table v-if="varRows.length" :cols="VAR_COLS" :rows="varRows" empty="没有变体数据"></mini-table>
            <div class="tablewrap" v-if="varTopRows.length">
              <table><thead><tr><th>变体值</th><th>销售额排名</th><th>销量排名</th></tr></thead>
                <tbody><tr v-for="r in varTopRows" :key="r.name">
                  <td class="ttl">{{ r.name }}</td><td class="num">{{ r.rank || '—' }}</td><td class="num">{{ r.salesRank || '—' }}</td>
                </tr></tbody></table>
            </div>
          </div>
        </section>

        <section class="resultcard">
          <div class="resulthead">
            <div class="resultr"><h3>评论分析</h3><span class="muted">{{ revLang }}</span></div>
            <div class="resultbar-actions">
              <select class="insm" v-model="revLang"><option value="CN">中文</option><option value="EN">英文</option><option value="RU">俄文</option></select>
              <button class="btn ghost sm" @click="loadReview('stat')">星级分布</button>
              <button class="btn ghost sm" @click="loadReview('words')">词频</button>
              <button class="btn ghost sm" @click="loadReview('original')">原始评论</button>
              <button class="btn ghost sm" @click="loadReview('report')">AI 报表</button>
              <button class="btn ghost sm" @click="createRevTask">创建任务(200分)</button>
            </div>
          </div>
          <div class="statusline" v-html="revMeta || '报表/词频需先创建分析任务（200 积分/SKU），任务完成后再查'"></div>
          <div class="contentblock">
            <div class="empty" v-if="!revData">选择上面任一视图查看</div>
            <template v-else-if="revKind==='stat'">
              <div class="empty" v-if="!(revData.statistic && revData.statistic.reviewCount != null)">还没有该 SKU 的评论统计（可能未创建分析任务）</div>
              <template v-else>
                <div class="card-grid" style="padding-left:0;padding-right:0">
                  <div class="card"><b>{{ fmt(revData.statistic.reviewCount) }}</b><span>评论总数</span></div>
                  <div class="card"><b>{{ fmt(revData.statistic.averageRating) }}</b><span>平均评分</span></div>
                </div>
                <div class="barrow" v-for="n in [5,4,3,2,1]" :key="n">
                  <span class="barlab">{{ n }}★</span>
                  <span class="bar"><i :style="{width: Math.min(100, starPct(n)) + '%'}"></i></span>
                  <span class="barval">{{ fmt(starCnt(n)) }} · {{ fmt(starPct(n)) }}%</span>
                </div>
              </template>
            </template>
            <template v-else-if="revKind==='words'">
              <template v-if="(revData.sinicized||[]).length || (revData.origin||[]).length">
                <h4 v-if="(revData.sinicized||[]).length">中文词频（{{ revData.sinicized.length }}）</h4>
                <div class="wchips" v-if="(revData.sinicized||[]).length"><span class="wchip" v-for="w in revData.sinicized.slice(0,150)" :key="w">{{ w }}</span></div>
                <h4 v-if="(revData.origin||[]).length">原文词频（{{ revData.origin.length }}）</h4>
                <div class="wchips" v-if="(revData.origin||[]).length"><span class="wchip" v-for="w in revData.origin.slice(0,150)" :key="w">{{ w }}</span></div>
              </template>
              <div class="empty" v-else>没有词频数据（需先创建分析任务）</div>
            </template>
            <template v-else-if="revKind==='original'">
              <div class="empty" v-if="!(revData.rows||[]).length">没有原始评论</div>
              <div class="revlist" v-else>
                <div class="revitem" v-for="(r,i) in revData.rows.slice(0,60)" :key="i">
                  <div class="revhead"><b>{{ '★'.repeat(Math.max(0, Math.min(5, Number(r.star)||0))) }}</b>
                    <span class="muted">{{ r.date || r.ruDate || '' }} · {{ r.author || '匿名' }}<template v-if="r.skus"> · SKU {{ r.skus }}</template></span></div>
                  <div class="revtext">{{ r.text || '（无正文）' }}</div>
                  <div class="revphotos" v-if="(r.photos||[]).length"><img v-for="u in r.photos.slice(0,6)" :key="u" :src="u" loading="lazy"></div>
                </div>
              </div>
            </template>
            <template v-else>
              <template v-if="DIM_KEYS.some(k => (revData[k]||[]).length) || revData.optSugges || revData.qaAnalysis">
                <template v-for="k in DIM_KEYS" :key="k">
                  <template v-if="(revData[k]||[]).length">
                    <h4>{{ DIM_LABEL[k] }}（{{ revData[k].length }}）</h4>
                    <div class="wchips"><span class="wchip" v-for="(x,i) in revData[k]" :key="i">
                      {{ x.dimensionCn || x.dimensionRu || '' }}<template v-if="x.count != null"> · {{ fmt(x.count) }}条</template>
                      <template v-if="x.proportion != null"> · {{ (Number(x.proportion) * (Number(x.proportion) <= 1 ? 100 : 1)).toFixed(1) }}%</template>
                    </span></div>
                  </template>
                </template>
                <template v-if="revData.optSugges"><h4>运营建议</h4>
                  <div class="attrgrid"><template v-for="(v,k) in revData.optSugges" :key="k">
                    <div class="akey">{{ k }}</div><div class="aval">{{ v }}</div></template></div></template>
                <template v-if="revData.qaAnalysis"><h4>问答分析</h4>
                  <div class="attrgrid"><template v-for="(v,k) in revData.qaAnalysis" :key="k">
                    <div class="akey">{{ k }}</div><div class="aval">{{ v }}</div></template></div></template>
              </template>
              <div class="empty" v-else>没有报表数据（需先创建分析任务，再回来查报表）</div>
            </template>
          </div>
        </section>

        <section class="resultcard">
          <div class="resulthead">
            <div class="resultr"><h3>相似商品</h3><span class="badge solid">{{ simRows.length }}</span></div>
            <div class="resultbar-actions"><button class="btn ghost sm" @click="loadSimilar">查相似</button></div>
          </div>
          <div class="statusline" v-html="simMeta || '官方最多返回 21 条（含目标商品），带库存（约 10 积分/次）'"></div>
          <div class="contentblock"><mini-table :cols="SIM_COLS" :rows="simRows" empty="没有相似商品"></mini-table></div>
        </section>
      </template>
    </main>
  </div>

  <!-- 收藏面板 -->
  <div class="drawer" :class="{open: favOpen}" v-show="favOpen" style="width:min(460px,96vw)">
    <div class="drawer-head"><span>收藏（{{ favList.length }}）</span><button @click="favOpen = false">×</button></div>
    <div class="drawer-body">
      <div class="empty" v-if="!favList.length">还没有收藏。表格里点 ☆ 即可收藏。</div>
      <div class="revlist" v-else>
        <div class="revitem" v-for="f in favList" :key="f.sku" style="cursor:pointer" @click="openDrawer(f.sku)">
          <div class="revhead"><b>{{ f.title || f.sku }}</b></div>
          <div class="tiny">SKU {{ f.sku }}<template v-if="f.price"> · {{ money(f.price) }}₽</template>
            <template v-if="f.seller"> · {{ f.seller }}</template></div>
        </div>
      </div>
    </div>
  </div>

  <!-- 底部常驻工具条：翻页 + 表格横向滚动 -->
  <div class="bottombar" :class="{on: rows.length && page.tool !== 'product'}">
    <div class="bb-page">
      <button class="btn ghost sm" @click="go(-1)" :disabled="pageNo<=1">← 上一页</button>
      <span class="bb-info">第 {{ pageNo }} 页<template v-if="pageMeta.pages"> / {{ fmt(pageMeta.pages) }}</template></span>
      <button class="btn ghost sm" @click="go(1)"
              :disabled="pageMeta.pages ? pageNo >= pageMeta.pages : pageMeta.has_next_page === false">下一页 →</button>
    </div>
    <div class="bb-track" v-show="hOn" ref="hTrack" @pointerdown="trackDown" title="拖动横向浏览全部列">
      <div class="bb-thumb" :style="{ width: hThumbW + 'px', transform: 'translateX(' + hThumbX + 'px)' }"
           @pointerdown.stop="thumbDown"></div>
    </div>
  </div>

  <!-- 抽屉遮罩 -->
  <div class="drawer-backdrop" :class="{open: drawerOpen}" @click="closeDrawer"></div>
  <!-- 抽屉：仅 0 积分内容 -->
  <div class="drawer" :class="{open: drawerOpen}" v-show="drawerOpen">
    <div class="drawer-head"><span>商品 {{ drawerSku }}</span><button @click="closeDrawer">×</button></div>
    <div class="drawer-body">
      <div class="drawer-loading" v-if="drawerLoading">正在加载商品内容…</div>
      <div class="empty" style="color:var(--bad)" v-else-if="drawerContent && drawerContent.error">{{ drawerContent.error }}</div>
      <template v-else-if="drawerContent">
        <h4>图片（{{ (drawerContent.images||[]).length }}）</h4>
        <div class="thumbs"><a v-for="u in (drawerContent.images||[]).slice(0,24)" :key="u" :href="u" target="_blank" rel="noopener"><img :class="imgCls(u)" :src="u" loading="lazy" @load="onImgLoad"></a></div>
        <div class="contenthead"><b>{{ drawerContent.title }}</b>
          <span class="muted">{{ drawerContent.brand }}<template v-if="drawerContent.price"> · {{ money(drawerContent.price) }}₽</template></span></div>
        <h4>描述（{{ (drawerContent.description||'').length }} 字）</h4>
        <div class="descbox">{{ drawerContent.description || '无' }}</div>
        <h4>产品属性（{{ (drawerContent.attributes||[]).length }}）</h4>
        <div class="attrgrid"><template v-for="a in (drawerContent.attributes||[])" :key="a.name">
          <div class="akey">{{ a.name }}</div><div class="aval"><template v-if="a.name === '主题标签'"><span class="tagchip" v-for="v in a.values" :key="v">{{ v }}</span></template><template v-else>{{ (a.values||[]).join(' / ') }}</template></div></template></div>
        <h4>变体维度（{{ (drawerContent.aspects||[]).length }}）</h4>
        <div class="aspectrow" v-for="a in (drawerContent.aspects||[])" :key="a.name">
          <span class="aspectname">{{ a.name }}</span>
          <span class="wchips"><a class="wchip" href="javascript:;" v-for="v in a.values.slice(0,40)" :key="v.sku" @click="openDrawer(v.sku)">{{ v.value }}</a></span>
        </div>
        <h4>卖家与库存</h4>
        <div class="attrgrid"><template v-for="row in drawerExtra" :key="row[0]">
          <div class="akey">{{ row[0] }}</div><div class="aval">{{ row[1] }}</div></template></div>
        <h4>富文本<template v-if="drawerRich.texts.length || drawerRich.imgs.length">（{{ drawerRich.texts.length }} 段文字<template v-if="drawerRich.imgs.length"> · {{ drawerRich.imgs.length }} 张图</template>）</template></h4>
        <div class="richdesc" v-if="drawerRich.texts.length || drawerRich.imgs.length">
          <p v-for="(tx, i) in drawerRich.texts" :key="'rt'+i">{{ tx }}</p>
          <div class="richimgs"><a v-for="u in drawerRich.imgs" :key="u" :href="u" target="_blank" rel="noopener"><img :src="u" loading="lazy"></a></div>
        </div>
        <div class="empty" v-else>该商品没有富文本块（只有上方纯文本描述）</div>
      </template>
    </div>
    <div class="drawer-foot">抽屉只展示 0 积分内容；Seerfar 指标请到「竞品详情」查询（约 20 积分/次）。</div>
  </div>

  <transition name="toast">
    <div class="toast" :class="{bad: toastBad}" v-if="toastMsg">{{ toastMsg }}</div>
  </transition>
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

  const _app = createApp(App);
  _app.component('mini-table', MiniTable);
  _app.mount('#app');
})();
