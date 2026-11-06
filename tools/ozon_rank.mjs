/**
 * Ozon 榜单抓取器（复用已过 antibot 的 Chrome 会话）
 *
 * 用法:
 *   node tools/ozon_rank.mjs --category elektronika-15500 --sort new,score,discount --pages 3
 *   node tools/ozon_rank.mjs --all --sort new --pages 2
 *   node tools/ozon_rank.mjs --category a,b --sort score --pages 5 --out data/2026-11-06
 *
 * 参数:
 *   --category  csv 形式的类目 slug（如 elektronika-15500）
 *   --all       用内置 35 个一级类目
 *   --sort      new | score | rating | discount （逗号分隔，可多选）
 *   --pages     每个榜单抓几页，默认 3
 *   --out       输出目录，默认 data
 *   --delay     每请求间隔 ms，默认 600
 */
import fs from 'node:fs';
import path from 'node:path';

const CDP_PORT = Number(process.env.CDP_PORT || 9222);

const ALL_CATEGORIES = [
  'elektronika-15500', 'telefony-i-smart-chasy-15501', 'noutbuki-planshety-i-elektronnye-knigi-8730',
  'bytovaya-tehnika-10500', 'televizory-i-videotehnika-15527', 'audiotehnika-15543',
  'kompyuternye-komplektuyushchie-15709', 'tsifrovye-tovary-32056', 'igry-i-soft-13300',
  'odezhda-obuv-i-aksessuary-7500', 'obuv-17777', 'aksessuary-7697',
  'krasota-i-zdorove-6500', 'apteka-6000', 'dom-i-sad-14500', 'mebel-15000',
  'stroitelstvo-i-remont-9700', 'bytovaya-himiya-14572', 'produkty-pitaniya-9200',
  'supermarket-25000', 'detskie-tovary-7000', 'sport-i-otdyh-11000',
  'ohota-rybalka-turizm-33332', 'avtotovary-8500', 'avtomobili-39803',
  'tovary-dlya-zhivotnyh-12300', 'knigi-16500', 'kantselyarskie-tovary-18000',
  'hobbi-i-tvorchestvo-13500', 'yuvelirnye-ukrasheniya-50001', 'antikvariat-vintazh-iskusstvo-8000',
  'elektronnye-sigarety-i-tovary-dlya-kureniya-35659', 'muzyka-i-video-13100',
  'tovary-dlya-vzroslyh-9000', 'podarochnye-sertifikaty-37234',
];

// ---------- CLI ----------
const argv = process.argv.slice(2);
function arg(name, def) {
  const i = argv.indexOf('--' + name);
  if (i === -1) return def;
  const v = argv[i + 1];
  return v && !v.startsWith('--') ? v : true;
}
const catArg = arg('category', null);
const useAll = argv.includes('--all');
const sorts = String(arg('sort', 'new,score,rating,discount')).split(',').map(s => s.trim()).filter(Boolean);
const pages = Number(arg('pages', 3));
const outDir = path.resolve(String(arg('out', 'data')));
const delay = Number(arg('delay', 600));

const categories = useAll ? ALL_CATEGORIES : (catArg ? String(catArg).split(',').map(s => s.trim()) : []);
if (!categories.length) {
  console.error('need --category slug[,slug] or --all');
  process.exit(1);
}
fs.mkdirSync(outDir, { recursive: true });

// ---------- CDP ----------
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function newTab() {
  const r = await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?${encodeURIComponent('https://www.ozon.ru/')}`, { method: 'PUT' });
  return (r.ok ? r : await fetch(`http://127.0.0.1:${CDP_PORT}/json/new?${encodeURIComponent('https://www.ozon.ru/')}`)).json();
}

function connect(wsUrl) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(wsUrl);
    const pending = new Map();
    let id = 0;
    const api = {
      send(method, params = {}) {
        const mid = ++id;
        ws.send(JSON.stringify({ id: mid, method, params }));
        return new Promise((resolve, reject) => pending.set(mid, { resolve, reject }));
      },
      close() { ws.close(); },
    };
    ws.onopen = () => res(api);
    ws.onerror = () => rej(new Error('cdp ws error'));
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id && pending.has(m.id)) {
        const p = pending.get(m.id); pending.delete(m.id);
        m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
      }
    };
  });
}

// ---------- 解析 ----------
function txt(node) {
  if (!node || typeof node !== 'object') return '';
  if (node.textDS) return node.textDS.text || '';
  if (node.text && typeof node.text === 'object') return node.text.text || '';
  return '';
}
const clean = s => String(s || '').replace(/[\u2009\u202f\u00a0]/g, ' ').replace(/₽/g, '').replace(/\s+/g, ' ').trim();

function parseTile(it) {
  const row = {
    sku: it.sku || it.id, name: '', price: '', price_original: '', discount: '',
    stock: '', rating: '', reviews: '', url: '',
  };
  const link = (it.action || {}).link || '';
  row.url = link.startsWith('/') ? 'https://www.ozon.ru' + link.split('?')[0] : link;
  for (const st of it.mainState || []) {
    if (st.type === 'priceV2') {
      const p = st.priceV2 || {};
      for (const pr of p.price || []) {
        if (pr.textStyle === 'PRICE') row.price = clean(pr.text).replace(/\s/g, '');
        if (pr.textStyle === 'ORIGINAL_PRICE') row.price_original = clean(pr.text).replace(/\s/g, '');
      }
      row.discount = p.discount || '';
    } else if (st.type === 'textDS') {
      const t = txt(st);
      if (/осталось/.test(t)) row.stock = clean(t).replace(/\s/g, '');
      else if (st.id === 'name' || (!row.name && t.length > 12)) row.name = t;
    } else if (st.type === 'labelListV2') {
      const flat = JSON.stringify(st);
      if (flat.includes('ic_s_star_filled') || flat.includes('graphicRating')) {
        const texts = (st.labelListV2?.items || []).filter(x => x.type === 'text').map(x => x.text?.text || '');
        if (texts[0]) row.rating = texts[0];
        if (texts[1]) row.reviews = clean(texts[1]);
      }
    }
  }
  return row;
}

function extractTiles(payload) {
  if (!payload || !payload.widgetStates) return [];
  const rows = [];
  for (const [k, v] of Object.entries(payload.widgetStates)) {
    if (!/tileGrid|searchResults/i.test(k)) continue;
    let obj;
    try { obj = typeof v === 'string' ? JSON.parse(v) : v; } catch { continue; }
    for (const it of obj.items || []) {
      if (it && (it.sku || it.mainState)) rows.push(parseTile(it));
    }
  }
  return rows;
}

// 从 infiniteVirtualPaginator 里拿真正的下一页地址（带 search_page_state token）
function nextPageOf(payload) {
  if (!payload || !payload.widgetStates) return null;
  for (const [k, v] of Object.entries(payload.widgetStates)) {
    if (!/infiniteVirtualPaginator/i.test(k)) continue;
    let obj;
    try { obj = typeof v === 'string' ? JSON.parse(v) : v; } catch { continue; }
    if (obj && obj.nextPage) return obj.nextPage;
  }
  return null;
}

// ---------- CSV ----------
function toCsv(rows, cols) {
  const esc = v => {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  return '\ufeff' + [cols.join(','), ...rows.map(r => cols.map(c => esc(r[c])).join(','))].join('\n');
}

// ---------- 主流程 ----------
async function main() {
  const tab = await newTab();
  const cdp = await connect(tab.webSocketDebuggerUrl);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');

  // 等 antibot 通过
  for (let i = 0; i < 40; i++) {
    const r = await cdp.send('Runtime.evaluate', { expression: 'document.title', returnByValue: true });
    const t = r.result?.value || '';
    if (t && !/Antibot/i.test(t)) break;
    await sleep(500);
  }

  async function apiGet(pathAndQuery) {
    const url = 'https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=' + encodeURIComponent(pathAndQuery);
    for (let attempt = 0; attempt < 3; attempt++) {
      const res = await cdp.send('Runtime.evaluate', {
        expression: `(async()=>{const r=await fetch(${JSON.stringify(url)},{credentials:'include',headers:{'accept':'application/json'}});const t=await r.text();return JSON.stringify({s:r.status,b:t})})()`,
        awaitPromise: true, returnByValue: true,
      });
      if (res.exceptionDetails) { await sleep(1500); continue; }
      const { s, b } = JSON.parse(res.result.value);
      if (s === 200 && b.length > 5000 && !/Antibot/i.test(b)) {
        try { return JSON.parse(b); } catch { return null; }
      }
      await sleep(2000 + attempt * 2000);
    }
    return null;
  }

  const summary = [];
  const seenGlobal = new Set();
  for (const cat of categories) {
    for (const sort of sorts) {
      const all = [];
      const seen = new Set();
      let ok = 0;
      const start = `/category/${cat}/?sorting=${sort}&layout_container=searchResultsV2`;
      let stale = 0;
      for (let p = 1; p <= pages; p++) {
        const payload = await apiGet(`${start}&page=${p}`, p);
        if (!payload) break;
        const rows = extractTiles(payload);
        if (!rows.length) break;
        let added = 0;
        for (const r of rows) {
          if (seen.has(r.sku)) continue;
          seen.add(r.sku);
          all.push({ category: cat, sort, page: p, rank: all.length + 1, ...r });
          added++;
        }
        if (!added) { if (++stale >= 3) break; } else stale = 0;
        ok++;
        await sleep(delay);
      }
      if (!all.length) { summary.push({ category: cat, sort, pages: ok, products: 0 }); continue; }

      const prices = all.map(r => Number(r.price)).filter(n => n > 0);
      const discounts = all.map(r => Math.abs(parseFloat(String(r.discount).replace('%', '').replace('−', '-')))).filter(n => !isNaN(n));
      const ratings = all.map(r => parseFloat(r.rating)).filter(n => !isNaN(n));
      const avg = a => a.length ? +(a.reduce((x, y) => x + y, 0) / a.length).toFixed(2) : null;

      const cols = ['category', 'sort', 'page', 'rank', 'sku', 'name', 'price', 'price_original', 'discount', 'stock', 'rating', 'reviews', 'url'];
      const file = path.join(outDir, `${cat}__${sort}.csv`);
      fs.writeFileSync(file, toCsv(all, cols), 'utf8');
      all.forEach(r => seenGlobal.add(r.sku));

      const stat = {
        category: cat, sort, pages: ok, products: all.length,
        price_avg: avg(prices),
        price_min: prices.length ? Math.min(...prices) : null,
        price_max: prices.length ? Math.max(...prices) : null,
        discount_avg: avg(discounts),
        rating_avg: avg(ratings),
        file,
      };
      summary.push(stat);
      console.log(JSON.stringify(stat));
    }
  }

  fs.writeFileSync(path.join(outDir, '_summary.json'), JSON.stringify(summary, null, 2), 'utf8');
  console.log('\nDONE ->', outDir);
  cdp.close();
  process.exit(0);
}
main().catch(e => { console.error(e); process.exit(1); });
