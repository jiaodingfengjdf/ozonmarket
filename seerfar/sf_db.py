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
    def upsert_products(self, rows):
        sql = (
            "INSERT INTO product(sku,title,brand,seller,price,sales,revenue,review_count,"
            "review_rating,category_id,category_cn,image_url,product_url,up_time,"
            "seller_type,raw,updated_at) VALUES("
            ":sku,:title,:brand,:seller,:price,:sales,:revenue,:review_count,"
            ":review_rating,:category_id,:category_cn,:image_url,:product_url,:up_time,"
            ":seller_type,:raw,:updated_at) ON CONFLICT(sku) DO UPDATE SET "
            "title=excluded.title,brand=excluded.brand,seller=excluded.seller,"
            "price=excluded.price,sales=excluded.sales,revenue=excluded.revenue,"
            "review_count=excluded.review_count,review_rating=excluded.review_rating,"
            "category_id=excluded.category_id,category_cn=excluded.category_cn,"
            "image_url=excluded.image_url,product_url=excluded.product_url,"
            "up_time=excluded.up_time,seller_type=excluded.seller_type,"
            "raw=excluded.raw,updated_at=excluded.updated_at"
        )
        now = time.time()
        keys = ("sku", "title", "brand", "seller", "price", "sales", "revenue",
                "review_count", "review_rating", "category_id", "category_cn",
                "image_url", "product_url", "up_time", "seller_type")
        seq = []
        for r in rows:
            if not r.get("sku"):
                continue
            d = {k: r.get(k) for k in keys}
            d["sku"] = str(d["sku"])
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
        allowed = {"sku", "title", "brand", "seller", "price", "sales", "revenue",
                   "review_count", "review_rating", "category_cn", "updated_at"}
        if order not in allowed:
            order = "revenue"
        direction = "ASC" if str(direction).upper() == "ASC" else "DESC"
        sql = "SELECT * FROM product" + ((" WHERE " + where) if where else "")
        sql += f" ORDER BY {order} {direction} LIMIT ? OFFSET ?"
        return self.q(sql, tuple(args) + (int(limit), int(offset)))

    def snapshot(self, sku, row):
        self.exec(
            "INSERT INTO product_snapshot(sku,day,price,sales,revenue,review_count,"
            "review_rating,stock,raw) VALUES(?,?,?,?,?,?,?,?,?)",
            (str(sku), today_str(), row.get("price"), row.get("sales"),
             row.get("revenue"), row.get("review_count"), row.get("review_rating"),
             row.get("stock"), dumps(row)))

    # ---------- 关键词 ----------
    def upsert_keywords(self, rows, kind=""):
        sql = (
            "INSERT INTO keyword(id,query,query_cn,kind,search_volume,growth30,"
            "competing_products,sellers,avg_price,conversion_sharing,market_space,"
            "categories,raw,updated_at) VALUES("
            ":id,:query,:query_cn,:kind,:search_volume,:growth30,:competing_products,"
            ":sellers,:avg_price,:conversion_sharing,:market_space,:categories,:raw,:updated_at) "
            "ON CONFLICT(id) DO UPDATE SET query=excluded.query,query_cn=excluded.query_cn,"
            "kind=excluded.kind,search_volume=excluded.search_volume,growth30=excluded.growth30,"
            "competing_products=excluded.competing_products,sellers=excluded.sellers,"
            "avg_price=excluded.avg_price,conversion_sharing=excluded.conversion_sharing,"
            "market_space=excluded.market_space,categories=excluded.categories,"
            "raw=excluded.raw,updated_at=excluded.updated_at"
        )
        now = time.time()
        keys = ("id", "query", "query_cn", "kind", "search_volume", "growth30",
                "competing_products", "sellers", "avg_price", "conversion_sharing",
                "market_space")
        seq = []
        for r in rows:
            d = {k: r.get(k) for k in keys}
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
        allowed = {"query", "query_cn", "search_volume", "growth30",
                   "competing_products", "sellers", "avg_price", "conversion_sharing",
                   "market_space", "updated_at", "kind"}
        if order not in allowed:
            order = "search_volume"
        sql = "SELECT * FROM keyword" + ((" WHERE " + where) if where else "")
        sql += f" ORDER BY {order} DESC LIMIT ? OFFSET ?"
        return self.q(sql, tuple(args) + (int(limit), int(offset)))

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
