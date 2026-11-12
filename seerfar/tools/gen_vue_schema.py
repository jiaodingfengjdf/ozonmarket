# -*- coding: utf-8 -*-
"""从现有静态页面生成 Vue SPA 的页面 schema（保证筛选字段与页头 100% 对齐）。

产出：static/vue/schema.js  →  window.__SCHEMA__ = { pages: [...], nav: [...] }

每个 page 结构：
  { tool, path, title, sub, presets[], formHtml, resultTitle, resultHint, actions[] }
formHtml 直接沿用原 `.fall` + `.formfoot` 的 HTML（含 data-f 属性），
Vue 侧用 v-html 渲染后仍按 [data-f] 收集参数，因此不会漏字段。
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
OUT = STATIC / "vue" / "schema.js"


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def extract(html_text: str):
    title = ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.S)
    if m:
        title = strip_tags(m.group(1))
    sub = ""
    m = re.search(r'<p class="muted"[^>]*>(.*?)</p>', html_text, re.S)
    if m:
        sub = strip_tags(m.group(1))

    presets = []
    for m in re.finditer(r'<button[^>]*class="preset([^"]*)"[^>]*data-preset="([^"]*)"[^>]*>(.*?)</button>', html_text, re.S):
        inner = m.group(3)
        nm = re.search(r'class="pname"[^>]*>(.*?)</span>', inner, re.S)
        ds = re.search(r'class="pdesc"[^>]*>(.*?)</span>', inner, re.S)
        presets.append({
            "key": m.group(2),
            "active": "active" in m.group(1),
            "name": strip_tags(nm.group(1)) if nm else m.group(2),
            "desc": strip_tags(ds.group(1)) if ds else "",
        })

    m = re.search(r'<form class="filtercard"[^>]*data-tool="([^"]+)"[^>]*>(.*?)</form>', html_text, re.S)
    tool = m.group(1) if m else ""
    form_html = m.group(2).strip() if m else ""
    # 去掉最外层 .fall（保留其内容）与 applied-bar（由 Vue 渲染）
    form_html = re.sub(r'<div class="applied-bar".*?</div>\s*</div>', "", form_html, flags=re.S)

    result_title = ""
    m = re.search(r'<div class="resultr"><h3>(.*?)</h3>', html_text, re.S)
    if m:
        result_title = strip_tags(m.group(1))
    hint = ""
    m = re.search(r'<div class="statusline"[^>]*data-meta[^>]*>(.*?)</div>', html_text, re.S)
    if m:
        hint = strip_tags(m.group(1))

    actions = []
    m = re.search(r'<div class="resultbar-actions"[^>]*>(.*?)</div>\s*</div>', html_text, re.S)
    if m:
        for a in re.finditer(r'<button[^>]*>([^<]+)</button>', m.group(1)):
            actions.append(a.group(1).strip())

    return {
        "tool": tool, "title": title, "sub": sub, "presets": presets,
        "formHtml": form_html,
        "resultTitle": result_title or "查询结果",
        "resultHint": hint, "actions": actions,
    }


NAV = [
    ("在线选品", "/app/#/select"), ("市场热词", "/app/#/hotwords"), ("关键词挖掘", "/app/#/mining"),
    ("关键词反查", "/app/#/backsearch"), ("竞品详情", "/app/#/product"), ("类目大盘", "/app/#/category"),
    ("店铺分析", "/app/#/shop"), ("本地商品库", "/app/#/local-products"),
    ("本地关键词库", "/app/#/local-keywords"), ("调用日志", "/app/#/logs"),
]

FILES = [
    ("index.html", "/select"), ("hotwords.html", "/hotwords"), ("mining.html", "/mining"),
    ("backsearch.html", "/backsearch"), ("product.html", "/product"), ("category.html", "/category"),
    ("shop.html", "/shop"), ("local-products.html", "/local-products"),
    ("local-keywords.html", "/local-keywords"), ("logs.html", "/logs"),
]


def main():
    missing = [fn for fn, _ in FILES if not (STATIC / fn).exists()]
    if missing:
        print("旧静态页面已移除（%d/%d 缺失），schema.js 为唯一事实来源，跳过生成。" % (len(missing), len(FILES)))
        print("如需重建筛选表单，请改 static/vue/schema.js 或恢复旧 HTML 后重跑。")
        return
    pages = []
    for fn, path in FILES:
        f = STATIC / fn
        if not f.exists():
            print("跳过（不存在）:", fn)
            continue
        pages.append(dict(extract(f.read_text(encoding="utf-8")), path=path, file=fn))
        p = pages[-1]
        print(f"{fn:22} tool={p['tool']:16} fields={p['formHtml'].count('data-f='):3} presets={len(p['presets'])}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = "window.__SCHEMA__ = " + json.dumps(
        {"pages": pages, "nav": [{"label": a, "href": b} for a, b in NAV]},
        ensure_ascii=False, indent=1) + ";\n"
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print("\n写出:", OUT.relative_to(ROOT), len(body), "字节")


if __name__ == "__main__":
    main()
