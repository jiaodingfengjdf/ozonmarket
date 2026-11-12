# -*- coding: utf-8 -*-
"""Seerfar 选品台 · 本地 Web 服务。

只用 Python 标准库 http.server，不依赖 Flask/FastAPI。
启动：python server.py --port 8900   →   http://127.0.0.1:8900/
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sf_catalog import get_catalog
from sf_client import (ApiError, AuthError, BudgetExceeded, ConfirmRequired,
                       CreditExhausted, ENDPOINTS, get_client)
import sf_content as CONTENT
import sf_db
from sf_db import STORE
from sf_export import (EXPORT_DIR, export_full, export_keywords, export_products,
                       export_report, export_workbook)
from sf_select import KEYWORD_COLUMNS, PRODUCT_COLUMNS, SORT_FIELDS, Selector

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

def _force(b):
    """前端把 force 复选框放在 filters 里，统一兼容顶层与 filters 两种传法。"""
    f = b.get("filters") or {}
    return bool(b.get("force") or f.get("force"))


def _multi_guard(b, endpoint_name):
    """多页抓取要按页计费，pages>1 时先返回预估，等前端确认（confirm=true）再执行。"""
    f = b.get("filters") or {}
    try:
        pages = int(f.get("pages") or 1)
    except (TypeError, ValueError):
        pages = 1
    if pages <= 1 or b.get("confirm"):
        return None
    cost = CLIENT.cost_of(endpoint_name) * pages
    return {"need_confirm": True, "pages": pages,
            "estimated_credit": round(cost, 1),
            "tip": f"抓取 {pages} 页，最多约 {round(cost, 1)} 积分（命中缓存不扣费）"}


CLIENT = get_client()
CATALOG = get_catalog(CLIENT)
SELECTOR = Selector(CLIENT, catalog=CATALOG)
CATALOG.ensure_imported()  # 首次启动自动导入内置类目表（本地操作，不扣积分）


class Handler(BaseHTTPRequestHandler):
    server_version = "SeerfarSelector/1.0"

    def log_message(self, fmt, *args):
        # 只打印 API 与错误，静态文件请求不打日志
        msg = fmt % args
        if "/api/" in msg or " 4" in msg or " 5" in msg:
            sys.stderr.write("[web] " + msg + "\n")

    # ---------- 基础响应 ----------
    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def ok(self, data, **meta):
        self.json({"ok": True, "data": data, "meta": meta})

    def fail(self, err, code=400, kind="Error"):
        self.json({"ok": False, "error": str(err), "type": kind}, code)

    def qs_filters(self, qs):
        """query string → 本地库筛选字典（字段白名单，避免拼 SQL 被注入）。"""
        def one(k, d=None):
            return (qs.get(k) or [d])[0]
        f = {}
        for k in ("q", "category_id", "seller", "brand", "kind",
                  "favorite_only", "has_opportunity"):
            v = one(k)
            if v not in (None, ""):
                f[k] = v
        allowed = set(sf_db.PRODUCT_FILTER_NUM) | set(sf_db.KEYWORD_FILTER_NUM)
        for name in qs.keys():
            if name.endswith("_min") or name.endswith("_max"):
                if name[:-4] in allowed:
                    f[name] = one(name)
        return f

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # ---------- 路由 ----------
    # 10 个独立功能页面（干净 URL → static/ 下的 HTML）

    PAGES = {
        "/": "vue/index.html",
        "/index.html": "vue/index.html",
        "/select": "vue/index.html",
        "/hotwords": "vue/index.html",
        "/mining": "vue/index.html",
        "/backsearch": "vue/index.html",
        "/product": "vue/index.html",
        "/category": "vue/index.html",
        "/shop": "vue/index.html",
        "/local-products": "vue/index.html",
        "/local-keywords": "vue/index.html",
        "/logs": "vue/index.html",
    }

    def do_GET(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)
        one = lambda k, d=None: (qs.get(k) or [d])[0]
        try:
            if p in ("/app", "/app/") or p.startswith("/app/"):
                return self.static("vue/index.html")      # Vue SPA（hash 路由）
            if p in self.PAGES:
                return self.static(self.PAGES[p])
            if p.startswith("/static/"):
                return self.static(p[len("/static/"):])
            if p == "/api/download":
                return self.download(one("file", ""))
            if p == "/api/status":
                return self.ok({**CLIENT.stats(), "server": {"port": self.server.server_port,
                                                             "endpoints": len(ENDPOINTS)}})
            if p == "/api/categories":
                q = one("q")
                if q:
                    return self.ok(CATALOG.search(q, 200))
                return self.ok(CATALOG.tree(one("parent") or None,
                                            int(one("level", 1) or 1)))
            if p == "/api/category/leaves":
                # 一级/二级类目下钻到三级（叶子）子类目，用于直接出商品清单
                return self.ok(CATALOG.leaves(one("parent", ""),
                                              int(one("limit", 200) or 200)))
            if p == "/api/local/products":
                f = self.qs_filters(qs)
                rows, total = STORE.products_page(f,
                                                  one("sort", "revenue") or "revenue",
                                                  one("direction", "DESC") or "DESC",
                                                  int(one("limit", 200) or 200),
                                                  int(one("offset", 0) or 0))
                favs = STORE.favorite_sku_set()
                for r in rows:
                    r["favorite"] = r.get("sku") in favs
                return self.ok({"rows": rows, "total": total, "filters": f})
            if p == "/api/local/keywords":
                f = self.qs_filters(qs)
                rows, total = STORE.keywords_page(f, one("sort", "search_volume") or "search_volume",
                                                  int(one("limit", 200) or 200),
                                                  int(one("offset", 0) or 0))
                return self.ok({"rows": rows, "total": total, "filters": f})
            if p == "/api/favorites":
                return self.ok({"rows": STORE.favorites(int(one("limit", 500) or 500))})
            if p == "/api/logs":
                return self.ok({"recent": STORE.recent_logs(int(one("limit", 60) or 60)),
                                "daily": STORE.daily_usage()})
            if p == "/api/product":
                return self.ok(SELECTOR.product(one("sku", ""), one("date_range", "past_30_days"),
                                                with_trend=one("trend", "1") != "0",
                                                with_similar=one("similar") == "1"))
            if p == "/api/variations":
                return self.ok(SELECTOR.variations(one("sku", ""),
                                                   int(one("page", 1) or 1),
                                                   int(one("size", 50) or 50)))
            if p == "/api/varchars":
                return self.ok(SELECTOR.var_characteristics(one("sku", "")))
            if p == "/api/vartop":
                return self.ok(SELECTOR.var_top(one("sku", ""), one("characteristic", "")))
            if p == "/api/reviews":
                return self.reviews(one("sku", ""), one("type", "stat"), one("language", "CN"))
            if p == "/api/shop":
                return self.ok(SELECTOR.shop(int(one("id", "0") or 0),
                                             {"size": int(one("size", 20) or 20)}))
            if p == "/api/shop/brands":
                r = SELECTOR.shop_brands(int(one("id", "0") or 0),
                                         int(one("page", 1) or 1),
                                         int(one("size", 20) or 20))
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/shop/categories":
                r = SELECTOR.shop_categories(int(one("id", "0") or 0),
                                             int(one("page", 1) or 1),
                                             int(one("size", 20) or 20))
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/content":
                return self.content(one("sku", ""), one("refresh") == "1",
                                  one("cached_only") == "1")
            if p == "/api/similar":
                r = SELECTOR.similar(one("sku", ""))
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/filters":
                return self.ok({"product_columns": PRODUCT_COLUMNS,
                                "keyword_columns": KEYWORD_COLUMNS,
                                "sort_fields": {k: sorted(v) for k, v in SORT_FIELDS.items()}})
            return self.fail("未知接口 " + p, 404, "NotFound")
        except (CreditExhausted, BudgetExceeded, AuthError, ConfirmRequired) as e:
            return self.fail(e, 429 if isinstance(e, CreditExhausted) else 403, type(e).__name__)
        except (ApiError, ValueError, TypeError) as e:
            return self.fail(e, 400, type(e).__name__)
        except Exception as e:
            traceback.print_exc()
            return self.fail(e, 500, type(e).__name__)

    def do_POST(self):
        p = urlparse(self.path).path
        b = self.body()
        try:
            if p == "/api/top":
                g = _multi_guard(b, "top")
                if g:
                    return self.ok(g)
                r = SELECTOR.top(b.get("filters") or {}, force=_force(b))
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/category":
                g = _multi_guard(b, "category")
                if g:
                    return self.ok(g)
                cid = CATALOG.resolve(b.get("category_id")) or b.get("category_id") or ""
                r = SELECTOR.category(cid, b.get("filters") or {}, force=_force(b))
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/hotwords":
                g = _multi_guard(b, "market")
                if g:
                    return self.ok(g)
                r = SELECTOR.hot_words(b.get("filters") or {}, force=_force(b))
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/mining":
                g = _multi_guard(b, "mining")
                if g:
                    return self.ok(g)
                r = SELECTOR.mining(b.get("keyword") or "", b.get("filters") or {},
                                    force=_force(b))
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/backsearch":
                g = _multi_guard(b, "backsearch")
                if g:
                    return self.ok(g)
                r = SELECTOR.backsearch(b.get("skus") or [], b.get("filters") or {},
                                        force=_force(b))
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/shop":
                g = _multi_guard(b, "shop")
                if g:
                    return self.ok(g)
                r = SELECTOR.shop(int(b.get("id") or 0), b.get("filters") or {})
                return self.ok(r, cached=r.get("cached"), cost=r.get("cost"))
            if p == "/api/categories/enrich":
                if not b.get("confirm"):
                    n = len(STORE.q("SELECT id FROM category WHERE level=? AND (cn IS NULL OR cn='')",
                                    (int(b.get("level") or 1),)))
                    limit = int(b.get("limit") or n)
                    n = min(n, limit)
                    return self.ok({"need_confirm": True, "count": n,
                                    "estimated_credit": n * CLIENT.cost_of("category"),
                                    "tip": "补全中文名会按调用次数扣积分，名称永久存本地库"})
                res = CATALOG.enrich_level(int(b.get("level") or 1),
                                           int(b.get("limit") or 0) or None)
                return self.ok({"done": len(res),
                                "ok": sum(1 for x in res if x.get("ok")),
                                "stats": CATALOG.stats(), "rows": res})
            if p == "/api/reviews/task":
                if not b.get("confirm"):
                    skus = b.get("skus") or []
                    return self.ok({"need_confirm": True, "count": len(skus),
                                    "estimated_credit": len(skus) * 200})
                return self.ok(SELECTOR.review_task(b.get("skus") or [], confirm=True))
            if p == "/api/estimate":
                calls = [(x.get("name"), x.get("body")) for x in (b.get("calls") or [])]
                return self.ok(CLIENT.estimate(calls))
            if p == "/api/favorites/toggle":
                return self.ok(SELECTOR.favorite_toggle(b.get("sku") or "",
                                                        b.get("tags") or "",
                                                        b.get("note") or ""))
            if p == "/api/profit":
                rows = b.get("rows") or []
                if not rows:
                    return self.fail("没有可计算的行", 400)
                r = SELECTOR.profit(rows, b.get("params") or {},
                                    persist=bool(b.get("persist", True)))
                return self.ok(r)
            if p == "/api/cache/clear":
                if not b.get("confirm"):
                    return self.ok({"need_confirm": True, "stats": STORE.cache_stats()})
                return self.ok({"deleted": STORE.cache_clear(b.get("path") or None)})
            if p == "/api/export":
                return self.do_export(b)
            return self.fail("未知接口 " + p, 404, "NotFound")
        except (CreditExhausted, BudgetExceeded, AuthError, ConfirmRequired) as e:
            return self.fail(e, 429 if isinstance(e, CreditExhausted) else 403, type(e).__name__)
        except (ApiError, ValueError, TypeError) as e:
            return self.fail(e, 400, type(e).__name__)
        except Exception as e:
            traceback.print_exc()
            return self.fail(e, 500, type(e).__name__)

    # ---------- 具体处理 ----------
    def content(self, sku, refresh=False, cached_only=False):
        """Ozon 前台商品内容（属性/描述/变体维度/图片/标签）。0 积分，走本机浏览器。"""
        sku = str(sku or "").strip()
        if not sku.isdigit():
            raise ValueError("SKU 必须是纯数字")
        cfg = (CLIENT.cfg or {}).get("content") or {}
        ttl = float(cfg.get("ttl_hours") or 72)
        if not refresh:
            cached = STORE.content_get(sku, ttl)
            if cached:
                return self.ok(cached, cached=True)
        if cached_only:
            # 抽屉首次打开只读缓存：没有就让前端显示「一键抓取」，不要偷偷起浏览器
            return self.ok({"sku": sku, "cached": False, "need_fetch": True})
        if not cfg.get("enabled", True):
            return self.fail("内容抓取已在 config.json 的 content.enabled 关闭", 400, "ContentDisabled")
        data = CONTENT.fetch(sku, cfg)
        STORE.content_put(data)
        return self.ok(dict(data, cached=False), cached=False)

    def reviews(self, sku, kind, language):
        if not sku:
            raise ValueError("缺少 sku")
        if kind == "stat":
            return self.ok(SELECTOR.review_stat(sku))
        if kind == "original":
            return self.ok(SELECTOR.review_original(sku))
        if kind == "words":
            return self.ok(SELECTOR.review_words(sku, language))
        if kind == "report":
            return self.ok(SELECTOR.review_report(sku, language))
        raise ValueError("未知评论类型 " + kind)

    def do_export(self, b):
        rows = b.get("rows") or []
        kind = b.get("kind") or "products"
        if not rows:
            return self.fail("没有可导出的数据", 400)
        # 前端可能带 raw 大对象，导出前剔除（columns 里本来也不包含 raw）
        clean = [{k: v for k, v in r.items() if k not in ("raw", "opportunity_parts")}
                 for r in rows]
        if kind == "keywords":
            path = export_keywords(clean, b.get("filename"))
        elif kind == "report":
            path = export_report(clean,
                                 b.get("keywords") or None,
                                 b.get("favorites") or None,
                                 b.get("meta") or None,
                                 b.get("overview") or None,
                                 b.get("filename"))
        elif kind == "full":
            path = export_full(clean, b.get("keywords"), b.get("overview"),
                               b.get("filename"))
        else:
            path = export_products(clean, b.get("filename"))
        return self.ok({"file": path.name, "url": "/api/download?file=" + quote(path.name),
                        "rows": len(clean), "path": str(path)})

    def download(self, name):
        # 只接受纯文件名，防目录穿越
        name = Path(unquote(name)).name
        f = EXPORT_DIR / name
        if not name or not f.exists() or not f.is_file():
            return self.fail("文件不存在", 404)
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def static(self, rel):
        rel = Path(unquote(rel)).name if "/" not in unquote(rel) else unquote(rel)
        f = (STATIC / rel).resolve()
        if not str(f).startswith(str(STATIC.resolve())) or not f.is_file():
            return self.fail("静态文件不存在: " + str(rel), 404)
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)


def _lan_ips():
    """列出本机所有可用 IPv4 地址，真实局域网段优先。

    注意：开了代理/TUN 的机器会多出 198.18.x.x 这类虚拟网卡地址，
    那个地址同事往往连不上，所以按网段排序，把典型私网段排前面。
    """
    ips = []
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            default = s.getsockname()[0]
        finally:
            s.close()
        if default and not default.startswith("127.") and default not in ips:
            ips.append(default)
    except OSError:
        pass

    def rank(ip):
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31:
            return 2
        return 3

    return sorted(set(ips), key=rank)


def main():
    ap = argparse.ArgumentParser(description="Seerfar Ozon 选品台")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default=None)
    a = ap.parse_args()
    cfg = CLIENT.cfg.get("server", {})
    # 默认监听 0.0.0.0，局域网内其它设备也能访问；只给本机用就把 config 的 server.host 改回 127.0.0.1
    host = a.host or cfg.get("host", "0.0.0.0")
    port = a.port or int(cfg.get("port", 8900))
    srv = ThreadingHTTPServer((host, port), Handler)
    print("Seerfar Ozon 选品台已启动")
    print(f"  本机访问    http://127.0.0.1:{port}/")
    if host in ("0.0.0.0", "::"):
        lans = _lan_ips()
        if lans:
            print(f"  局域网访问  http://{lans[0]}:{port}/")
            if len(lans) > 1:
                print("              其它网卡地址：" + "、".join(f"http://{i}:{port}/" for i in lans[1:]))
        print(f"  防火墙提示  局域网打不开时，请放行 TCP {port} 端口")
    else:
        print(f"  监听地址    {host}（仅本机）")
    print(f"  数据源 {CLIENT.base} | 类目 {CATALOG.stats().get('total', 0)} 个 | "
          f"本地商品 {STORE.product_count()} 条")
    print("  Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
