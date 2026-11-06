"""标定 Ozon SKU → 上架日期模型（可复现）。

思路
----
Ozon 不公开上架日期。但：
1. SKU 全局自增，与创建时间强单调 → 可以建 sku→日期 的单调映射；
2. 商品页评价列表**按时间倒序**，页数覆盖全部评价；评价总数 ≤ 30 的商品，
   第 1 页就是全部评价，其 min(publishedAt) ≈ 真实首评时间 ≈ 上架时间 + 少量滞后。

所以只取「评价数很少」的商品做锚点，噪音最小；再用保序回归（PAVA）
强制单调，得到全号段可用的曲线。

用法: python tools/calibrate_sku_date.py
输出: web/sku_date_model.json
"""
import csv
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="
SAMPLE = 70


def parse_review_count(s):
    d = re.sub(r"\D", "", str(s or ""))
    return int(d) if d else None


def collect_candidates():
    """挑评价数少的商品：评价列表一页即全量"""
    cand = {}
    for f in glob.glob(os.path.join(ROOT, "data", "*", "*.csv")):
        if os.path.basename(f).startswith("_"):
            continue
        try:
            with open(f, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    sku = (r.get("sku") or "").strip()
                    n = parse_review_count(r.get("reviews"))
                    if not sku.isdigit() or n is None:
                        continue
                    if 1 <= n <= 30:
                        cand[int(sku)] = n
        except Exception:
            pass
    return sorted(cand)


def pick_even(items, n):
    if not items:
        return []
    if len(items) <= n:
        return items
    step = (len(items) - 1) / (n - 1)
    return sorted({items[round(i * step)] for i in range(n)})


def fetch(urls):
    js = os.path.join(ROOT, "tools", "cdp_fetch.mjs")
    for i in range(0, len(urls), 10):
        subprocess.run(["node", js] + urls[i:i + 10], capture_output=True, text=True, cwd=ROOT)


def min_review_ts(path, review_count_hint=None):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None, None
    ws = d.get("widgetStates", {})
    for k, v in ws.items():
        if "webListReviews" not in k:
            continue
        try:
            o = json.loads(v) if isinstance(v, str) else v
        except Exception:
            continue
        rv = o.get("reviews") or []
        ts = [r.get("publishedAt") or r.get("createdAt") for r in rv if isinstance(r, dict)]
        ts = [t for t in ts if isinstance(t, (int, float)) and t > 0]
        if not ts:
            return None, 0
        return min(ts), len(ts)
    return None, None


def pava(points):
    """保序回归：让 date 随 sku 单调不下降"""
    blocks = [[p["sku"], p["ts"], 1] for p in points]
    i = 0
    out = []
    while i < len(blocks):
        cur = blocks[i][:]
        while out and out[-1][1] > cur[1]:
            prev = out.pop()
            n = prev[2] + cur[2]
            cur = [cur[0], (prev[1] * prev[2] + cur[1] * cur[2]) / n, n]
        out.append(cur)
        i += 1
    return [{"sku": b[0], "ts": int(b[1])} for b in out]


def main():
    web = os.path.join(ROOT, "web")
    os.makedirs(web, exist_ok=True)
    cands = collect_candidates()
    print(f"候选商品（评价数 1~30）: {len(cands)}")
    sample = pick_even(cands, SAMPLE)
    print(f"取样: {len(sample)}，范围 {min(sample)} ~ {max(sample)}")

    urls, umap = [], {}
    for sku in sample:
        u = API + urllib.parse.quote(f"/product/{sku}/reviews/", safe="")
        umap[u] = sku
        urls.append(u)
    fetch(urls)

    pts = []
    for u, sku in umap.items():
        h = hashlib.sha1(u.encode()).hexdigest()[:10]
        f = os.path.join(ROOT, "out", h + ".json")
        if not os.path.exists(f):
            continue
        ts, n = min_review_ts(f)
        if ts and n and n <= 30:
            pts.append({"sku": sku, "ts": int(ts),
                        "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")})
    pts.sort(key=lambda p: p["sku"])
    print(f"有效锚点: {len(pts)}")
    for p in pts[:10]:
        print(f"  {p['sku']} -> {p['date']}")

    if len(pts) < 6:
        print("锚点太少，保留旧模型")
        return

    curve = pava(pts)
    model = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "method": "首评时间锚点 + 保序回归；上架日期 ≈ 曲线值，误差约数天~数周",
        "points": curve,
    }
    json.dump(model, open(os.path.join(web, "sku_date_model.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n模型点: {len(curve)} -> web/sku_date_model.json")
    print("曲线首尾:", curve[0], curve[-1])


if __name__ == "__main__":
    main()
