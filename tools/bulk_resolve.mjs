/**
 * 批量把类目名解析成 ozon.ru 前台类目 slug —— 走本地服务的 /api/resolve。
 *
 * 为什么不再自己开 CDP 标签页：
 *   自己在 headless 里 newTab 拿到的会话可能已经被风控标记（哪怕 title 正常），
 *   于是整批零命中。统一交给 server.py 的 CDP 客户端 + 限速器 + 脏标签页检测，
 *   成功率稳定得多；脚本只当“驱动器”，category_map.json 由服务端单写，不会打架。
 *
 * 用法:
 *   node tools/bulk_resolve.mjs                       # 全部未映射节点
 *   node tools/bulk_resolve.mjs --limit 200
 *   node tools/bulk_resolve.mjs --api http://127.0.0.1:8899 --conc 2
 *
 * 可随时 Ctrl+C / 关掉，重跑自动跳过已映射。
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve('.');
const TREE = path.join(ROOT, 'web', 'categories_tree.json');
const MAP = path.join(ROOT, 'web', 'category_map.json');

const argv = process.argv.slice(2);
const arg = (n, d) => {
  const i = argv.indexOf('--' + n);
  return i > -1 && argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : d;
};
const API = String(arg('api', 'http://127.0.0.1:8899')).replace(/\/+$/, '');
const LIMIT = Number(arg('limit', '999999'));
const CONC = Number(arg('conc', '2'));
const DELAY = Number(arg('delay', '150'));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const tree = JSON.parse(fs.readFileSync(TREE, 'utf8')).tree;
const names = new Set();
(function walk(ns) {
  for (const n of ns) {
    if (n.n) names.add(n.n);
    if (n.c) walk(n.c);
  }
})(tree);

let map = {};
try { map = JSON.parse(fs.readFileSync(MAP, 'utf8')); } catch { map = {}; }

const pending = [...names].filter((n) => !map['name:' + n]).slice(0, LIMIT);
console.log(`本地服务 ${API}｜节点名 ${names.size}｜已映射 ${Object.keys(map).length}｜本次待解析 ${pending.length}`);
if (!pending.length) process.exit(0);

async function resolveOne(name) {
  try {
    const r = await fetch(`${API}/api/resolve?name=${encodeURIComponent(name)}`);
    if (!r.ok) return { name, slug: null, err: 'http ' + r.status };
    const j = await r.json();
    return { name, slug: j.slug || null, err: j.error || null };
  } catch (e) {
    return { name, slug: null, err: String(e.message || e) };
  }
}

const t0 = Date.now();
let done = 0, hit = 0, miss = 0, errStreak = 0, cooling = 0;

for (let i = 0; i < pending.length; i += CONC) {
  const batch = pending.slice(i, i + CONC);
  const res = await Promise.all(batch.map(resolveOne));
  let batchHit = 0;
  for (const r of res) {
    done++;
    if (r.slug) { hit++; batchHit++; }
    else miss++;
    if (r.err && /冷却|限流|Chrome/.test(r.err)) cooling++;
  }

  if (batchHit === 0) {
    errStreak++;
    if (errStreak % 5 === 0) {
      const el = (Date.now() - t0) / 1000;
      console.log(`  ⚠ 连续 ${errStreak} 批零命中（累计 ${done}/${pending.length}），等待重试…`);
    }
    if (errStreak >= 30) {
      console.log('连续 30 批零命中，先停。稍后重跑即可从断点继续。');
      process.exit(2);
    }
    await sleep(Math.min(20000, 2000 * errStreak));
  } else {
    errStreak = 0;
  }

  if (done % 100 < CONC || done >= pending.length) {
    const el = (Date.now() - t0) / 1000;
    const rate = done / el;
    const left = pending.length - done;
    const eta = rate > 0 ? Math.round(left / rate / 60) : '?';
    console.log(`  ${done}/${pending.length}  命中 ${hit}  未命中 ${miss}  ${rate.toFixed(1)}/s  剩余约 ${eta} 分钟`);
  }
  await sleep(DELAY);
}

console.log(`\n完成：命中 ${hit}，未命中 ${miss}。映射文件由服务端写入 ${MAP}`);
process.exit(0);
