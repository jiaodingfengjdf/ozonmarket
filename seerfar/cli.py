# -*- coding: utf-8 -*-
"""Seerfar 选品台 · 命令行入口。

常用：
  python cli.py init                      导入 10021 个 Seerfar 类目 ID（本地，不扣积分）
  python cli.py stats                     配额 / 今日消耗 / 缓存 / 本地数据量
  python cli.py selftest                  只读接口连通性自检
  python cli.py categories --enrich --yes 批量补全一级类目中文名（约 290 积分）
  python cli.py top --size 50 --export    热销榜单并导出 XLSX
  python cli.py category 15621031 --size 20 --export
  python cli.py hotwords --size 50 --export
  python cli.py mining "наушники" --size 30
  python cli.py product 175924376
  python cli.py backsearch 175924376
  python cli.py shop 7

所有批量/删除类动作默认 dry-run，加 --yes 才真正执行（积分不可退回）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sf_catalog import get_catalog
from sf_client import ENDPOINTS, ApiError, BudgetExceeded, CreditExhausted, get_client
from sf_db import STORE
from sf_export import export_full, export_keywords, export_products
from sf_select import KEYWORD_COLUMNS, PRODUCT_COLUMNS, Selector, get_selector

ROOT = Path(__file__).resolve().parent


def out(obj, as_json=False):
    """格式化为 JSON 字符串（由调用方决定打印或拼接）。"""
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def table(rows, columns, limit=20):
    """控制台简表，只显示前 limit 行。"""
    if not rows:
        print("(无数据)")
        return
    heads = [h for h, _ in columns]
    keys = [k for _, k in columns]
    widths = [max(8, min(30, len(h) * 2 + 2)) for h in heads]
    print(" | ".join(h.ljust(w) for h, w in zip(heads, widths)))
    print("-" * (sum(widths) + 3 * len(widths)))
    for r in rows[:limit]:
        cells = []
        for k, w in zip(keys, widths):
            v = r.get(k)
            s = "" if v is None else (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v))
            cells.append(s[:w].ljust(w))
        print(" | ".join(cells))


def confirm_cost(label, n, unit_cost, yes):
    est = round(n * unit_cost, 1)
    print(f"[预算] {label}：预计 {n} 次真实调用 ≈ {est} 积分（命中缓存则更少）")
    if not yes:
        print("[DRY-RUN] 未加 --yes，本次不执行。确认后请追加 --yes。")
        return False
    return True


def build_filters(a):
    """把 CLI 参数翻译成 Selector 认识的筛选字典。"""
    f = {
        "page": a.page, "size": a.size, "sort": a.sort, "direction": a.direction,
        "keyword": getattr(a, "keyword", None),
        "category_id": getattr(a, "category_id", None),
        "search_date": getattr(a, "search_date", None),
        "creation_date": getattr(a, "creation_date", None),
        "match_type": getattr(a, "match_type", 0),
        "variations_merge": getattr(a, "variations_merge", 0),
    }
    for key in ("price", "monthly_sales", "monthly_revenue", "review_count",
                "review_rating", "search_volume", "sellers", "competing_products",
                "market_space", "growth"):
        src = {"monthly_sales": "monthlySales", "monthly_revenue": "monthlyRevenue",
               "review_count": "reviewCount", "review_rating": "reviewRating",
               "search_volume": "searchVolume", "competing_products": "products",
               "market_space": "marketSpace", "growth": "searchChange30",
               "sellers": "sellers", "price": "price"}.get(key, key)
        lo = getattr(a, key + "_min", None)
        hi = getattr(a, key + "_max", None)
        if lo is not None:
            f[src + "_min"] = lo
        if hi is not None:
            f[src + "_max"] = hi
    if getattr(a, "category_ids", None):
        f["category_ids"] = [x.strip() for x in a.category_ids.split(",") if x.strip()]
    if getattr(a, "keywords", None):
        f["keywords"] = [x.strip() for x in a.keywords.split(",") if x.strip()]
    return f


def add_common(p):
    p.add_argument("--page", type=int, default=1, help="页码")
    p.add_argument("--size", type=int, default=20, help="每页条数（最大 100）")
    p.add_argument("--sort", default=None, help="排序字段，见 README 白名单")
    p.add_argument("--direction", default="DESC", choices=["DESC", "ASC"])
    p.add_argument("--keyword", default=None, help="关键词包含")
    p.add_argument("--keywords", default=None, help="多个关键词，逗号分隔")
    p.add_argument("--category-id", default=None, help="Seerfar 类目 ID")
    p.add_argument("--category-ids", default=None, help="多个类目 ID，逗号分隔")
    p.add_argument("--search-date", default=None,
                   help="榜单/挖词的 searchDate：yyyy-MM 自动补 01 号查上月；查类目请用 --date")
    p.add_argument("--creation-date", type=int, default=None,
                   help="上架时间：1近30天/3近90天/6近180天/12近一年/24近2年")
    p.add_argument("--match-type", type=int, default=0, choices=[0, 1], help="0精准 1模糊")
    p.add_argument("--variations-merge", type=int, default=0, choices=[0, 1])
    p.add_argument("--price-min", type=float, default=None)
    p.add_argument("--price-max", type=float, default=None)
    p.add_argument("--monthly-sales-min", type=float, default=None)
    p.add_argument("--monthly-sales-max", type=float, default=None)
    p.add_argument("--monthly-revenue-min", type=float, default=None)
    p.add_argument("--monthly-revenue-max", type=float, default=None)
    p.add_argument("--review-count-min", type=float, default=None)
    p.add_argument("--review-count-max", type=float, default=None)
    p.add_argument("--review-rating-min", type=float, default=None)
    p.add_argument("--review-rating-max", type=float, default=None)
    p.add_argument("--search-volume-min", type=float, default=None)
    p.add_argument("--search-volume-max", type=float, default=None)
    p.add_argument("--sellers-min", type=float, default=None)
    p.add_argument("--sellers-max", type=float, default=None)
    p.add_argument("--competing-products-min", type=float, default=None)
    p.add_argument("--competing-products-max", type=float, default=None)
    p.add_argument("--market-space-min", type=float, default=None)
    p.add_argument("--market-space-max", type=float, default=None)
    p.add_argument("--export", action="store_true", help="导出 XLSX")
    p.add_argument("--pages", type=int, default=1, help="连续抓取页数（>1 需 --yes）")
    p.add_argument("--yes", action="store_true", help="确认执行会产生积分的操作")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")


def main():
    ap = argparse.ArgumentParser(description="Seerfar Ozon 选品台 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="导入类目 ID 表（本地，不扣积分）")
    sub.add_parser("quota", help="查询 API Key 积分")
    sub.add_parser("stats", help="本地运行状态")
    sub.add_parser("selftest", help="只读接口连通性自检（约 60 积分）")

    p = sub.add_parser("categories", help="类目树查询 / 批量补名称")
    p.add_argument("--level", type=int, default=1, choices=[1, 2, 3])
    p.add_argument("--parent", default=None, help="父类目 ID")
    p.add_argument("--search", default=None, help="按中文/俄文/ID 搜索")
    p.add_argument("--enrich", action="store_true", help="批量补全该层中文名（花积分）")
    p.add_argument("--limit", type=int, default=None, help="最多补几个")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("category", help="查类目：大盘 + 商品清单 + 排名（需三级类目 ID）")
    p.add_argument("category_id", help="Seerfar 类目 ID；一级/二级只出大盘，三级才出商品")
    add_common(p)
    p.add_argument("--date", default=None,
                   help="查类目专用：留空=显式传当前月 yyyy-MM；填 yyyy-MM 查历史月（近 1 年内）")
    p.add_argument("--last30", action="store_true",
                   help="不传 date（官方称查近 30 天），覆盖默认的当前月")
    p.add_argument("--date-null", action="store_true",
                   help="A/B 用：显式传 date:null（官方示例写法）而非省略字段，对比 startDate")
    p.add_argument("--fulfillment", default=None,
                   choices=["OZON", "FBO", "FBS", "RFBS", "FBP"])
    p.add_argument("--labels", default=None, help="标签 0新品,1正品,2畅销，逗号分隔")
    p.add_argument("--brands", default=None, help="品牌名，逗号分隔")
    p.add_argument("--brand-type", type=int, default=0, choices=[0, 1, 2],
                   help="0包含 1排除 2无品牌")
    p.add_argument("--seller-names", default=None, help="卖家名，逗号分隔")
    p.add_argument("--skus", default=None, help="指定 SKU，最多 10 个，逗号分隔")
    p.add_argument("--tag", default=None, help="标签词")
    p.add_argument("--leaves", action="store_true",
                   help="只列出该类目下三级子类目（本地查询，不扣积分）")

    p = sub.add_parser("top", help="热销榜单")
    add_common(p)

    p = sub.add_parser("hotwords", help="市场热词")
    add_common(p)

    p = sub.add_parser("mining", help="关键词挖掘")
    p.add_argument("keyword", help="种子词（俄文或中文）")
    add_common(p)

    p = sub.add_parser("backsearch", help="关键词反查（按竞品 SKU）")
    p.add_argument("skus", nargs="+")
    add_common(p)
    p.add_argument("--has-variant", type=int, default=0, choices=[0, 1])

    p = sub.add_parser("product", help="竞品详情 + 趋势")
    p.add_argument("sku")
    p.add_argument("--date-range", default="past_30_days")
    p.add_argument("--similar", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("shop", help="店铺商品")
    p.add_argument("shop_id", type=int)
    add_common(p)

    p = sub.add_parser("export", help="从本地库导出（不扣积分）")
    p.add_argument("--type", default="products", choices=["products", "keywords"])
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--file", default=None)

    p = sub.add_parser("content", help="抓取 Ozon 前台商品内容（属性/描述/图片，0 积分）")
    p.add_argument("--sku", required=True)
    p.add_argument("--refresh", action="store_true")

    p = sub.add_parser("rescore", help="重算本地库机会分（从 raw 还原，0 积分）")
    p.add_argument("--limit", type=int, default=100000)

    p = sub.add_parser("cache-clear", help="清空 API 缓存（需 --yes）")
    p.add_argument("--path", default=None, help="按路径模糊匹配")
    p.add_argument("--yes", action="store_true")

    a = ap.parse_args()
    client = get_client()
    cat = get_catalog(client)
    sel = Selector(client, catalog=cat)

    try:
        # ---------- 本地操作 ----------
        if a.cmd == "init":
            print(out(cat.import_xlsx()))
            return 0
        if a.cmd == "quota":
            print(out(client.quota().data))
            return 0
        if a.cmd == "stats":
            print(out(client.stats()))
            return 0
        if a.cmd == "export":
            if a.type == "products":
                rows = STORE.products(limit=a.limit)
                p = export_products(rows, a.file)
            else:
                rows = STORE.keywords(limit=a.limit)
                p = export_keywords(rows, a.file)
            print("已导出:", p, "行数:", len(rows))
            return 0
        if a.cmd == "rescore":
            import json
            from sf_select import norm_product, opportunity
            rows = STORE.q("SELECT sku, raw FROM product LIMIT ?", (a.limit,))
            done, from_raw = 0, 0
            batch = []
            for r in rows:
                try:
                    raw = json.loads(r["raw"]) if r.get("raw") else {}
                except (ValueError, TypeError):
                    raw = {}
                if raw:
                    p = norm_product(raw)
                    p["sku"] = r["sku"]
                    from_raw += 1
                else:
                    p = {k: r.get(k) for k in ("sku", "sales", "revenue", "sales_rate",
                                               "review_count", "variants", "gross_margin",
                                               "conv_to_cart_pdp")}
                p["opportunity"] = opportunity(p, "product")["score"]
                batch.append(p)
                done += 1
            STORE.upsert_products(batch)
            print("已重算机会分:", done, "（其中从 raw 还原:", from_raw, "）")
            return 0
        if a.cmd == "content":
            import sf_content as C
            cfg = (client.cfg or {}).get("content") or {}
            ttl = float(cfg.get("ttl_hours") or 72)
            cached = None if a.refresh else STORE.content_get(str(a.sku), ttl)
            if cached:
                d = cached
            else:
                d = C.fetch(str(a.sku), cfg)
                STORE.content_put(d)
            print("标题:", d.get("title"))
            print("品牌:", d.get("brand"), "| 评分:", d.get("rating"), "| 评论:", d.get("review_count"))
            print("价格:", d.get("price"), "| 原价:", d.get("original_price"))
            print("属性:", len(d.get("attributes") or []),
                  "| 变体维度:", len(d.get("aspects") or []),
                  "| 图片:", len(d.get("images") or []),
                  "| 描述字数:", len(d.get("description") or ""),
                  "| 标签:", len(d.get("tags") or []))
            print("来源:", d.get("source"), "| 缓存命中:", bool(cached))
            if d.get("attributes"):
                print("属性预览:", "; ".join(f"{a['name']}={('/'.join(a['values'][:2]))}"
                                          for a in d["attributes"][:6]))
            return 0
        if a.cmd == "cache-clear":
            if not a.yes:
                print("[DRY-RUN] 清空缓存请追加 --yes")
                return 0
            n = STORE.cache_clear(a.path)
            print("已删除缓存条数:", n)
            return 0

        # ---------- 类目 ----------
        if a.cmd == "categories":
            if a.search:
                rows = cat.search(a.search)
                print(out([{k: r[k] for k in ("id", "level", "cn", "ru", "cn_path")}
                           for r in rows], a.json))
                return 0
            if a.enrich:
                sql = "SELECT id FROM category WHERE level=? AND (cn IS NULL OR cn='')"
                n = len(STORE.q(sql, (a.level,)))
                if a.limit:
                    n = min(n, a.limit)
                if not confirm_cost(f"补全 level={a.level} 的 {n} 个类目中文名",
                                    n, client.cost_of("category"), a.yes):
                    return 0
                def prog(i, total, r):
                    print(f"  [{i}/{total}] {r.get('id')} -> {r.get('cn') or r.get('error')}")
                res = cat.enrich_level(a.level, a.limit, progress=prog)
                print(out({"done": len(res), "ok": sum(1 for x in res if x.get("ok")),
                           "stats": cat.stats()}, a.json))
                return 0
            rows = cat.tree(a.parent, a.level)
            print(out(rows, a.json))
            return 0

        # ---------- 自检 ----------
        if a.cmd == "selftest":
            print("[自检] 只读接口，预计约 60 积分；已缓存的请求不重复扣费\n")
            page = {"pageNumber": 1, "pageSize": 1,
                    "orders": [{"field": "revenue", "direction": "DESC"}]}
            checks = [
                ("quota", "quota", None),
                ("top", "top", {"page": page}),
                ("category", "category", {"categoryId": "15621031", "page": page}),
                ("market", "market", {"page": {"pageNumber": 1, "pageSize": 1,
                                               "orders": [{"field": "searchVolume", "direction": "DESC"}]}}),
                ("product", "product", {"sku": "175924376", "dateRange": "past_30_days"}),
                ("monthly_trend", "monthly_trend", {"sku": 175924376}),
            ]
            report = []
            for label, name, body in checks:
                try:
                    r = client.call(name, body)
                    d = r.data
                    size = len(d) if isinstance(d, list) else (
                        len((d or {}).get("records") or (d or {}).get("productList") or [])
                        if isinstance(d, dict) else 0)
                    report.append({"api": label, "ok": True, "cached": r.cached,
                                   "items": size, "ms": r.elapsed_ms, "cost": r.cost})
                except Exception as e:
                    report.append({"api": label, "ok": False, "error": str(e)})
                print(f"  {label:<16} {'OK' if report[-1]['ok'] else 'FAIL':<5} "
                      f"cached={report[-1].get('cached')} {report[-1].get('error','')}")
            print("\n" + out(report, True))
            print("\n本地统计:", out(STORE.category_stats(), True))
            return 0 if all(x["ok"] for x in report) else 1

        # ---------- 业务查询 ----------
        f = build_filters(a) if hasattr(a, "page") else {}
        pages = getattr(a, "pages", 1)
        if pages > 1 and not confirm_cost(f"{a.cmd} 连续 {pages} 页", pages,
                                          client.cost_of(a.cmd if a.cmd in ENDPOINTS else "top"), a.yes):
            return 0

        all_rows, meta = [], {}
        for pg in range(pages):
            f["page"] = (getattr(a, "page", 1) or 1) + pg
            if a.cmd == "top":
                res = sel.top(f)
            elif a.cmd == "category":
                cid = cat.resolve(a.category_id) or a.category_id
                if getattr(a, "leaves", False):
                    rows = cat.leaves(cid)
                    print(out({"parent": cid, "count": len(rows), "leaves": rows},
                              getattr(a, "json", False)))
                    return 0
                # 官方「查类目」的全部枚举/文本筛选参数
                for extra in ("date", "fulfillment", "labels", "brands",
                              "brand_type", "seller_names", "skus", "tag"):
                    v = getattr(a, extra, None)
                    if v not in (None, ""):
                        f[extra] = v
                if getattr(a, "last30", False):
                    f["last30"] = True
                if getattr(a, "date_null", False):
                    f["date_null"] = True
                res = sel.category(cid, f)
                meta["overview"] = res.get("overview")
                meta["hint"] = res.get("hint")
                meta["leaves_count"] = len(res.get("leaves") or [])
            elif a.cmd == "hotwords":
                res = sel.hot_words(f)
            elif a.cmd == "mining":
                res = sel.mining(a.keyword, f)
            elif a.cmd == "backsearch":
                f["has_variant"] = getattr(a, "has_variant", 0)
                res = sel.backsearch(a.skus, f)
            elif a.cmd == "shop":
                res = sel.shop(a.shop_id, f)
                meta["summary"] = res.get("summary")
            else:
                print("未知命令"); return 1
            all_rows.extend(res.get("rows") or [])
            meta.update({k: res.get(k) for k in ("total", "pages", "cached", "cost")})
            print(f"[第 {f['page']} 页] {len(res.get('rows') or [])} 行，"
                  f"cached={res.get('cached')}，本次 {res.get('cost', 0)} 积分")

        if a.cmd == "product":
            pass  # 单独分支在下方处理

        cols = KEYWORD_COLUMNS if a.cmd in ("hotwords", "mining", "backsearch") else PRODUCT_COLUMNS
        if getattr(a, "json", False):
            print(out({"meta": meta, "rows": all_rows}, True))
        else:
            table(all_rows, cols[:12], limit=20)
            print(f"\n共 {len(all_rows)} 行 | total={meta.get('total')} | cached={meta.get('cached')}")
            if meta.get("overview"):
                print("类目大盘:", out(meta["overview"], True))
            if meta.get("hint"):
                print("提示:", meta["hint"])
            if meta.get("leaves_count"):
                print(f"该类目下有 {meta['leaves_count']} 个三级子类目；"
                      f"用 `python cli.py category {a.category_id} --leaves` 列出，再选三级 ID 查商品")
            if meta.get("summary"):
                print("店铺汇总:", out(meta["summary"], True))

        if getattr(a, "export", False):
            path = (export_keywords(all_rows) if cols is KEYWORD_COLUMNS
                    else export_products(all_rows))
            print("已导出:", path)
        return 0

    except (CreditExhausted, BudgetExceeded, ApiError, ValueError) as e:
        print(f"[错误] {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130


def _product_cmd(a):
    """竞品详情单独实现（参数与其它命令不同）。"""
    cat = get_catalog(get_client())
    sel = Selector(get_client(), catalog=cat)
    res = sel.product(a.sku, a.date_range, with_similar=a.similar)
    if a.json:
        print(out(res, True))
    else:
        p = res["product"]
        print(f"SKU {p['sku']} | {p['title'][:70]}")
        print(f"价格 {p['price']} ₽ | 评分 {p['review_rating']} | 评论 {p['review_count']}")
        print("汇总:", out(res["summary"], True))
        print(f"类目: {p['category_cn']}")
        print(f"类目排名: {out(res['ranks'][:5], True)}")
        print(f"日趋势 {len(res['trend'])} 天 | 月度 {len(res.get('monthly') or [])} 月")
        if res.get("similar"):
            print(f"相似商品 {len(res['similar'])} 条:")
            table(res["similar"][:10], PRODUCT_COLUMNS[:8])
    return 0


if __name__ == "__main__":
    # product 命令走独立分支，避免 add_common 的参数污染
    if len(sys.argv) > 1 and sys.argv[1] == "product":
        p = argparse.ArgumentParser(description="竞品详情")
        p.add_argument("sku")
        p.add_argument("--date-range", default="past_30_days")
        p.add_argument("--similar", action="store_true")
        p.add_argument("--json", action="store_true")
        try:
            sys.exit(_product_cmd(p.parse_args(sys.argv[2:])))
        except Exception as e:
            print(f"[错误] {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(2)
    sys.exit(main())
