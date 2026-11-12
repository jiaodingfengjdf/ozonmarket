# -*- coding: utf-8 -*-
"""选品利润模型（阶段3）：把官方 grossMargin 换成「你自己的账」。

官方 `grossMargin` 口径不明、不含头程与佣金，无法直接用于跨境定价决策。
这里按跨境电商真实成本结构重算：

  售价(₽)
  − 采购成本(CNY→₽)
  − 头程物流(按「实重 vs 体积重」取大 × 单价)
  − 平台佣金(售价 × 佣金%)
  − 支付/结算费(售价 × %)
  − 广告费(售价 × DRR%)
  − 退货损耗(售价 × 退货率% × 0.5，只算一半因为退货可部分再售)
  = 净利(₽) → 真毛利率 = 净利 / 售价

保本价 = (采购 + 头程) / (1 − 佣金% − 支付% − 广告% − 退货%)
建议售价 = (采购 + 头程) / (1 − 佣金% − 支付% − 广告% − 退货% − 目标毛利%)

体积重：Ozon/多数渠道按 长×宽×高(cm) / 5000 计费，接口给的 dimension 是 mm 字符串（如 231×183×103）。
"""
from __future__ import annotations

import re

# 默认参数（界面可改，改了会记住）
DEFAULTS = {
    "cost_cny": 0.0,            # 单件采购成本（人民币）
    "rate_cny_rub": 12.5,       # 1 CNY = ? RUB
    "shipping_cny_per_kg": 35.0,  # 头程单价（人民币/kg）
    "commission_pct": 15.0,     # Ozon 类目佣金
    "payment_pct": 2.0,         # 支付/结算费
    "drr_pct": 0.0,             # 广告费占比；0 且 use_row_drr=true 时用商品自带的 drr
    "return_pct": 0.0,          # 退货取消损耗（按售价计）
    "volumetric_divisor": 5000,  # 体积重 = 体积(cm³)/该系数
    "target_margin_pct": 20.0,  # 目标毛利率（算建议售价用）
    "use_row_drr": True,
    "shipping_override_rub": None,  # 直接指定每件物流费(₽)，填了就不用重量算
}


def _num(v, default=None):
    if v is None or v == "":
        return default
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else default
    except (TypeError, ValueError):
        return default


def dims_cm3(dimension):
    """'231×183×103'（mm）→ 4359.0 cm³；无法解析返回 0。"""
    if not dimension:
        return 0.0
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(dimension))]
    if len(nums) < 3:
        return 0.0
    a, b, c = nums[0], nums[1], nums[2]
    # 接口给的是毫米；若明显偏小（<50）则按厘米兜底
    if min(a, b, c) >= 50:
        return (a * b * c) / 1000.0   # 视为毫米：mm³ → cm³
    return a * b * c                  # 视为厘米


def chargeable_kg(weight_g=None, volume_l=None, dimension=None, divisor=5000):
    """计费重(kg)：实重与体积重取大。"""
    w_kg = (_num(weight_g, 0) or 0) / 1000.0
    vol_cm3 = (_num(volume_l, 0) or 0) * 1000.0
    if not vol_cm3:
        vol_cm3 = dims_cm3(dimension)
    d = _num(divisor, 5000) or 5000
    v_kg = (vol_cm3 / d) if vol_cm3 > 0 else 0.0
    return round(max(w_kg, v_kg), 3), round(w_kg, 3), round(v_kg, 3)


def compute(row: dict, params: dict | None = None) -> dict:
    p = dict(DEFAULTS)
    p.update({k: v for k, v in (params or {}).items() if v is not None})

    price = _num(row.get("price"), 0) or 0
    cost_cny = _num(p.get("cost_cny"), 0) or 0
    rate = _num(p.get("rate_cny_rub"), 12.5) or 12.5
    ship_unit = _num(p.get("shipping_cny_per_kg"), 0) or 0
    commission_pct = _num(p.get("commission_pct"), 0) or 0
    payment_pct = _num(p.get("payment_pct"), 0) or 0
    return_pct = _num(p.get("return_pct"), 0) or 0
    drr_pct = _num(p.get("drr_pct"), 0) or 0
    if not drr_pct and p.get("use_row_drr", True):
        drr_pct = _num(row.get("drr"), 0) or 0
    target = _num(p.get("target_margin_pct"), 20) or 0

    kg, w_kg, v_kg = chargeable_kg(row.get("weight"), row.get("volume"),
                                   row.get("dimension"), p.get("volumetric_divisor"))
    override = _num(p.get("shipping_override_rub"))
    shipping_rub = override if override is not None else kg * ship_unit * rate

    cost_rub = cost_cny * rate
    commission = price * commission_pct / 100.0
    payment = price * payment_pct / 100.0
    ad = price * drr_pct / 100.0
    ret = price * return_pct / 100.0 * 0.5
    net = price - cost_rub - shipping_rub - commission - payment - ad - ret

    fixed = cost_rub + shipping_rub
    pct = commission_pct + payment_pct + drr_pct + return_pct * 0.5
    denom = 1 - pct / 100.0
    breakeven = round(fixed / denom, 2) if denom > 0 else None
    denom2 = denom - target / 100.0
    suggested = round(fixed / denom2, 2) if denom2 > 0 else None

    return {
        "price": round(price, 2),
        "chargeable_kg": kg, "weight_kg": w_kg, "volumetric_kg": v_kg,
        "cost_rub": round(cost_rub, 2),
        "shipping_rub": round(shipping_rub, 2),
        "commission_rub": round(commission, 2),
        "payment_rub": round(payment, 2),
        "ad_rub": round(ad, 2),
        "return_rub": round(ret, 2),
        "net_profit": round(net, 2),
        "net_margin": round(net / price * 100, 2) if price else None,
        "breakeven": breakeven,
        "suggested": suggested,
        "roi": round(net / fixed * 100, 2) if fixed > 0 else None,
        "assumed": {"drr_pct": round(drr_pct, 2), "commission_pct": commission_pct,
                    "payment_pct": payment_pct, "return_pct": return_pct,
                    "rate": rate, "shipping_cny_per_kg": ship_unit},
    }


def enrich(rows, params=None):
    """给一批商品行算利润；返回 (enriched_rows, summary)。"""
    out = []
    for r in rows or []:
        c = compute(r, params)
        merged = dict(r)
        merged.update(c)
        out.append(merged)
    priced = [r for r in out if (r.get("price") or 0) > 0]
    margins = [r["net_margin"] for r in priced if r.get("net_margin") is not None]
    profits = [r["net_profit"] for r in out if r.get("net_profit") is not None]
    summary = {
        "rows": len(out),
        "avg_net_margin": round(sum(margins) / len(margins), 2) if margins else None,
        "avg_net_profit": round(sum(profits) / len(profits), 2) if profits else None,
        "loss_rows": sum(1 for r in out if (r.get("net_profit") or 0) < 0),
        "avg_chargeable_kg": (round(sum(r["chargeable_kg"] for r in out) / len(out), 3)
                              if out else None),
        "params": {k: v for k, v in dict(DEFAULTS, **(params or {})).items()},
    }
    return out, summary
