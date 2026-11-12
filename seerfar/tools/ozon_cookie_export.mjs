// tools/ozon_cookie_export.mjs —— 从「已经开着」的调试 Chrome 导出 Ozon cookie。
//
// 注意：本脚本**不会启动 Chrome**。它只连接本机已运行的 CDP 端口，
// 用浏览器级 Storage.getCookies 取回过完 abt-challenge 的会话，
// 落盘成 data/ozon_cookies.json，供 web/ozon_http.py 纯 HTTP 直连复用。
//
// 用法：
//   node tools/ozon_cookie_export.mjs                  # 默认 9222 -> data/ozon_cookies.json
//   node tools/ozon_cookie_export.mjs --port 9223
//   node tools/ozon_cookie_export.mjs --stdout         # 只检查，不落盘
//
// cookie 过期 / Ozon 又开始 307 重定向时，重跑一次即可（或用已开着的 Chrome 过一次挑战再跑）。

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const opt = (k, d) => {
  const i = args.indexOf(k);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : d;
};
const PORT = Number(opt('--port', process.env.OZON_CDP_PORT || '9222'));
const OUT = path.resolve(ROOT, opt('--out', 'data/ozon_cookies.json'));
const STDOUT_ONLY = args.includes('--stdout');

function cdpCall(wsUrl, method, params = {}, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    const timer = setTimeout(() => { try { ws.close(); } catch {} reject(new Error(`CDP 超时: ${method}`)); }, timeoutMs);
    ws.onopen = () => ws.send(JSON.stringify({ id: 1, method, params }));
    ws.onerror = (e) => { clearTimeout(timer); reject(new Error('WebSocket 连接失败：' + (e?.message || 'unknown'))); };
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id !== 1) return;
      clearTimeout(timer);
      try { ws.close(); } catch {}
      if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
      else resolve(msg.result);
    };
    ws.onclose = () => clearTimeout(timer);
  });
}

const version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`, { signal: AbortSignal.timeout(5000) })).json();
const browserWs = version.webSocketDebuggerUrl;
if (!browserWs) throw new Error('拿不到浏览器级 WebSocket 地址');

let result;
try {
  result = await cdpCall(browserWs, 'Storage.getCookies');
} catch (e) {
  // 某些 Chrome 版本没有 Storage.getCookies，退回 Network.getAllCookies（页面级）
  const tabs = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
  const page = tabs.find(t => t.type === 'page') || tabs[0];
  if (!page) throw e;
  result = await cdpCall(page.webSocketDebuggerUrl, 'Network.getAllCookies');
}

const all = result?.cookies || [];
const cookies = all
  .filter(c => /(^|\.)ozon\.ru$/.test((c.domain || '').replace(/^\./, '')))
  .filter(c => c.name && c.value !== undefined)
  .map(c => ({
    name: c.name,
    value: c.value,
    domain: c.domain,
    path: c.path || '/',
    expires: c.expires || -1,
    secure: !!c.secure,
    httpOnly: !!c.httpOnly,
  }));

if (!cookies.length) {
  console.error('没有拿到任何 .ozon.ru cookie。请先在那个 Chrome 里打开 https://www.ozon.ru/ 过一次验证，再重跑。');
  process.exit(2);
}

const payload = {
  exported_at: new Date().toISOString(),
  source: 'cdp-export',
  browser: version.Browser || '',
  user_agent: version['User-Agent'] || '',
  note: '从已运行的调试 Chrome 导出；含敏感会话，勿外传/勿入库。失效时重跑 tools/ozon_cookie_export.mjs。',
  cookies,
};

if (STDOUT_ONLY) {
  console.log(JSON.stringify({ ok: true, count: cookies.length, names: cookies.map(c => c.name), browser: payload.browser }, null, 2));
} else {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(payload, null, 2), 'utf8');
  try { fs.chmodSync(OUT, 0o600); } catch {}
  console.log(`已导出 ${cookies.length} 条 Ozon cookie -> ${OUT}`);
  console.log('名称：' + cookies.map(c => c.name).join(', '));
  console.log('浏览器：' + payload.browser);
}
