"""对抓取到的榜单 CSV 做大盘汇总。
用法: python tools/report.py data/2026-11-06
输出: <dir>/_stats.csv, <dir>/_report.md
"""
import csv
import glob
import json
import os
import statistics as st
import sys

BANDS = [(0, 500), (500, 1000), (1000, 2000), (2000, 5000), (5000, 10000), (10000, 10 ** 9)]
BAND_LABEL = ["0-500₽", "500-1000₽", "1000-2000₽", "2000-5000₽", "5000-10000₽", "10000₽+"]


def num(v):
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except Exception:
        return None


def load(d):
    rows = []
    for f in glob.glob(os.path.join(d, "*.csv")):
        if os.path.basename(f).startswith("_"):
            continue
        with open(f, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                r["_file"] = os.path.basename(f)
                rows.append(r)
    return rows


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "data"
    rows = load(d)
    if not rows:
        print("no csv in", d)
        return

    groups = {}
    for r in rows:
        groups.setdefault((r["category"], r["sort"]), []).append(r)

    stats = []
    for (cat, sort), g in sorted(groups.items()):
        prices = [p for p in (num(r["price"]) for r in g) if p]
        orig = [p for p in (num(r["price_original"]) for r in g) if p]
        disc = [abs(p) for p in (num(str(r["discount"]).replace("%", "").replace("−", "-")) for r in g) if p is not None]
        rate = [p for p in (num(r["rating"]) for r in g) if p]
        rev = []
        for r in g:
            t = str(r.get("reviews", "")).replace("\u2009", " ").replace(" ", "")
            digits = "".join(ch for ch in t if ch.isdigit())
            if digits:
                rev.append(int(digits))
        bands = [0] * len(BANDS)
        for p in prices:
            for i, (lo, hi) in enumerate(BANDS):
                if lo <= p < hi:
                    bands[i] += 1
                    break
        stats.append({
            "category": cat, "sort": sort, "products": len(g),
            "price_avg": round(st.mean(prices), 1) if prices else "",
            "price_median": round(st.median(prices), 1) if prices else "",
            "price_min": min(prices) if prices else "",
            "price_max": max(prices) if prices else "",
            "orig_avg": round(st.mean(orig), 1) if orig else "",
            "discount_avg": round(st.mean(disc), 1) if disc else "",
            "rating_avg": round(st.mean(rate), 2) if rate else "",
            "rating4_8_plus_pct": round(100 * sum(1 for x in rate if x >= 4.8) / len(rate), 1) if rate else "",
            "reviews_median": int(st.median(rev)) if rev else "",
            "band_json": json.dumps(dict(zip(BAND_LABEL, bands)), ensure_ascii=False),
        })

    cols = list(stats[0].keys())
    with open(os.path.join(d, "_stats.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(stats)

    lines = ["# Ozon 榜单大盘汇总", "", f"- 明细行数: {len(rows)}", f"- 组合数: {len(stats)}", ""]
    lines.append("| 类目 | 排序 | 商品数 | 均价 | 中位价 | 最低 | 最高 | 平均折扣 | 均分 | 4.8+占比 | 评论中位 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in stats:
        lines.append("| {category} | {sort} | {products} | {price_avg} | {price_median} | {price_min} | {price_max} | {discount_avg}% | {rating_avg} | {rating4_8_plus_pct}% | {reviews_median} |".format(**s))
    lines.append("")
    lines.append("## 价格带分布")
    lines.append("")
    lines.append("| 类目 | 排序 | " + " | ".join(BAND_LABEL) + " |")
    lines.append("|---" * (len(BAND_LABEL) + 2) + "|")
    for s in stats:
        b = json.loads(s["band_json"])
        lines.append(f"| {s['category']} | {s['sort']} | " + " | ".join(str(b[k]) for k in BAND_LABEL) + " |")
    with open(os.path.join(d, "_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines[:12]))
    print("\n-> ", os.path.join(d, "_stats.csv"), os.path.join(d, "_report.md"))


if __name__ == "__main__":
    main()
