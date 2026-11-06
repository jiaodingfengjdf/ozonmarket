"""每日快照 + 黑马识别。

每次运行把指定类目 × 榜单的当前状态存成 JSONL；再与上一次快照对比，
算出：新上榜 SKU、价格变动、评论增量（评论增速是最接近"真实销量"的可抓指标）。

用法:
    python tools/snapshot.py                      # 默认 5 个类目 × 4 榜 × 3 页
    python tools/snapshot.py --cats all --pages 5 # 全 35 类目
    python tools/snapshot.py --report             # 只出报告，不抓
输出:
    data/snapshots/YYYY-MM-DD.jsonl
    data/snapshots/_darkhorses_YYYY-MM-DD.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "data", "snapshots")
API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="

DEFAULT_CATS = [
    "elektronika-15500", "krasota-i-zdorove-6500", "dom-i-sad-14500",
    "detskie-tovary-7000", "odezhda-obuv-i-aksessuary-7500",
]
SORTS = ["new", "score", "rating", "discount"]

sys.path.insert(0, os.path.join(ROOT, "web"))
try:
    from server import CATEGORIES, extract_products, build_path, load_model, sku_listed_date  # noqa
except Exception:
    CATEGORIES, extract_products, build_path, load_model, sku_listed_date = [], None, None, None, None


def fetch_batch(urls, batch=10):
    js = os.path.join(ROOT, "tools", "cdp_fetch.mjs")
    for i in range(0, len(urls), batch):
        subprocess.run(["node", js] + urls[i:i + batch], capture_output=True, text=True, cwd=ROOT)


def sha(url):
    import hashlib
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def run(cats, pages):
    from datetime import datetime as dt
    os.makedirs(SNAP, exist_ok=True)
    urls, meta = [], {}
    for cat in cats:
        for s in SORTS:
            for p in range(1, pages + 1):
                path = build_path(cat, s, p, None)
                u = API + urllib.parse.quote(path, safe="")
                meta[u] = (cat, s, p)
                urls.append(u)
    print(f"计划请求 {len(urls)} 个（{len(cats)} 类目 × {len(SORTS)} 榜 × {pages} 页）")
    started = time.time()
    fetch_batch(urls)
    print(f"取数完成 {time.time() - started:.0f}s")

    rows, seen = [], set()
    for u, (cat, s, p) in meta.items():
        f = os.path.join(ROOT, "out", sha(u) + ".json")
        if not os.path.exists(f):
            continue
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for it in extract_products(data):
            key = (s, it["sku"])
            if key in seen:
                continue
            seen.add(key)
            d, _ = sku_listed_date(it["sku"])
            it["listed_date"] = d
            it["category"] = cat
            it["sort"] = s
            it["page"] = p
            it["captured_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rows.append(it)

    today = date.today().isoformat()
    path = os.path.join(SNAP, f"{today}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"快照 {len(rows)} 条 -> {path}")
    return path


def load_all():
    out = {}
    for f in sorted(glob.glob(os.path.join(SNAP, "*.jsonl"))):
        day = os.path.basename(f)[:10]
        for line in open(f, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            out.setdefault((r.get("sort"), r.get("sku")), []).append((day, r))
    return out


def report():
    hist = load_all()
    if not hist:
        print("没有快照")
        return
    days = sorted({d for v in hist.values() for d, _ in v})
    latest = days[-1]
    prev = days[-2] if len(days) > 1 else None
    print(f"快照天数: {len(days)}  最新 {latest}  上一份 {prev or '—'}")

    rows = []
    for (sort, sku), seq in hist.items():
        seq.sort(key=lambda x: x[0])
        if seq[-1][0] != latest:
            continue
        cur = seq[-1][1]
        first_day = seq[0][0]
        prev_rec = seq[-2][1] if len(seq) > 1 else None
        rev_now = cur.get("reviews") or 0
        rev_prev = (prev_rec or {}).get("reviews") or 0
        growth = rev_now - rev_prev if prev_rec else None
        rows.append({
            "sku": sku, "sort": sort, "category": cur.get("category"),
            "name": cur.get("name"), "price": cur.get("price"),
            "rating": cur.get("rating"), "reviews": rev_now,
            "review_growth": growth,
            "listed_date": cur.get("listed_date"),
            "first_seen": first_day,
            "is_new_entry": prev_rec is None and len(days) > 1,
            "url": cur.get("url"),
        })

    # 黑马：上架 60 天内 + 有评论增量，按增量排
    def age_days(d):
        try:
            return (date.today() - date.fromisoformat(d)).days
        except Exception:
            return 9999

    dark = [r for r in rows if age_days(r["listed_date"]) <= 60 and r["review_growth"]]
    dark.sort(key=lambda r: -r["review_growth"])

    out = os.path.join(SNAP, f"_darkhorses_{latest}.csv")
    cols = list(rows[0].keys())
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(dark or rows[:200])
    print(f"黑马候选 {len(dark)} 条 -> {out}")
    for r in (dark or rows)[:10]:
        print(f"  +{r['review_growth'] if r['review_growth'] is not None else '-'} 条评论 | "
              f"{r['listed_date']} | {r['price']}₽ | {str(r['name'])[:48]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cats", default="default", help="default | all | slug,slug")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    if a.report:
        report()
        return

    if a.cats == "all":
        cats = [c[0] for c in CATEGORIES]
    elif a.cats == "default":
        cats = DEFAULT_CATS
    else:
        cats = [c.strip() for c in a.cats.split(",") if c.strip()]

    run(cats, a.pages)
    report()


if __name__ == "__main__":
    main()
