"""拉取 Ozon Seller API 的**中俄双语**全类目树。

关键：`/v1/description-category/tree` 支持 `language` 参数，
官方就提供简中（ZH_HANS）。所以类目名不需要机器翻译——
俄文取 DEFAULT，中文取 ZH_HANS，按 id 对齐即可。

用法: python tools/build_tree.py
输出: web/categories_tree.json      {n: 俄文, zh: 中文, id, type, c: 子节点}
      out_seller_tree.json          俄文原始响应
      out_tree_zh.json              中文原始响应
"""
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "categories_tree.json")
RAW_RU = os.path.join(ROOT, "out_seller_tree.json")
RAW_ZH = os.path.join(ROOT, "out_tree_zh.json")


def creds():
    cid = os.environ.get("OZON_CLIENT_ID")
    key = os.environ.get("OZON_API_KEY")
    if cid and key:
        return cid, key
    try:
        cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        s = cfg["seller"]
        return str(s["client_id"]), s["api_key"]
    except Exception:
        raise SystemExit("缺少凭证：设置 OZON_CLIENT_ID / OZON_API_KEY 或填写 config.json")


def fetch(language, out_path):
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
        print("复用已有响应:", out_path)
        return out_path
    cid, key = creds()
    body = os.path.join(ROOT, "body_lang.json")
    with open(body, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"language": language}))
    subprocess.run([
        "curl", "-s", "-X", "POST", "https://api-seller.ozon.ru/v1/description-category/tree",
        "-H", f"Client-Id: {cid}", "-H", f"Api-Key: {key}",
        "-H", "Content-Type: application/json",
        "--data-binary", "@" + body, "-o", out_path, "--max-time", "180",
    ], cwd=ROOT, check=True)
    print(f"{language} 已拉取:", out_path, os.path.getsize(out_path), "bytes")
    return out_path


def index_zh(nodes, acc):
    for n in nodes:
        key = n.get("description_category_id") or n.get("type_id")
        if key is not None:
            acc[key] = n.get("category_name") or n.get("type_name") or ""
        index_zh(n.get("children") or [], acc)


def convert(nodes, zh_map, level=1):
    out = []
    for n in nodes:
        name_ru = n.get("category_name") or n.get("type_name") or ""
        key = n.get("description_category_id") or n.get("type_id")
        node = {"n": name_ru}
        zh = zh_map.get(key)
        if zh and zh != name_ru:
            node["zh"] = zh
        if "description_category_id" in n:
            node["id"] = n["description_category_id"]
        if "type_id" in n:
            node["id"] = n["type_id"]
            node["type"] = 1
        kids = n.get("children") or []
        if kids:
            node["c"] = convert(kids, zh_map, level + 1)
        out.append(node)
    return out


def count(ns):
    return len(ns) + sum(count(x.get("c") or []) for x in ns)


def main():
    ru_path = fetch("DEFAULT", RAW_RU)
    zh_path = fetch("ZH_HANS", RAW_ZH)
    ru = json.load(open(ru_path, encoding="utf-8"))["result"]
    zh = json.load(open(zh_path, encoding="utf-8"))["result"]

    zh_map = {}
    index_zh(zh, zh_map)

    tree = convert(ru, zh_map)
    missing = []
    def scan(ns):
        for x in ns:
            if not x.get("zh"):
                missing.append(x["n"])
            scan(x.get("c") or [])
    scan(tree)

    data = {
        "source": "ozon seller api /v1/description-category/tree (DEFAULT + ZH_HANS)",
        "total": count(tree),
        "zh_official": len(zh_map),
        "tree": tree,
    }
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"节点 {data['total']}，官方中文 {len(zh_map)} 条，写入 {OUT}")
    print(f"仍缺中文的节点: {len(missing)}")
    for m in missing[:8]:
        print("   ", m)


if __name__ == "__main__":
    main()
