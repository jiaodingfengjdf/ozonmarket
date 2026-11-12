# -*- coding: utf-8 -*-
"""阶段 1 离线契约测试（不消耗任何积分）。

用一个假的客户端替换真调用，只验证「前端/CLI 的条件 → 官方 Body」是否正确：
  1. 店铺接口：fulfillment / labels / brand / keywords / tag / creationDate / categoryIds / skus 是否真的发出去
  2. 市场热词：左侧类目勾选（category_ids）是否落到 categories
  3. 关键词反查：type（自然/广告）是否发送；SKU 上限 20 / 空值是否拦住
  4. 评论接口：sku 是否 int、language 是否为 CN/EN/RU 枚举
  5. 多页抓取：pageNumber 是否逐页递增、行是否合并、成本是否累计
  6. 榜单本地过滤：filtered_out / local_filter 是否如实返回

运行： python tools/test_stage1.py
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


class FakeClient:
    """记录每次调用的 (name, body)，按端点返回构造好的假数据。"""

    def __init__(self):
        self.calls = []
        self.cost_each = 10.0

    def cost_of(self, name):
        return self.cost_each

    def call(self, name, body=None, **kw):
        self.calls.append((name, json.loads(json.dumps(body or {}))))
        page = (body or {}).get("page") or {}
        pno = int(page.get("pageNumber") or 1)
        if name == "top":
            rows = [{"sku": str(1000 + pno), "price": 100, "sales": 10, "revenue": 1000,
                     "sellerType": 1, "categoryInfo": {"cnTitlePath": "测试类目"}}]
            return FakeResult({"records": rows, "total": 300, "current": pno,
                               "totalPages": 3, "timeInterval": "近30天"})
        if name == "category":
            rows = [{"sku": str(2000 + pno), "price": 50, "sales": 5, "revenue": 250}]
            return FakeResult({"productList": rows, "products": 99, "hasNextPage": pno < 3,
                               "totalRevenue": 1e6, "avgPrice": 800,
                               "seasonalityAmplitude": 0.4, "categoryLibraryName": "测试"})
        if name == "shop":
            return FakeResult({"products": [{"sku": "3001", "price": 10}],
                               "productCount": 123, "rating": 4.8, "hasNextPage": False})
        if name in ("market", "mining", "backsearch"):
            rows = [{"query": "kw%d" % pno, "searchVolume": 1000, "competingProducts": 20}]
            return FakeResult({"records": rows, "total": 50, "current": pno, "totalPages": 2})
        if name in ("review_words", "review_report"):
            return FakeResult({"words": []})
        if name in ("review_stat", "review_original"):
            return FakeResult({"reviews": []})
        return FakeResult({})


def make_selector():
    tmp = Store(Path(tempfile.gettempdir()) / "sf_test_stage1.db")
    c = FakeClient()
    return S.Selector(c, store=tmp), c


def t_shop():
    print("\n[1] 查店铺：界面条件是否真的发到官方 Body")
    sel, c = make_selector()
    sel.shop(7, {"fulfillment": "FBO", "labels": ["0"], "brands": ["Acme"],
                 "brand_type": 0, "keywords": ["лампа"], "tag": "hot",
                 "creation_date": 1, "category_ids": "a_b_c,d_e_f",
                 "skus": ["123456"], "price_min": 100, "price_max": 900})
    body = c.calls[0][1]
    check("fulfillment 已发送（数组）", body.get("fulfillment") == ["FBO"], body.get("fulfillment"))
    check("labels 已发送（int 数组）", body.get("labels") == [0], body.get("labels"))
    check("brand.type+brandName 已发送", body.get("brand") == {"type": 0, "brandName": ["Acme"]}, body.get("brand"))
    check("keywords 已发送", body.get("keywords") == ["лампа"], body.get("keywords"))
    check("tag 已发送", body.get("tag") == "hot", body.get("tag"))
    check("creationDate 已发送", body.get("creationDate") == 1, body.get("creationDate"))
    check("categoryIds 拆分正确", body.get("categoryIds") == ["a_b_c", "d_e_f"], body.get("categoryIds"))
    check("skus 已发送", body.get("skus") == ["123456"], body.get("skus"))
    check("price 区间已发送", body.get("price") == {"min": 100, "max": 900}, body.get("price"))


def t_hotwords():
    print("\n[2] 市场热词：左侧类目勾选 → categories")
    sel, c = make_selector()
    sel.hot_words({"category_ids": ["111_222_333", "444_555_666"], "match_type": 0})
    body = c.calls[0][1]
    check("categories 来自 category_ids", body.get("categories") == ["111_222_333", "444_555_666"], body.get("categories"))
    sel2, c2 = make_selector()
    sel2.hot_words({"categories": "777_888_999"})
    check("categories 兼容逗号串", c2.calls[0][1].get("categories") == ["777_888_999"], c2.calls[0][1].get("categories"))


def t_backsearch():
    print("\n[3] 关键词反查：type + SKU 上限")
    sel, c = make_selector()
    sel.backsearch(["175924376", "1061073694"], {"types": ["0", "1"]})
    body = c.calls[0][1]
    check("skuIds 已发送", body.get("skuIds") == ["175924376", "1061073694"], body.get("skuIds"))
    check("type 已发送（字符串数组）", body.get("type") == ["0", "1"], body.get("type"))
    sel2, c2 = make_selector()
    sel2.backsearch(["175924376"], {"types": ["1"]})
    check("只选广告词时 type=['1']", c2.calls[0][1].get("type") == ["1"], c2.calls[0][1].get("type"))
    try:
        sel.backsearch([str(i) for i in range(21)])
        check(">20 个 SKU 应报错", False)
    except ValueError as e:
        check(">20 个 SKU 被拦住", True, e)
    try:
        sel.backsearch([])
        check("空 SKU 应报错", False)
    except ValueError:
        check("空 SKU 被拦住", True)


def t_review():
    print("\n[4] 评论接口：sku=int，language 枚举")
    sel, c = make_selector()
    sel.review_words("175924376", "zh-CN")
    name, body = c.calls[-1]
    check("review_words language=CN", body.get("language") == "CN", body.get("language"))
    check("review_words sku 为 int", isinstance(body.get("sku"), int), type(body.get("sku")))
    sel.review_report("175924376", "ru-RU")
    check("review_report language=RU", c.calls[-1][1].get("language") == "RU", c.calls[-1][1].get("language"))
    sel.review_report("175924376", "EN")
    check("review_report language=EN 透传", c.calls[-1][1].get("language") == "EN", c.calls[-1][1].get("language"))


def t_pages():
    print("\n[5] 多页抓取")
    sel, c = make_selector()
    r = sel.top({"pages": 3, "size": 50})
    pnos = [x[1]["page"]["pageNumber"] for x in c.calls if x[0] == "top"]
    check("榜单按页递增抓取", pnos == [1, 2, 3], pnos)
    check("榜单合并 3 页行数", len(r["rows"]) == 3, len(r["rows"]))
    check("榜单成本累计 30", r["cost"] == 30.0, r["cost"])
    check("返回 fetched_pages=3", r["fetched_pages"] == 3, r.get("fetched_pages"))

    sel2, c2 = make_selector()
    r2 = sel2.category("15621032_15621049_115951147", {"pages": 5})
    pnos2 = [x[1]["page"]["pageNumber"] for x in c2.calls if x[0] == "category"]
    check("类目按 hasNextPage 提前停止", pnos2 == [1, 2, 3], pnos2)
    check("类目合并行数", len(r2["rows"]) == 3, len(r2["rows"]))

    sel3, c3 = make_selector()
    sel3.shop(7, {"pages": 3})
    check("店铺无下一页时只请求 1 次", len([x for x in c3.calls if x[0] == "shop"]) == 1)

    sel4, c4 = make_selector()
    sel4.hot_words({"pages": 2})
    check("热词多页抓取", [x[1]["page"]["pageNumber"] for x in c4.calls if x[0] == "market"] == [1, 2])


def t_local_filter():
    print("\n[6] 榜单本地过滤：如实标注作用范围")
    sel, c = make_selector()
    r = sel.top({"seller_type": "0", "cross_border": "1"})
    lf = r.get("local_filter") or {}
    check("local_filter 说明字段", lf.get("fields") == ["店铺类型", "跨境可售"], lf.get("fields"))
    check("过滤掉非本土行", r["filtered_out"] == 1, r["filtered_out"])
    check("scope 明确写本页", "本页" in (lf.get("scope") or ""), lf.get("scope"))
    sel2, c2 = make_selector()
    r2 = sel2.top({})
    check("无条件时 fields 为空", (r2["local_filter"] or {}).get("fields") == [],
          (r2["local_filter"] or {}).get("fields"))


def t_helpers():
    print("\n[7] 参数归一化辅助")
    check("pages 上限 10", S._pages_of({"pages": 99}) == 10)
    check("pages 非法值回落 1", S._pages_of({"pages": "abc"}) == 1)
    check("lang zh-CN→CN", S.lang_enum("zh-CN") == "CN")
    check("lang ru→RU", S.lang_enum("ru") == "RU")
    check("lang 未知→CN", S.lang_enum("xx") == "CN")
    check("ids 去重", S._ids_list("a,a,b") == ["a", "b"])
    try:
        S._sku_int("12ab")
        check("非数字 SKU 应报错", False)
    except ValueError:
        check("非数字 SKU 被拦住", True)


if __name__ == "__main__":
    t_shop(); t_hotwords(); t_backsearch(); t_review()
    t_pages(); t_local_filter(); t_helpers()
    print(f"\n==== 结果：{len(PASS)} 通过 / {len(FAIL)} 失败 ====")
    if FAIL:
        print("失败项：" + "；".join(FAIL))
        sys.exit(1)
