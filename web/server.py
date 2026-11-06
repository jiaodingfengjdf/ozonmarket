#!/usr/bin/env python3
"""Ozon 选品工作台 —— 本地服务。

数据全部实时取自 ozon.ru（composer-api），通过本机 Chrome 的 CDP 会话透传，
绕开 ozon 的 abt-challenge（纯 HTTP 请求一律 403）。

启动:
    python web/server.py --port 8899
打开:
    http://127.0.0.1:8899/
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import random
import re
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
STATIC = os.path.join(HERE, "static")
CDP_PORT = int(os.environ.get("OZON_CDP_PORT", "9222"))
API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="

# ---------------------------------------------------------------- 类目

CATEGORIES = [
    ("elektronika-15500", "电子产品", "Электроника"),
    ("telefony-i-smart-chasy-15501", "手机与智能手表", "Телефоны и смарт-часы"),
    ("noutbuki-planshety-i-elektronnye-knigi-8730", "笔记本 / 平板 / 电子书", "Ноутбуки, планшеты и электронные книги"),
    ("audiotehnika-15543", "耳机与音频", "Наушники и аудиотехника"),
    ("televizory-i-videotehnika-15527", "电视与影音", "Телевизоры и видеотехника"),
    ("bytovaya-tehnika-10500", "家用电器", "Бытовая техника"),
    ("kompyuternye-komplektuyushchie-15709", "电脑配件", "Комплектующие для ПК"),
    ("tsifrovye-tovary-32056", "数码商品", "Цифровые товары"),
    ("igry-i-soft-13300", "游戏与软件", "Игры и софт"),
    ("odezhda-obuv-i-aksessuary-7500", "服装 / 鞋 / 配饰", "Одежда, обувь и аксессуары"),
    ("obuv-17777", "鞋", "Обувь"),
    ("aksessuary-7697", "配饰", "Аксессуары"),
    ("krasota-i-zdorove-6500", "美妆与健康", "Красота и здоровье"),
    ("apteka-6000", "药品", "Аптека"),
    ("dom-i-sad-14500", "家居与花园", "Дом и сад"),
    ("mebel-15000", "家具", "Мебель"),
    ("stroitelstvo-i-remont-9700", "建材与装修", "Строительство и ремонт"),
    ("bytovaya-himiya-14572", "日用化学品", "Бытовая химия"),
    ("produkty-pitaniya-9200", "食品", "Продукты питания"),
    ("supermarket-25000", "超市", "Супермаркет"),
    ("detskie-tovary-7000", "母婴童品", "Детские товары"),
    ("sport-i-otdyh-11000", "运动与休闲", "Спорт и отдых"),
    ("ohota-rybalka-turizm-33332", "狩猎 / 钓鱼 / 旅游", "Охота, рыбалка, туризм"),
    ("avtotovary-8500", "汽车用品", "Автотовары"),
    ("avtomobili-39803", "汽车", "Автомобили"),
    ("tovary-dlya-zhivotnyh-12300", "宠物用品", "Товары для животных"),
    ("knigi-16500", "图书", "Книги"),
    ("kantselyarskie-tovary-18000", "文具", "Канцелярские товары"),
    ("hobbi-i-tvorchestvo-13500", "兴趣与手工", "Хобби и творчество"),
    ("yuvelirnye-ukrasheniya-50001", "珠宝首饰", "Ювелирные украшения"),
    ("antikvariat-vintazh-iskusstvo-8000", "古董 / 复古 / 艺术品", "Антиквариат, винтаж, искусство"),
    ("elektronnye-sigarety-i-tovary-dlya-kureniya-35659", "电子烟与烟具", "Электронные сигареты"),
    ("muzyka-i-video-13100", "音乐与影像", "Музыка и видео"),
    ("tovary-dlya-vzroslyh-9000", "成人用品", "Товары для взрослых"),
    ("podarochnye-sertifikaty-37234", "礼品卡", "Подарочные сертификаты"),
]

SORTS = [
    ("score", "热门榜", "综合热度 / Популярные"),
    ("new", "新品榜", "按上架时间倒序"),
    ("rating", "评分榜", "好评优先"),
    ("discount", "折扣榜", "折扣力度"),
]

# ---------------- 中文对照表 ----------------

FILTER_ZH = {
    "category": "类目", "is_promo": "促销活动", "delivery": "配送时效",
    "currency_price": "价格", "is_installment": "分期付款", "brand": "品牌",
    "brandcertified": "品牌已认证", "is_official_brand_seller": "品牌官方店",
    "type": "类型", "exactmodels": "适用机型", "country": "产地",
    "color": "颜色", "isdiscount": "有折扣", "seller": "店铺",
    "is_for_game_promo": "游戏活动专享",
}

VALUE_ZH = {
    # 配送
    "Неважно": "不限", "От 1 часа": "1 小时内", "Сегодня": "今日达",
    "Завтра": "次日达", "До 3 дней": "3 天内", "До 7 дней": "7 天内",
    "До 12 дней": "12 天内",
    # 颜色
    "Черный": "黑色", "Белый": "白色", "Серый": "灰色", "Красный": "红色",
    "Синий": "蓝色", "Голубой": "浅蓝", "Зеленый": "绿色", "Желтый": "黄色",
    "Оранжевый": "橙色", "Розовый": "粉色", "Фиолетовый": "紫色", "Коричневый": "棕色",
    "Бежевый": "米色", "Золотой": "金色", "Серебряный": "银色", "Бирюзовый": "青色",
    "Мультиколор": "多色", "Прозрачный": "透明", "Хаки": "卡其", "Бордовый": "酒红",
    # 促销/其它
    "Распродажа 11.11": "11.11 大促", "Товары со скидкой": "折扣商品",
    "Бренд проверен": "品牌已认证", "Рассрочка\n0-0-6": "0-0-6 免息分期",
}

SUBCAT_ZH = {
    "Телефоны и смарт-часы": "手机与智能手表",
    "Наушники и аудиотехника": "耳机与音频",
    "Ноутбуки, планшеты и электронные книги": "笔记本 / 平板 / 电子书",
    "Телевизоры и видеотехника": "电视与影音",
    "Комплектующие для ПК": "电脑配件",
    "Офисная техника": "办公设备",
}


def zh(text, table=None):
    s = str(text or "")
    tbl = table if table is not None else VALUE_ZH
    if s in tbl:
        return tbl[s]
    s2 = s.strip()
    if s2 in tbl:
        return tbl[s2]
    return s

# ---------------------------------------------------------------- SKU → 上架日期

_DATE_MODEL = None


def load_model():
    global _DATE_MODEL
    p = os.path.join(HERE, "sku_date_model.json")
    if _DATE_MODEL is None:
        try:
            _DATE_MODEL = json.load(open(p, encoding="utf-8"))
        except Exception:
            _DATE_MODEL = {"points": []}
    return _DATE_MODEL


def sku_listed_date(sku):
    """按标定曲线插值，返回 (date_str, 'est') 或 (None, None)"""
    try:
        s = int(sku)
    except Exception:
        return None, None
    pts = load_model().get("points") or []
    if not pts:
        return None, None
    if s <= pts[0]["sku"]:
        ts = pts[0]["ts"]
    elif s >= pts[-1]["sku"]:
        ts = pts[-1]["ts"]
    else:
        ts = pts[-1]["ts"]
        for a, b in zip(pts, pts[1:]):
            if a["sku"] <= s <= b["sku"]:
                span = b["sku"] - a["sku"]
                r = 0 if span == 0 else (s - a["sku"]) / span
                ts = a["ts"] + (b["ts"] - a["ts"]) * r
                break
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"), "est"


# ---------------------------------------------------------------- 网络策略（节奏 + 熔断）

class Governor:
    """单出口令牌桶：限制请求节奏、加抖动、命中限流后指数退避。

    ozon 的风控看的是「同一出口 IP 的请求密度 + 行为规律性」，
    TLS 指纹走真实 Chrome 已经是正常浏览器（见 tools/fingerprint_check.mjs），
    真正要压的是这里的节奏。
    """

    def __init__(self, min_interval=0.85, jitter=0.45, max_concurrency=1):
        self.min_interval = min_interval
        self.jitter = jitter
        self.max_concurrency = max_concurrency
        self._sema = threading.Semaphore(max_concurrency)
        self._lock = threading.Lock()
        self._next_at = 0.0
        self._cooldown_until = 0.0
        self._strikes = 0
        self.stats = {"ok": 0, "blocked": 0, "served": 0}

    def acquire(self):
        with self._lock:
            now = time.time()
            if now < self._cooldown_until:
                raise RuntimeError(f"限流冷却中，约 {max(1, int(self._cooldown_until - now) // 60)} 分钟后重试")
            wait = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self.min_interval * (1 + random.uniform(-self.jitter, self.jitter))
        if wait:
            time.sleep(wait)
        self._sema.acquire()

    def release(self, status="ok"):
        try:
            self._sema.release()
        except Exception:
            pass
        with self._lock:
            if status == "ok":
                self.stats["ok"] += 1
                self._strikes = max(0, self._strikes - 1)
            elif status == "blocked":
                self.stats["blocked"] += 1
                self._strikes += 1
                back = min(1800, 60 * (2 ** max(0, self._strikes - 1)))
                self._cooldown_until = time.time() + back
            else:  # error：CDP 抖动之类，短暂停就好
                self._cooldown_until = max(self._cooldown_until, time.time() + 15)

    def cooldown_left(self):
        return max(0, int(self._cooldown_until - time.time()))


GOV = Governor()


# ---------------------------------------------------------------- CDP

class CDP:
    """复用本机 Chrome 调试端口，在页面上下文里 fetch ozon 接口

    刻意保持「同一个标签页」：反复 /json/new 会造成标签页抖动，
    而且每次新页都要重新过 antibot，属于典型自动化特征。
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.ws = None
        self.ws_url = None
        self.tab_id = None
        self.bid = 0
        self.drop_tab = False

    def _pick_tab(self, fresh=False):
        """优先复用已有的 ozon 标签页（避免标签抖动）；被风控污染过就换新的"""
        if not fresh and not self.drop_tab:
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=8))
            except Exception:
                tabs = []
            for t in tabs:
                u = t.get("url") or ""
                if t.get("type") == "page" and "ozon.ru" in u and "captcha" not in u and "complaint" not in u:
                    return t
        self.drop_tab = False
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{CDP_PORT}/json/new?https%3A%2F%2Fwww.ozon.ru%2F", method="PUT")
            return json.load(urllib.request.urlopen(req, timeout=10))
        except Exception:
            return None

    def _tab_healthy(self):
        try:
            href = self.evaluate("location.href") or ""
        except Exception:
            return True
        return not any(x in href for x in ("captcha", "complaint", "incident"))

    def connect(self):
        import websocket
        with self.lock:
            if self.ws is not None:
                return
            tab = self._pick_tab()
            if not tab:
                raise RuntimeError("Chrome 调试端口不可用，请先启动带 --remote-debugging-port=9222 的 Chrome")
            self.ws_url = tab["webSocketDebuggerUrl"]
            self.tab_id = tab.get("id")
            self.ws = websocket.create_connection(self.ws_url, timeout=60, max_msg_size=0)
            self._send("Page.enable")
            self._send("Runtime.enable")
            for _ in range(40):
                t = self._send("Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
                title = ((t or {}).get("result") or {}).get("value") or ""
                if title and "Antibot" not in title:
                    break
                time.sleep(0.5)

    def _send(self, method, params=None):
        self.bid += 1
        mid = self.bid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result")

    def evaluate(self, expr, await_promise=False):
        with self.lock:
            self.connect()
            r = self._send("Runtime.evaluate", {
                "expression": expr, "awaitPromise": await_promise,
                "returnByValue": True, "timeout": 15000,
            })
            if r.get("exceptionDetails"):
                raise RuntimeError(str(r["exceptionDetails"])[:400])
            return (r.get("result") or {}).get("value")

    def reset(self, drop_tab=False):
        with self.lock:
            try:
                if self.ws:
                    self.ws.close()
            except Exception:
                pass
            self.ws = None
            if drop_tab:
                self.drop_tab = True


CDP_CLIENT = CDP()
_ozon_cache = {}
_cache_lock = threading.Lock()

# 请求头保持最小集：实测加 sec-fetch-* 之类的伪造就直接被 403（见 tools/header_probe.mjs）
# 真实浏览器自己发的头已经是正确的，画蛇添足反而触发风控。
FETCH_JS = """(async()=>{
  const url = %s;
  const r = await fetch(url, {
    credentials: 'include',
    headers: { 'accept': 'application/json, text/plain, */*' }
  });
  const t = await r.text();
  return JSON.stringify({ s: r.status, b: t });
})()"""


def ozon_get(path_query, ttl=90):
    """path_query 形如 /category/xxx/?sorting=score&page=1"""
    key = path_query
    now = time.time()
    with _cache_lock:
        hit = _ozon_cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]

    url = API + urllib.parse.quote(path_query, safe="")
    js = FETCH_JS % json.dumps(url)
    last = None
    status = "ok"
    GOV.acquire()
    try:
        for attempt in range(2):
            try:
                raw = CDP_CLIENT.evaluate(js, await_promise=True)
                payload = json.loads(raw)
                body = payload["b"]
                if "incidentId" in body:
                    last = "被 Ozon 风控（incidentId）"
                    status = "blocked"
                    CDP_CLIENT.reset(drop_tab=True)
                    break
                if payload["s"] == 200 and len(body) > 3000 and "Antibot" not in body:
                    data = json.loads(body)
                    with _cache_lock:
                        _ozon_cache[key] = (now, data)
                        if len(_ozon_cache) > 400:
                            for k in list(_ozon_cache)[:200]:
                                _ozon_cache.pop(k, None)
                    return data
                last = f"status={payload['s']} len={len(body)}"
                if payload["s"] == 403:
                    status = "blocked"
                    CDP_CLIENT.reset(drop_tab=True)
                    break
                if payload["s"] >= 500:
                    status = "error"
                    break
            except Exception as e:
                last = repr(e)[:300]
                status = "error"
                CDP_CLIENT.reset()
                break
            time.sleep(1.0 + attempt)
    finally:
        GOV.release(status)
    raise RuntimeError(f"ozon 请求失败: {last}")

# ---------------------------------------------------------------- 解析

def _txt(node):
    if not isinstance(node, dict):
        return ""
    if "textDS" in node:
        return node["textDS"].get("text", "") or ""
    if isinstance(node.get("text"), dict):
        return node["text"].get("text", "") or ""
    if isinstance(node.get("text"), str):
        return node["text"]
    return ""


def _clean(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\u2009", " ").replace("\u202f", " ").replace("₽", "")).strip()


def parse_tile(it):
    row = {
        "sku": str(it.get("sku") or it.get("id") or ""),
        "name": "", "price": None, "old_price": None, "discount": "",
        "stock": "", "rating": None, "reviews": None, "reviews_text": "",
        "image": "", "images": [], "url": "", "brand": "",
    }
    link = (it.get("action") or {}).get("link") or ""
    row["url"] = "https://www.ozon.ru" + link.split("?")[0] if link.startswith("/") else link

    for st in it.get("mainState") or []:
        t = st.get("type")
        if t == "priceV2":
            p = st.get("priceV2") or {}
            for pr in p.get("price") or []:
                if pr.get("textStyle") == "PRICE":
                    row["price"] = _num(_clean(pr.get("text")))
                elif pr.get("textStyle") == "ORIGINAL_PRICE":
                    row["old_price"] = _num(_clean(pr.get("text")))
            row["discount"] = (p.get("discount") or "").replace("−", "-")
        elif t == "textDS":
            s = _txt(st)
            if "осталось" in s:
                row["stock"] = _clean(s)
            elif st.get("id") == "name" or (not row["name"] and len(s) > 12):
                row["name"] = _clean(s)
        elif t == "labelListV2":
            flat = json.dumps(st, ensure_ascii=False)
            if "ic_s_star_filled" in flat or "graphicRating" in flat:
                texts = [_txt(x) for x in (st.get("labelListV2", {}).get("items") or []) if x.get("type") == "text"]
                texts = [_clean(x) for x in texts if _clean(x)]
                if texts:
                    row["rating"] = _num(texts[0].replace(",", "."))
                if len(texts) > 1:
                    row["reviews_text"] = texts[1]
                    row["reviews"] = _num(re.sub(r"[^\d]", "", texts[1]))

    ti = it.get("tileImage") or {}
    for item in ti.get("items") or []:
        img = ((item.get("image") or {}).get("link") or "")
        if img:
            row["images"].append(img)
    row["image"] = row["images"][0] if row["images"] else ""
    return row


def _num(v):
    try:
        s = re.sub(r"[^\d.\-]", "", str(v).replace(",", "."))
        f = float(s)
        return int(f) if f == int(f) else f
    except Exception:
        return None


def extract_products(payload):
    if not payload:
        return []
    ws = payload.get("widgetStates") or {}
    rows, seen = [], set()
    for k, v in ws.items():
        if "tileGrid" not in k and "searchResults" not in k:
            continue
        try:
            obj = json.loads(v) if isinstance(v, str) else v
        except Exception:
            continue
        for it in obj.get("items") or []:
            if not isinstance(it, dict) or not (it.get("sku") or it.get("mainState")):
                continue
            r = parse_tile(it)
            if r["sku"] in seen:
                continue
            seen.add(r["sku"])
            rows.append(r)
    return rows


def _iter_filter_sections(payload):
    """通用：从任意 payload 里找出 sections[].filters[] 结构
    （类目页 filtersDesktop、全部筛选弹窗、搜索页都可能有，widget 名不固定）"""
    found = []

    def walk(node, depth=0):
        if depth > 8:
            return
        if isinstance(node, dict):
            secs = node.get("sections")
            if isinstance(secs, list) and secs and isinstance(secs[0], dict) and "filters" in secs[0]:
                found.append(node)
                return
            for v in node.values():
                walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)

    for v in (payload.get("widgetStates") or {}).values():
        try:
            obj = json.loads(v) if isinstance(v, str) else v
        except Exception:
            continue
        walk(obj)
    return found


def extract_filters(payload):
    """把 filters 结构归一化成前端可用的 schema"""
    if not payload:
        return []
    roots = _iter_filter_sections(payload)
    if not roots:
        # 退化：老的 filtersDesktop 路径
        ws = payload.get("widgetStates") or {}
        for k, v in ws.items():
            if "filtersDesktop" in k:
                try:
                    roots = [json.loads(v) if isinstance(v, str) else v]
                except Exception:
                    roots = []
                break
    if not roots:
        return []

    out = []
    seen_keys = set()
    for raw in roots:
        for sec in raw.get("sections") or []:
            for f in sec.get("filters") or []:
                t = f.get("type")
                key = f.get("key")
                body = f.get(t) or {}
                if not isinstance(body, dict):
                    continue
                title = body.get("title") or key
                title_zh = FILTER_ZH.get(key) or zh(title)

                if t == "boolFilter":
                    if ("bool", key) not in seen_keys:
                        seen_keys.add(("bool", key))
                        out.append({"key": key, "type": "bool", "title": title, "titleZh": title_zh})
                    continue
                if t == "categoryFilter":
                    cats = []
                    for c in body.get("categories") or []:
                        u = c.get("urlValue") or ""
                        m = re.search(r"/category/([a-z0-9\-]+-\d+)/", u)
                        if m and c.get("level", 0) > 0:
                            nm = c.get("title") or ""
                            cats.append({"slug": m.group(1), "title": nm, "zh": zh(nm, SUBCAT_ZH)})
                    if cats and ("subcat", "subcat") not in seen_keys:
                        seen_keys.add(("subcat", "subcat"))
                        out.append({"key": "subcat", "type": "subcat", "title": "子类目",
                                    "titleZh": "子类目", "values": cats})
                    continue

                values = []
                if t == "multipleRangesFilter":
                    rng = body.get("rangeFilter") or {}
                    if ("range", key) not in seen_keys:
                        seen_keys.add(("range", key))
                        out.append({"key": key, "type": "range", "title": rng.get("title") or "Цена",
                                    "titleZh": "价格区间（₽）",
                                    "min": rng.get("minValue"), "max": rng.get("maxValue")})
                    for s in (body.get("checkboxesFilter") or {}).get("sections") or []:
                        for itm in s.get("items") or []:
                            v = _txt(itm.get("title"))
                            values.append({"key": itm.get("key"), "title": v, "zh": zh(v)})
                    if values and ("range_preset", key) not in seen_keys:
                        seen_keys.add(("range_preset", key))
                        out.append({"key": key, "type": "range_preset", "title": "Цена",
                                    "titleZh": "价格档位", "values": values})
                    continue
                if t == "colorFilter":
                    for c in body.get("colorIcons") or []:
                        d = c.get("description") or ""
                        values.append({"key": str(c.get("key")), "title": d, "zh": zh(d),
                                       "icon": ((c.get("icon") or {}).get("backgroundImage") or "")})
                    if ("color", key) not in seen_keys:
                        seen_keys.add(("color", key))
                        out.append({"key": key, "type": "color", "title": title,
                                    "titleZh": title_zh, "values": values})
                    continue
                if t in ("checkboxesFilter", "radioFilter"):
                    for s in body.get("sections") or []:
                        for itm in s.get("items") or []:
                            v = _txt(itm.get("title"))
                            values.append({"key": str(itm.get("key")), "title": v,
                                           "zh": zh(v) if key in ("delivery",) else v})
                    if values and ("check", key) not in seen_keys:
                        seen_keys.add(("check", key))
                        out.append({"key": key, "type": "check", "title": title, "titleZh": title_zh,
                                    "multi": not body.get("isRadio"), "values": values})
                    continue
    return out


def build_path(cat, sort, page, filters):
    q = {"sorting": sort, "layout_container": "searchResultsV2", "page": str(page)}
    q.update(filters or {})
    qs = "&".join(f"{urllib.parse.quote(k)}={urllib.parse.quote(str(v), safe=';')}"
                  for k, v in q.items() if v not in (None, "", []))
    return f"/category/{cat}/?{qs}"


# ---------------------------------------------------------------- 导出

def export_xlsx(rows, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    full = bool(rows) and ("attributes_text" in rows[0] or "offer_code" in rows[0])
    if full:
        import pdp
        cols = [(k, lbl) for k, lbl in pdp.COLUMNS]
        widths = {"name": 46, "category": 46, "url": 42, "gallery": 40, "description": 60,
                  "rich_description": 40, "attributes_text": 60, "thumbnail": 34,
                  "seller_url": 32, "seller_company": 26, "seller_address": 38}
        cols = [(k, w if isinstance(w, int) else widths.get(k, 14)) for k, w in cols]
        img_key = "thumbnail"
    else:
        cols = [("图片", 16), ("SKU", 14), ("标题", 60), ("现价₽", 10), ("原价₽", 10), ("折扣", 9),
                ("评分", 8), ("评论数", 10), ("上架日期", 12), ("库存", 16), ("链接", 45)]
        img_key = "image"

    wb = Workbook()
    ws = wb.active
    ws.title = "Ozon选品"
    head_fill = PatternFill("solid", fgColor="1F4E79")
    for i, (name, w) in enumerate(cols, 1):
        c = ws.cell(row=1, column=i, value=name if full else name)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    import urllib.request as ur

    for r, item in enumerate(rows, 2):
        for cidx, (key, _w) in enumerate(cols, 1):
            val = item.get(key) if full else item.get({
                "图片": "image", "SKU": "sku", "标题": "name", "现价₽": "price", "原价₽": "old_price",
                "折扣": "discount", "评分": "rating", "评论数": "reviews", "上架日期": "listed_date",
                "库存": "stock", "链接": "url"}[key])
            cell = ws.cell(row=r, column=cidx, value=val)
            if key == "url" or key == "seller_url":
                if isinstance(val, str) and val.startswith("http"):
                    cell.hyperlink = val
                    cell.font = Font(color="0563C1", underline="single")
        try:
            img_url = item.get(img_key)
            if img_url:
                req = ur.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                data = ur.urlopen(req, timeout=15).read()
                from openpyxl.drawing.image import Image as XLImage
                from PIL import Image as PILImage
                bio = io.BytesIO(data)
                im = PILImage.open(bio).convert("RGB")
                im.thumbnail((96, 128))
                out = io.BytesIO()
                im.save(out, format="JPEG", quality=82)
                out.seek(0)
                xi = XLImage(out)
                ws.add_image(xi, f"A{r}")
                ws.row_dimensions[r].height = 96
        except Exception:
            pass
    wb.save(path)


# ---------------- web 类目映射（Seller 类目名 → ozon.ru 的 /category/slug-id/） ----------------

# Seller 类目名 → ozon.ru 的 /category/slug-id/ —— 搜索解析不到的手工指定
MANUAL_MAP = {
    "Галантерея и аксессуары": "aksessuary-7697",
    "Фермерское хозяйство": "produkty-pitaniya-9200",
    "Продукты питания Ozon Fresh": "supermarket-25000",
    "Красота и гигиена": "krasota-i-zdorove-6500",
    "Музыкальные инструменты": "muzyka-i-video-13100",
    "Кино, музыка, видеоигры, софт": "igry-i-soft-13300",
}

MAP_PATH = os.path.join(HERE, "category_map.json")
_MAP = None
_MAP_MTIME = None
_MAP_LOCK = threading.Lock()


def load_map():
    """读映射缓存；文件被外部（bulk_resolve）更新过就自动重载"""
    global _MAP, _MAP_MTIME
    try:
        mt = os.path.getmtime(MAP_PATH)
    except Exception:
        mt = 0
    if _MAP is None or mt != _MAP_MTIME:
        try:
            _MAP = json.load(open(MAP_PATH, encoding="utf-8"))
        except Exception:
            _MAP = {}
        _MAP_MTIME = mt
    return _MAP


def save_map():
    try:
        json.dump(load_map(), open(MAP_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    except Exception:
        pass


def add_mapping(name, slug):
    """只更新单个键，先读盘再写，避免覆盖 bulk_resolve 的进度"""
    global _MAP, _MAP_MTIME
    with _MAP_LOCK:
        try:
            m = json.load(open(MAP_PATH, encoding="utf-8"))
        except Exception:
            m = dict(_MAP or {})
        m["name:" + name] = slug
        try:
            tmp = MAP_PATH + ".tmp"
            json.dump(m, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
            os.replace(tmp, MAP_PATH)
        except Exception:
            pass
        _MAP = m
        try:
            _MAP_MTIME = os.path.getmtime(MAP_PATH)
        except Exception:
            pass


def seed_map_from_categories():
    """用已有的 35 个一级类目的俄文名 + 手工映射做种子"""
    m = load_map()
    changed = False
    for slug, z, r in CATEGORIES:
        if "name:" + r not in m:
            m["name:" + r] = slug
            changed = True
    for name, slug in MANUAL_MAP.items():
        if "name:" + name not in m:
            m["name:" + name] = slug
            changed = True
    if changed:
        save_map()


def resolve_slug(name):
    """拿 Seller 类目名去 ozon.ru 搜一次，取 Ozon 自动预测到的类目 slug；结果缓存"""
    if not name:
        return None, None
    if name in MANUAL_MAP:
        return MANUAL_MAP[name], "manual"
    key = "name:" + name
    with _MAP_LOCK:
        m = load_map()
        if key in m:
            return m[key], "cache"

    q = "/search/?text=" + urllib.parse.quote(name) + "&layout_container=searchResultsV2"
    data = ozon_get(q, ttl=86400)
    url = ((data or {}).get("pageInfo") or {}).get("url") or ""
    mm = re.match(r"/category/([a-z0-9\-]+-\d+)/", url)
    slug = mm.group(1) if mm else None
    how = "predicted"

    # 兜底：Ozon 没自动预测时，从搜索结果的分类筛选里挑名字最接近的那个
    if not slug:
        slug, how = _best_candidate(name, data)

    if slug:
        add_mapping(name, slug)
    return slug, how


def _common_len(a, b):
    """最长公共子串长度（用于俄文类目名近似匹配）"""
    a, b = str(a or "").lower(), str(b or "").lower()
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _best_candidate(name, data):
    """从 categoryFilter 里挑候选类目，按名字近似度打分"""
    if not data:
        return None, "none"
    cands = []
    ws = data.get("widgetStates") or {}
    for k, v in ws.items():
        if "filtersDesktop" not in k:
            continue
        try:
            o = json.loads(v) if isinstance(v, str) else v
        except Exception:
            continue
        for sec in o.get("sections") or []:
            for fl in sec.get("filters") or []:
                if fl.get("key") != "category":
                    continue
                for c in (fl.get("categoryFilter") or {}).get("categories") or []:
                    u = c.get("urlValue") or ""
                    m2 = re.search(r"/category/([a-z0-9\-]+-\d+)/", u)
                    if m2 and c.get("title"):
                        cands.append((c["title"], m2.group(1), int(c.get("level") or 0)))
    if not cands:
        return None, "none"

    scored = []
    for title, sl, lvl in cands:
        sc = _common_len(name, title)
        # 越浅的层级越保守（L0 是顶级类目，近似度要更高才算）
        need = 6 if lvl == 0 else 5
        if sc >= need:
            scored.append((sc - lvl, title, sl))
    if not scored:
        return None, "none"
    scored.sort(reverse=True)
    return scored[0][2], "candidate"


# ---------------------------------------------------------------- 类目属性（Seller API）

_filter_cache = {}
_filter_cache_lock = threading.Lock()

ATTR_CACHE_PATH = os.path.join(HERE, "attrs_cache.json")
_ATTR_CACHE = None
_ATTR_LOCK = threading.Lock()
_TREE_CACHE = None


def seller_creds():
    cid = os.environ.get("OZON_CLIENT_ID")
    key = os.environ.get("OZON_API_KEY")
    if cid and key:
        return cid, key
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    s = cfg["seller"]
    return str(s["client_id"]), s["api_key"]


def seller_post(path, body):
    cid, key = seller_creds()
    req = urllib.request.Request(
        "https://api-seller.ozon.ru" + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Client-Id": cid, "Api-Key": key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def load_tree():
    global _TREE_CACHE
    if _TREE_CACHE is None:
        try:
            _TREE_CACHE = json.load(open(os.path.join(HERE, "categories_tree.json"), encoding="utf-8"))
        except Exception:
            _TREE_CACHE = {"tree": []}
    return _TREE_CACHE


def _norm(s):
    s = str(s or "").lower().replace("ё", "е")
    s = re.sub(r"[^a-zа-я0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def find_seller_node(slug):
    """按 web slug 反查 Seller 树节点，返回 (desc_category_id, type_id, 节点名)
    宽类目（如「电子产品」）本身没有 type，就下沉到第一个带类型的子类目。"""
    m = load_map()
    names = [k[5:] for k, v in m.items() if k.startswith("name:") and v == slug]
    if not names:
        return None

    def usable(node, parent_desc):
        if node.get("type"):
            return parent_desc, node.get("id"), node["n"]
        kids = node.get("c") or []
        tkids = [k for k in kids if k.get("type")]
        if tkids:
            return node.get("id"), tkids[0]["id"], f'{node["n"]} › {tkids[0]["n"]}'
        return None

    # 1) 精确名匹配
    def find_exact(nodes, target):
        for n in nodes:
            if n.get("n") == target:
                return n
            r = find_exact(n.get("c") or [], target)
            if r:
                return r
        return None

    tree = load_tree().get("tree") or []
    node = None
    for nm in names:
        node = find_exact(tree, nm)
        if node:
            break

    # 2) 名字对不上时做模糊匹配（取词重叠最高的）
    if node is None:
        best, best_score = None, 0
        wanted = [_norm(n) for n in names]
        stack = list(tree)
        while stack:
            n = stack.pop()
            nn = _norm(n.get("n"))
            for w in wanted:
                if not w or not nn:
                    continue
                tw, tn = set(w.split()), set(nn.split())
                inter = len(tw & tn)
                score = inter / max(1, len(tw | tn))
                if inter and score > best_score:
                    best, best_score = n, score
            stack.extend(n.get("c") or [])
        if best is not None and best_score >= 0.5:
            node = best

    if node is None:
        return None

    from collections import deque
    q = deque([(node, None)])
    seen = 0
    while q and seen < 200:
        n, d = q.popleft()
        seen += 1
        if n.get("type"):
            return d, n.get("id"), n["n"]
        kids = n.get("c") or []
        tk = [k for k in kids if k.get("type")]
        if tk:
            return n.get("id"), tk[0]["id"], f'{n["n"]} › {tk[0]["n"]}'
        for k in kids[:8]:
            q.append((k, n.get("id")))
    return None


def load_attr_cache():
    global _ATTR_CACHE
    if _ATTR_CACHE is None:
        try:
            _ATTR_CACHE = json.load(open(ATTR_CACHE_PATH, encoding="utf-8"))
        except Exception:
            _ATTR_CACHE = {}
    return _ATTR_CACHE


def save_attr_cache():
    try:
        json.dump(_ATTR_CACHE, open(ATTR_CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def attribute_values(desc_id, type_id, attr_id, limit=200, language="ZH_HANS"):
    body = {"attribute_id": attr_id, "description_category_id": desc_id, "type_id": type_id,
            "language": language, "last_value_id": 0, "limit": limit}
    try:
        r = seller_post("/v1/description-category/attribute/values", body)
        return [{"id": v.get("id"), "value": v.get("value"), "info": v.get("info")}
                for v in (r.get("result") or [])], bool(r.get("has_next"))
    except Exception:
        return [], False


def seller_attributes(web_slug):
    """返回某 web 类目对应的发品属性（含字典值），带磁盘缓存"""
    found = find_seller_node(web_slug)
    if not found:
        return {"attrs": [], "note": "该类目在 Seller 树里没找到对应节点", "cat": web_slug}
    desc_id, type_id, node_name = found
    if not desc_id or not type_id:
        return {"attrs": [], "note": "该节点没有可用的 type_id（需再下沉一层）", "cat": web_slug,
                "desc_id": desc_id, "type_id": type_id}

    ck = f"{desc_id}:{type_id}"
    with _ATTR_LOCK:
        cache = load_attr_cache()
        if ck in cache:
            return cache[ck]

    res = seller_post("/v1/description-category/attribute",
                      {"description_category_id": desc_id, "type_id": type_id, "language": "DEFAULT"})
    try:
        res_zh = seller_post("/v1/description-category/attribute",
                             {"description_category_id": desc_id, "type_id": type_id, "language": "ZH_HANS"})
        zh_map = {x.get("id"): x.get("name") for x in (res_zh.get("result") or [])}
    except Exception:
        zh_map = {}
    attrs = []
    for a in res.get("result") or []:
        dict_id = str(a.get("dictionary_id") or "0")
        item = {
            "id": a.get("id"),
            "name": a.get("name"),
            "name_zh": zh_map.get(a.get("id")),
            "type": a.get("type"),
            "multi": bool(a.get("is_collection")),
            "dict": dict_id != "0",
            "dict_id": dict_id,
            "values": [],
        }
        if item["dict"]:
            vals, more = attribute_values(desc_id, type_id, a.get("id"))
            item["values"] = vals
            item["more"] = more
        attrs.append(item)

    out = {"cat": web_slug, "node": node_name, "desc_id": desc_id, "type_id": type_id,
           "count": len(attrs), "dictionary_count": sum(1 for x in attrs if x["dict"]),
           "attrs": attrs}
    with _ATTR_LOCK:
        cache[ck] = out
        _ATTR_CACHE = cache
        save_attr_cache()
    return out


# ---------------------------------------------------------------- 类目大盘

JOBS = {}
JOBS_LOCK = threading.Lock()


def _median(a):
    if not a:
        return None
    s = sorted(a)
    return s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2


def _avg(a):
    return round(sum(a) / len(a), 1) if a else None


def aggregate_market(cat_slug, cat_zh, cat_ru, sorts, pages_n, detail_n=0, df=None):
    """抓一个类目的若干榜 × 若干页，算大盘指标。

    detail_n > 0 时对前 N 个商品补 PDP 详情（卖家/品牌/产地/尺寸），
    用于卖家集中度与卖家评分分布；df 为详情筛选条件，命中才计入统计。
    """
    rows, seen = [], set()
    for s in sorts:
        for p in range(1, pages_n + 1):
            try:
                data = ozon_get(build_path(cat_slug, s, p, None), ttl=600)
            except Exception:
                break
            got = extract_products(data)
            if not got:
                break
            for it in got:
                if it["sku"] in seen:
                    continue
                seen.add(it["sku"])
                d, _ = sku_listed_date(it["sku"])
                it["listed_date"] = d
                rows.append(it)

    if not rows:
        return {"slug": cat_slug, "zh": cat_zh, "ru": cat_ru, "n": 0}

    # ---- 补详情（卖家维度）----
    detail_rows = []
    if detail_n:
        import pdp
        for it in rows[:detail_n]:
            try:
                main = ozon_get(f"/product/{it['sku']}/", ttl=3600)
                page2 = ozon_get(f"/product/{it['sku']}/?layout_container=pdpPage2column&layout_page_index=2",
                                 ttl=3600)
                rec = pdp.parse_full(main, page2)
                it["_d"] = rec
                detail_rows.append(it)
            except Exception:
                continue
            time.sleep(0.35)

    # ---- 详情筛选 ----
    if df:
        def ok(it):
            d = it.get("_d")
            if not d:
                return False
            s = lambda v: str(v or "").lower()
            if df.get("brand") and s(df["brand"]) not in s(d.get("brand")):
                return False
            if df.get("seller") and s(df["seller"]) not in s(d.get("seller")):
                return False
            if df.get("country") and s(df["country"]) not in s(d.get("country")):
                return False
            if df.get("honest") and s(d.get("honest_sign")) != s(df["honest"]):
                return False
            def ge(v, lim):
                try:
                    return lim in (None, "", ) or (v is not None and float(v) >= float(lim))
                except Exception:
                    return True
            if not ge(d.get("seller_rating"), df.get("seller_rating_min")):
                return False
            if not ge(d.get("rating"), df.get("rating_min")):
                return False
            if not ge(d.get("reviews"), df.get("reviews_min")):
                return False
            if not ge(d.get("stock"), df.get("stock_min")):
                return False
            if df.get("stock_max") not in (None, ""):
                try:
                    if d.get("stock") is None or float(d["stock"]) > float(df["stock_max"]):
                        return False
                except Exception:
                    pass
            return True
        before = len(rows)
        rows = [r for r in rows if ok(r)]
        filtered_out = before - len(rows)
    else:
        filtered_out = 0

    if not rows:
        return {"slug": cat_slug, "zh": cat_zh, "ru": cat_ru, "n": 0,
                "filtered_out": filtered_out, "detail_n": len(detail_rows)}

    prices = [r["price"] for r in rows if r.get("price")]
    discs = [abs(parseFloat(r["discount"])) for r in rows if parseFloat(r["discount"]) is not None]
    rates = [r["rating"] for r in rows if r.get("rating")]
    revs = [r.get("reviews") or 0 for r in rows]
    total_rev = sum(revs) or 1

    top = sorted(rows, key=lambda r: -(r.get("reviews") or 0))
    cr5_rev = round(100 * sum((r.get("reviews") or 0) for r in top[:5]) / total_rev, 1)
    cr10_rev = round(100 * sum((r.get("reviews") or 0) for r in top[:10]) / total_rev, 1)

    today = datetime.now(timezone.utc)
    new30 = new90 = 0
    for r in rows:
        d = r.get("listed_date")
        if not d:
            continue
        try:
            age = (today - datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days
        except Exception:
            continue
        if age <= 30:
            new30 += 1
        if age <= 90:
            new90 += 1

    bands = [(0, 500), (500, 1000), (1000, 2000), (2000, 5000), (5000, 10000), (10000, 10 ** 12)]
    band_counts = [sum(1 for p in prices if lo <= p < hi) for lo, hi in bands]

    n = len(rows)
    new30_pct = round(100 * new30 / n, 1)
    disc_avg = _avg(discs) or 0

    # ---- 卖家维度（依赖详情）----
    sellers = {}
    sr = []
    for it in rows:
        d = it.get("_d") or {}
        name = d.get("seller")
        if not name:
            continue
        sellers[name] = sellers.get(name, 0) + 1
        if d.get("seller_rating") is not None:
            sr.append(d["seller_rating"])
    detail_cnt = sum(1 for it in rows if it.get("_d"))
    seller_n = len(sellers)
    if detail_cnt and sellers:
        shares = sorted(sellers.values(), reverse=True)
        cr1 = round(100 * shares[0] / detail_cnt, 1)
        seller_cr5 = round(100 * sum(shares[:5]) / detail_cnt, 1)
    else:
        cr1 = seller_cr5 = None

    return {
        "slug": cat_slug, "zh": cat_zh, "ru": cat_ru,
        "n": n,
        "detail_n": detail_cnt,
        "filtered_out": filtered_out,
        "low_confidence": n < 15,
        "price_median": _median(prices),
        "price_avg": _avg(prices),
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "discount_avg": disc_avg,
        "rating_avg": round(_avg(rates) or 0, 2),
        "reviews_median": int(_median(revs) or 0),
        "reviews_total": total_rev,
        "new30_pct": new30_pct,
        "new90_pct": round(100 * new90 / n, 1),
        "cr5": cr5_rev,
        "cr10": cr10_rev,
        "seller_n": seller_n,
        "seller_cr1": cr1,
        "seller_cr5": seller_cr5,
        "seller_rating_avg": round(_avg(sr) or 0, 2) if sr else None,
        "seller_low_pct": round(100 * sum(1 for x in sr if x < 4.5) / len(sr), 1) if sr else None,
        "bands": band_counts,
        "opportunity": None,
        "top": [{"sku": r["sku"], "name": r.get("name"), "price": r.get("price"),
                 "reviews": r.get("reviews"), "rating": r.get("rating"),
                 "listed_date": r.get("listed_date"), "url": r.get("url")} for r in top[:3]],
    }


def score_opportunity(results):
    """跨类目归一化后打分：新品活跃 40 + 集中度低 30 + 折扣空间 30"""
    ok = [r for r in results if r.get("n")]
    if not ok:
        return
    def norm(key, invert=False):
        vals = [r.get(key) or 0 for r in ok]
        mx = max(vals) or 1
        return {r["slug"]: (1 - (r.get(key) or 0) / mx) if invert else (r.get(key) or 0) / mx for r in ok}
    n_new = norm("new30_pct")
    n_cr5 = norm("cr5", invert=True)
    n_disc = norm("discount_avg")
    for r in ok:
        s = 40 * n_new[r["slug"]] + 30 * n_cr5[r["slug"]] + 30 * n_disc[r["slug"]]
        r["opportunity"] = round(s, 1)


def parseFloat(v):
    try:
        return abs(float(str(v).replace("%", "").replace("−", "-")))
    except Exception:
        return None


def market_worker(jid, cat_list, pages_n, sorts, detail_n=0, df=None):
    res = []
    try:
        for i, (slug, zh, ru) in enumerate(cat_list):
            with JOBS_LOCK:
                JOBS[jid]["label"] = zh
            try:
                res.append(aggregate_market(slug, zh, ru, sorts, pages_n, detail_n, df))
            except Exception as e:
                res.append({"slug": slug, "zh": zh, "ru": ru, "n": 0, "error": str(e)[:120]})
            score_opportunity(res)
            with JOBS_LOCK:
                JOBS[jid]["progress"] = round((i + 1) / len(cat_list), 3)
                JOBS[jid]["result"] = list(res)
        score_opportunity(res)
        with JOBS_LOCK:
            JOBS[jid]["done"] = True
            JOBS[jid]["result"] = res
        try:
            cache = {"built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                     "pages": pages_n, "sorts": sorts, "rows": res}
            os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
            json.dump(cache, open(os.path.join(ROOT, "data", "market_last.json"), "w", encoding="utf-8"),
                      ensure_ascii=False)
        except Exception:
            pass
    except Exception as e:
        with JOBS_LOCK:
            JOBS[jid]["error"] = str(e)[:300]
            JOBS[jid]["done"] = True


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "OzonPicker/1.0"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._file(os.path.join(STATIC, "index.html"), "text/html; charset=utf-8")
            if u.path == "/app.js":
                return self._file(os.path.join(STATIC, "app.js"), "application/javascript; charset=utf-8")
            if u.path == "/style.css":
                return self._file(os.path.join(STATIC, "style.css"), "text/css; charset=utf-8")

            if u.path == "/api/net/status":
                with _cache_lock:
                    return self._json({
                        "cooldown": GOV.cooldown_left(),
                        "strikes": GOV._strikes,
                        "stats": GOV.stats,
                        "min_interval": GOV.min_interval,
                        "jitter": GOV.jitter,
                        "cache": len(_ozon_cache),
                    })

            if u.path == "/api/net/reset":
                GOV._cooldown_until = 0.0
                GOV._strikes = 0
                CDP_CLIENT.reset(drop_tab=True)
                with _cache_lock:
                    _ozon_cache.clear()
                return self._json({"ok": True, "msg": "冷却已清除，缓存已清空，下次请求会重新建标签页"})

            if u.path == "/api/map/stats":
                try:
                    m = load_map()
                    tree = load_tree().get("tree") or []
                    total, hit = 0, 0
                    def walk(ns):
                        nonlocal total, hit
                        for nd in ns:
                            total += 1
                            if m.get("name:" + (nd.get("n") or "")):
                                hit += 1
                            walk(nd.get("c") or [])
                    walk(tree)
                    return self._json({
                        "nodes": total, "mapped": hit,
                        "pct": round(100 * hit / total, 1) if total else 0,
                        "map_entries": len(m),
                    })
                except Exception as e:
                    return self._json({"error": str(e)[:200]}, 500)

            if u.path == "/api/zh":
                try:
                    import zh as zhm
                except Exception:
                    return self._json({"results": {}, "error": "zh module missing"})
                texts = [t for t in (q.get("texts") or "").split("|") if t.strip()][:60]
                online = q.get("online", "1") != "0"
                res = zhm.translate(texts, allow_online=online)
                return self._json({"results": res, "stats": zhm.stats()})

            if u.path == "/api/tree":
                p = os.path.join(HERE, "categories_tree.json")
                try:
                    data = json.load(open(p, encoding="utf-8"))
                except Exception:
                    return self._json({"tree": [], "total": 0})
                m = load_map()
                def annotate(nodes):
                    for n in nodes:
                        slug = m.get("name:" + n.get("n", ""))
                        if slug:
                            n["slug"] = slug
                        if n.get("c"):
                            annotate(n["c"])
                annotate(data.get("tree") or [])
                data["mapped"] = sum(1 for k in m if k.startswith("name:"))
                try:
                    import zh as zhm
                    def fill(nodes):
                        for nd in nodes:
                            if not nd.get("zh") and nd.get("n"):
                                z = zhm.dict_lookup(nd["n"]) or zhm.cache().get(nd["n"])
                                if z:
                                    nd["zh"] = z
                            if nd.get("c"):
                                fill(nd["c"])
                    fill(data.get("tree") or [])
                except Exception:
                    pass
                return self._json(data)

            if u.path == "/api/resolve":
                name = q.get("name") or ""
                try:
                    slug, how = resolve_slug(name)
                except Exception as e:
                    return self._json({"slug": None, "error": str(e)[:200]})
                return self._json({"slug": slug, "how": how, "name": name})

            if u.path == "/api/categories":
                return self._json({"items": [{"slug": s, "zh": z, "ru": r} for s, z, r in CATEGORIES],
                                   "sorts": [{"key": k, "name": n, "desc": d} for k, n, d in SORTS]})

            if u.path == "/api/filters":
                cat = q.get("cat") or CATEGORIES[0][0]
                sort = q.get("sort", "score")
                ck = f"{cat}|{sort}"
                with _filter_cache_lock:
                    hit = _filter_cache.get(ck)
                if hit and time.time() - hit[0] < 1800:
                    return self._json({"filters": hit[1], "src": hit[2], "cat": cat, "cached": True})

                filters, src = [], "none"
                # 1) 全部筛选弹窗：含类目属性（category-specific）筛选
                try:
                    modal = ozon_get(f"/modal/allFilters/category/{cat}/"
                                     f"?layout_container=searchResultsV2&sorting={sort}", ttl=1800)
                    filters = extract_filters(modal)
                    if filters:
                        src = "allFilters"
                except Exception:
                    filters = []
                # 2) 退化到类目页侧边栏
                if not filters:
                    try:
                        page = ozon_get(build_path(cat, sort, 1, None), ttl=600)
                        filters = extract_filters(page)
                        src = "category" if filters else "none"
                    except Exception as e:
                        return self._json({"filters": [], "src": "blocked",
                                           "error": str(e)[:200], "cat": cat}, 503)
                with _filter_cache_lock:
                    _filter_cache[ck] = (time.time(), filters, src)
                return self._json({"filters": filters, "src": src, "cat": cat})

            if u.path == "/api/attrs":
                cat = q.get("cat") or ""
                try:
                    out = seller_attributes(cat)
                except Exception as e:
                    return self._json({"attrs": [], "error": str(e)[:300], "cat": cat}, 200)
                return self._json(out)

            if u.path == "/api/search":
                cats_q = (q.get("cats") or "").strip()
                cat_list = [c for c in cats_q.split(",") if c.strip()][:10] if cats_q else []
                if not cat_list:
                    cat_list = [q.get("cat") or CATEGORIES[0][0]]
                sort = q.get("sort", "score")
                page = int(q.get("page", "1"))
                depth = max(1, min(12, int(q.get("pages", "4"))))
                filters = json.loads(q.get("filters") or "{}")
                items, seen = [], set()
                per_cat = {}
                for cat in cat_list:
                    got_cat = 0
                    for p in range(page, page + depth):
                        try:
                            data = ozon_get(build_path(cat, sort, p, filters))
                        except Exception as e:
                            per_cat[cat] = {"items": got_cat, "error": str(e)[:120]}
                            break
                        got = extract_products(data)
                        if not got:
                            break
                        for it in got:
                            if it["sku"] in seen:
                                continue
                            seen.add(it["sku"])
                            d, src = sku_listed_date(it["sku"])
                            it["listed_date"] = d
                            it["listed_source"] = src
                            it["cat"] = cat
                            items.append(it)
                            got_cat += 1
                        if got_cat >= depth * 8:
                            break
                    per_cat.setdefault(cat, {"items": got_cat})
                    if len(cat_list) > 1:
                        time.sleep(0.3)
                try:
                    import zh as zhm
                    names = [it.get("name") or "" for it in items]
                    tr = zhm.translate(names)
                    for it in items:
                        it["name_zh"] = tr.get(it.get("name") or "")
                except Exception:
                    pass
                return self._json({"items": items, "page": page, "pagesFetched": depth,
                                   "cats": cat_list, "perCat": per_cat,
                                   "cat": cat_list[0], "sort": sort})

            if u.path == "/api/market/start":
                cats = q.get("cats", "all")
                pages_n = max(1, min(8, int(q.get("pages", "2"))))
                sorts = [s for s in (q.get("sorts") or "score").split(",") if s in dict((k, 1) for k, _, _ in SORTS)]
                if not sorts:
                    sorts = ["score"]
                if cats == "all":
                    cat_list = [(s, z, r) for s, z, r in CATEGORIES]
                else:
                    want = set(cats.split(","))
                    cat_list = [(s, z, r) for s, z, r in CATEGORIES if s in want]
                detail_n = max(0, min(20, int(q.get('detail', '0'))))
                try:
                    df = json.loads(q.get('df') or '{}')
                except Exception:
                    df = {}
                jid = uuid.uuid4().hex[:12]
                JOBS[jid] = {"progress": 0.0, "done": False, "error": None, "result": None,
                             "total": len(cat_list), "label": ""}
                t = threading.Thread(target=market_worker, args=(jid, cat_list, pages_n, sorts, detail_n, df), daemon=True)
                t.start()
                return self._json({"id": jid, "total": len(cat_list), "pages": pages_n,
                                   "sorts": sorts, "detail": detail_n, "df": df})

            if u.path == "/api/market/last":
                p = os.path.join(ROOT, "data", "market_last.json")
                try:
                    return self._json(json.load(open(p, encoding="utf-8")))
                except Exception:
                    return self._json({"rows": [], "built_at": None})

            if u.path == "/api/market/status":
                j = JOBS.get(q.get("id", ""))
                if not j:
                    return self._json({"error": "no such job"}, 404)
                return self._json(j)

            if u.path == "/api/product/full":
                try:
                    import pdp
                except Exception:
                    from . import pdp  # type: ignore
                skus = [s for s in (q.get("skus") or q.get("sku") or "").split(",") if s.strip()][:40]
                if not skus:
                    return self._json({"items": [], "error": "no sku"}, 400)
                out, errors = [], {}
                for sku in skus:
                    try:
                        main = ozon_get(f"/product/{sku}/", ttl=1800)
                        page2 = ozon_get(f"/product/{sku}/?layout_container=pdpPage2column&layout_page_index=2", ttl=1800)
                        rec = pdp.parse_full(main, page2)
                        rec["sku"] = rec["sku"] or sku
                        try:
                            import zh as zhm
                            rec["name_zh"] = zhm.one(rec.get("name") or "")
                            rec["country_zh"] = zhm.one(rec.get("country") or "")
                            rec["category_zh"] = zhm.one(rec.get("category") or "") if rec.get("category") else None
                            names = [a["name"] for a in rec.get("attributes") or []]
                            pairs = zhm.translate(names)
                            for a in rec.get("attributes") or []:
                                a["name_zh"] = pairs.get(a["name"])
                        except Exception:
                            pass
                        out.append(rec)
                    except Exception as e:
                        errors[sku] = str(e)[:200]
                    time.sleep(0.4)
                return self._json({"items": out, "errors": errors,
                                   "columns": [{"key": k, "label": v} for k, v in pdp.COLUMNS]})

            if u.path == "/api/product":
                sku = q.get("sku", "")
                data = ozon_get(f"/product/{sku}/", ttl=300)
                ws = (data or {}).get("widgetStates") or {}
                out = {"sku": sku, "images": [], "chars": [], "name": "", "first_review": None}
                for k, v in ws.items():
                    try:
                        o = json.loads(v) if isinstance(v, str) else v
                    except Exception:
                        continue
                    if k.startswith("webGallery"):
                        out["images"] = [i.get("src") for i in (o.get("images") or []) if i.get("src")]
                        out["name"] = o.get("name") or out["name"]
                    elif k.startswith("webShortCharacteristics"):
                        def _rich(node):
                            if not isinstance(node, dict):
                                return ""
                            return "".join(str(x.get("content") or x.get("text") or "")
                                           for x in (node.get("textRs") or []) if isinstance(x, dict))
                        for ch in o.get("characteristics") or []:
                            t = _rich(ch.get("title") or {})
                            vs = " / ".join(str(x.get("text") or "") for x in (ch.get("values") or []) if isinstance(x, dict))
                            if t and vs:
                                out["chars"].append([t, vs])
                d, _ = sku_listed_date(sku)
                out["listed_date"] = d
                return self._json(out)

            if u.path == "/api/export":
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)) if self.command == "POST" else b""
                rows = json.loads(body.decode("utf-8-sig")) if body else []
                out_dir = os.path.join(ROOT, "export")
                os.makedirs(out_dir, exist_ok=True)
                fn = "ozon_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join(out_dir, fn)
                export_xlsx(rows, path)
                return self._json({"ok": True, "file": path, "name": fn})

            self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            self._json({"error": str(e)[:500]}, 500)

    def do_POST(self):
        return self.do_GET()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    try:
        seed_map_from_categories()
    except Exception:
        pass
    try:
        cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        n = cfg.get("network") or {}
        if n.get("min_interval"):
            GOV.min_interval = float(n["min_interval"])
        if n.get("jitter"):
            GOV.jitter = float(n["jitter"])
    except Exception:
        pass
    print(f"Ozon 选品工作台 -> http://{a.host}:{a.port}/")
    print(f"节奏控制: 最小间隔 {GOV.min_interval}s / 抖动 {int(GOV.jitter*100)}% / 并发 1")
    print(f"依赖 Chrome 调试端口 {CDP_PORT}（--remote-debugging-port={CDP_PORT}）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()




