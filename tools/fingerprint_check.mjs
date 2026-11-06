/**
 * 指纹自检：确认我们发往 ozon 的请求在「服务端看来」是什么 TLS / HTTP2 / 头指纹。
 *
 * 做法：用同一个 CDP 浏览器打开第三方指纹回显站，读回服务端观察到的结果
 * （TLS 握手发生在我们这台 Chrome 里，所以回显的就是真实的握手指纹）。
 *
 * 用法: node tools/fingerprint_check.mjs
 */
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

async function probe(url) {
  const tab = await newTab('about:blank');
  const cdp = await connect(tab.webSocketDebuggerUrl);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.navigate', { url });
  let text = '';
  for (let i = 0; i < 30; i++) {
    await sleep(600);
    const r = await cdp.send('Runtime.evaluate', {
      expression: 'document.body ? document.body.innerText : ""',
      returnByValue: true,
    });
    text = (r.result && r.result.value) || '';
    if (text && text.length > 30) break;
  }
  cdp.close();
  try { await fetch(`http://127.0.0.1:${CDP_PORT}/json/close/${tab.id}`); } catch { }
  return text;
}

function line(k, v) { console.log(`  ${k.padEnd(22)} ${v}`); }

async function main() {
  console.log('=== TLS / HTTP2 指纹（tls.peet.ws 回显）===');
  const t = await probe('https://tls.peet.ws/api/all');
  let j = null;
  try { j = JSON.parse(t); } catch { }
  if (j) {
    line('JA3 hash', j.tls?.ja3_hash || '-');
    line('JA3 text', (j.tls?.ja3 || '-').slice(0, 80) + '...');
    line('JA4', j.tls?.ja4 || '-');
    line('PeetPrint', j.tls?.peetprint_hash || '-');
    line('HTTP/2 akamai', j.http2?.akamai_fingerprint_hash || '-');
    line('HTTP/2 设置', JSON.stringify(j.http2?.sent_frames?.[0]?.frame_settings || {}).slice(0, 120));
    line('TLS 版本', (j.tls?.tls_version_record ?? '-') + ' / ciphers ' + (j.tls?.ciphers?.length ?? '-'));
    line('ALPN', (j.tls?.extensions || []).find((e) => e.name === 'application_layer_protocol_negotiation')?.protocols?.join(',') || '-');
  } else {
    console.log('  (未拿到 JSON，原始返回前 200 字)', t.slice(0, 200));
  }

  console.log('\n=== 请求头（httpbin 回显）===');
  const h = await probe('https://httpbin.org/headers');
  try {
    const obj = JSON.parse(h);
    Object.entries(obj.headers || {}).forEach(([k, v]) => line(k, String(v).slice(0, 90)));
  } catch {
    console.log(h.slice(0, 400));
  }
  console.log('\n以上握手由本机 Chrome 真实发起；只要走 CDP，服务端看到的就是这套指纹。');
}

main().catch((e) => { console.error(e); process.exit(1); });
