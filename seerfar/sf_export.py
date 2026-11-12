# -*- coding: utf-8 -*-
"""XLSX / CSV 导出。

选品结果按中文表头宽表输出；数值保持数值类型（Excel 可直接排序/计算），
长文本不截断，图片只写 URL 不下载（避免几百张图拖慢导出）。
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sf_select import KEYWORD_COLUMNS, PRODUCT_COLUMNS

ROOT = Path(__file__).resolve().parent
EXPORT_DIR = ROOT / "export"


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def _safe_sheet_name(name: str) -> str:
    for ch in '[]:*?/\\':
        name = name.replace(ch, "_")
    return name[:31] or "Sheet"


def export_workbook(sheets, filename=None, out_dir=None) -> Path:
    """sheets: [(sheet名, rows, columns)]，columns 为 [(中文表头, 数据键), ...]。"""
    out = Path(out_dir) if out_dir else EXPORT_DIR
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # HTTP Content-Disposition 只能安全承载 ASCII 文件名，统一转成 ASCII
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(filename or f"seerfar_products_{stamp}"))
    name = (name.strip("_") or f"seerfar_export_{stamp}")[:90]
    if not name.lower().endswith(".xlsx"):
        name += ".xlsx"
    path = out / name

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return _export_csv_fallback(sheets, path.with_suffix(".csv"))

    wb = Workbook()
    wb.remove(wb.active)
    head_fill = PatternFill("solid", fgColor="1F4E79")
    head_font = Font(color="FFFFFF", bold=True, size=11)

    for sheet_name, rows, columns in sheets:
        ws = wb.create_sheet(_safe_sheet_name(sheet_name))
        ws.append([h for h, _ in columns])
        for c in range(1, len(columns) + 1):
            cell = ws.cell(row=1, column=c)
            cell.fill = head_fill
            cell.font = head_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for r in rows or []:
            ws.append([_cell(r.get(k)) for _, k in columns])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}1"
        # 自适应列宽（中文按 2 个字符宽度估算）
        for i, (header, key) in enumerate(columns, 1):
            width = max(10, min(46, len(str(header)) * 2 + 4))
            for r in (rows or [])[:200]:
                v = _cell(r.get(key))
                if isinstance(v, str):
                    width = max(width, min(46, len(v[:60]) * 1.4 + 3))
            ws.column_dimensions[get_column_letter(i)].width = width
        # 数值列显示千分位
        numeric_keys = {"price", "sales", "revenue", "review_count", "views",
                        "search_volume", "competing_products", "sellers", "avg_price",
                        "total_sales", "total_revenue"}
        for i, (_, key) in enumerate(columns, 1):
            if key in numeric_keys:
                for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                    row[0].number_format = "#,##0.##"
    wb.save(path)
    return path


def _export_csv_fallback(sheets, path: Path) -> Path:
    sheet_name, rows, columns = sheets[0]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([h for h, _ in columns])
        for r in rows or []:
            w.writerow([_cell(r.get(k)) for _, k in columns])
    return path


def export_products(rows, filename=None, title="商品清单"):
    return export_workbook([(title, rows, PRODUCT_COLUMNS)], filename)


def export_keywords(rows, filename=None, title="关键词"):
    return export_workbook([(title, rows, KEYWORD_COLUMNS)], filename)


def export_full(products=None, keywords=None, overview=None, filename=None):
    """一次导出多 sheet：类目大盘 / 商品 / 关键词。"""
    sheets = []
    if overview is not None:
        cols = [("指标", "k"), ("数值", "v")]
        rows = [{"k": k, "v": _cell(v)} for k, v in overview.items()]
        sheets.append(("类目大盘", rows, cols))
    if products:
        sheets.append(("商品清单", products, PRODUCT_COLUMNS))
    if keywords:
        sheets.append(("关键词", keywords, KEYWORD_COLUMNS))
    if not sheets:
        sheets.append(("空", [], [("提示", "msg")]))
    return export_workbook(sheets, filename)
