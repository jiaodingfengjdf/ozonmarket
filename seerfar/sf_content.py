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
    "chrome": "",              # 留空自动探测 Chrome/Edge
    "timeout_ms": 45000,       # 浏览器启动 + 页面渲染预算
    "ttl_hours": 72,           # 缓存有效期
    "min_interval": 1.5,       # 两次抓取的最小间隔（对 Ozon 友好）
    "headless": True,
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


def fetch(sku, cfg=None):
    """抓取单个 SKU 的前台内容（不落库）。"""
    cfg = _cfg(cfg)
    if not cfg.get("enabled", True):
        raise ContentError("内容抓取已在 config.json 的 content.enabled 关闭")
    sku = str(sku or "").strip()
    if not sku.isdigit():
        raise ContentError("SKU 必须是纯数字")
    _wait_turn(cfg.get("min_interval"))
    url = COMPOSER.format(sku=sku)
    dom = dump_dom(url, cfg)
    payload = extract_json(dom)
    data = parse_payload(payload, sku)
    data["raw_size"] = len(json.dumps(payload, ensure_ascii=False))
    return data
