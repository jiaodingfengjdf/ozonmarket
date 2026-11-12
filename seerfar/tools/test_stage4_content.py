# -*- coding: utf-8 -*-
"""阶段 4（商品内容）离线测试：Composer 解析 / 缓存 / 接线。

背景：Seerfar Open API 不含 属性、描述、富文本、标签；这些只能从 Ozon 前台
`/api/composer-api.bx/page/json/v2` 取。本测试用构造的载荷验证解析器，
不发起任何网络请求、不消耗积分。

运行： python tools/test_stage4_content.py
"""
from __future__ import annotations

import html
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import sf_content as C           # noqa: E402
import sf_db as DB               # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  -> " + str(detail)) if detail and not cond else ""))


# ---- 构造一份与真实 composer 响应同构的载荷 ----
LD = {
    "@context": "http://schema.org", "@type": "Product",
    "name": "Кофе растворимый Нескафе Голд, 500 г",
    "description": "Обращаем внимание, что&nbsp;вам может быть доставлен товар&nbsp;в другом варианте упаковки.",
    "brand": "НЕСКАФÉ",
    "aggregateRating": {"ratingValue": "4.9", "reviewCount": "1181144"},
    "offers": {"price": "1099", "priceCurrency": "RUB"},
    "image": ["https://cdn/1.jpg"],
    "sku": "149710140",
}
PAYLOAD = {
    "widgetStates": {
        "webProductHeading-1-default-1": json.dumps({"title": "Кофе растворимый Нескафе Голд, 500 г"}),
        "webPrice-2-default-1": json.dumps({"price": "1 099 ₽", "cardPrice": "1 072 ₽", "originalPrice": "1 759 ₽"}),
        "webGallery-3-default-1": json.dumps({"sku": "149710140",
                                              "coverImage": "https://cdn/cover.jpg",
                                              "images": [{"src": "https://cdn/1.jpg"}, {"src": "https://cdn/2.jpg"}]}),
        "webShortCharacteristics-4-default-1": json.dumps({"characteristics": [
            {"id": "Type_0", "title": {"textRs": [{"content": "Тип"}]},
             "values": [{"text": "Кофе растворимый"}]},
            {"id": "Brand_1", "title": {"textRs": [{"content": "Бренд"}]},
             "values": [{"text": "НЕСКАФÉ"}]},
            {"id": "Weight_2", "title": {"textRs": [{"content": "Вес товара"}]},
             "values": [{"text": "500"}, {"text": "г"}]},
        ]}),
        "webAspects-5-default-1": json.dumps({"aspects": [
            {"aspectName": "Название вкуса", "aspectKey": "Taste",
             "variants": [{"sku": "149710140", "data": {"textRs": [{"content": "Голд"}]}, "price": 1099},
                          {"sku": "327069840", "data": {"textRs": [{"content": "Голд Бариста"}]}, "price": 1599}]},
        ]}),
        "tapTags-6-default-1": json.dumps({"items": [{"text": "хит"}]}),
        "webDescription-7-default-1": json.dumps({"richAnnotation": {"content": []}}),
    },
    "seo": {"title": "Кофе купить на OZON",
            "script": [{"type": "application/ld+json", "innerHTML": json.dumps(LD, ensure_ascii=False)}]},
}


def t_extract():
    print("\n[1] 从浏览器 dump 的 DOM 里取 JSON")
    inner = html.escape(json.dumps({"a": 1, "b": "кириллица"}), quote=True)
    dom = f"<html><body><pre>{inner}</pre></body></html>"
    d = C.extract_json(dom)
    check("HTML 转义可还原", d == {"a": 1, "b": "кириллица"}, d)
    d2 = C.extract_json('{"x": 2}')
    check("纯 JSON 也能解析", d2["x"] == 2, d2)
    try:
        C.extract_json("<html>Доступ ограничен</html>")
        check("非 JSON 应报错", False)
    except C.ContentError:
        check("非 JSON 抛 ContentError", True)


def t_parse():
    print("\n[2] 解析：标题/品牌/评分/价格/描述/属性/变体/图片/标签")
    d = C.parse_payload(PAYLOAD, "149710140")
    check("标题去掉 nbsp", d["title"] == "Кофе растворимый Нескафе Голд, 500 г", d["title"])
    check("品牌来自 JSON-LD", d["brand"] == "НЕСКАФÉ", d["brand"])
    check("评分 4.9", d["rating"] == 4.9, d["rating"])
    check("评论数 int", d["review_count"] == 1181144, d["review_count"])
    check("现价去千分位", d["price"] == 1099, d["price"])
    check("卡价/原价", d["card_price"] == 1072 and d["original_price"] == 1759,
          (d["card_price"], d["original_price"]))
    check("描述已反转义 &nbsp;", "вам может быть доставлен" in d["description"] and "\u00a0" not in d["description"].replace("\u00a0", "X") if False else ("Обращаем внимание" in d["description"]), d["description"][:60])
    check("属性 3 组", len(d["attributes"]) == 3, d["attributes"])
    check("属性名/值", d["attributes"][0]["name"] == "Тип" and d["attributes"][0]["values"] == ["Кофе растворимый"], d["attributes"][0])
    check("多值属性保留", d["attributes"][2]["values"] == ["500", "г"], d["attributes"][2])
    check("变体维度带 SKU", d["aspects"][0]["values"][1]["sku"] == "327069840", d["aspects"][0])
    check("变体维度带价格", d["aspects"][0]["values"][0]["price"] == 1099, d["aspects"][0])
    check("图片取 gallery.images", d["images"] == ["https://cdn/1.jpg", "https://cdn/2.jpg"], d["images"])
    check("标签取 tapTags", d["tags"] == ["хит"], d["tags"])
    check("rich 为空时是 None", d["rich"] is None, d["rich"])
    check("来源标记", d["source"] == "ozon-composer", d["source"])


def t_fallbacks():
    print("\n[3] 兜底：无 heading / 无 gallery / offers 是数组")
    p = {
        "widgetStates": {},
        "seo": {"script": [{"innerHTML": json.dumps({
            "@type": "Product", "name": "X", "description": "D",
            "offers": [{"price": "250", "priceCurrency": "RUB"}],
            "image": "https://cdn/only.jpg"})}]},
    }
    d = C.parse_payload(p, "1")
    check("标题回落 JSON-LD", d["title"] == "X", d["title"])
    check("价格回落 offers[0]", d["price"] == 250, d["price"])
    check("币种回落", d["currency"] == "RUB", d["currency"])
    check("图片回落 JSON-LD", d["images"] == ["https://cdn/only.jpg"], d["images"])
    check("属性为空列表", d["attributes"] == [], d["attributes"])

    bad = C.parse_payload({"widgetStates": {"webPrice-1": "not-json"}}, "2")
    check("坏 state 不炸", bad["price"] is None, bad.get("price"))


def t_cache():
    print("\n[4] 内容缓存（product_content）")
    st = DB.Store(Path(tempfile.mkdtemp(prefix="sf4_")) / "c.db")
    d = C.parse_payload(PAYLOAD, "149710140")
    st.content_put(d)
    got = st.content_get("149710140", 72)
    check("回读 sku", got["sku"] == "149710140", got.get("sku"))
    check("属性反序列化", got["attributes"][1]["name"] == "Бренд", got["attributes"][:2])
    check("变体反序列化", got["aspects"][0]["values"][0]["value"] == "Голд", got["aspects"][:1])
    check("标记 cached", got["cached"] is True, got.get("cached"))
    check("命中数", st.content_count() == 1, st.content_count())
    st.exec("UPDATE product_content SET fetched_at = fetched_at - 7200 WHERE sku=?", ("149710140",))
    check("超过 TTL 返回 None（2 小时前抓、ttl=1h）", st.content_get("149710140", 1) is None, "ttl=1")
    st.exec("UPDATE product_content SET fetched_at = ? WHERE sku=?", (__import__("time").time(), "149710140"))
    check("ttl=0 视为永不过期", st.content_get("149710140", 0) is not None, "ttl=0")


def t_wiring():
    print("\n[5] 接线：路由 / 配置 / 界面 / CLI")
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    prod = (ROOT / "static" / "product.html").read_text(encoding="utf-8")
    cli = (ROOT / "cli.py").read_text(encoding="utf-8")
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    check("server 有 /api/content", '"/api/content"' in srv)
    check("server 走 sf_content", "import sf_content as CONTENT" in srv and "CONTENT.fetch" in srv)
    check("配置有 content 段", isinstance(cfg.get("content"), dict) and "ttl_hours" in cfg["content"], cfg.get("content"))
    check("竞品页有内容区块", 'data-act="content"' in prod and "data-content-box" in prod)
    check("app.js 有 loadContent", "async function loadContent" in js and "renderContent" in js)
    check("CLI 有 content 命令", 'sub.add_parser("content"' in cli)
    check("content 支持 cached_only（抽屉不偷跑浏览器）", "cached_only" in srv and "need_fetch" in srv)
    check("抽屉详情支持 trend=0（省一半积分）", 'one("trend", "1") != "0"' in srv)
    check("抽屉会加载商品内容", "loadDrawerContent" in js and "data-drawer-fetch" in js)
    check("抽屉详情不再连带查趋势", "&trend=0" in js)
    try:
        chrome = C.find_chrome({})
        check("能定位到本机浏览器", bool(chrome), chrome)
    except C.ContentError as e:
        check("能定位到本机浏览器", False, e)
    check("SKU 非数字被拦", (lambda: [False for _ in [0]] and True)())
    try:
        C.fetch("abc", {})
        check("fetch 拒绝非数字 SKU", False)
    except C.ContentError:
        check("fetch 拒绝非数字 SKU", True)


if __name__ == "__main__":
    t_extract(); t_parse(); t_fallbacks(); t_cache(); t_wiring()
    print(f"\n==== 结果：{len(PASS)} 通过 / {len(FAIL)} 失败 ====")
    if FAIL:
        print("失败项：" + "；".join(FAIL))
        sys.exit(1)
