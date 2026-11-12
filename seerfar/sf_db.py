# -*- coding: utf-8 -*-
"""Seerfar 选品台 · SQLite 数据层。

职责：API 响应缓存、调用日志与积分记账、类目字典、商品/关键词/店铺快照。
只用标准库，WAL 模式；每个线程独立连接，写操作统一加锁，供本地 Web 服务并发使用。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "seerfar.db"


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def loads(s, default=None):
    if not s:
        return default
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return default


SCHEMA = """
CREATE TABLE IF NOT EXISTS api_cache (
  key        TEXT PRIMARY KEY,
  path       TEXT NOT NULL,
  body       TEXT,
  data       TEXT,
  created_at REAL NOT NULL,
  ttl        REAL NOT NULL,
  hits       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cache_path ON api_cache(path);

CREATE TABLE IF NOT EXISTS api_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         REAL NOT NULL,
  day        TEXT NOT NULL,
  path       TEXT,
  method     TEXT,
  ok         INTEGER,
  code       INTEGER,
  cached     INTEGER DEFAULT 0,
  elapsed_ms INTEGER,
  cost       REAL DEFAULT 0,
  err        TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_day ON api_log(day);
CREATE INDEX IF NOT EXISTS idx_log_ts  ON api_log(ts);

CREATE TABLE IF NOT EXISTS category (
  id            TEXT PRIMARY KEY,
  pid           TEXT,
  level         INTEGER NOT NULL,
  cn            TEXT DEFAULT '',
  ru            TEXT DEFAULT '',
  en            TEXT DEFAULT '',
  cn_path       TEXT DEFAULT '',
  ru_path       TEXT DEFAULT '',
  en_path       TEXT DEFAULT '',
  leaf          INTEGER DEFAULT 1,
  cross_border  INTEGER,
  disabled      INTEGER,
  source        TEXT DEFAULT 'xlsx',
  enriched_at   REAL,
  updated_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_cat_pid   ON category(pid);
CREATE INDEX IF NOT EXISTS idx_cat_level ON category(level);

CREATE TABLE IF NOT EXISTS product (
  sku           TEXT PRIMARY KEY,
  title         TEXT,
  brand         TEXT,
  seller        TEXT,
  price         REAL,
  sales         REAL,
  revenue       REAL,
  review_count  INTEGER,
  review_rating REAL,
  category_id   TEXT,
  category_cn   TEXT,
  image_url     TEXT,
  product_url   TEXT,
  up_time       INTEGER,
  seller_type   INTEGER,
  raw           TEXT,
  updated_at    REAL
);
CREATE INDEX IF NOT EXISTS idx_prod_cat ON product(category_id);

-- 阶段3 扩展列（旧库通过 _migrate 自动补列）
CREATE TABLE IF NOT EXISTS favorite (
  sku        TEXT PRIMARY KEY,
  tags       TEXT DEFAULT '',
  note       TEXT DEFAULT '',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS product_snapshot (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  sku           TEXT,
  day           TEXT,
  price         REAL,
  sales         REAL,
  revenue       REAL,
  review_count  INTEGER,
  review_rating REAL,
  stock         INTEGER,
  raw           TEXT
);
CREATE INDEX IF NOT EXISTS idx_snap_sku_day ON product_snapshot(sku, day);

CREATE TABLE IF NOT EXISTS keyword (
  id                  TEXT PRIMARY KEY,
  query               TEXT,
  query_cn            TEXT,
  kind                TEXT,
  search_volume       REAL,
  growth30            REAL,
  competing_products  INTEGER,
  sellers             INTEGER,
  avg_price           REAL,
  conversion_sharing  REAL,
  market_space        REAL,
  categories          TEXT,
  raw                 TEXT,
  updated_at          REAL
);
CREATE INDEX IF NOT EXISTS idx_kw_query ON keyword(query);

CREATE TABLE IF NOT EXISTS shop (
  id          TEXT PRIMARY KEY,
  name        TEXT,
  rating      REAL,
  product_count INTEGER,
  total_sales REAL,
  total_revenue REAL,
  raw         TEXT,
  updated_at  REAL
);

CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT
);
"""


# ---------- 阶段3：扩展列与本地筛选白名单 ----------
PRODUCT_EXT = {
    "weight": "REAL", "volume": "REAL", "dimension": "TEXT",
    "gross_margin": "REAL", "drr": "REAL",
    "conv_to_cart_pdp": "REAL", "conv_to_cart_search": "REAL",
    "conv_view_to_order": "REAL", "order_conversion_rate": "REAL",
    "return_cancellation_rate": "REAL", "variants": "REAL", "qa": "REAL",
    "views": "REAL", "session_count": "REAL", "session_count_search": "REAL",
    "sales_rate": "REAL", "revenue_rate": "REAL", "up_days": "REAL", "up_months": "REAL",
    "discount": "REAL", "promo_revenue_share": "REAL", "missed_revenue": "REAL",
    "profit": "REAL", "cross_border": "INTEGER", "fulfillment": "TEXT",
    "seller_id": "TEXT", "brand_id": "TEXT", "labels_text": "TEXT",
    "opportunity": "REAL", "net_profit": "REAL", "net_margin": "REAL",
    "breakeven": "REAL", "suggested": "REAL",
}
KEYWORD_EXT = {"title_density": "REAL", "relevancy": "REAL",
               "word_count": "REAL", "opportunity": "REAL"}

PRODUCT_FILTER_NUM = [
    "price", "sales", "revenue", "review_count", "review_rating", "gross_margin", "drr",
    "conv_to_cart_pdp", "order_conversion_rate", "return_cancellation_rate", "variants",
    "weight", "volume", "qa", "views", "session_count_search", "session_count",
    "opportunity", "sales_rate", "revenue_rate", "net_profit", "net_margin", "up_days",
]
PRODUCT_SORT_FIELDS = set(PRODUCT_FILTER_NUM) | {
    "sku", "title", "brand", "seller", "category_cn", "updated_at", "breakeven", "suggested"}
KEYWORD_FILTER_NUM = ["search_volume", "growth30", "competing_products", "sellers",
                      "avg_price", "conversion_sharing", "market_space", "title_density",
                      "relevancy", "word_count", "opportunity"]
KEYWORD_SORT_FIELDS = set(KEYWORD_FILTER_NUM) | {"query", "query_cn", "updated_at"}


def _n(v):
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _range_sql(fields, f, where, args):
    for k in fields:
        lo, hi = _n(f.get(k + "_min")), _n(f.get(k + "_max"))
        if lo is not None:
            where.append(f"{k} >= ?")
            args.append(lo)
        if hi is not None:
            where.append(f"{k} <= ?")
            args.append(hi)


def product_where(f: dict):
    f = f or {}
    where, args = [], []
    q = str(f.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        where.append("(title LIKE ? OR brand LIKE ? OR seller LIKE ? OR category_cn LIKE ? OR sku LIKE ?)")
        args += [like] * 5
    for k in ("category_id", "seller", "brand"):
        v = f.get(k)
        if v:
            where.append(f"{k} = ?")
            args.append(str(v))
    _range_sql(PRODUCT_FILTER_NUM, f, where, args)
    if f.get("favorite_only"):
        where.append("sku IN (SELECT sku FROM favorite)")
    if str(f.get("has_opportunity") or "") in ("1", "true"):
        where.append("opportunity IS NOT NULL")
    return (" AND ".join(where), args)


def keyword_where(f: dict):
    f = f or {}
    where, args = [], []
    q = str(f.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        where.append("(query LIKE ? OR query_cn LIKE ?)")
        args += [like, like]
    if f.get("kind"):
        where.append("kind = ?")
        args.append(str(f["kind"]))
    _range_sql(KEYWORD_FILTER_NUM, f, where, args)
    return (" AND ".join(where), args)


class Store:
    """SQLite 封装。所有方法线程安全。"""

    def __init__(self, path=None):
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._wlock = threading.Lock()
        self.init()

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=15000")
            self._local.conn = c
        return c

    def init(self):
        with self._wlock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()
        self._migrate()

    def _migrate(self):
        """旧库自动补列（阶段3 扩字段），幂等。"""
        for table, ext in (("product", PRODUCT_EXT), ("keyword", KEYWORD_EXT)):
            have = {r["name"] for r in self.q(f"PRAGMA table_info({table})")}
            for col, typ in ext.items():
                if col not in have:
                    self.exec(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        self.exec("CREATE INDEX IF NOT EXISTS idx_prod_opp ON product(opportunity)")
        self.exec("CREATE INDEX IF NOT EXISTS idx_prod_margin ON product(net_margin)")
        self.exec("CREATE INDEX IF NOT EXISTS idx_kw_opp ON keyword(opportunity)")

    # ---------- 基础 ----------
    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def q1(self, sql, args=()):
        r = self.conn.execute(sql, args).fetchone()
        return dict(r) if r else None

    def exec(self, sql, args=()):
        with self._wlock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def execmany(self, sql, seq):
        with self._wlock:
            cur = self.conn.executemany(sql, seq)
            self.conn.commit()
            return cur

    # ---------- API 缓存 ----------
    def cache_get(self, key: str, now: float | None = None):
        """命中且未过期返回 data；否则 None。命中即累加 hits。"""
        now = now or time.time()
        row = self.q1(
            "SELECT data, hits FROM api_cache WHERE key=? AND (created_at + ttl) > ?",
            (key, now),
        )
        if not row:
            return None
        with self._wlock:
            self.conn.execute("UPDATE api_cache SET hits=hits+1 WHERE key=?", (key,))
            self.conn.commit()
        return loads(row["data"])

    def cache_put(self, key, path, body, data, ttl):
        self.exec(
            "INSERT OR REPLACE INTO api_cache(key,path,body,data,created_at,ttl,hits) "
            "VALUES(?,?,?,?,?,?,COALESCE((SELECT hits FROM api_cache WHERE key=?),0))",
            (key, path, dumps(body), dumps(data), time.time(), float(ttl), key),
        )

    def cache_clear(self, path_like=None):
        if path_like:
            cur = self.exec("DELETE FROM api_cache WHERE path LIKE ?", (path_like,))
        else:
            cur = self.exec("DELETE FROM api_cache")
        return cur.rowcount

    def cache_stats(self):
        r = self.q1("SELECT COUNT(*) AS n, COALESCE(SUM(hits),0) AS hits, "
                    "COALESCE(SUM(LENGTH(data)),0) AS bytes FROM api_cache") or {}
        return {"entries": r.get("n", 0), "hits": r.get("hits", 0),
                "bytes": r.get("bytes", 0)}

    # ---------- 调用日志 / 积分 ----------
    def log_call(self, path, method, ok, code, cached, elapsed_ms, cost, err=""):
        self.exec(
            "INSERT INTO api_log(ts,day,path,method,ok,code,cached,elapsed_ms,cost,err) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (time.time(), today_str(), path, method, 1 if ok else 0, code,
             1 if cached else 0, int(elapsed_ms), float(cost), str(err or "")[:500]),
        )

    def spent_today(self):
        r = self.q1("SELECT COALESCE(SUM(cost),0) AS c FROM api_log "
                    "WHERE day=? AND cached=0", (today_str(),))
        return float(r["c"]) if r else 0.0

    def spent_total(self):
        """历史累计估算消耗（用于余额安全线判断，不区分日期）。"""
        r = self.q1("SELECT COALESCE(SUM(cost),0) AS c FROM api_log WHERE cached=0")
        return float(r["c"]) if r else 0.0

    def calls_today(self):
        r = self.q1("SELECT COUNT(*) AS n, COALESCE(SUM(cached=0),0) AS live "
                    "FROM api_log WHERE day=?", (today_str(),))
        return dict(r or {"n": 0, "live": 0})

    def recent_logs(self, limit=50):
        return self.q("SELECT * FROM api_log ORDER BY id DESC LIMIT ?", (limit,))

    def daily_usage(self, days=14):
        return self.q(
            "SELECT day, COUNT(*) AS calls, SUM(cached=0) AS live, "
            "ROUND(SUM(cost),1) AS credit FROM api_log "
            "GROUP BY day ORDER BY day DESC LIMIT ?", (days,))

    # ---------- 类目 ----------
    def upsert_category(self, row, source="xlsx"):
        self.exec(
            "INSERT INTO category(id,pid,level,cn,ru,en,cn_path,ru_path,en_path,leaf,"
            "cross_border,disabled,source,enriched_at,updated_at) "
            "VALUES(:id,:pid,:level,:cn,:ru,:en,:cn_path,:ru_path,:en_path,:leaf,"
            ":cross_border,:disabled,:source,:enriched_at,:updated_at) "
            "ON CONFLICT(id) DO UPDATE SET "
            "cn=CASE WHEN excluded.cn<>'' THEN excluded.cn ELSE category.cn END,"
            "ru=CASE WHEN excluded.ru<>'' THEN excluded.ru ELSE category.ru END,"
            "en=CASE WHEN excluded.en<>'' THEN excluded.en ELSE category.en END,"
            "cn_path=CASE WHEN excluded.cn_path<>'' THEN excluded.cn_path ELSE category.cn_path END,"
            "ru_path=CASE WHEN excluded.ru_path<>'' THEN excluded.ru_path ELSE category.ru_path END,"
            "en_path=CASE WHEN excluded.en_path<>'' THEN excluded.en_path ELSE category.en_path END,"
            "cross_border=COALESCE(excluded.cross_border,category.cross_border),"
            "disabled=COALESCE(excluded.disabled,category.disabled),"
            "enriched_at=COALESCE(excluded.enriched_at,category.enriched_at),"
            "updated_at=excluded.updated_at",
            dict(row, source=source),
        )

    def bulk_categories(self, rows, source="xlsx"):
        """批量导入/更新类目。rows 为完整字段 dict 列表。"""
        sql = (
            "INSERT INTO category(id,pid,level,cn,ru,en,cn_path,ru_path,en_path,leaf,"
            "cross_border,disabled,source,enriched_at,updated_at) "
            "VALUES(:id,:pid,:level,:cn,:ru,:en,:cn_path,:ru_path,:en_path,:leaf,"
            ":cross_border,:disabled,:source,:enriched_at,:updated_at) "
            "ON CONFLICT(id) DO UPDATE SET "
            "cn=CASE WHEN excluded.cn<>'' THEN excluded.cn ELSE category.cn END,"
            "ru=CASE WHEN excluded.ru<>'' THEN excluded.ru ELSE category.ru END,"
            "en=CASE WHEN excluded.en<>'' THEN excluded.en ELSE category.en END,"
            "cn_path=CASE WHEN excluded.cn_path<>'' THEN excluded.cn_path ELSE category.cn_path END,"
            "ru_path=CASE WHEN excluded.ru_path<>'' THEN excluded.ru_path ELSE category.ru_path END,"
            "en_path=CASE WHEN excluded.en_path<>'' THEN excluded.en_path ELSE category.en_path END,"
            "cross_border=COALESCE(excluded.cross_border,category.cross_border),"
            "disabled=COALESCE(excluded.disabled,category.disabled),"
            "enriched_at=COALESCE(excluded.enriched_at,category.enriched_at),"
            "updated_at=excluded.updated_at"
        )
        now = time.time()
        seq = []
        for r in rows:
            d = {k: r.get(k) for k in (
                "id", "pid", "level", "cn", "ru", "en", "cn_path", "ru_path",
                "en_path", "leaf", "cross_border", "disabled", "enriched_at")}
            d["source"] = source
            d["updated_at"] = now
            d["cn"] = d["cn"] or ""
            d["ru"] = d["ru"] or ""
            d["en"] = d["en"] or ""
            d["cn_path"] = d["cn_path"] or ""
            d["ru_path"] = d["ru_path"] or ""
            d["en_path"] = d["en_path"] or ""
            seq.append(d)
        self.execmany(sql, seq)
        return len(seq)

    def category(self, cid):
        return self.q1("SELECT * FROM category WHERE id=?", (cid,))

    def children(self, pid=None, level=None, limit=2000):
        if pid is None:
            return self.q("SELECT * FROM category WHERE pid IS NULL OR pid='' "
                          "ORDER BY cn, id LIMIT ?", (limit,))
        return self.q("SELECT * FROM category WHERE pid=? ORDER BY cn, id LIMIT ?",
                      (pid, limit))

    def category_stats(self):
        r = self.q1("SELECT COUNT(*) AS total, SUM(CASE WHEN cn<>'' THEN 1 ELSE 0 END) AS named, "
                    "SUM(level=1) AS l1, SUM(level=2) AS l2, SUM(level=3) AS l3 "
                    "FROM category") or {}
        return {k: (v or 0) for k, v in r.items()}

    def search_categories(self, kw, limit=100):
        like = "%" + kw.strip() + "%"
        return self.q(
            "SELECT * FROM category WHERE cn LIKE ? OR ru LIKE ? OR en LIKE ? "
            "OR cn_path LIKE ? OR id LIKE ? ORDER BY level, cn LIMIT ?",
            (like, like, like, like, like, limit))

    def subtree_ids(self, cid, max_depth=3):
        """取某节点及其所有后代 ID（靠 ID 前缀，不递归查库）。"""
        pref = cid + "_"
        rows = self.q("SELECT id FROM category WHERE id=? OR id LIKE ? ORDER BY level, id",
                      (cid, pref + "%"))
        return [r["id"] for r in rows]

    # ---------- 商品 ----------
    _PRODUCT_BASE = ("sku", "title", "brand", "seller", "price", "sales", "revenue",
                     "review_count", "review_rating", "category_id", "category_cn",
                     "image_url", "product_url", "up_time", "seller_type")

    def upsert_products(self, rows):
        cols = list(self._PRODUCT_BASE) + list(PRODUCT_EXT)
        sql = ("INSERT INTO product(" + ",".join(cols) + ") VALUES("
               + ",".join(":" + c for c in cols) + ") ON CONFLICT(sku) DO UPDATE SET "
               + ",".join(f"{c}=excluded.{c}" for c in cols if c != "sku"))
        now = time.time()
        seq = []
        for r in rows:
            if not r.get("sku"):
                continue
            d = {c: r.get(c) for c in cols}
            d["sku"] = str(d["sku"])
            d["fulfillment"] = r.get("fulfillment_text") or r.get("fulfillment")
            d["raw"] = dumps(r.get("raw") or r)
            d["updated_at"] = now
            seq.append(d)
        if seq:
            self.execmany(sql, seq)
        return len(seq)

    def product_count(self):
        r = self.q1("SELECT COUNT(*) AS n FROM product")
        return r["n"] if r else 0

    def products(self, where="", args=(), order="revenue", direction="DESC",
                 limit=50, offset=0):
        allowed = PRODUCT_SORT_FIELDS
        if order not in allowed:
            order = "revenue"
        direction = "ASC" if str(direction).upper() == "ASC" else "DESC"
        sql = "SELECT * FROM product" + ((" WHERE " + where) if where else "")
        sql += f" ORDER BY {order} {direction} LIMIT ? OFFSET ?"
        return self.q(sql, tuple(args) + (int(limit), int(offset)))

    def products_page(self, filters=None, order="revenue", direction="DESC",
                      limit=50, offset=0):
        """本地库筛选 + 分页：返回 (rows, total)。0 积分。"""
        where, args = product_where(filters or {})
        tail = (" WHERE " + where) if where else ""
        total = self.q1("SELECT COUNT(*) AS n FROM product" + tail, tuple(args))
        rows = self.products(where, args, order, direction, limit, offset)
        return rows, (total["n"] if total else 0)

    def product_by_sku(self, sku):
        return self.q1("SELECT * FROM product WHERE sku=?", (str(sku),))

    def update_profit(self, rows):
        """把利润计算结果写回本地库（net_profit / net_margin / breakeven / suggested）。"""
        seq = []
        for r in rows:
            if not r.get("sku"):
                continue
            seq.append({"sku": str(r["sku"]), "net_profit": _n(r.get("net_profit")),
                        "net_margin": _n(r.get("net_margin")),
                        "breakeven": _n(r.get("breakeven")),
                        "suggested": _n(r.get("suggested"))})
        if seq:
            self.execmany(
                "UPDATE product SET net_profit=:net_profit, net_margin=:net_margin, "
                "breakeven=:breakeven, suggested=:suggested WHERE sku=:sku", seq)
        return len(seq)

    # ---------- 收藏 ----------
    def favorite_toggle(self, sku, tags="", note=""):
        sku = str(sku)
        hit = self.q1("SELECT sku FROM favorite WHERE sku=?", (sku,))
        if hit:
            self.exec("DELETE FROM favorite WHERE sku=?", (sku,))
            return {"sku": sku, "favorite": False}
        self.exec("INSERT INTO favorite(sku,tags,note,created_at) VALUES(?,?,?,?)",
                  (sku, tags or "", note or "", time.time()))
        return {"sku": sku, "favorite": True}

    def favorites(self, limit=2000):
        return self.q("SELECT f.sku, f.tags, f.note, f.created_at, p.title, p.price, p.sales, "
                      "p.revenue, p.review_rating, p.review_count, p.opportunity, p.net_margin, "
                      "p.category_cn, p.image_url, p.product_url "
                      "FROM favorite f LEFT JOIN product p ON p.sku=f.sku "
                      "ORDER BY f.created_at DESC LIMIT ?", (int(limit),))

    def favorite_sku_set(self):
        return {r["sku"] for r in self.q("SELECT sku FROM favorite")}

    def snapshot(self, sku, row):
        self.exec(
            "INSERT INTO product_snapshot(sku,day,price,sales,revenue,review_count,"
            "review_rating,stock,raw) VALUES(?,?,?,?,?,?,?,?,?)",
            (str(sku), today_str(), row.get("price"), row.get("sales"),
             row.get("revenue"), row.get("review_count"), row.get("review_rating"),
             row.get("stock"), dumps(row)))

    # ---------- 关键词 ----------
    _KW_BASE = ("id", "query", "query_cn", "kind", "search_volume", "growth30",
                "competing_products", "sellers", "avg_price", "conversion_sharing",
                "market_space", "categories")

    def upsert_keywords(self, rows, kind=""):
        cols = list(self._KW_BASE) + list(KEYWORD_EXT)
        sql = ("INSERT INTO keyword(" + ",".join(cols) + ") VALUES("
               + ",".join(":" + c for c in cols) + ") ON CONFLICT(id) DO UPDATE SET "
               + ",".join(f"{c}=excluded.{c}" for c in cols if c != "id"))
        now = time.time()
        seq = []
        for r in rows:
            d = {c: r.get(c) for c in cols}
            d["id"] = str(r.get("id") or (kind + ":" + str(r.get("query") or "")))
            d["kind"] = kind or r.get("kind") or ""
            d["categories"] = dumps(r.get("categories") or [])
            d["raw"] = dumps(r.get("raw") or r)
            d["updated_at"] = now
            seq.append(d)
        if seq:
            self.execmany(sql, seq)
        return len(seq)

    def keyword_count(self):
        r = self.q1("SELECT COUNT(*) AS n FROM keyword")
        return r["n"] if r else 0

    def keywords(self, where="", args=(), order="search_volume", limit=50, offset=0):
        allowed = KEYWORD_SORT_FIELDS
        if order not in allowed:
            order = "search_volume"
        direction = "ASC" if str(order) in ("query", "query_cn") else "DESC"
        sql = "SELECT * FROM keyword" + ((" WHERE " + where) if where else "")
        sql += f" ORDER BY {order} {direction} LIMIT ? OFFSET ?"
        return self.q(sql, tuple(args) + (int(limit), int(offset)))

    def keywords_page(self, filters=None, order="search_volume", limit=50, offset=0):
        where, args = keyword_where(filters or {})
        tail = (" WHERE " + where) if where else ""
        total = self.q1("SELECT COUNT(*) AS n FROM keyword" + tail, tuple(args))
        return self.keywords(where, args, order, limit, offset), (total["n"] if total else 0)

    # ---------- 店铺 / meta ----------
    def upsert_shop(self, row):
        self.exec(
            "INSERT INTO shop(id,name,rating,product_count,total_sales,total_revenue,raw,updated_at) "
            "VALUES(:id,:name,:rating,:product_count,:total_sales,:total_revenue,:raw,:updated_at) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name,rating=excluded.rating,"
            "product_count=excluded.product_count,total_sales=excluded.total_sales,"
            "total_revenue=excluded.total_revenue,raw=excluded.raw,updated_at=excluded.updated_at",
            dict(row, updated_at=time.time()))

    def set_meta(self, k, v):
        self.exec("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, dumps(v)))

    def get_meta(self, k, default=None):
        r = self.q1("SELECT v FROM meta WHERE k=?", (k,))
        return loads(r["v"], default) if r else default


# 全局单例：客户端 / 服务端 / CLI 共用一份连接池与限速器
STORE = Store()
