"""Ozon 商品详情（PDP）全字段解析。

字段口径参考 marketninja 插件的列定义，映射到 composer-api 的 PDP JSON：
  - 主数据来自 /product/{sku}/
  - 描述与完整属性来自 /product/{sku}/?layout_container=pdpPage2column&layout_page_index=2
"""
from __future__ import annotations

import json
import re


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = re.sub(r"[^\d.,\-]", "", str(v).replace("\u2009", "").replace("\u202f", "").replace(" ", ""))
    s = s.replace(",", ".")
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except Exception:
        return None


def _text(node):
    """递归取所有 text/content 字段拼起来"""
    out = []

    def walk(n):
        if isinstance(n, str):
            return
        if isinstance(n, dict):
            if isinstance(n.get("text"), str):
                out.append(n["text"])
            if isinstance(n.get("content"), str):
                out.append(n["content"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return out


def _widgets(payload):
    ws = (payload or {}).get("widgetStates") or {}
    out = {}
    for k, v in ws.items():
        try:
            out[k] = json.loads(v) if isinstance(v, str) else v
        except Exception:
            continue
    return out


def _first(widgets, prefix):
    for k, v in widgets.items():
        if k.startswith(prefix):
            return v
    return None


def _find_with(widgets, key):
    """找第一个包含某字段的 widget"""
    for k, v in widgets.items():
        if isinstance(v, dict) and key in v:
            return v
    return None


def _norm_attr_key(name):
    n = (name or "").lower().replace("ё", "е")
    if "вес" in n:
        return "weight"
    if "длина" in n:
        return "length"
    if "ширина" in n:
        return "width"
    if "высота" in n:
        return "height"
    if "глубина" in n:
        return "depth"
    if "страна" in n:
        return "country"
    if "бренд" in n or "торговая марка" in n:
        return "brand"
    return None


def parse_full(main, page2):
    w1 = _widgets(main)
    w2 = _widgets(page2)

    rec = {
        "sku": None, "offer_code": None, "brand": None, "name": None, "category": None,
        "special_price": None, "price": None, "original_price": None, "discount": None,
        "seller": None, "seller_id": None, "seller_rating": None, "seller_reviews": None,
        "seller_age": None, "seller_company": None, "seller_psrn": None, "seller_address": None,
        "honest_sign": None, "seller_url": None,
        "rating": None, "reviews": None, "questions": None, "stock": None,
        "image_count": None, "thumbnail": None, "gallery": None,
        "url": None, "description": None, "rich_description": None,
        "country": None, "length": None, "width": None, "height": None,
        "depth": None, "weight": None, "attributes": [],
    }

    # ---- 映像 / SKU ----
    g = _first(w1, "webGallery")
    if isinstance(g, dict):
        rec["sku"] = str(g.get("sku") or "")
        imgs = [i.get("src") for i in (g.get("images") or []) if i.get("src")]
        rec["gallery"] = ";".join(imgs)
        rec["image_count"] = len(imgs)
        rec["thumbnail"] = g.get("coverImage") or (imgs[0] if imgs else None)

    lt = (main or {}).get("layoutTrackingInfo") or {}
    if not rec["sku"] and lt.get("sku"):
        rec["sku"] = str(lt["sku"])

    # ---- 标题 ----
    h = _first(w1, "webProductHeading")
    if isinstance(h, dict):
        rec["name"] = h.get("title")

    # ---- 类目 / 品牌（面包屑最后一段常是品牌）----
    bc = _first(w1, "breadCrumbs")
    if isinstance(bc, dict):
        crumbs = bc.get("breadcrumbs") or []
        names = [c.get("text") for c in crumbs if c.get("text")]
        brand_crumb = None
        for c in crumbs:
            link = c.get("link") or ""
            if "/brand/" in link:
                brand_crumb = c.get("text")
            elif re.match(r"^/category/[^/]+/[^/]+/$", link):
                # 形如 /category/strubtsiny-9934/vira-7013891/ —— 末段是品牌
                brand_crumb = c.get("text")
        if brand_crumb:
            names = [n for n in names if n != brand_crumb]
            rec["brand"] = brand_crumb
        rec["category"] = " / ".join(names)

    # ---- 价格 ----
    wp = _first(w1, "webPrice")
    if isinstance(wp, dict):
        rec["special_price"] = _num(wp.get("cardPrice"))
        rec["price"] = _num(wp.get("price"))
        rec["original_price"] = _num(wp.get("originalPrice"))
    if rec["original_price"] and rec["special_price"]:
        rec["discount"] = round(100 * (1 - rec["special_price"] / rec["original_price"]))
    elif rec["original_price"] and rec["price"]:
        rec["discount"] = round(100 * (1 - rec["price"] / rec["original_price"]))

    # ---- 评分 / 评价 / 提问 ----
    rs = _first(w1, "webReviewProductScore")
    if isinstance(rs, dict):
        rec["rating"] = rs.get("totalScore")
        rec["reviews"] = rs.get("reviewsCount")
    q = _first(w1, "webQuestionCount")
    if isinstance(q, dict):
        rec["questions"] = _num(q.get("text"))

    # ---- 库存 ----
    bp = _first(w1, "bigPromoPDP")
    if isinstance(bp, dict):
        sn = bp.get("stockNumber")
        if isinstance(sn, dict):
            rec["stock"] = _num(sn.get("text"))

    # ---- 卖家 ----
    sp = _first(w1, "webStickyProducts")
    if isinstance(sp, dict):
        s = sp.get("seller") or {}
        rec["seller"] = (s.get("name") or "").strip() or None
        rec["seller_url"] = s.get("link")

    cs = _first(w1, "webCurrentSeller")
    if isinstance(cs, dict):
        cell = cs.get("sellerCell") or {}
        center = (cell.get("centerBlock") or {}).get("title")
        if isinstance(center, dict) and center.get("text"):
            rec["seller"] = rec["seller"] or center["text"].strip()
        rec["seller_url"] = rec["seller_url"] or (cell.get("common") or {}).get("action", {}).get("link")
        badge = ((cs.get("header") or {}).get("badge") or {})
        sid = (((badge.get("subscribed") or {}).get("common") or {}).get("action") or {}).get("params", {}).get("sellerId")
        rec["seller_id"] = _num(sid)
        rt = cs.get("rating")
        if isinstance(rt, dict):
            rec["seller_rating"] = _num((rt.get("title") or {}).get("text"))
        ch = cs.get("chat")
        if isinstance(ch, dict):
            ph = ch.get("placeholderValue")
            if isinstance(ph, str):
                m = re.search(r"(?:артикул|code is)\s*([^.\s]+)", ph, re.I)
                if m:
                    rec["offer_code"] = m.group(1).strip().rstrip(".")

        # trustFactors：订单数 / 关于店铺（公司名、地址、ОГРН、诚信标志）
        tfs = cs.get("trustFactors")
        if isinstance(tfs, list):
            for tf in tfs:
                title = ((tf.get("title") or {}).get("text") or "").strip()
                badge_txt = ((tf.get("badge") or {}).get("text") or "").strip()
                subs = ((tf.get("tooltip") or {}).get("subtitle") or [])
                sub_texts = [x.get("content") for x in subs if isinstance(x, dict) and isinstance(x.get("content"), str)]
                joined = " ".join(t for t in sub_texts if t)
                if title.lower().startswith("заказ"):
                    rec["seller_reviews"] = badge_txt or None
                if "магазин" in title.lower() or "продавц" in title.lower():
                    if sub_texts:
                        rec["seller_company"] = sub_texts[0].strip() or None
                    m = re.search(r"\b(\d{13}|\d{15})\b", joined)
                    if m:
                        rec["seller_psrn"] = m.group(1)
                    # 地址：优先含「Адрес」的那条，其次像地址的（г./обл/ул/д.），最后退到第 2 条
                    addr = None
                    for t in sub_texts:
                        if re.search(r"адрес", t, re.I):
                            addr = re.sub(r"^[^:]*:\s*", "", t).strip()
                            break
                    if not addr:
                        for t in sub_texts[1:]:
                            if re.search(r"(^|\s)(г\.|обл|ул|д\.|пр-т|шоссе|район)", t, re.I):
                                addr = t.strip()
                                break
                    if addr:
                        rec["seller_address"] = addr
                    if sub_texts:
                        low = joined.lower()
                        if any(k in low for k in ("проверен", "verified", "знак", "довер")):
                            rec["honest_sign"] = "是"
            if rec["honest_sign"] is None and rec.get("seller_id"):
                rec["honest_sign"] = "否"

    # ---- 描述（page2）----
    wd = _first(w2, "webDescription") or _first(w1, "webDescription")
    if isinstance(wd, dict):
        ra = wd.get("richAnnotation")
        if isinstance(ra, str):
            rec["description"] = re.sub(r"<[^>]+>", " ", ra).replace("&nbsp;", " ").strip()
            rec["rich_description"] = ra if "<" in ra else None
        rj = wd.get("richAnnotationJson")
        if rj and not rec["rich_description"]:
            rec["rich_description"] = json.dumps(rj, ensure_ascii=False)

    # ---- 完整属性（page2）----
    ch = _first(w2, "webCharacteristics") or _first(w1, "webCharacteristics")
    attrs = []
    if isinstance(ch, dict):
        for grp in ch.get("characteristics") or []:
            if not isinstance(grp, dict):
                continue
            for arr_key in ("short", "full", "items", "list"):
                for it in grp.get(arr_key) or []:
                    if not isinstance(it, dict):
                        continue
                    name = it.get("name") or ""
                    vals = " / ".join(x.get("text", "") for x in (it.get("values") or []) if x.get("text"))
                    if name and vals and not any(a["name"] == name for a in attrs):
                        attrs.append({"name": name, "value": vals, "key": it.get("key")})
    # 兜底：短属性
    if not attrs:
        sc = _first(w1, "webShortCharacteristics")
        if isinstance(sc, dict):
            for it in sc.get("characteristics") or []:
                nm = "".join(x.get("content", "") for x in ((it.get("title") or {}).get("textRs") or []))
                vals = " / ".join(x.get("text", "") for x in (it.get("values") or []))
                if nm and vals:
                    attrs.append({"name": nm, "value": vals, "key": it.get("id")})

    rec["attributes"] = attrs
    for a in attrs:
        k = _norm_attr_key(a["name"])
        if not k:
            continue
        rec[k] = rec[k] or _num(a["value"]) if k in ("length", "width", "height", "depth", "weight") else (rec[k] or a["value"])
    # 数值属性统一转数字
    for k in ("length", "width", "height", "depth", "weight"):
        if isinstance(rec.get(k), str):
            rec[k] = _num(rec[k])

    # ---- 品牌 ----
    if not rec["brand"]:
        for a in attrs:
            if _norm_attr_key(a["name"]) == "brand":
                rec["brand"] = a["value"]
                break
    if not rec["brand"]:
        b = _find_with(w1, "title")
        br = _first(w1, "webBrand")
        if isinstance(br, dict):
            rec["brand"] = br.get("title") or br.get("name")

    # ---- URL ----
    for link in ((main or {}).get("seo") or {}).get("link") or []:
        if link.get("rel") == "canonical":
            rec["url"] = link.get("href")
    if not rec["url"] and rec["sku"]:
        rec["url"] = f"https://www.ozon.ru/product/{rec['sku']}/"

    return rec


# 导出列（顺序即 Excel 列顺序）
COLUMNS = [
    ("sku", "SKU"), ("offer_code", "卖家货号"), ("brand", "品牌"), ("name", "名称"),
    ("category", "类目"), ("special_price", "特价"), ("price", "价格"),
    ("original_price", "原价"), ("discount", "折扣"),
    ("seller", "卖家"), ("seller_id", "卖家ID"), ("seller_rating", "卖家评分"),
    ("seller_reviews", "卖家评价/订单"), ("seller_age", "店龄"),
    ("seller_company", "公司名称"), ("seller_psrn", "工商注册号"),
    ("seller_address", "卖家地址"), ("honest_sign", "诚信标志"),
    ("seller_url", "卖家主页"),
    ("rating", "评分"), ("reviews", "评价数"), ("questions", "提问数"),
    ("stock", "数量"), ("image_count", "图片数"),
    ("url", "URL"), ("thumbnail", "缩略图"), ("gallery", "图片库"),
    ("description", "描述"), ("rich_description", "富文本"),
    ("country", "产地"), ("length", "长度"), ("width", "宽度"),
    ("height", "高度"), ("depth", "深度"), ("weight", "重量"),
    ("attributes_text", "完整属性"),
]


def flatten(rec):
    out = dict(rec)
    out["attributes_text"] = "; ".join(f"{a['name']}: {a['value']}" for a in rec.get("attributes") or [])
    return out
