# -*- coding: utf-8 -*-
"""Seerfar 类目字典。

数据源：用户提供的「Ozon类目.xlsx」（Seerfar 官方类目 ID 清单）。
  - 单列「类目ID」，共 10021 个：29 一级 / 618 二级 / 9374 三级
  - ID 本身就是层级路径：15621031_200000933_115949936
    父 ID = 去掉最后一段；因此不需要任何跨体系映射，也不需要 Ozon Seller API。
  - 表里只有 ID 没有名称；名称从 Seerfar 接口的 categoryInfo 里免费沉淀
    （查类目 / 市场热词 / 榜单 / 商品响应都会带中俄英三语名称与完整路径）。

重要：Seller API 的 description_category_id 与这套 ID 完全不通用，
不要把 Seller 类目 ID 直接传给 Seerfar 的 categoryId（实测返回 data: null）。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from sf_db import STORE

ROOT = Path(__file__).resolve().parent
DEFAULT_XLSX = ROOT / "data" / "ozon_categories.xlsx"
PATH_SPLIT = re.compile(r"\s*[/>]\s*|\s*>\s*")


def _mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


def _split_path(s):
    if not s:
        return []
    return [x.strip() for x in PATH_SPLIT.split(str(s)) if x.strip()]


def _levels(cid: str):
    """把层级式 ID 拆成从根到当前的累积 ID 列表。"""
    parts = str(cid).split("_")
    return ["_".join(parts[:i + 1]) for i in range(len(parts))]


def _row(cid, pid, level, cn="", ru="", en="", cn_path="", ru_path="",
         en_path="", leaf=1, cross_border=None, disabled=None, enriched=False):
    return {
        "id": str(cid), "pid": pid, "level": level,
        "cn": cn or "", "ru": ru or "", "en": en or "",
        "cn_path": cn_path or "", "ru_path": ru_path or "",
        "en_path": en_path or "", "leaf": int(leaf),
        "cross_border": cross_border, "disabled": disabled,
        "enriched_at": time.time() if enriched else None,
    }


class Catalog:
    def __init__(self, store=None, client=None):
        self.store = store or STORE
        self.client = client
        self._pending = []

    def attach(self, client):
        """注册响应钩子：任何接口返回里带 categoryInfo 都顺手补名称（零额外积分）。"""
        self.client = client
        if self.harvest not in client.on_response:
            client.on_response.append(self.harvest)
        return self

    # ---------- 初始化：导入 xlsx 类目表 ----------
    def import_xlsx(self, path=None) -> dict:
        """导入 Seerfar 官方类目表。

        表结构 6 列（10021 行全部填充）：
          类目ID | 类目名称（英文） | 类目名称（俄文） | 类目名称（中文） | 父类目ID | 层级
        按表头名定位列，避免列顺序变化时读错；导入后本地拼接三语全路径。
        """
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("缺少 openpyxl，请先执行: pip install openpyxl")
        p = Path(path) if path else DEFAULT_XLSX
        if not p.exists():
            raise FileNotFoundError(f"类目表不存在: {p}")
        wb = openpyxl.load_workbook(p, read_only=False, data_only=True)
        ws = wb["category"] if "category" in wb.sheetnames else wb.active
        it = ws.iter_rows(min_row=1, values_only=True)
        headers = [str(h).strip() if h is not None else "" for h in (next(it) or ())]

        def col(*keys):
            for k in keys:
                for i, h in enumerate(headers):
                    if k in h:
                        return i
            return None

        i_id, i_en, i_ru, i_cn = col("类目ID", "id"), col("英文", "en"), col("俄文", "ru"), col("中文", "cn")
        i_pid, i_lv = col("父类目", "pid"), col("层级", "level")
        if i_id is None:
            raise ValueError(f"表头里找不到「类目ID」列，实际表头: {headers}")

        raw = []
        for row in it:
            vals = list(row or [])

            def get(i):
                return (str(vals[i]).strip()
                        if i is not None and i < len(vals) and vals[i] is not None else "")

            cid = get(i_id)
            if not cid:
                continue
            lv = get(i_lv)
            raw.append({
                "id": cid,
                "en": get(i_en), "ru": get(i_ru), "cn": get(i_cn),
                "pid": get(i_pid) or ("_".join(cid.split("_")[:-1]) if "_" in cid else ""),
                "level": int(lv) if lv.isdigit() else len(cid.split("_")),
            })
        wb.close()

        pids = {r["pid"] for r in raw if r["pid"] and r["pid"] != "0"}
        by_id = {r["id"]: r for r in raw}
        # 本地拼接三语全路径（不调接口、不花积分）
        for r in raw:
            seg = r["id"].split("_")
            chain = ["_".join(seg[:i + 1]) for i in range(len(seg))]
            r["cn_path"] = " > ".join((by_id.get(x) or {}).get("cn", "") for x in chain)
            r["ru_path"] = " > ".join((by_id.get(x) or {}).get("ru", "") for x in chain)
            r["en_path"] = " > ".join((by_id.get(x) or {}).get("en", "") for x in chain)
            r["pid"] = None if (not r["pid"] or r["pid"] == "0") else r["pid"]
            r["leaf"] = 0 if r["id"] in pids else 1

        n = self.store.bulk_categories(
            [_row(r["id"], r["pid"], r["level"], r["cn"], r["ru"], r["en"],
                  r["cn_path"], r["ru_path"], r["en_path"], leaf=r["leaf"]) for r in raw],
            source="xlsx")
        self.store.set_meta("catalog_xlsx", {
            "path": str(p), "rows": n, "mtime": _mtime(p), "imported_at": time.time()})
        return {"file": str(p), "imported": n,
                "levels": {1: sum(1 for r in raw if r["level"] == 1),
                           2: sum(1 for r in raw if r["level"] == 2),
                           3: sum(1 for r in raw if r["level"] == 3)}}

    def ensure_imported(self):
        """类目表缺失/文件更新/存在未命名节点时自动重导（幂等，xlsx 为权威命名来源）。"""
        if not DEFAULT_XLSX.exists():
            if self.store.category_stats().get("total", 0) == 0:
                raise FileNotFoundError(f"缺少类目表: {DEFAULT_XLSX}")
            return {"imported": 0, "reason": "no xlsx, use existing rows"}
        last = self.store.get_meta("catalog_xlsx") or {}
        st = self.store.category_stats()
        if (last.get("mtime") == _mtime(DEFAULT_XLSX) and last.get("rows")
                and st.get("named", 0) >= st.get("total", 0)):
            return {"imported": 0, "reason": "up-to-date", "stats": st}
        return self.import_xlsx()

    # ---------- 名称沉淀（从任意 Seerfar 响应里免费提取） ----------
    def harvest(self, name, data):
        found = []
        self._walk(data, found)
        if found:
            self.store.bulk_categories(found, source="api")
        return len(found)

    def _walk(self, node, found, depth=0):
        if depth > 12 or len(found) > 400:
            return
        if isinstance(node, list):
            for x in node[:400]:
                self._walk(x, found, depth + 1)
            return
        if not isinstance(node, dict):
            return
        # 标准结构：categoryInfo: {category:{...}, fullCategoryId:[...], cnTitlePath:"..."}
        ci = node.get("categoryInfo")
        if isinstance(ci, dict):
            self._absorb(ci, found)
        # 热词结构：categoryInfos: [{id,titleCn,titleRu,cnTitlePath,...}]
        cis = node.get("categoryInfos")
        if isinstance(cis, list):
            for c in cis:
                if isinstance(c, dict):
                    self._absorb_list_item(c, found)
        for k, v in node.items():
            if k in ("categoryInfo", "categoryInfos"):
                continue
            if isinstance(v, (dict, list)):
                self._walk(v, found, depth + 1)

    def _absorb(self, ci, found):
        cat = ci.get("category") or {}
        cid = cat.get("id") or (ci.get("fullCategoryId") or [None])[-1]
        if not cid:
            return
        full = ci.get("fullCategoryId") or _levels(cid)
        cn_path = ci.get("cnTitlePath") or ""
        ru_path = ci.get("titlePath") or ""
        en_path = ci.get("enTitlePath") or ""
        self._absorb_path(cid, full, cn_path, ru_path, en_path, found,
                          cross_border=cat.get("crossBorderSellable"),
                          disabled=cat.get("disabled"),
                          leaf_cn=cat.get("cnTitle"), leaf_ru=cat.get("title"),
                          leaf_en=cat.get("enTitle"))

    def _absorb_list_item(self, c, found):
        cid = c.get("id")
        if not cid:
            return
        full = _levels(cid)
        self._absorb_path(cid, full, c.get("cnTitlePath") or "",
                          c.get("titlePath") or "", c.get("enTitlePath") or "",
                          found, cross_border=c.get("crossBorderSellable"),
                          leaf_cn=c.get("titleCn") or c.get("cnTitle"),
                          leaf_ru=c.get("titleRu") or c.get("title"),
                          leaf_en=c.get("titleEn") or c.get("enTitle"))

    def _absorb_path(self, cid, full_ids, cn_path, ru_path, en_path, found,
                     cross_border=None, disabled=None,
                     leaf_cn=None, leaf_ru=None, leaf_en=None):
        """路径分段与层级 ID 一一对应时，一次把整条路径各级名称都补上。"""
        if not isinstance(full_ids, list) or not full_ids:
            full_ids = _levels(cid)
        full_ids = [str(x) for x in full_ids]
        cn_seg = _split_path(cn_path)
        ru_seg = _split_path(ru_path)
        en_seg = _split_path(en_path)
        n = len(full_ids)
        for i, node_id in enumerate(full_ids):
            parts = node_id.split("_")
            pid = "_".join(parts[:-1]) if len(parts) > 1 else None
            cn = cn_seg[i] if len(cn_seg) == n else (leaf_cn if i == n - 1 else "")
            ru = ru_seg[i] if len(ru_seg) == n else (leaf_ru if i == n - 1 else "")
            en = en_seg[i] if len(en_seg) == n else (leaf_en if i == n - 1 else "")
            found.append(_row(
                node_id, pid, len(parts), cn, ru, en,
                " > ".join(cn_seg[:i + 1]) if len(cn_seg) == n else "",
                " > ".join(ru_seg[:i + 1]) if len(ru_seg) == n else "",
                " > ".join(en_seg[:i + 1]) if len(en_seg) == n else "",
                leaf=1, cross_border=cross_border if i == n - 1 else None,
                disabled=disabled if i == n - 1 else None,
                enriched=bool(cn or ru or en)))

    # ---------- 主动补全（会花积分，需显式调用） ----------
    def enrich(self, cid: str) -> dict:
        """调一次查类目接口，用返回的 categoryInfo 补全该节点及整条路径名称。"""
        if not self.client:
            raise RuntimeError("需要先 attach(client)")
        page = {"pageNumber": 1, "pageSize": 1,
                "orders": [{"field": "revenue", "direction": "DESC"}]}
        before = self.store.category(cid) or {}
        res = self.client.call("category", {"categoryId": cid, "page": page})
        after = self.store.category(cid) or {}
        d = res.data or {}
        return {"id": cid, "ok": bool(d), "cached": res.cached,
                "cn": after.get("cn") or before.get("cn", ""),
                "cn_path": after.get("cn_path", ""),
                "total_revenue": d.get("totalRevenue"),
                "total_sales": d.get("totalSales")}

    def enrich_level(self, level=1, limit=None, only_unnamed=True, progress=None):
        """批量补全某一层的中文名。level=1 共 29 个，约 290 积分（一次性投入，永久存库）。"""
        if not self.client:
            raise RuntimeError("需要先 attach(client)")
        sql = "SELECT id, cn FROM category WHERE level=?"
        if only_unnamed:
            sql += " AND (cn IS NULL OR cn='')"
        sql += " ORDER BY id"
        rows = self.store.q(sql, (level,))
        if limit:
            rows = rows[:int(limit)]
        out = []
        for i, r in enumerate(rows, 1):
            try:
                out.append(self.enrich(r["id"]))
            except Exception as e:
                out.append({"id": r["id"], "ok": False, "error": str(e)})
            if progress:
                progress(i, len(rows), out[-1])
        return out

    # ---------- 查询 / 导航 ----------
    def stats(self):
        return self.store.category_stats()

    def tree(self, parent=None, level=None):
        if parent:
            rows = self.store.children(parent)
        elif level == 1 or parent is None:
            rows = self.store.children(None)
        else:
            rows = self.store.q("SELECT * FROM category WHERE level=? ORDER BY cn,id LIMIT 3000",
                                (level,))
        out = []
        for r in rows:
            kids = self.store.q1("SELECT COUNT(*) AS n FROM category WHERE pid=?", (r["id"],))
            out.append({
                "id": r["id"], "pid": r["pid"], "level": r["level"],
                "cn": r["cn"] or r["id"], "ru": r["ru"], "en": r["en"],
                "cn_path": r["cn_path"], "named": bool(r["cn"]),
                "leaf": bool(r["leaf"]), "children": kids["n"] if kids else 0,
                "cross_border": r["cross_border"],
            })
        return out

    def search(self, q, limit=100):
        return self.store.search_categories(q, limit)

    def resolve(self, q) -> str | None:
        """把用户输入（Seerfar ID / 中文名 / 俄文名 / 英文名）解析成 categoryId。"""
        q = (q or "").strip()
        if not q:
            return None
        if re.fullmatch(r"[\d_]+", q):
            return q if self.store.category(q) else q
        rows = self.store.search_categories(q, 1)
        return rows[0]["id"] if rows else None

    def leaves(self, cid, limit=200):
        """取某节点下所有三级（叶子）子类目，供「查类目」直接下钻出商品清单。

        用 substr 而不是 LIKE：LIKE 里的 `_` 是单字符通配符，会误匹配类目 ID。
        """
        rows = self.store.q(
            "SELECT id, cn, ru, cn_path FROM category WHERE level=3 "
            "AND substr(id,1,length(?)+1)=?||'_' ORDER BY cn, id LIMIT ?",
            (str(cid), str(cid), int(limit)))
        return [{"id": r["id"], "cn": r["cn"] or r["id"], "named": bool(r["cn"]),
                 "cn_path": r["cn_path"] or ""} for r in rows]

    def subtree(self, cid, limit=500):
        ids = self.store.subtree_ids(cid)[:limit]
        return {"id": cid, "count": len(ids), "ids": ids}


CATALOG = Catalog()


def get_catalog(client=None):
    if client:
        CATALOG.attach(client)
    return CATALOG
