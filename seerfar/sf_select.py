# -*- coding: utf-8 -*-
"""Seerfar 选品业务逻辑层。

负责：把前端/CLI 的中文筛选条件翻译成官方 Body 参数 → 调客户端 → 归一化 → 落库。
所有筛选字段名、排序字段白名单、枚举值均来自官方 Open API 文档，不做猜测。
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from sf_client import SeerfarClient, get_client
from sf_db import STORE, dumps

# 各接口允许的排序字段（官方文档 page.orders.field 支持列表）
SORT_FIELDS = {
    "top": {"revenue", "price", "sales", "grossMargin", "views", "sessionCountSearch",
            "sessionCount", "convToCartPdp", "orderConversionRate", "drr",
            "returnCancellationRate", "missedRevenue", "variants", "reviewCount",
            "reviewRating", "upTime", "weight", "volume", "questionsAndAnswers"},
    "category": {"revenue", "price", "sales", "grossMargin", "views", "sessionCountSearch",
                 "sessionCount", "convToCartPdp", "orderConversionRate", "drr",
                 "returnCancellationRate", "missedRevenue", "variants", "reviewCount",
                 "reviewRating", "upTime", "weight", "volume", "questionsAndAnswers"},
    "market": {"searchVolume", "avgPrice", "sales", "revenue", "count30GrowthRate",
               "productCount", "sellers", "competingProducts", "reviews", "ratings",
               "marketSpace", "itemsViews", "conversionSharing", "returnCancellationRate",
               "weight", "volume"},
    "mining": {"uniqQueriesWCa", "ca", "searchVolume", "count30GrowthRate", "relevancy",
               "titleDensity", "wordCount", "avgPrice", "competingProducts", "productCount",
               "sellers", "adRivalCount", "itemsViews", "marketSpace", "conversionSharing",
               "returnCancellationRate"},
    "backsearch": {"exposure", "conversion", "uniqQueriesWCa", "ca", "searchVolume",
                   "count30GrowthRate", "naturalRank", "adRank", "titleDensity",
                   "wordCount", "competingProducts", "productCount", "sellers",
                   "adRivalCount", "itemsViews", "marketSpace", "conversionSharing",
                   "returnCancellationRate"},
    "var_search": {"price", "upTime", "sales", "revenue", "reviewCount", "reviewRating"},
}

# 榜单/类目公共的数值区间筛选字段
COMMON_RANGES = [
    "reviewCount", "drr", "reviewRating", "questionsAndAnswers", "price",
    "monthlyRevenue", "monthlySales", "monthlySalesRate", "weight", "volume",
    "grossMargin", "variants", "convToCartPdp", "returnCancellationRate",
]
MARKET_RANGES = [
    "price", "monthlySales", "monthlyRevenue", "weight", "volume", "reviews",
    "ratings", "searchVolume", "searchChange30", "sellers", "products",
    "productViews", "conversionSharing", "marketSpace",
]
MINING_RANGES = [
    "uniqQueriesWCa", "relevancy", "searchVolume", "ca", "products", "wordCount",
    "titleDensity", "price", "sellers", "adRivalCount", "productViews",
    "conversionSharing", "searchChange30", "marketSpace",
]

# 中文表头 → 数据键（导出与前端宽表共用），顺序 = 界面展示顺序
# 分组：基础+产品数据 → 价格与销售 → 口碑与售后 → 流量与转化漏斗 → 广告与促销 → 上架/变体 → 综合
PRODUCT_COLUMNS = [
    ("SKU", "sku"), ("商品标题", "title"),
    ("重量g", "weight"), ("体积L", "volume"), ("尺寸", "dimension"),
    ("中文类目", "category_cn"), ("品牌", "brand"), ("卖家", "seller"),
    ("卖家类型", "seller_type_text"), ("配送", "fulfillment_text"),
    ("价格₽", "price"), ("平均折扣%", "discount"),
    ("月销量", "sales"), ("销量增长%", "sales_rate"),
    ("月销售额₽", "revenue"), ("销售额增长%", "revenue_rate"), ("毛利率%", "gross_margin"),
    ("评论数", "review_count"), ("评分", "review_rating"), ("问答数", "qa"), ("退货取消率%", "return_cancellation_rate"),
    ("展示总量", "views"), ("曝光量", "session_count_search"), ("产品卡浏览", "session_count"),
    ("搜索加购率%", "conv_to_cart_search"), ("购物车转化率%", "conv_to_cart_pdp"),
    ("展示转化%", "conv_view_to_order"), ("订单转化%", "order_conversion_rate"),
    ("广告费用份额%", "drr"), ("促销销售占比%", "promo_revenue_share"),
    ("上架时间", "up_time_date"), ("上架天数", "up_days"), ("上架月数", "up_months"),
    ("变体数", "variants"),
    ("标签", "labels_text"), ("类目ID", "category_id"), ("变体SKU", "variation_ids"),
    ("品牌ID", "brand_id"), ("卖家ID", "seller_id"), ("品牌链接", "brand_url"),
    ("商品链接", "product_url"), ("图片", "image_url"),
    ("利润₽", "profit"), ("评分增长", "ratings_rate"), ("原销量", "origin_sales"),
    # 阶段3：自建利润模型（POST /api/profit 计算后才有值，未算则为空）
    ("计费重kg", "chargeable_kg"), ("净利₽", "net_profit"), ("真毛利率%", "net_margin"),
    ("保本价₽", "breakeven"), ("建议售价₽", "suggested"), ("ROI%", "roi"),
    # 以下三项官方文档标注「已弃用」，实测返回 null；保留列以便平台恢复返回时直接可用
    ("类目排名(已弃用)", "category_rank"),
    ("自然排名(已弃用)", "natural_rank"), ("广告排名(已弃用)", "ad_rank"),
]
KEYWORD_COLUMNS = [
    ("关键词", "query"), ("中文", "query_cn"), ("月搜索量", "search_volume"),
    ("30天增长%", "growth30"), ("竞品数", "competing_products"), ("卖家数", "sellers"),
    ("均价₽", "avg_price"), ("转化份额%", "conversion_sharing"),
    ("市场空间", "market_space"), ("标题密度", "title_density"),
    ("相关度", "relevancy"), ("词数", "word_count"), ("类目", "categories_text"),
    ("机会分", "opportunity"),
]


def num(v, default=None):
    if v is None or v == "":
        return default
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _range(src: dict, key: str, lo_key=None, hi_key=None):
    lo = num(src.get(lo_key or key + "_min"))
    hi = num(src.get(hi_key or key + "_max"))
    if lo is None and hi is None:
        return None
    return {"min": lo, "max": hi}


def _page(page=1, size=20, field="revenue", direction="DESC", allowed=None):
    page, size = max(1, int(page or 1)), min(100, max(1, int(size or 20)))
    direction = "ASC" if str(direction).upper() == "ASC" else "DESC"
    if allowed and field not in allowed:
        field = "revenue" if "revenue" in allowed else sorted(allowed)[0]
    return {"pageNumber": page, "pageSize": size,
            "orders": [{"field": field, "direction": direction}]}


def _pages_of(f: dict, hard_max=10) -> int:
    """本次请求要抓多少页（1~10）。官方单页上限 100 条，多页会按页计费。"""
    try:
        n = int(f.get("pages") or 1)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(hard_max, n))


# 评论接口的分析语言是枚举 CN/EN/RU，不是语言代码（文档明确「不是 zh-CN 等语言代码」）
LANG_ENUM = {
    "cn": "CN", "zh": "CN", "zh-cn": "CN", "zh_cn": "CN", "chinese": "CN",
    "en": "EN", "en-us": "EN", "en_us": "EN", "english": "EN",
    "ru": "RU", "ru-ru": "RU", "ru_ru": "RU", "russian": "RU",
}


def lang_enum(v) -> str:
    return LANG_ENUM.get(str(v or "").strip().lower(), "CN")


def _sku_int(v):
    """评论接口要求 sku 为 integer（64 位内），这里做严格数字校验。"""
    s = str(v or "").strip()
    if not s.isdigit():
        raise ValueError(f"SKU 必须是纯数字：{v!r}")
    return int(s)


def _ids_list(v, limit=None) -> list[str]:
    """ID 列表参数：兼容数组、逗号串、单个值，去重保序。"""
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        items = [str(x).strip() for x in v]
    else:
        items = [x.strip() for x in re.split(r"[,，\s]+", str(v))]
    out = list(dict.fromkeys(x for x in items if x))
    return out[:limit] if limit else out


def _fmt_ts(v, fmt="%Y-%m-%d"):
    """毫秒时间戳 → 日期字符串（上架时间等）。"""
    f = num(v)
    if not f:
        return ""
    try:
        return datetime.fromtimestamp(f / 1000).strftime(fmt)
    except (ValueError, OSError, OverflowError):
        return ""


def norm_product(r: dict) -> dict:
    ci = r.get("categoryInfo") or {}
    cat = ci.get("category") or {}
    st = r.get("sellerType")
    labels = r.get("labels") or []
    label_map = {0: "新品", 1: "正品", 2: "畅销品"}
    return {
        "sku": str(r.get("sku") or ""),
        "title": r.get("title") or "",
        "brand": r.get("brandName") or "",
        "seller": r.get("sellerName") or "",
        "price": num(r.get("price")),
        "sales": num(r.get("sales") or r.get("monthlySales")),
        "revenue": num(r.get("revenue") or r.get("monthlyRevenue")),
        "sales_rate": num(r.get("salesRate")),
        "review_count": num(r.get("reviewCount")),
        "review_rating": num(r.get("reviewRating")),
        "gross_margin": num(r.get("grossMargin")),
        "drr": num(r.get("drr")),
        "conv_to_cart_pdp": num(r.get("convToCartPdp")),
        "views": num(r.get("views")),
        "variants": num(r.get("variants")),
        "weight": num(r.get("weight")),
        "volume": num(r.get("volume")),
        "dimension": r.get("dimension") or "",
        "up_days": num(r.get("upDays")),
        "up_time": num(r.get("upTime")),
        "up_time_date": _fmt_ts(r.get("upTime")),
        "category_id": cat.get("id") or (ci.get("fullCategoryId") or [None])[-1] or "",
        "category_cn": ci.get("cnTitlePath") or cat.get("cnTitle") or "",
        "cross_border": cat.get("crossBorderSellable"),
        "seller_type": st,
        "seller_type_text": {0: "本土", 1: "跨境"}.get(st, ""),
        "fulfillment_text": "&".join(r.get("fulfillment") or []),
        "labels_text": "、".join(label_map.get(x, str(x)) for x in labels),
        "product_url": r.get("productUrl") or "",
        "image_url": r.get("imageUrl") or "",
        # —— 以下为「查类目」productList 的完整运营/排名字段，之前漏掉了 ——
        "revenue_rate": num(r.get("revenueRate")),
        "profit": num(r.get("profit")),
        "ratings_rate": num(r.get("ratingsRate")),
        "origin_sales": num(r.get("originSales")),
        "qa": num(r.get("questionsAndAnswers")),
        "review_incr": num(r.get("reviewIncr")),
        "seller_id": r.get("sellerId"),
        "brand_id": r.get("brandId"),
        "brand_url": r.get("brandUrl") or "",
        "discount": num(r.get("discount")),
        "promo_revenue_share": num(r.get("promoRevenueShare")),
        "conv_to_cart_search": num(r.get("convToCartSearch")),
        "conv_view_to_order": num(r.get("convViewToOrder")),
        "order_conversion_rate": num(r.get("orderConversionRate")),
        "return_cancellation_rate": num(r.get("returnCancellationRate")),
        "session_count": num(r.get("sessionCount")),
        "session_count_search": num(r.get("sessionCountSearch")),
        "missed_revenue": num(r.get("missedRevenue")),
        "category_rank": num(r.get("categoryRank")),
        "natural_rank": num(r.get("naturalRank")),
        "ad_rank": num(r.get("adRank")),
        "up_months": num(r.get("upMonths")),
        "variation_ids": r.get("variationIds") or [],
        "variations_relation_id": r.get("variationsRelationId"),
        "raw": r,
    }


def norm_keyword(r: dict, kind="market") -> dict:
    cis = r.get("categoryInfos") or []
    cats = r.get("categories") or [c.get("id") for c in cis if isinstance(c, dict)]
    return {
        "id": str(r.get("id") or (kind + ":" + str(r.get("query") or ""))),
        "query": r.get("query") or "",
        "query_cn": r.get("queryCn") or "",
        "kind": kind,
        "search_volume": num(r.get("searchVolume")),
        "growth30": num(r.get("count30GrowthRate")),
        "competing_products": num(r.get("competingProducts")),
        "sellers": num(r.get("sellers")),
        "avg_price": num(r.get("avgPrice")),
        "conversion_sharing": num(r.get("conversionSharing")),
        "market_space": num(r.get("marketSpace")),
        "title_density": num(r.get("titleDensity")),
        "relevancy": num(r.get("relevancy")),
        "word_count": num(r.get("wordCount")),
        "categories": [str(x) for x in cats if x],
        "categories_text": "、".join(str(x) for x in cats if x),
        "raw": r,
    }


# 机会分默认权重与量纲（可在 config.json 的 opportunity 段覆盖）
OPP_DEFAULT = {
    "weights": {
        "keyword": {"demand": 35, "growth": 25, "low_comp": 25, "conv": 15},
        "product": {"sales": 35, "growth": 25, "low_comp": 25, "conv": 15},
    },
    "scales": {
        "keyword": {"search_volume": 1000000, "market_space": 1000,
                    "competing_products": 10000, "sellers": 2000,
                    "conversion_sharing": 100, "avg_price": 20000, "growth": 60},
        "product": {"sales": 10000, "revenue": 10000000, "review_count": 20000,
                    "variants": 50, "gross_margin": 100, "conv_to_cart_pdp": 50,
                    "growth": 80},
    },
}


def _merge_cfg(base, override):
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def opportunity(row: dict, kind="keyword", cfg=None) -> dict:
    """选品机会分（本系统自定义启发式，非 Seerfar 官方指标，0~100，逐项可解释）。

    权重与量纲可配置（config.json → opportunity），默认：
      商品：销量 35 + 增长 25 + 低竞争 25 + 毛利/转化 15
      关键词：需求 35 + 增长 25 + 低竞争 25 + 转化/空间 15
    全部对数压缩，避免头部爆款把分数拉爆；权重会自动归一到 100。
    """
    conf = _merge_cfg(OPP_DEFAULT, cfg or {})
    w = conf["weights"].get(kind) or conf["weights"]["product"]
    s = conf["scales"].get(kind) or conf["scales"]["product"]

    def lg(v, scale, cap=1.0):
        v = num(v, 0) or 0
        if v <= 0 or not scale:
            return 0.0
        return min(cap, math.log10(1 + v) / math.log10(1 + scale))

    total_w = sum(w.values()) or 1.0
    norm = 100.0 / total_w

    if kind == "keyword":
        demand = lg(row.get("search_volume"), s["search_volume"]) * 0.6 \
            + lg(row.get("market_space"), s["market_space"]) * 0.4
        growth = max(0.0, min(1.0, (num(row.get("growth30"), 0) or 0) / (s.get("growth") or 60.0)))
        comp = 1.0 - lg(row.get("competing_products"), s["competing_products"]) * 0.6 \
            - lg(row.get("sellers"), s["sellers"]) * 0.4
        conv = lg(row.get("conversion_sharing"), s["conversion_sharing"]) * 0.6 \
            + lg(row.get("avg_price"), s["avg_price"]) * 0.4
        parts = {"需求": round(demand * w["demand"] * norm, 1),
                 "增长": round(growth * w["growth"] * norm, 1),
                 "低竞争": round(max(0.0, comp) * w["low_comp"] * norm, 1),
                 "转化/空间": round(conv * w["conv"] * norm, 1)}
    else:
        demand = lg(row.get("sales"), s["sales"]) * 0.5 \
            + lg(row.get("revenue"), s["revenue"]) * 0.5
        growth = max(0.0, min(1.0, (num(row.get("sales_rate"), 0) or 0) / (s.get("growth") or 80.0)))
        comp = 1.0 - lg(row.get("review_count"), s["review_count"]) * 0.7 \
            - lg(row.get("variants"), s["variants"]) * 0.3
        conv = lg(row.get("gross_margin"), s["gross_margin"]) * 0.6 \
            + lg(row.get("conv_to_cart_pdp"), s["conv_to_cart_pdp"]) * 0.4
        parts = {"销量": round(demand * w["sales"] * norm, 1),
                 "增长": round(growth * w["growth"] * norm, 1),
                 "低竞争": round(max(0.0, comp) * w["low_comp"] * norm, 1),
                 "毛利/转化": round(conv * w["conv"] * norm, 1)}
    score = round(sum(parts.values()), 1)
    return {"score": score, "parts": parts}


def _extract_skus(v) -> list[str]:
    """商品ID / 商品链接 → SKU 列表。支持 https://www.ozon.ru/product/123456/ 直接粘贴。"""
    if isinstance(v, (list, tuple)):
        items = [str(x) for x in v]
    else:
        items = re.split(r"[,，\s\n]+", str(v or ""))
    out = []
    for s in items:
        s = s.strip()
        if not s:
            continue
        m = re.search(r"(\d{6,})", s)
        if m:
            out.append(m.group(1))
    return list(dict.fromkeys(out))[:10]   # 官方限制最多 10 个


class Selector:
    def __init__(self, client: SeerfarClient | None = None, store=None, catalog=None):
        self.c = client or get_client()
        self.db = store or STORE
        self.catalog = catalog
        self.opp_cfg = (self.c.cfg or {}).get("opportunity") if hasattr(self.c, "cfg") else None
        if self.catalog:
            self.catalog.attach(self.c)

    # ---------- 在线选品主查询（查热销榜单） ----------
    def top(self, f: dict | None = None, *, force=False) -> dict:
        """把「在线选品」筛选面板的全部条件翻译成官方 Body 参数。

        官方不支持的条件（BSR / 库存 / 评论率 / 跟卖 / 店铺类型 …）不编造字段，
        能做的放结果侧本地过滤，其余在界面上明确禁用并说明原因。
        """
        f = f or {}
        body = {
            "page": _page(f.get("page"), f.get("size"), f.get("sort") or "revenue",
                          f.get("direction") or "DESC", SORT_FIELDS["top"]),
            "variationsMerge": int(f.get("variations_merge") or 0),
            "filterRemoveProduct": False if f.get("include_removed") else True,
        }
        # 官方区间参数：公共 14 组 + 榜单额外的卖家数 / 评分增长
        for k in COMMON_RANGES + ["sellers", "ratingsRate"]:
            v = _range(f, k)
            if v:
                body[k] = v

        def as_list(v):
            if isinstance(v, (list, tuple)):
                return [str(x).strip() for x in v if str(x).strip()]
            return [x.strip() for x in re.split(r"[,，\n]+", str(v or "")) if x.strip()]

        ids = f.get("category_ids") or ([f["category_id"]] if f.get("category_id") else [])
        if ids:
            body["categoryIds"] = [str(x) for x in ids if x][:20]
        if f.get("keywords") or f.get("keyword"):
            body["keywords"] = as_list(f.get("keywords") or f.get("keyword"))
        seller = f.get("seller_names") or f.get("seller_name")
        if seller:
            body["sellerName"] = as_list(seller)
        brands = as_list(f.get("brands") or f.get("brand") or "")
        btype = f.get("brand_type")
        if brands or btype not in (None, ""):
            body["brand"] = {"type": int(btype or 0), "brandName": brands}
        if f.get("fulfillment"):
            v = f["fulfillment"]
            body["fulfillment"] = (list(v) if isinstance(v, (list, tuple))
                                   else as_list(v))
        if f.get("labels") not in (None, "", []):
            body["labels"] = [int(x) for x in as_list(f["labels"])]
        if f.get("creation_date") not in (None, "", 0):
            body["creationDate"] = int(f["creation_date"])
        if f.get("search_date"):
            body["searchDate"] = f["search_date"]
        skus = _extract_skus(f.get("skus") or f.get("product_ids") or "")
        if skus:
            body["skus"] = skus
        if f.get("tag"):
            body["tag"] = str(f["tag"])

        # —— 多页抓取（pages>1 时逐页请求；命中缓存不重复扣费）——
        want_pages = _pages_of(f)
        rows, cost, fetched, d, res = [], 0.0, 0, {}, None
        for pno in range(1, want_pages + 1):
            body["page"]["pageNumber"] = pno
            res = self.c.call("top", body, force=force)
            d = res.data or {}
            recs = d.get("records") or []
            cost += res.cost
            fetched = pno
            rows.extend(norm_product(r) for r in recs if isinstance(r, dict))
            total_pages = int(d.get("totalPages") or 1)
            if pno >= total_pages or not recs:
                break

        # —— 结果侧本地过滤：官方没有对应筛选参数，但响应里有该字段 ——
        # 注意：这里只作用于「本次已抓取的行」，不是全站。返回 local_filter 让前端如实提示。
        def keep(r):
            st = f.get("seller_type")
            if st not in (None, "", "all") and r.get("seller_type") is not None:
                if int(r["seller_type"]) != int(st):
                    return False
            cb = str(f.get("cross_border", "")).lower()
            if cb in ("1", "true", "yes") and r.get("cross_border") is False:
                return False
            if cb in ("0", "false", "no") and r.get("cross_border") is True:
                return False
            t0, t1 = f.get("up_time_from"), f.get("up_time_to")
            up = r.get("up_time")
            if up and t0 and float(up) < float(t0):
                return False
            if up and t1 and float(up) > float(t1):
                return False
            return True

        before = len(rows)
        rows = [r for r in rows if keep(r)]
        filtered_out = before - len(rows)
        for r in rows:
            o = opportunity(r, "product", self.opp_cfg)
            r["opportunity"] = o["score"]
            r["opportunity_parts"] = o["parts"]
        self.db.upsert_products(rows)
        # 哪些条件是「本地过滤」（官方无对应参数），供前端如实标注作用范围
        local_fields = []
        if str(f.get("seller_type") or "").strip() not in ("", "all"):
            local_fields.append("店铺类型")
        if str(f.get("cross_border") or "").strip() not in ("", "all"):
            local_fields.append("跨境可售")
        if f.get("up_time_from") or f.get("up_time_to"):
            local_fields.append("上架日期区间")
        scope = f"本页（{fetched} 页合计 {before} 行）"
        return {"rows": rows, "total": d.get("total"), "page": d.get("current"),
                "pages": d.get("totalPages"), "cached": res.cached if res else False,
                "cost": round(cost, 1), "filtered_out": filtered_out,
                "fetched_pages": fetched,
                "local_filter": {"fields": local_fields, "filtered_out": filtered_out,
                                 "scope": scope, "before": before},
                "applied": {k: v for k, v in body.items() if k not in ("page",)},
                "time_interval": d.get("timeInterval"), "raw": d}

    # ---------- 类目大盘 ----------
    def category(self, category_id: str, f: dict | None = None, *, force=False) -> dict:
        f = f or {}
        body = {
            "categoryId": str(category_id),
            "page": _page(f.get("page"), f.get("size"), f.get("sort") or "revenue",
                          f.get("direction") or "DESC", SORT_FIELDS["category"]),
            "filterRemoveProduct": True,
        }
        for k in COMMON_RANGES:
            v = _range(f, k)
            if v:
                body[k] = v
        # —— 以下严格对齐官方「Ozon 查类目」Body 参数表 ——
        if f.get("date"):
            body["date"] = f["date"]      # 历史月份 yyyy-MM，仅近 1 年；近 30 天不传
        # keywords / sellerName / skus / labels 都接受「逗号分隔字符串」或数组
        def as_list(v):
            if isinstance(v, (list, tuple)):
                return [str(x).strip() for x in v if str(x).strip()]
            return [x.strip() for x in str(v).split(",") if x.strip()]
        if f.get("keywords") or f.get("keyword"):
            body["keywords"] = as_list(f.get("keywords") or f.get("keyword"))
        seller = f.get("seller_names") or f.get("seller_name") or f.get("sellers")
        if seller:
            body["sellerName"] = as_list(seller)
        if f.get("skus"):
            body["skus"] = [str(x).strip() for x in as_list(f["skus"])][:10]
        if f.get("tag"):
            body["tag"] = str(f["tag"])
        if f.get("fulfillment"):
            # 注意：查类目接口这里是「字符串」，查热销榜单是数组，不能混用
            v = f["fulfillment"]
            body["fulfillment"] = v if isinstance(v, str) else (v[0] if v else "")
        if f.get("labels") not in (None, "", []):
            body["labels"] = [int(x) for x in as_list(f["labels"])]
        if f.get("creation_date") not in (None, "", 0):
            body["creationDate"] = int(f["creation_date"])
        # brand.type：0 包含 / 1 排除 / 2 无品牌；type=2 时不需要 brandName
        btype = f.get("brand_type")
        brands = as_list(f.get("brands") or f.get("brand") or "")
        if brands or btype not in (None, ""):
            body["brand"] = {"type": int(btype or 0), "brandName": brands}

        # —— 多页抓取：该接口用 hasNextPage 表示还有没有下一页 ——
        want_pages = _pages_of(f)
        rows, cost, fetched, d, res = [], 0.0, 0, {}, None
        for pno in range(1, want_pages + 1):
            body["page"]["pageNumber"] = pno
            res = self.c.call("category", body, force=force)
            d = res.data or {}
            cost += res.cost
            fetched = pno
            # 注意：查类目接口的 data.products 是「商品总数」整数，商品数组只在 productList。
            # 查店铺接口的 data.products 才是数组，两者不能混用。
            records = d.get("productList") or []
            if not isinstance(records, list):
                records = []
            rows.extend(norm_product(r) for r in records if isinstance(r, dict))
            if not records or not d.get("hasNextPage"):
                break
        for r in rows:
            r["opportunity"] = opportunity(r, "product", self.opp_cfg)["score"]
        self.db.upsert_products(rows)
        overview = {
            "id": d.get("id"), "rating": d.get("rating"),
            "total_revenue": d.get("totalRevenue"), "total_sales": d.get("totalSales"),
            "avg_price": d.get("avgPrice"), "seller_type": d.get("sellerType"),
            "products": d.get("products"), "start_date": d.get("startDate"),
            "end_date": d.get("endDate"),
            "seasonality_amplitude": d.get("seasonalityAmplitude"),
            "seasonality_coef": d.get("seasonalityCoef"),
            "category_library_name": d.get("categoryLibraryName"),
            "cn_path": (d.get("categoryInfo") or {}).get("cnTitlePath") or "",
            "has_next_page": d.get("hasNextPage"),
        }
        # 实测：一级/二级类目接口只给大盘汇总，productList 为空；三级类目才有商品清单。
        # 把该节点下的三级子类目一并返回，前端可直接下拉切换，不再让界面停在空表。
        hint, leaves = "", []
        if len(str(category_id).split("_")) < 3:
            leaves = [
                {"id": r["id"], "cn": r["cn"] or r["id"], "named": bool(r["cn"]),
                 "cn_path": r["cn_path"] or ""}
                for r in self.db.q(
                    "SELECT id, cn, ru, cn_path FROM category WHERE level=3 "
                    "AND substr(id,1,length(?)+1)=?||'_' ORDER BY cn, id LIMIT 200",
                    (str(category_id), str(category_id)))
            ]
            if not rows:
                hint = (f"该类目是汇总层级，官方只返回大盘指标；已找到其下 {len(leaves)} 个"
                        f"三级子类目，在上方下拉里选一个即可查看商品清单、销量与排名。")
        return {"overview": overview, "rows": rows, "cached": res.cached if res else False,
                "cost": round(cost, 1), "fetched_pages": fetched,
                "has_next_page": d.get("hasNextPage"),
                "hint": hint, "leaves": leaves, "raw": d}

    # ---------- 关键词三条线 ----------
    def _keyword_call(self, name, body, kind, force=False, pages=1):
        rows, cost, fetched, d, res = [], 0.0, 0, {}, None
        for pno in range(1, pages + 1):
            body["page"]["pageNumber"] = pno
            res = self.c.call(name, body, force=force)
            d = res.data or {}
            cost += res.cost
            fetched = pno
            recs = d.get("records") or []
            rows.extend(norm_keyword(r, kind) for r in recs)
            total_pages = int(d.get("totalPages") or 1)
            if pno >= total_pages or not recs:
                break
        for r in rows:
            r["opportunity"] = opportunity(r, "keyword", self.opp_cfg)["score"]
        self.db.upsert_keywords(rows, kind)
        return {"rows": rows, "total": d.get("total"), "page": d.get("current"),
                "pages": d.get("totalPages"), "cached": res.cached if res else False,
                "cost": round(cost, 1), "fetched_pages": fetched}

    def hot_words(self, f: dict | None = None, *, force=False) -> dict:
        f = f or {}
        body = {"page": _page(f.get("page"), f.get("size"),
                             f.get("sort") or "searchVolume",
                             f.get("direction") or "DESC", SORT_FIELDS["market"]),
                "matchType": int(f.get("match_type") or 0)}
        for k in MARKET_RANGES:
            v = _range(f, k)
            if v:
                body[k] = v
        cats = _ids_list(f.get("categories") or f.get("category_ids") or f.get("category_id"))
        if cats:
            body["categories"] = cats[:20]
        if f.get("keywords"):
            body["keywords"] = list(f["keywords"])
        elif f.get("keyword"):
            body["keywords"] = [f["keyword"]]
        if f.get("search_date"):
            body["searchDate"] = f["search_date"]
        return self._keyword_call("market", body, "market", force, _pages_of(f))

    def mining(self, keyword: str, f: dict | None = None, *, force=False) -> dict:
        f = f or {}
        body = {"keyword": str(keyword),
                "page": _page(f.get("page"), f.get("size"),
                             f.get("sort") or "relevancy",
                             f.get("direction") or "DESC", SORT_FIELDS["mining"]),
                "matchType": int(f.get("match_type") or 0)}
        for k in MINING_RANGES:
            v = _range(f, k)
            if v:
                body[k] = v
        for k in ("include_keywords", "exclude_keywords"):
            if f.get(k):
                body["includeKeywords" if k == "include_keywords" else "excludeKeywords"] = list(f[k])
        return self._keyword_call("mining", body, "mining", force, _pages_of(f))

    def backsearch(self, sku_ids, f: dict | None = None, *, force=False) -> dict:
        f = f or {}
        ids = _ids_list(sku_ids)
        if not ids:
            raise ValueError("关键词反查至少需要 1 个竞品 SKU")
        if len(ids) > 20:
            raise ValueError(f"关键词反查单次最多 20 个 SKU，当前传入 {len(ids)} 个")
        body = {"skuIds": ids,
                "hasVariant": int(f.get("has_variant") or 0),
                "page": _page(f.get("page"), f.get("size"),
                             f.get("sort") or "exposure",
                             f.get("direction") or "DESC", SORT_FIELDS["backsearch"]),
                "matchType": int(f.get("match_type") or 0)}
        # 文档：type 传字符串数组，0=自然搜索词 1=广告搜索词，不传则不筛选
        types = _ids_list(f.get("types") or f.get("type"))
        if types:
            body["type"] = [str(x) for x in types if str(x) in ("0", "1")][:2]
            if not body["type"]:
                body.pop("type")
        for k in ("uniqQueriesWCa", "ca", "searchVolume", "searchChange30",
                  "naturalRank", "adRank", "titleDensity", "wordCount", "products",
                  "adRivalCount", "productViews", "conversionSharing", "sellers",
                  "exposure", "conversion", "marketSpace"):
            v = _range(f, k)
            if v:
                body[k] = v
        for k in ("include_keywords", "exclude_keywords"):
            if f.get(k):
                body["includeKeywords" if k == "include_keywords" else "excludeKeywords"] = list(f[k])
        r = self._keyword_call("backsearch", body, "backsearch", force, _pages_of(f))
        r["sku_ids"] = ids
        return r

    # ---------- 商品 / 变体 / 店铺 ----------
    def product(self, sku: str, date_range="past_30_days", *, with_trend=True,
                with_similar=False, force=False) -> dict:
        res = self.c.call("product", {"sku": str(sku), "dateRange": date_range}, force=force)
        d = res.data or {}
        p = norm_product(d.get("product") or {})
        p["stock"] = num(d.get("stock"))
        p["total_sales"] = num(d.get("totalSales"))
        p["total_revenue"] = num(d.get("totalRevenue"))
        p["daily_sales"] = num(d.get("dailySales"))
        self.db.upsert_products([p])
        self.db.snapshot(sku, {"price": p["price"], "sales": p["total_sales"],
                               "revenue": p["total_revenue"],
                               "review_count": p["review_count"],
                               "review_rating": p["review_rating"], "stock": p["stock"]})
        out = {"product": p, "summary": {
            "total_sales": d.get("totalSales"), "total_revenue": d.get("totalRevenue"),
            "daily_sales": d.get("dailySales"), "stock": d.get("stock"),
            "start_date": d.get("startDate"), "end_date": d.get("endDate")},
            "ranks": d.get("categoryRanks") or [],
            "trend": d.get("salesTrendVOList") or [],
            "cached": res.cached, "cost": res.cost}
        if with_trend:
            try:
                t = self.c.call("monthly_trend", {"sku": str(sku)}, force=force)
                out["monthly"] = t.data or []
                out["cost"] += t.cost
            except Exception as e:
                out["monthly_error"] = str(e)
        if with_similar:
            try:
                s = self.c.call("similar", {"sku": int(sku)}, force=force)
                out["similar"] = [norm_product(x) for x in (s.data or [])]
                out["cost"] += s.cost
            except Exception as e:
                out["similar_error"] = str(e)
        return out

    def similar(self, sku, *, force=False):
        """相似商品（单次约 10 积分），单独成接口，方便做竞品对比。"""
        r = self.c.call("similar", {"sku": _sku_int(sku)}, force=force)
        rows = []
        for x in (r.data or []):
            p = norm_product(x)
            p["stock"] = num(x.get("stock"))     # 相似商品列表额外带库存
            rows.append(p)
        return {"rows": rows, "cached": r.cached, "cost": r.cost}

    def variations(self, sku, page=1, size=50):
        r = self.c.call("var_search", {"sku": _sku_int(sku),
                                       "page": _page(page, size, "revenue", "DESC",
                                                     SORT_FIELDS["var_search"]),
                                       "clientLanguage": "zh-CN"})
        d = r.data or {}
        recs = d.get("records") or []
        rows = [norm_product(x) for x in recs]
        # 变体特征值（颜色:Черный 等）单独拼一列，norm_product 不包含该字段
        for src, row in zip(recs, rows):
            chars = src.get("characteristics") or []
            row["variation_text"] = " · ".join(
                f"{c.get('name') or c.get('sourceName')}:{c.get('value')}"
                for c in chars if c.get("value"))
        return {"rows": rows, "total": d.get("total"), "pages": d.get("totalPages"),
                "cached": r.cached, "cost": r.cost}

    def var_characteristics(self, sku):
        r = self.c.call("var_chars", {"sku": _sku_int(sku), "clientLanguage": "zh-CN"})
        return {"rows": r.data or [], "cached": r.cached, "cost": r.cost}

    def var_top(self, sku, characteristic):
        r = self.c.call("var_top", {"sku": _sku_int(sku), "characteristic": characteristic,
                                    "clientLanguage": "zh-CN"})
        d = r.data or {}
        return {"revenues": d.get("revenues") or [], "sales": d.get("sales") or {},
                "rows": d, "cached": r.cached, "cost": r.cost}

    def shop(self, shop_id, f=None, *, force=False):
        f = f or {}
        body = {"id": int(shop_id),
                "filterRemoveProduct": False if f.get("include_removed") else True,
                "page": _page(f.get("page"), f.get("size"), f.get("sort") or "revenue",
                              f.get("direction") or "DESC", SORT_FIELDS["top"])}
        for k in COMMON_RANGES:
            v = _range(f, k)
            if v:
                body[k] = v
        # —— 严格对齐官方「Ozon 查店铺」Body 参数表（之前界面有、后端没发）——
        if f.get("category_ids"):
            body["categoryIds"] = _ids_list(f["category_ids"])[:20]
        if f.get("skus"):
            body["skus"] = _ids_list(f["skus"])[:10]
        if f.get("keywords"):
            body["keywords"] = _ids_list(f["keywords"])
        if f.get("tag"):
            body["tag"] = str(f["tag"])
        if f.get("fulfillment"):
            # 查店铺接口这里与榜单一致，是「数组」
            body["fulfillment"] = _ids_list(f["fulfillment"])
        if f.get("labels") not in (None, "", []):
            body["labels"] = [int(x) for x in _ids_list(f["labels"]) if str(x).isdigit()]
        if f.get("creation_date") not in (None, "", 0):
            body["creationDate"] = int(f["creation_date"])
        brands = _ids_list(f.get("brands") or f.get("brand"))
        btype = f.get("brand_type")
        if brands or btype not in (None, ""):
            body["brand"] = {"type": int(btype or 0), "brandName": brands}

        want_pages = _pages_of(f)
        rows, cost, fetched, d, r = [], 0.0, 0, {}, None
        for pno in range(1, want_pages + 1):
            body["page"]["pageNumber"] = pno
            r = self.c.call("shop", body, force=force)
            d = r.data or {}
            cost += r.cost
            fetched = pno
            prods = d.get("products") or []
            rows.extend(norm_product(x) for x in prods)
            if not prods or not d.get("hasNextPage"):
                break
        for x in rows:
            x["opportunity"] = opportunity(x, "product", self.opp_cfg)["score"]
        self.db.upsert_products(rows)
        self.db.upsert_shop({"id": str(shop_id), "name": "",
                             "rating": d.get("rating"),
                             "product_count": d.get("productCount"),
                             "total_sales": d.get("totalSales"),
                             "total_revenue": d.get("totalRevenue"), "raw": dumps(d)})
        return {"summary": {k: d.get(k) for k in
                            ("productCount", "rating", "totalRevenue", "totalSales",
                             "dailySales", "fulfillment", "hasNextPage")},
                "rows": rows, "cached": r.cached if r else False,
                "cost": round(cost, 1), "fetched_pages": fetched,
                "has_next_page": d.get("hasNextPage"),
                "applied": {k: v for k, v in body.items() if k != "page"}}

    def shop_brands(self, shop_id, page=1, size=20, *, force=False):
        """店铺品牌结构：品牌 Top 榜 + 销售额/销量占比（官方 conversionSharing 是 Top10/Top100）。"""
        r = self.c.call("shop_brand", {"id": int(shop_id),
                                       "page": {"pageNumber": int(page or 1),
                                                "pageSize": min(100, int(size or 20))}},
                        force=force)
        d = r.data or {}
        box = d.get("brands") or {}
        recs = box.get("records") or []
        rows = []
        for x in recs:
            bi = x.get("brandInfo") or {}
            rows.append({
                "name": bi.get("brandName") or "",
                "brand_id": bi.get("brandId") or x.get("id"),
                "thumb": bi.get("thumbnailUrl") or "",
                "revenue": num(x.get("totalRevenues") if x.get("totalRevenues") is not None
                               else x.get("totalRevenue")),
                "sales": num(x.get("totalSales")),
                "revenue_rate": num(x.get("revenueRate")),
                "sales_rate": num(x.get("salesRate")),
                "products": num(x.get("products")),
                "products_with_sales": num(x.get("productsWithSales")),
                "avg_price": num(x.get("avgPrice")),
                "avg_revenue": num(x.get("avgRevenue")),
                "avg_sales": num(x.get("avgSales")),
                "avg_rating": num(x.get("avgRating")),
                "avg_reviews": num(x.get("avgReviewCount")),
                "sellers": num(x.get("sellers")),
                "sharing": num(x.get("conversionSharing")),
                "return_rate": num(x.get("returnCancellationRate")),
            })
        total_rev = sum(r["revenue"] or 0 for r in rows) or 0
        for x in rows:
            x["page_share"] = round((x["revenue"] or 0) / total_rev * 100, 2) if total_rev else None
        top = d.get("top") or {}
        return {"rows": rows, "top": {
                    "total": num(top.get("total")),
                    "total_revenue": num(top.get("totalRevenue")),
                    "total_sales": num(top.get("totalSales")),
                    "revenue_share_top10": num(top.get("revenueShareTop10")),
                    "sales_share_top10": num(top.get("salesShareTop10")),
                    "revenues": top.get("revenues") or [],
                    "sales": top.get("sales") or []},
                "total": num(box.get("total")), "pages": num(box.get("totalPages")),
                "page": num(box.get("current")),
                "cached": r.cached, "cost": r.cost}

    def shop_categories(self, shop_id, page=1, size=20, *, force=False):
        """店铺类目结构：该类目下的销售额/销量/商品数/均价。"""
        r = self.c.call("shop_category", {"id": int(shop_id),
                                          "page": {"pageNumber": int(page or 1),
                                                   "pageSize": min(100, int(size or 20))}},
                        force=force)
        d = r.data or {}
        box = d.get("categories") or {}
        rows = []
        for x in box.get("records") or []:
            ci = x.get("categoryInfo") or {}
            cat = ci.get("category") or {}
            rows.append({
                "category_id": cat.get("id") or x.get("id") or "",
                "cn": cat.get("cnTitle") or "",
                "ru": cat.get("title") or "",
                "cn_path": ci.get("cnTitlePath") or cat.get("cnTitle") or "",
                "revenue": num(x.get("totalRevenues")),
                "sales": num(x.get("totalSales")),
                "revenue_rate": num(x.get("revenueRate")),
                "sales_rate": num(x.get("salesRate")),
                "products": num(x.get("products")),
                "avg_price": num(x.get("avgPrice")),
            })
        total_rev = sum(x["revenue"] or 0 for x in rows) or 0
        for x in rows:
            x["page_share"] = round((x["revenue"] or 0) / total_rev * 100, 2) if total_rev else None
        top = d.get("top") or {}
        return {"rows": rows, "top": {"revenues": top.get("revenues") or [],
                                      "sales": top.get("sales") or []},
                "total": num(box.get("total")), "pages": num(box.get("totalPages")),
                "page": num(box.get("current")),
                "cached": r.cached, "cost": r.cost}

    # ---------- 评论（只读；任务创建必须显式确认） ----------
    def review_stat(self, sku):
        r = self.c.call("review_stat", {"sku": str(sku)})
        d = r.data or {}
        st = d.get("reviewStatistic") or {}
        return {"rows": d, "statistic": st, "sku": d.get("sku") or str(sku),
                "title": d.get("title"), "image_url": d.get("imageUrl"),
                "cached": r.cached, "cost": r.cost}

    def review_original(self, sku):
        r = self.c.call("review_original", {"sku": str(sku)})
        d = r.data or {}
        return {"rows": d.get("reviews") or [], "skus": d.get("skus") or [],
                "cached": r.cached, "cost": r.cost}

    def review_words(self, sku, language="CN"):
        # 文档：sku 为 integer；language 为枚举 CN/EN/RU（不是 zh-CN）
        r = self.c.call("review_words", {"sku": _sku_int(sku), "language": lang_enum(language)})
        d = r.data or {}
        return {"rows": d, "origin": d.get("origin") or [],
                "sinicized": d.get("sinicized") or [],
                "language": lang_enum(language), "cached": r.cached, "cost": r.cost}

    def review_report(self, sku, language="CN"):
        r = self.c.call("review_report", {"sku": _sku_int(sku), "language": lang_enum(language)})
        d = r.data or {}
        return {"rows": d, "language": lang_enum(language),
                "cached": r.cached, "cost": r.cost}

    def review_task(self, skus, *, confirm=False):
        """创建评论分析任务：官方单价 200 积分/SKU，默认拒绝，必须 confirm=True。"""
        if not confirm:
            raise ValueError("创建评论分析任务会按 200 积分/SKU 扣费，必须显式确认")
        r = self.c.call("review_task", {"skus": [str(x) for x in skus]}, confirm=True)
        return {"rows": r.data or {}, "cached": r.cached, "cost": r.cost}


    # ---------- 利润（阶段3）----------
    def profit(self, rows, params=None, *, persist=True):
        from sf_profit import enrich
        out, summary = enrich(rows, params or {})
        if persist:
            try:
                self.db.update_profit(out)
            except Exception:
                pass
        return {"rows": out, "summary": summary}

    # ---------- 收藏 ----------
    def favorite_toggle(self, sku, tags="", note=""):
        if not str(sku or "").strip():
            raise ValueError("缺少 sku")
        return self.db.favorite_toggle(str(sku).strip(), tags, note)


def get_selector(client=None, catalog=None) -> Selector:
    return Selector(client, catalog=catalog)
