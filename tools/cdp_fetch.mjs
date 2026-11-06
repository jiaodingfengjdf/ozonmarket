// CDP 复用已过验的 Chrome 会话，在页面上下文里 fetch Ozon 接口
// 用法: node cdp_fetch.mjs <url1> [url2 ...]
// 输出: 每个 URL 保存到 out/ 目录，文件名由 URL hash 决定；同时打印摘要
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const PORT = Number(process.env.CDP_PORT || 9222);
const OUT = path.resolve('out');
fs.mkdirSync(OUT, { recursive: true });

async function targetList() {
  const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
  return r.json();
}

async function newTab(url) {
  const r = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' });
  if (!r.ok) {
    const r2 = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`);
    return r2.json();
  }
  return r.json();
}

function connect(wsUrl) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(wsUrl);
    const pending = new Map();
    let id = 0;
    ws.onopen = () => res({
      send(method, params = {}) {
        const mid = ++id;
        ws.send(JSON.stringify({ id: mid, method, params }));
        return new Promise((resolve, reject) => pending.set(mid, { resolve, reject }));
      },
      on(event, fn) { ws.addEventListener('message', (e) => {
        const m = JSON.parse(e.data);
        if (m.method === event) fn(m.params);
      }); },
      close() { ws.close(); },
    });
    ws.onerror = (e) => rej(new Error('ws error ' + e.message));
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id && pending.has(m.id)) {
        const p = pending.get(m.id); pending.delete(m.id);
        m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
      }
    };
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const urls = process.argv.slice(2);
  if (!urls.length) { console.error('no urls'); process.exit(1); }

  const tab = await newTab('https://www.ozon.ru/');
  const cdp = await connect(tab.webSocketDebuggerUrl);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');

  // 等首页过 antibot
  for (let i = 0; i < 40; i++) {
    const r = await cdp.send('Runtime.evaluate', {
      expression: 'document.title',
      returnByValue: true,
    });
    const t = r.result?.value || '';
    if (t && !/Antibot/i.test(t)) break;
    await sleep(500);
  }

  for (const url of urls) {
    const expr = `
      (async () => {
        const r = await fetch(${JSON.stringify(url)}, {
          credentials: 'include',
          headers: { 'accept': 'application/json, text/plain, */*', 'x-o3-app-name': 'dweb_client' }
        });
        const t = await r.text();
        return JSON.stringify({ status: r.status, len: t.length, body: t });
      })()
    `;
    try {
      const res = await cdp.send('Runtime.evaluate', {
        expression: expr, awaitPromise: true, returnByValue: true,
      });
      if (res.exceptionDetails) { console.log('EXC', url, JSON.stringify(res.exceptionDetails).slice(0, 300)); continue; }
      const payload = JSON.parse(res.result.value);
      const h = crypto.createHash('sha1').update(url).digest('hex').slice(0, 10);
      const file = path.join(OUT, `${h}.json`);
      fs.writeFileSync(file, payload.body, 'utf8');
      console.log(`${payload.status}\t${payload.len}\t${file}\t${url.slice(0, 130)}`);
    } catch (e) {
      console.log('ERR', url, e.message);
    }
  }
  cdp.close();
  process.exit(0);
}
main();
