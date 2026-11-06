/** 对比不同请求头组合下 ozon 的返回，定位是哪一项触发了风控 */
import path from 'node:path';

const CDP_PORT = Number(process.env.CDP_PORT || 9222);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function newTab(url) {
  const u = `http://127.0.0.1:${CDP_PORT}/json/new?${encodeURIComponent(url)}`;
  let r = await fetch(u, { method: 'PUT' });
  if (!r.ok) r = await fetch(u);
  return r.json();
}
function connect(wsUrl) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(wsUrl);
    const pending = new Map(); let id = 0;
    const api = { send(m, p = {}) { const mid = ++id; ws.send(JSON.stringify({ id: mid, method: m, params: p })); return new Promise((ok, no) => pending.set(mid, { resolve: ok, reject: no })); }, close() { ws.close(); } };
    ws.onopen = () => res(api);
    ws.onerror = () => rej(new Error('ws'));
    ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); } };
  });
}

const URL0 = 'https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=' +
  encodeURIComponent('/category/elektronika-15500/?sorting=new&layout_container=searchResultsV2&page=1');

const VARIANTS = [
  ['只有 accept', { accept: 'application/json' }],
  ['SPA 全套', {
    accept: 'application/json, text/plain, */*',
    'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'x-o3-app-name': 'dweb_client',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
  }],
  ['只加 x-o3-app-name', { accept: 'application/json', 'x-o3-app-name': 'dweb_client' }],
  ['accept + accept-language', { accept: 'application/json', 'accept-language': 'ru-RU,ru;q=0.9' }],
];

async function main() {
  const tab = await newTab('https://www.ozon.ru/');
  const cdp = await connect(tab.webSocketDebuggerUrl);
  await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
  for (let i = 0; i < 40; i++) {
    const r = await cdp.send('Runtime.evaluate', { expression: 'document.title', returnByValue: true });
    if ((r.result?.value || '') && !/Antibot/.test(r.result.value)) break;
    await sleep(500);
  }
  for (const [name, headers] of VARIANTS) {
    const expr = `(async()=>{const r=await fetch(${JSON.stringify(URL0)},{credentials:'include',headers:${JSON.stringify(headers)}});const t=await r.text();return JSON.stringify({s:r.status,n:t.length,inc:t.includes('incidentId')})})()`;
    const res = await cdp.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    const v = res.result?.value ? JSON.parse(res.result.value) : { s: 'exc' };
    console.log(`${String(name).padEnd(26)} status=${v.s} len=${v.n} incident=${v.inc}`);
    await sleep(1500);
  }
  cdp.close();
  process.exit(0);
}
main().catch(e => { console.error(e); process.exit(1); });
