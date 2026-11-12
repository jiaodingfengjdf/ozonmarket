# -*- coding: utf-8 -*-
"""阶段 2 离线契约测试（不消耗积分）：把已写好但没界面用的 10 个接口接上后的数据契约。

覆盖：
  1. 店铺品牌结构：records → 归一化列（含 page_share / top 份额）
  2. 店铺类目结构：totalRevenues 复数口径、cnTitlePath 路径
  3. 相似商品：单独接口 /api/similar
  4. 商品变体：characteristics → variation_text（颜色:Черный）
  5. 变体特征 / 变体 Top：sourceName 与 revenues/sales 两榜
  6. 评论：statistic 提取、origin/sinicized 词频、原始评论、AI 报表九维
  7. 路由与前端接线：server.py 有新路由，product/shop 页有对应动作按钮

运行： python tools/test_stage2.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import sf_select as S            # noqa: E402
from sf_db import Store          # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  -> " + str(detail)) if detail and not cond else ""))


class FakeResult:
    def __init__(self, data, cost=10.0, cached=False):
        self.data, self.cost, self.cached = data, cost, cached
        self.code, self.ok, self.path, self.name = 200, True, "", ""
        self.elapsed_ms, self.request_id, self.attempts = 1, "", 1


PRODUCT = {"sku": 1001, "title": "T", "price": 100, "sales": 5, "revenue": 500,
           "reviewCount": 3, "reviewRating": 4.8, "sellerName": "S",
           "categoryInfo": {"cnTitlePath": "A > B"}}


class FakeClient:
    def __init__(self):
        self.calls = []

    def cost_of(self, name):
        return 10.0

    def call(self, name, body=None, **kw):
        self.calls.append((name, json.loads(json.dumps(body or {}))))
        if name == "shop_brand":
            return FakeResult({"brands": {"records": [
                {"totalRevenues": 600, "totalSales": 60, "revenueRate": 10, "salesRate": 5,
                 "products": 12, "productsWithSales": 9, "avgPrice": 1500, "avgRevenue": 9e6,
                 "avgSales": 4000, "avgRating": 4.8, "avgReviewCount": 100.5, "sellers": 1,
                 "conversionSharing": 72.35, "returnCancellationRate": 3.5,
                 "brandInfo": {"brandId": 33321059, "brandName": "SvetoCopy",
                               "thumbnailUrl": "https://x/b.jpg"}},
                {"totalRevenue": 400, "totalSales": 40, "products": 8,
                 "brandInfo": {"brandId": 2, "brandName": "Second"}}],
                "total": 2, "current": 1, "totalPages": 1},
                "top": {"total": 2, "totalRevenue": 1000, "totalSales": 100,
                        "revenueShareTop10": 100, "salesShareTop10": 100,
                        "revenues": [], "sales": []}})
        if name == "shop_category":
            return FakeResult({"categories": {"records": [
                {"id": "15621032_15621049_115951147", "totalRevenues": 124187644,
                 "totalSales": 75246, "revenueRate": 11, "salesRate": 7, "products": 18,
                 "avgPrice": 1794,
                 "categoryInfo": {"category": {"id": "15621032_15621049_115951147",
                                               "cnTitle": "打印纸", "title": "Бумага",
                                               "level": 3},
                                  "cnTitlePath": "办公 > 打印纸"}}],
                "total": 1, "current": 1, "totalPages": 1},
                "top": {"revenues": [{"id": "1", "name": "打印纸", "quantity": 1}], "sales": []}})
        if name == "similar":
            return FakeResult([dict(PRODUCT, stock=42)])
        if name == "var_search":
            return FakeResult({"records": [
                {"sku": 1001, "title": "T", "price": 100, "sales": 5, "revenue": 500,
                 "characteristics": [{"sourceName": "Цвет", "name": "颜色", "value": "Черный"}],
                 "categoryInfo": {"cnTitlePath": "A"}}],
                "total": 1, "totalPages": 1})
        if name == "var_chars":
            return FakeResult([{"sourceName": "Цвет", "name": "颜色"}])
        if name == "var_top":
            return FakeResult({"revenues": [{"name": "Черный", "quantity": 785000}],
                               "sales": [{"name": "Черный", "quantity": 245}]})
        if name == "review_stat":
            return FakeResult({"sku": "1001", "title": "T", "imageUrl": "https://x/i.jpg",
                               "reviewStatistic": {"sku": "1001", "reviewCount": 22,
                                                   "reviewRating": 4.5, "fiveStarCount": 18,
                                                   "fiveStarPercent": 81.82, "oneStarCount": 2,
                                                   "oneStarPercent": 9.09}})
        if name == "review_words":
            return FakeResult({"sku": 1001, "origin": ["удобно", "дешево"],
                               "sinicized": ["方便", "便宜"]})
        if name == "review_original":
            return FakeResult({"skus": ["1001"], "reviews": [
                {"date": "2026-09-27", "star": 5, "author": "A", "text": "ok",
                 "photos": ["https://x/p.jpg"], "skus": "1001"}]})
        if name == "review_report":
            return FakeResult({"sku": 1001, "advantages": [{"dimensionCn": "容量大", "count": 12, "proportion": 0.3}],
                               "disadvantages": [], "optSugges": {"标题": "突出容量"},
                               "qaAnalysis": {"问题": "多大"}})
        return FakeResult({})


def sel():
    tmp = Store(Path(tempfile.gettempdir()) / "sf_test_stage2.db")
    c = FakeClient()
    return S.Selector(c, store=tmp), c


def t_shop_brands():
    print("\n[1] 店铺品牌结构")
    s, c = sel()
    r = s.shop_brands(7, size=20)
    row = r["rows"][0]
    check("name 取自 brandInfo.brandName", row["name"] == "SvetoCopy", row["name"])
    check("revenue 取 totalRevenues（真实字段名）", row["revenue"] == 600, row["revenue"])
    check("revenue 兼容旧的单数 totalRevenue", r["rows"][1]["revenue"] == 400, r["rows"][1]["revenue"])
    check("sharing 取 conversionSharing", row["sharing"] == 72.35, row["sharing"])
    check("page_share 按本页求和归一", abs(row["page_share"] - 60.0) < 0.01, row["page_share"])
    check("top 份额透传", r["top"]["revenue_share_top10"] == 100, r["top"])
    check("total/pages 取自 brands 分页", r["total"] == 2 and r["pages"] == 1, (r["total"], r["pages"]))


def t_shop_cats():
    print("\n[2] 店铺类目结构")
    s, c = sel()
    r = s.shop_categories(7)
    row = r["rows"][0]
    check("revenue 取 totalRevenues（复数口径）", row["revenue"] == 124187644, row["revenue"])
    check("cn_path 取 cnTitlePath", row["cn_path"] == "办公 > 打印纸", row["cn_path"])
    check("category_id 正确", row["category_id"] == "15621032_15621049_115951147", row["category_id"])
    check("page_share=100", row["page_share"] == 100.0, row["page_share"])


def t_similar():
    print("\n[3] 相似商品（独立接口）")
    s, c = sel()
    r = s.similar("1001")
    check("请求 similar 端点", c.calls[-1][0] == "similar", c.calls[-1][0])
    check("sku 传整数", isinstance(c.calls[-1][1]["sku"], int), type(c.calls[-1][1]["sku"]))
    check("返回归一化 rows", r["rows"][0]["sku"] == "1001", r["rows"][:1])
    check("相似商品带库存", r["rows"][0].get("stock") == 42, r["rows"][0].get("stock"))


def t_variations():
    print("\n[4] 商品变体 + variotion_text")
    s, c = sel()
    r = s.variations("1001", size=50)
    row = r["rows"][0]
    check("variation_text 拼接 颜色:Черный", row.get("variation_text") == "颜色:Черный", row.get("variation_text"))
    check("sku 传整数", isinstance(c.calls[-1][1]["sku"], int), type(c.calls[-1][1]["sku"]))
    check("带 clientLanguage", c.calls[-1][1].get("clientLanguage") == "zh-CN", c.calls[-1][1].get("clientLanguage"))


def t_var_meta():
    print("\n[5] 变体特征 / 变体 Top")
    s, c = sel()
    ch = s.var_characteristics("1001")
    check("特征列表 sourceName 保留", ch["rows"][0]["sourceName"] == "Цвет", ch["rows"])
    top = s.var_top("1001", "Цвет")
    check("revenues 榜返回", top["revenues"][0]["name"] == "Черный", top["revenues"])
    check("sales 榜返回", top["sales"][0]["quantity"] == 245, top["sales"])
    check("characteristic 原样传递", c.calls[-1][1]["characteristic"] == "Цвет", c.calls[-1][1])


def t_reviews():
    print("\n[6] 评论四件套")
    s, c = sel()
    st = s.review_stat("1001")
    check("statistic.reviewCount 提取", (st["statistic"] or {}).get("reviewCount") == 22, st["statistic"])
    check("stat 保留 title/image", st["title"] == "T" and st["image_url"], (st["title"], st["image_url"]))

    w = s.review_words("1001", "zh-CN")
    check("words 语言转 CN", c.calls[-1][1]["language"] == "CN", c.calls[-1][1]["language"])
    check("words sinicized 列表", w["sinicized"] == ["方便", "便宜"], w["sinicized"])
    check("words origin 列表", w["origin"] == ["удобно", "дешево"], w["origin"])

    o = s.review_original("1001")
    check("original 评论条数", len(o["rows"]) == 1, o["rows"])
    check("original 星级", o["rows"][0]["star"] == 5, o["rows"][0])

    rp = s.review_report("1001", "EN")
    check("report 语言 EN", c.calls[-1][1]["language"] == "EN", c.calls[-1][1]["language"])
    check("report 九维透传", (rp["rows"] or {}).get("advantages")[0]["count"] == 12, rp["rows"])
    check("report 建议透传", (rp["rows"] or {}).get("optSugges"), rp["rows"])


def t_wiring():
    print("\n[7] 路由与前端接线（静态扫描，确保没有白写）")
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    for route in ("/api/shop/brands", "/api/shop/categories", "/api/similar"):
        check(f"server 路由 {route}", route in srv)
    shop = (ROOT / "static" / "shop.html").read_text(encoding="utf-8")
    prod = (ROOT / "static" / "product.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    check("店铺页有品牌/类目按钮", 'data-act="shop-brands"' in shop and 'data-act="shop-cats"' in shop)
    check("竞品页有变体/评论按钮", 'data-act="var-list"' in prod and 'data-act="rev-stat"' in prod)
    check("竞品页有相似商品按钮", 'data-act="similar"' in prod)
    for act in ("shop-brands", "shop-cats", "var-list", "var-chars", "rev-stat", "rev-words",
                "rev-original", "rev-report", "rev-task", "similar"):
        check(f"app.js 处理 {act}", f"'{act}':" in js)


if __name__ == "__main__":
    t_shop_brands(); t_shop_cats(); t_similar(); t_variations()
    t_var_meta(); t_reviews(); t_wiring()
    print(f"\n==== 结果：{len(PASS)} 通过 / {len(FAIL)} 失败 ====")
    if FAIL:
        print("失败项：" + "；".join(FAIL))
        sys.exit(1)
