"""解析 Ozon composer-api 返回的 tileGrid / searchResults 商品数据。
用法: python tools/parse_tiles.py out/xxx.json [out/yyy.json ...]
输出: out/_parsed/<hash>.csv 与终端摘要
"""
import csv
import json
import os
import re
import sys

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "_parsed")


def text_of(node):
    """从 textDS / label 结构里抽纯文本"""
    if not isinstance(node, dict):
        return ""
    if "textDS" in node:
        return node["textDS"].get("text", "")
    if "text" in node and isinstance(node["text"], dict):
        return node["text"].get("text", "")
    return ""


def parse_item(it):
    row = {
        "sku": it.get("sku") or it.get("id"),
        "name": "",
        "price": "",
        "price_original": "",
        "discount": "",
        "stock": "",
        "rating": "",
        "reviews": "",
        "url": "",
    }
    link = (it.get("action") or {}).get("link", "")
    row["url"] = "https://www.ozon.ru" + link if link.startswith("/") else link

    for st in it.get("mainState", []):
        t = st.get("type")
        if t == "priceV2":
            p = st["priceV2"]
            prices = p.get("price", [])
            for pr in prices:
                if pr.get("textStyle") == "PRICE":
                    row["price"] = pr.get("text", "").replace("\u2009", "").replace("₽", "").strip()
                elif pr.get("textStyle") == "ORIGINAL_PRICE":
                    row["price_original"] = pr.get("text", "").replace("\u2009", "").replace("₽", "").strip()
            row["discount"] = p.get("discount", "")
        elif t == "textDS":
            txt = text_of(st)
            if re.search(r"осталось|ед\b", txt):
                row["stock"] = txt.replace("\u2009", "")
            elif st.get("id") == "name" or (not row["name"] and len(txt) > 15):
                row["name"] = txt
        elif t == "labelListV2":
            flat = json.dumps(st, ensure_ascii=False)
            if "ic_s_star_filled" in flat or "graphicRating" in flat:
                texts = [x.get("text", {}).get("text", "") for x in st["labelListV2"].get("items", []) if x.get("type") == "text"]
                # 第一个是评分，第二个通常是评论数
                nums = [x for x in texts if x]
                if nums:
                    row["rating"] = nums[0]
                if len(nums) > 1:
                    row["reviews"] = nums[1]
    return row


def extract(path):
    d = json.load(open(path, encoding="utf-8"))
    if "widgetStates" not in d:
        return None, []
    ws = d["widgetStates"]
    rows = []
    for k, v in ws.items():
        if "tileGrid" not in k and "searchResults" not in k:
            continue
        try:
            obj = json.loads(v) if isinstance(v, str) else v
        except Exception:
            continue
        for it in obj.get("items", []) or []:
            if isinstance(it, dict) and ("sku" in it or "mainState" in it):
                rows.append(parse_item(it))
    return d, rows


def main():
    files = sys.argv[1:]
    os.makedirs(OUT_DIR, exist_ok=True)
    summary = []
    for f in files:
        d, rows = extract(f)
        if d is None:
            print(f"{f}: no widgetStates")
            continue
        name = os.path.splitext(os.path.basename(f))[0]
        csv_path = os.path.join(OUT_DIR, name + ".csv")
        if rows:
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        page_info = d.get("pageInfo", {})
        summary.append({
            "file": name,
            "products": len(rows),
            "pageInfo": page_info,
            "csv": csv_path if rows else "",
            "skus": [r["sku"] for r in rows],
        })
    for s in summary:
        print(json.dumps(s, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
