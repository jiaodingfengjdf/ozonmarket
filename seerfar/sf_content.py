# -*- coding: utf-8 -*-
"""Ozon 前台内容抓取（Composer API）：商品属性 / 描述 / 变体维度 / 图片 / 标签。

为什么需要它：Seerfar Open API 只给市场数据（销量、价格、流量、评论），
**不含商品详情内容**——没有 attributes / description / rich content / hashtags。
这些只能从 Ozon 前台自己的 `/api/composer-api.bx/page/json/v2` 取。

实现要点（实测 2026-11-13）：
  1. 直接 HTTP 请求会 307 → 403（`incidentId` 反爬拦截），必须走真实浏览器。
  2. 用本机 Chrome/Edge 的 headless 模式 + 真实 UA（默认 UA 带 HeadlessChrome 会被识破），
     `--dump-dom` 打开 composer JSON 地址，浏览器自动带上通行 cookie；
     返回体是 `<html><body><pre>{...json...}</pre>`，取出 pre 文本即为完整 JSON（约 180KB）。
  3. 一份 JSON 里同时含：
       seo.script[0].innerHTML        → JSON-LD Product（name/description/brand/rating/offers/image）
       webShortCharacteristics-*      → 属性表（"О товаре"）
       webAspects-*                   → 变体维度（颜色/规格… 每个值的 SKU 与价格）
       webGallery-*                   → 主图列表
       webPrice-* / webProductHeading-* / webBrand-* / tapTags-*
  4. **富文本 richAnnotation**：当前前台已不再返回该 widget（新旧 PDP 都不含），
     只能拿到 JSON-LD 文本描述 + 图片；如需富文本 HTML，得走 Seller API。
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

DEFAULT = {
    "enabled": True,
    "chrome": "",              # 留空自动探测 Chrome/Edge（仅浏览器兜底用）
    "timeout_ms": 45000,       # 浏览器渲染预算（兜底路径）
    "http_timeout": 25,        # 纯 HTTP 超时（cookie 直连路径）
    "ttl_hours": 72,           # 缓存有效期
    "min_interval": 0.6,       # 两次抓取的最小间隔（纯 HTTP 路径可更快）
    "headless": True,
    "browser_fallback": True,  # cookie 缺失/失效时是否退到浏览器渲染
    "user_agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"),
}

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

COMPOSER = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{sku}/"
# 旧项目 pdp.py 的口径：第二页要用 pdpPage2column 才有 webCharacteristics / webDescription
PAGE2 = ("https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{sku}/"
         "?layout_container=pdpPage2column&layout_page_index=2")

# 用户明确不需要「重量 / 长宽高」：属性名命中这些词就丢弃（"Размер" 保留，可能是服装尺码）
WEIGHT_DIM_RX = re.compile(
    r"вес|весов|длин|ширин|высот|глубин|габарит|"
    r"weight|length|width|height|depth|dimension", re.I)

_lock = threading.Lock()
_last_call = 0.0


class ContentError(Exception):
    """抓取失败（浏览器缺失 / 反爬拦截 / 超时 / 解析失败）。"""


def _cfg(override=None):
    c = dict(DEFAULT)
    c.update({k: v for k, v in (override or {}).items() if v is not None})
    return c


def find_chrome(cfg=None):
    cfg = _cfg(cfg)
    if cfg.get("chrome") and Path(cfg["chrome"]).exists():
        return cfg["chrome"]
    for p in CHROME_CANDIDATES:
        if p and Path(p).exists():
            return p
    raise ContentError("未找到 Chrome/Edge：请在 config.json 的 content.chrome 指定可执行文件路径")


def _wait_turn(min_interval):
    global _last_call
    with _lock:
        gap = float(min_interval or 0)
        elapsed = time.time() - _last_call
        if elapsed < gap:
            time.sleep(gap - elapsed)
        _last_call = time.time()


def dump_dom(url, cfg=None):
    """用本机浏览器打开 url 并返回渲染后的 DOM（含 <pre>JSON</pre>）。"""
    cfg = _cfg(cfg)
    chrome = find_chrome(cfg)
    profile = Path(tempfile.gettempdir()) / ("ozc_" + uuid.uuid4().hex[:10])
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        chrome,
        "--headless=new" if cfg.get("headless", True) else "--start-maximized",
        "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--lang=ru-RU",
        f"--user-agent={cfg['user_agent']}",
        f"--user-data-dir={profile}",
        "--window-size=1280,900",
        f"--virtual-time-budget={int(cfg['timeout_ms'])}",
        "--dump-dom", url,
    ]
    try:
        proc = subprocess.run(args, capture_output=True, timeout=max(15, cfg["timeout_ms"] / 1000 + 25))
        out = proc.stdout.decode("utf-8", "ignore")
        err = proc.stderr.decode("utf-8", "ignore")
    except subprocess.TimeoutExpired:
        raise ContentError(f"浏览器渲染超时（{cfg['timeout_ms']}ms）")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not out.strip():
        raise ContentError("浏览器无输出：" + (err.strip()[:200] or "未知原因"))
    return out


def extract_json(dom_html):
    """从 <pre>{...}</pre> 或直接 JSON 文本里取出 dict。"""
    m = re.search(r"<pre[^>]*>(.*?)</pre>", dom_html, re.S | re.I)
    text = m.group(1) if m else dom_html
    text = html.unescape(text).strip()
    if not text.startswith("{"):
        raise ContentError("返回内容不是 JSON（可能被反爬拦截）：" + text[:160])
    try:
        return json.loads(text)
    except ValueError as e:
        raise ContentError(f"JSON 解析失败：{e}")


def _states(payload):
    ws = payload.get("widgetStates") or {}
    out = {}
    for k, v in ws.items():
        name = k.split("-")[0]
        if name not in out:
            out[name] = v
    return out


def _as_obj(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return {}
    return v if isinstance(v, (dict, list)) else {}


def _text_of(node, *keys):
    """从 {textRs:[{content}]} / {text:[{content}]} 里拼出文本。"""
    if not isinstance(node, dict):
        return ""
    for key in keys:
        arr = node.get(key)
        if isinstance(arr, str) and arr:
            return html.unescape(arr)
        if isinstance(arr, list):
            parts = [html.unescape(str(x.get("content") or "")) for x in arr
                     if isinstance(x, dict) and x.get("content")]
            if parts:
                return "".join(parts).strip()
    return ""


def _ld_json(seo):
    for item in (seo or {}).get("script") or []:
        body = item.get("innerHTML") or ""
        if '"@type":"Product"' in body.replace(" ", ""):
            try:
                return json.loads(body)
            except ValueError:
                continue
    return {}


def parse_payload(payload, sku=""):
    st = _states(payload)
    ld = _ld_json(payload.get("seo") or {})

    # ---- 基础信息 ----
    head = _as_obj(st.get("webProductHeading"))
    title = html.unescape(head.get("title") or ld.get("name") or "").replace("\u00a0", " ")
    brand = ld.get("brand") or ""
    if isinstance(brand, dict):
        brand = brand.get("name") or ""
    rating = review_count = None
    ar = ld.get("aggregateRating") or {}
    if ar:
        try:
            rating = float(ar.get("ratingValue"))
        except (TypeError, ValueError):
            rating = None
        try:
            review_count = int(ar.get("reviewCount"))
        except (TypeError, ValueError):
            review_count = None

    # ---- 价格 ----
    price = card_price = original_price = None
    currency = "₽"
    pw = _as_obj(st.get("webPrice"))

    def _num(s):
        if s is None:
            return None
        digits = re.sub(r"[^\d]", "", str(s))
        return int(digits) if digits else None

    price = _num(pw.get("price"))
    card_price = _num(pw.get("cardPrice"))
    original_price = _num(pw.get("originalPrice"))
    if price is None:
        offers = ld.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = _num(offers.get("price"))
        currency = offers.get("priceCurrency") or currency

    # ---- 描述（JSON-LD） ----
    description = html.unescape(ld.get("description") or "").replace("\u00a0", " ").strip()

    # ---- 属性表（webShortCharacteristics） ----
    attributes = []
    sc = _as_obj(st.get("webShortCharacteristics"))
    for c in sc.get("characteristics") or []:
        name = _text_of(c.get("title") or {}, "textRs", "text")
        vals = []
        for v in c.get("values") or []:
            if isinstance(v, dict):
                t = v.get("text") or _text_of(v, "textRs")
                if t:
                    vals.append(html.unescape(str(t)).strip())
            elif v:
                vals.append(str(v))
        if name or vals:
            attributes.append({"name": name, "values": vals})

    # ---- 变体维度（webAspects）：每个值带 SKU 与价格 ----
    aspects = []
    asp = _as_obj(st.get("webAspects"))
    for a in asp.get("aspects") or []:
        name = a.get("aspectName") or a.get("aspectKey") or ""
        vals = []
        for v in a.get("variants") or []:
            data = v.get("data") or {}
            txt = _text_of(data, "textRs") or data.get("searchableText") or ""
            if txt:
                vals.append({"value": html.unescape(str(txt)).strip(),
                             "sku": v.get("sku"), "price": v.get("price")})
        if name and vals:
            aspects.append({"name": name, "key": a.get("aspectKey"), "values": vals})

    # ---- 图片 ----
    images = []
    gal = _as_obj(st.get("webGallery"))
    for im in gal.get("images") or []:
        src = im.get("src") if isinstance(im, dict) else None
        if src:
            images.append(src)
    if not images and gal.get("coverImage"):
        images.append(gal["coverImage"])
    if not images and ld.get("image"):
        img = ld["image"]
        images = img if isinstance(img, list) else [img]

    # ---- 标签（tapTags / hashtags，很多商品为空） ----
    tags = []
    for key in ("tapTags", "webHashtags"):
        box = _as_obj(st.get(key))
        for it in box.get("items") or []:
            if isinstance(it, dict):
                t = it.get("text") or _text_of(it, "textRs")
                if t:
                    tags.append(str(t))
            elif isinstance(it, str):
                tags.append(it)

    # ---- 富文本（部分商品才有；当前 PDP 基本已移除） ----
    rich = _as_obj(st.get("webRichAnnotation"))
    rich_json = rich.get("content") if isinstance(rich, dict) and rich.get("content") else None

    return {
        "sku": str(sku or ld.get("sku") or gal.get("sku") or ""),
        "title": title,
        "brand": html.unescape(str(brand)),
        "description": description,
        "rating": rating,
        "review_count": review_count,
        "price": price, "card_price": card_price, "original_price": original_price,
        "currency": currency,
        "attributes": attributes,
        "aspects": aspects,
        "images": images,
        "tags": tags,
        "rich": rich_json,
        "seo_title": html.unescape((payload.get("seo") or {}).get("title") or ""),
        "source": "ozon-composer",
        "states": len(payload.get("widgetStates") or {}),
    }


def _sanitize_html(s):
    """富文本只保留排版类标签，去掉 script/style/事件属性/javascript: 链接。"""
    if not s:
        return None
    s = re.sub(r"(?is)<\s*(script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*\1\s*>", "", s)
    s = re.sub(r"(?is)<\s*(script|style|iframe|object|embed)[^>]*/?>", "", s)
    s = re.sub(r"(?i)\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", s)
    s = re.sub(r"(?i)(href|src)\s*=\s*(\"|')\s*javascript:[^\"']*(\"|')", r'\1="#"', s)
    return s.strip() or None


def fetch_http(sku, cfg=None):
    """旧项目方案：cookie 快照 + urllib 直连 composer（主页 + page2 两请求），最快最省。

    注意：Ozon 会对非浏览器 TLS 指纹的 /api/ 请求返回 403（robots.txt 却是 200），
    所以这条路径只在部分网络/时段可用，失败会自动回落到浏览器渲染。
    """
    cfg = _cfg(cfg)
    import ozon_http
    import pdp

    _wait_turn(cfg.get("min_interval"))
    timeout = float(cfg.get("http_timeout") or 25)
    main = ozon_http.get_json(f"/product/{sku}/", timeout=timeout)
    page2 = ozon_http.get_json(
        f"/product/{sku}/?layout_container=pdpPage2column&layout_page_index=2", timeout=timeout)
    rec = pdp.parse_full(main, page2)
    return build_content(rec, main, sku, source="ozon-composer-http", page2_payload=page2)


def fetch_browser(sku, cfg=None, note=""):
    """浏览器渲染路径：并发打开 composer 主页 + page2（pdpPage2column），拿完整属性与富文本。"""
    cfg = _cfg(cfg)
    import pdp
    from concurrent.futures import ThreadPoolExecutor

    urls = [COMPOSER.format(sku=sku), PAGE2.format(sku=sku)]
    with ThreadPoolExecutor(max_workers=2) as ex:
        doms = list(ex.map(lambda u: dump_dom(u, cfg), urls))
    main = extract_json(doms[0])
    try:
        page2 = extract_json(doms[1])
    except ContentError:
        page2 = {}
    rec = pdp.parse_full(main, page2)
    data = build_content(rec, main, sku, source="ozon-composer-browser", page2_payload=page2)
    data["raw_size"] = sum(len(d) for d in doms)
    if note:
        data["http_error"] = note[:200]
    return data


def _collect_text(node, out=None):
    """递归收集 richAnnotationJson 里的文本（顺带收下 block 标题）。"""
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("content", "text", "title") and isinstance(v, str) and v.strip():
                out.append(v.strip())
            else:
                _collect_text(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_text(v, out)
    return out


def desc_from_states(payload):
    """合并**所有** webDescription widget：
       · {characteristics:[{title,content}]}  → 结构化描述块（成分/储存条件…）
       · {richAnnotationJson:{...}}           → 富文本 JSON（raTextBlock/raShowcase…）
    返回 (description_text, rich_obj)。
    """
    ws = payload.get("widgetStates") or {}
    blocks, texts, rich_objs, rich_html = [], [], [], None
    for k, v in ws.items():
        if not k.startswith("webDescription"):
            continue
        d = _as_obj(v)
        if not isinstance(d, dict):
            continue
        for c in d.get("characteristics") or []:
            if isinstance(c, dict):
                title, body = c.get("title"), c.get("content")
                if title and body:
                    blocks.append(f"{title}：{body}")
                elif body:
                    blocks.append(str(body))
        rj = d.get("richAnnotationJson")
        if isinstance(rj, dict):
            rich_objs.append(rj)
            texts.extend(_collect_text(rj))
        ra = d.get("richAnnotation")
        if isinstance(ra, str) and ra.strip():
            if "<" in ra:
                rich_html = rich_html or ra
                texts.append(re.sub(r"<[^>]+>", " ", ra))
            else:
                texts.append(ra.strip())
    seen, parts = set(), []
    for t in texts + blocks:
        t = re.sub(r"\s+", " ", html.unescape(str(t))).strip()
        if t and t not in seen:
            seen.add(t)
            parts.append(t)
    desc = "\n".join(parts).strip() or None
    rich = rich_objs[0] if rich_objs else (rich_html or None)
    return desc, rich


def build_content(rec, main_payload, sku="", source="ozon-composer-http", page2_payload=None):
    """把 pdp.parse_full 的结果 + composer 主页 widget 合成统一结构。"""
    st = _states(main_payload or {})
    _base = parse_payload(main_payload or {}, sku) if main_payload else {}

    attributes = []
    for a in rec.get("attributes") or []:
        name = (a.get("name") or "").strip()
        raw = a.get("value") or ""
        vals = [x.strip() for x in str(raw).split(" / ") if str(x).strip()]
        if name and vals and not WEIGHT_DIM_RX.search(name):
            attributes.append({"name": name, "values": vals, "key": a.get("key")})

    aspects = []
    asp = _as_obj(st.get("webAspects"))
    for a in asp.get("aspects") or []:
        vals = []
        for v in a.get("variants") or []:
            data = v.get("data") or {}
            txt = _text_of(data, "textRs") or data.get("searchableText") or ""
            if txt:
                vals.append({"value": html.unescape(str(txt)).strip(),
                             "sku": v.get("sku"), "price": v.get("price")})
        if a.get("aspectName") and vals:
            aspects.append({"name": a["aspectName"], "key": a.get("aspectKey"), "values": vals})

    images = [u for u in str(rec.get("gallery") or "").split(";") if u.strip()]

    # 描述与富文本：page2 的 webDescription 有多个 widget，pdp 只取第一个，这里全量合并；
    # 都没有时回落到主页 JSON-LD 的 description（最稳）。
    desc_states, rich_obj = desc_from_states(page2_payload or main_payload or {})
    ld = _ld_json((main_payload or {}).get("seo") or {})
    ld_desc = html.unescape(ld.get("description") or "").replace("\u00a0", " ").strip()
    desc = (rec.get("description") or "").strip() or (desc_states or "")
    # JSON-LD 的 description 通常是最完整的正文；结构化块/富文本只是补充
    if len(ld_desc) > len(desc):
        desc = ld_desc
    rich = rec.get("rich_description")
    if isinstance(rich, str):
        head = rich.strip()[:1]
        if head in ("{", "["):
            try:
                rich = json.loads(rich)          # pdp 会把 richAnnotationJson 序列化成字符串
            except ValueError:
                pass
        elif "<" in rich:
            rich = _sanitize_html(rich)
    if not rich:
        rich = rich_obj

    tags = []
    for key in ("tapTags", "webHashtags"):
        box = _as_obj(st.get(key))
        for it in box.get("items") or []:
            if isinstance(it, dict):
                t = it.get("text") or _text_of(it, "textRs")
                if t:
                    tags.append(str(t))
            elif isinstance(it, str):
                tags.append(it)

    extra = {
        "offer_code": rec.get("offer_code"),
        "category": rec.get("category"),
        "seller": rec.get("seller"), "seller_id": rec.get("seller_id"),
        "seller_rating": rec.get("seller_rating"), "seller_reviews": rec.get("seller_reviews"),
        "seller_company": rec.get("seller_company"), "seller_psrn": rec.get("seller_psrn"),
        "seller_address": rec.get("seller_address"), "honest_sign": rec.get("honest_sign"),
        "seller_url": rec.get("seller_url"),
        "stock": rec.get("stock"), "questions": rec.get("questions"),
        "country": rec.get("country"),
        "discount": rec.get("discount"), "url": rec.get("url"),
        "image_count": rec.get("image_count"),
    }
    # 重量/长宽高不要：从 extra 里剔除（attributes 已在上面按名称过滤）
    for k in ("weight", "length", "width", "height", "depth"):
        extra.pop(k, None)

    return {
        "sku": str(rec.get("sku") or sku or ""),
        "title": html.unescape(rec.get("name") or "").replace("\u00a0", " "),
        "brand": rec.get("brand") or "",
        "description": (desc or "").replace("\u00a0", " ").strip(),
        "rating": (rec.get("rating") if rec.get("rating") is not None else _base.get("rating")),
        "review_count": (rec.get("reviews") if rec.get("reviews") is not None
                         else _base.get("review_count")),
        "price": (rec.get("price") if rec.get("price") is not None else _base.get("price")),
        "card_price": (rec.get("special_price") if rec.get("special_price") is not None
                       else _base.get("card_price")),
        "original_price": (rec.get("original_price") if rec.get("original_price") is not None
                           else _base.get("original_price")),
        "currency": "₽",
        "attributes": attributes,
        "aspects": aspects,
        "images": images,
        "tags": tags,
        "rich": rich,
        "extra": extra,
        "seo_title": html.unescape((main_payload or {}).get("seo", {}).get("title") or ""),
        "source": source,
        "states": len((main_payload or {}).get("widgetStates") or {}),
    }


def fetch(sku, cfg=None):
    """抓取单个 SKU 的前台内容：先走旧项目的 cookie 直连，失败再退到浏览器渲染。"""
    cfg = _cfg(cfg)
    if not cfg.get("enabled", True):
        raise ContentError("内容抓取已在 config.json 的 content.enabled 关闭")
    sku = str(sku or "").strip()
    if not sku.isdigit():
        raise ContentError("SKU 必须是纯数字")

    http_err = None
    try:
        return fetch_http(sku, cfg)
    except Exception as e:                     # CookieMissing / CookieExpired / 网络
        http_err = e

    if not cfg.get("browser_fallback", True):
        raise ContentError(f"cookie 直连失败：{http_err}")

    _wait_turn(cfg.get("min_interval"))
    return fetch_browser(sku, cfg, note=f"http 直连失败改用浏览器：{http_err}")
