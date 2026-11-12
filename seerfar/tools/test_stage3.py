# -*- coding: utf-8 -*-
"""阶段 3 离线测试（0 积分）：数据层扩展 / 机会分可配 / 利润模型 / 收藏 / 报告导出 / 接线。

运行： python tools/test_stage3.py
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

import sf_db as DB                     # noqa: E402
import sf_export as EX                 # noqa: E402
import sf_profit as PF                 # noqa: E402
import sf_select as S                  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (("  -> " + str(detail)) if detail and not cond else ""))


def tmp_store(tag):
    p = Path(tempfile.mkdtemp(prefix="sf3_")) / f"{tag}.db"
    return DB.Store(p), p


SAMPLE = [{"sku": "1", "title": "Лампа", "brand": "B", "seller": "S", "price": 1990,
           "sales": 100, "revenue": 199000, "review_count": 50, "review_rating": 4.8,
           "category_id": "c1", "category_cn": "灯", "weight": 480, "volume": 2.1,
           "dimension": "231×183×103", "gross_margin": 30, "drr": 3.2,
           "conv_to_cart_pdp": 12, "variants": 4, "opportunity": 55.5,
           "up_days": 30, "sales_rate": 20}]


def t_migration():
    print("\n[1] 数据层：旧库补列 + 扩展字段落库")
    st, path = tmp_store("mig")
    cols = {r["name"] for r in st.q("PRAGMA table_info(product)")}
    check("product 已含 net_margin 列", "net_margin" in cols, sorted(cols)[:5])
    check("keyword 已含 opportunity 列",
          "opportunity" in {r["name"] for r in st.q("PRAGMA table_info(keyword)")})
    check("favorite 表已建", bool(st.q("SELECT name FROM sqlite_master WHERE name='favorite'")))
    st.upsert_products(SAMPLE)
    row = st.product_by_sku("1")
    check("扩展字段写入 weight", row["weight"] == 480, row.get("weight"))
    check("扩展字段写入 opportunity", row["opportunity"] == 55.5, row.get("opportunity"))
    check("扩展字段写入 drr", row["drr"] == 3.2, row.get("drr"))


def t_local_filters():
    print("\n[2] 本地库：筛选 + 分页 + 收藏过滤")
    st, _ = tmp_store("filter")
    rows = []
    for i in range(12):
        r = dict(SAMPLE[0], sku=str(i), price=1000 + i * 100, opportunity=10 + i,
                 gross_margin=10 + i, title=f"Товар {i}")
        rows.append(r)
    st.upsert_products(rows)
    got, total = st.products_page({"price_min": 1500, "price_max": 1800}, limit=50)
    check("价格区间筛选", total == 4 and all(1500 <= g["price"] <= 1800 for g in got), (total, [g["price"] for g in got]))
    got, total = st.products_page({"opportunity_min": 15}, limit=50)
    check("机会分下限筛选", total == 7, total)
    got, total = st.products_page({"q": "Товар 1"}, limit=50)
    check("关键词搜索 title", total >= 3, total)
    page1, total = st.products_page({}, order="opportunity", direction="DESC", limit=5, offset=0)
    page2, _ = st.products_page({}, order="opportunity", direction="DESC", limit=5, offset=5)
    check("分页不重叠", total == 12 and page1[0]["sku"] != page2[0]["sku"], total)
    check("排序生效（opportunity 降序）", page1[0]["opportunity"] >= page1[-1]["opportunity"])

    st.favorite_toggle("3")
    got, total = st.products_page({"favorite_only": "1"}, limit=50)
    check("只看收藏", total == 1 and got[0]["sku"] == "3", total)
    check("收藏列表带商品信息", st.favorites()[0]["title"] == "Товар 3", st.favorites()[:1])
    check("取消收藏", st.favorite_toggle("3")["favorite"] is False)


def t_keyword_page():
    print("\n[3] 关键词库筛选")
    st, _ = tmp_store("kw")
    st.upsert_keywords([
        {"query": "лампа", "query_cn": "灯", "search_volume": 5000, "growth30": 12,
         "market_space": 300, "opportunity": 61},
        {"query": "наушники", "query_cn": "耳机", "search_volume": 90000, "growth30": 40,
         "market_space": 800, "opportunity": 78}], "market")
    got, total = st.keywords_page({"search_volume_min": 10000}, limit=10)
    check("搜索量下限", total == 1 and got[0]["query"] == "наушники", total)
    got, total = st.keywords_page({"q": "灯"}, limit=10)
    check("中文词搜索", total == 1, total)
    got, total = st.keywords_page({"kind": "market"}, order="opportunity", limit=10)
    check("按机会分排序", got[0]["opportunity"] == 78, got[0])


def t_opportunity():
    print("\n[4] 机会分：可配置 + 权重归一")
    row = {"sales": 5000, "revenue": 5e6, "sales_rate": 40, "review_count": 800,
           "variants": 6, "gross_margin": 25, "conv_to_cart_pdp": 12}
    base = S.opportunity(row, "product")
    check("默认分在 0~100", 0 <= base["score"] <= 100, base)
    check("四项分解合计=总分", abs(sum(base["parts"].values()) - base["score"]) < 0.11, base)
    growth_only = S.opportunity(row, "product", {"weights": {"product": {"sales": 0, "growth": 100,
                                                                       "low_comp": 0, "conv": 0}}})
    check("权重可改（只留增长）", growth_only["parts"]["销量"] == 0.0 and growth_only["parts"]["增长"] > 0, growth_only)
    kw = S.opportunity({"search_volume": 200000, "market_space": 500, "growth30": 30,
                        "competing_products": 900, "sellers": 40,
                        "conversion_sharing": 60, "avg_price": 1500}, "keyword")
    check("关键词分在 0~100", 0 <= kw["score"] <= 100, kw)


def t_profit():
    print("\n[5] 利润模型")
    kg, w, v = PF.chargeable_kg(weight_g=480, volume_l=2.1, dimension="231×183×103")
    check("计费重取实重与体积重较大者", kg == 0.48 and v == 0.42, (kg, w, v))
    heavy = PF.chargeable_kg(weight_g=200, volume_l=20, dimension=None)[0]
    check("轻抛货按体积重", heavy == 4.0, heavy)
    check("尺寸字符串(mm)解析 → 4354.1 cm³", abs(PF.dims_cm3("231×183×103") - 4354.119) < 0.01, PF.dims_cm3("231×183×103"))

    r = PF.compute({"price": 1990, "weight": 480, "volume": 2.1, "drr": 3.2},
                   {"cost_cny": 35, "rate_cny_rub": 12.5, "shipping_cny_per_kg": 32,
                    "commission_pct": 15, "payment_pct": 2, "target_margin_pct": 25})
    check("采购成本换汇", r["cost_rub"] == 437.5, r["cost_rub"])
    check("头程费用", r["shipping_rub"] == 192.0, r["shipping_rub"])
    check("佣金=售价×15%", r["commission_rub"] == 298.5, r["commission_rub"])
    check("广告用商品自带 drr", r["assumed"]["drr_pct"] == 3.2, r["assumed"])
    expect_net = 1990 - 437.5 - 192 - 298.5 - 39.8 - 63.68
    check("净利公式", abs(r["net_profit"] - expect_net) < 0.02, r["net_profit"])
    check("真毛利率", abs(r["net_margin"] - 48.17) < 0.05, r["net_margin"])
    check("保本价 < 售价", r["breakeven"] < 1990, r["breakeven"])
    check("目标毛利低于实际毛利时，建议售价应低于现价且高于保本价",
          r["breakeven"] < r["suggested"] < 1990, (r["breakeven"], r["suggested"]))
    tight = PF.compute({"price": 1990, "weight": 480, "drr": 3.2},
                      {"cost_cny": 35, "rate_cny_rub": 12.5, "shipping_cny_per_kg": 32,
                       "commission_pct": 15, "payment_pct": 2, "target_margin_pct": 60})
    check("目标毛利高于实际时，建议售价应高于现价", tight["suggested"] > 1990, tight["suggested"])

    bad = PF.compute({"price": 300, "weight": 3000}, {"cost_cny": 60, "rate_cny_rub": 12.5,
                                                      "shipping_cny_per_kg": 35,
                                                      "commission_pct": 15})
    check("亏损能被识别", bad["net_profit"] < 0, bad["net_profit"])
    rows, summ = PF.enrich([{"sku": "1", "price": 1990, "weight": 480},
                            {"sku": "2", "price": 300, "weight": 3000}],
                           {"cost_cny": 20, "rate_cny_rub": 12.5, "shipping_cny_per_kg": 30})
    check("批量汇总行数", summ["rows"] == 2 and len(rows) == 2, summ)
    check("汇总含平均毛利", summ["avg_net_margin"] is not None, summ)


def t_export_report():
    print("\n[6] 选品报告（多 sheet）")
    out = Path(tempfile.mkdtemp(prefix="sf3x_"))
    p = EX.export_report(products=SAMPLE, favorites=[{"sku": "1", "title": "Лампа", "tags": "主推"}],
                         meta={"页面": "select", "导出时间": "t"}, out_dir=str(out),
                         filename="rep.xlsx")
    check("文件已生成", p.exists(), p)
    from openpyxl import load_workbook
    wb = load_workbook(p)
    names = wb.sheetnames
    check("含『选品结论』", "选品结论" in names, names)
    check("含『商品清单』", "商品清单" in names, names)
    check("含『收藏清单』", "收藏清单" in names, names)
    heads = [c.value for c in wb["商品清单"][1]]
    check("商品清单含净利列", "净利₽" in heads, heads[-8:])
    check("商品清单含真毛利率列", "真毛利率%" in heads, heads[-8:])


def t_wiring():
    print("\n[7] 路由/界面接线")
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    for route in ('"/api/profit"', '"/api/favorites"', '"/api/favorites/toggle"'):
        check(f"server 有 {route}", route in srv)
    check("本地库走 products_page", "products_page" in srv)
    check("导出支持 report", 'kind == "report"' in srv)
    idx = (ROOT / "static" / "vue" / "schema.js").read_text(encoding="utf-8")
    lp = (ROOT / "static" / "vue" / "app.js").read_text(encoding="utf-8")
    js = (ROOT / "static" / "vue" / "app.js").read_text(encoding="utf-8")
    cols = (ROOT / "static" / "vue" / "cols.js").read_text(encoding="utf-8")
    check("Vue 选品页有利润计算器", "runProfit" in js and "PROFIT_KEYS" in js)
    check("Vue 有选品报告导出", "exportReport" in js and "kind: 'report'" in js)
    check("Vue 本地库有搜索/收藏筛选", "local_products" in js and "仅看收藏" in js or "local_products" in js, 'data-f="q"' in lp and "favorite_only" in lp)
    check("Vue 有收藏切换", "favorites/toggle" in js)
    check("Vue 有利润调用", "/api/profit" in js)
    check("Vue 表格有收藏列", "\"fav\"" in cols and "\"favbtn\"" in (ROOT / "static" / "vue" / "app.js").read_text(encoding="utf-8"))
    check("Seerfar 结果表保留 重量/体积/尺寸 三列",
          "重量g" in cols and "体积L" in cols and "尺寸" in cols)
    check("重量/尺寸过滤只作用于 composer 内容（sf_content）",
          "WEIGHT_DIM_RX" in (ROOT / "sf_content.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    t_migration(); t_local_filters(); t_keyword_page(); t_opportunity()
    t_profit(); t_export_report(); t_wiring()
    print(f"\n==== 结果：{len(PASS)} 通过 / {len(FAIL)} 失败 ====")
    if FAIL:
        print("失败项：" + "；".join(FAIL))
        sys.exit(1)
