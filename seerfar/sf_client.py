# -*- coding: utf-8 -*-
"""Seerfar Open API 客户端。

实测约束（2026-11-12，非文档推测）：
  1. 积分按「调用次数」扣，约 8~10 分/次，与 pageSize 无关；10000 分约够 1000~1250 次。
  2. 限流很紧：连续请求会触发 HTTP 429，连 /open-api/quota 一起被限。
  3. 偶发连接超时，必须自动重试。
  4. 本机系统代理指向不通的本地代理，默认禁用系统代理直连（可配置关闭）。

因此本客户端统一提供：全局限速 → 磁盘缓存（同参数不重复扣费）→ 指数退避重试
→ 业务码处理（8000 积分耗尽熔断）→ 积分预算保护 → 调用日志。
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import random
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sf_db import STORE, dumps, today_str

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

# 全部 17 个业务接口 + 配额接口，路径以官方文档为准
ENDPOINTS = {
    "quota":          ("GET",  "/open-api/quota"),
    "shop":           ("POST", "/open-api/shop/detail/search/ozon"),
    "shop_brand":     ("POST", "/open-api/shop/detail/brand/search/ozon"),
    "shop_category":  ("POST", "/open-api/shop/detail/category/search/ozon"),
    "product":        ("POST", "/open-api/product/detail/search/ozon"),
    "similar":        ("POST", "/open-api/product/detail/similar/ozon"),
    "var_chars":      ("POST", "/open-api/product/detail/variations/characteristics/ozon"),
    "var_top":        ("POST", "/open-api/product/detail/variations/top/ozon"),
    "var_search":     ("POST", "/open-api/product/detail/variations/search/ozon"),
    "monthly_trend":  ("POST", "/open-api/product/monthlySalesTrend/ozon"),
    "category":       ("POST", "/open-api/category/detail/search/ozon"),
    "top":            ("POST", "/open-api/productReport/search/ozon"),
    "market":         ("POST", "/open-api/market/search/ozon"),
    "mining":         ("POST", "/open-api/keyword/mining/ozon"),
    "backsearch":     ("POST", "/open-api/keyword/backSearch/ozon"),
    "review_task":    ("POST", "/open-api/review/analyse/ozon/task/add"),
    "review_report":  ("POST", "/open-api/review/analyse/ozon/report"),
    "review_words":   ("POST", "/open-api/review/analyse/ozon/wordFrequency"),
    "review_stat":    ("POST", "/open-api/review/analyse/ozon/reviewStatistic"),
    "review_original": ("POST", "/open-api/review/analyse/ozon/originalReview"),
}

# 会产生真实扣费的写操作：必须显式 confirm=True 才能调用
WRITE_ENDPOINTS = {"review_task"}

# 单次调用积分成本（保守估计，实测普通接口 8~10 分）
COST = {"quota": 0.0, "review_task": 200.0}
DEFAULT_COST = 10.0

# 缓存有效期（秒）：日级数据缓存久，实时数据缓存短
TTL = {
    "quota": 60,
    "category": 86400, "top": 21600, "market": 86400,
    "mining": 86400, "backsearch": 86400,
    "product": 43200, "similar": 86400, "monthly_trend": 86400 * 3,
    "var_chars": 86400 * 7, "var_top": 86400, "var_search": 86400,
    "shop": 21600, "shop_brand": 86400, "shop_category": 86400,
    "review_report": 86400 * 7, "review_words": 86400 * 7,
    "review_stat": 86400, "review_original": 86400,
}
DEFAULT_TTL = 21600

DEFAULT_CONFIG = {
    "api": {
        "base_url": "http://api.seerfar.cn",
        "key": "",
        "timeout": 45,
        "disable_proxy": True,
        "min_interval": 1.3,
        "jitter": 0.35,
        "max_retries": 3,
        "retry_backoff": [3, 8, 20],
    },
    "budget": {
        # enforce=false：不做任何本地积分限制（额度用尽时官方返回 8000 仍会自动熔断）
        "enforce": False,
        "reserve": 0,
        "daily_credit_limit": 0,
        "single_run_credit_limit": 0,
        "default_cost": 9.0,
    },
    "cache": {"enabled": True, "default_ttl": DEFAULT_TTL},
    "catalog": {"xlsx": "data/ozon_categories.xlsx"},
}


def _merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class SeerfarError(Exception):
    """客户端基础异常。"""


class AuthError(SeerfarError):
    """401 / 403：Key 无效、账号状态或权限问题。"""


class CreditExhausted(SeerfarError):
    """业务码 8000：API Key 积分耗尽，必须立刻熔断。"""


class BudgetExceeded(SeerfarError):
    """本地预算保护触发：拒绝继续发起付费调用。"""


class ConfirmRequired(SeerfarError):
    """写操作（如 200 分/SKU 的评论分析任务）需要显式确认。"""


class ApiError(SeerfarError):
    """其它接口/网络错误。"""


@dataclass
class Result:
    data: Any
    cached: bool = False
    elapsed_ms: int = 0
    code: int = 200
    path: str = ""
    name: str = ""
    cost: float = 0.0
    request_id: str = ""
    attempts: int = 1
    extra: dict = field(default_factory=dict)

    @property
    def ok(self):
        return self.code == 200

    def as_dict(self):
        return {"data": self.data, "cached": self.cached, "elapsed_ms": self.elapsed_ms,
                "code": self.code, "path": self.path, "name": self.name,
                "cost": self.cost, "request_id": self.request_id,
                "attempts": self.attempts}


class SeerfarClient:
    def __init__(self, config=None, store=None):
        self.cfg = _merge(DEFAULT_CONFIG, config or self._load_config())
        self.store = store or STORE
        api = self.cfg["api"]
        # 环境变量优先级最高，避免把密钥写死在代码里
        self.key = os.environ.get("SEERFAR_API_KEY") or api.get("key", "")
        self.base = (api.get("base_url") or "http://api.seerfar.cn").rstrip("/")
        self.timeout = float(api.get("timeout", 45))
        self.max_retries = int(api.get("max_retries", 3))
        self.backoff = list(api.get("retry_backoff") or [3, 8, 20])
        self.min_interval = float(api.get("min_interval", 1.3))
        self.jitter = float(api.get("jitter", 0.35))

        # 禁用系统代理：本机 127.0.0.1:17891 对出站请求不通（旧项目实测）
        handlers = []
        if api.get("disable_proxy", True):
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

        self._lock = threading.Lock()
        self._last_call = 0.0
        self._fused = False            # 8000 熔断标志
        self.run_cost = 0.0           # 本进程累计预估消耗
        self._server_used = None      # 最近一次 quota 拿到的官方已用积分
        self._server_limit = None     # 官方积分总额度
        self.on_response: list[Callable[[str, Any], None]] = []  # 响应钩子（类目沉淀等）

        if not self.key:
            raise AuthError("未配置 API Key：请填 config.json 的 api.key 或设置环境变量 SEERFAR_API_KEY")

    @staticmethod
    def _load_config():
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (ValueError, OSError) as e:
                raise ApiError(f"config.json 读取失败: {e}")
        return {}

    # ---------- 限速 ----------
    def _wait_turn(self):
        """全局串行限速：任意两次真实请求至少间隔 min_interval(±jitter)。"""
        with self._lock:
            gap = self.min_interval * (1 + random.uniform(-self.jitter, self.jitter))
            elapsed = time.time() - self._last_call
            if elapsed < gap:
                time.sleep(max(0.0, gap - elapsed))
            self._last_call = time.time()

    # ---------- 预算 ----------
    def cost_of(self, name):
        return float(COST.get(name, self.cfg["budget"].get("default_cost", DEFAULT_COST)))

    def _check_budget(self, name, cost):
        """积分预算检查。

        用户要求「不限制接口积分调用」，因此默认 `budget.enforce=false` 不做任何拦截。
        这里保留两个必要的安全网：
          1) 官方 8000 积分耗尽的熔断（必须保留，否则额度用光后会无限重试报错）
          2) 可选的本地保护（只有 enforce=true 时才生效，默认关闭）
        """
        if self._fused:
            raise CreditExhausted("已熔断：之前收到 8000（积分耗尽），本进程不再发起付费调用")
        b = self.cfg.get("budget", {})
        if cost <= 0 or not b.get("enforce", False):
            return
        # —— 以下仅在 enforce=true 时生效 ——
        spent = self.store.spent_today()
        daily = float(b.get("daily_credit_limit") or 0)
        if daily > 0 and spent + cost > daily:
            raise BudgetExceeded(
                f"今日估算消耗 {spent:.0f}/{daily:.0f} 分，本次需 {cost:.0f}。"
                f"放开请把 config.json 的 budget.daily_credit_limit 设为 0。")
        run = float(b.get("single_run_credit_limit") or 0)
        if run > 0 and self.run_cost + cost > run:
            raise BudgetExceeded(
                f"本次运行已消耗 {self.run_cost:.0f}/{run:.0f} 分，本次需 {cost:.0f}。")
        reserve = float(b.get("reserve") or 0)
        if reserve > 0 and self._server_limit:
            used = max(self.store.spent_total(), self._server_used or 0)
            left = self._server_limit - used
            if 0 < left < cost + reserve:
                raise BudgetExceeded(
                    f"积分余额不足：约剩 {left:.0f} 分（安全线 {reserve:.0f}），本次需 {cost:.0f}。")

    # ---------- 缓存 ----------
    @staticmethod
    def _cache_key(name, method, path, body):
        canon = dumps(body) if body is not None else ""
        raw = f"{method}|{path}|{canon}".encode("utf-8")
        return name + ":" + hashlib.sha256(raw).hexdigest()

    def ttl_of(self, name):
        return float(self.cfg["cache"].get("default_ttl", DEFAULT_TTL)) \
            if name not in TTL else float(TTL[name])

    # ---------- 主调用 ----------
    def call(self, name: str, body=None, *, ttl=None, force=False,
             confirm=False, use_cache=True) -> Result:
        """调用一个已注册接口。

        name     : ENDPOINTS 的键
        body     : POST JSON；GET 传 None
        ttl      : 覆盖默认缓存秒数；0 = 不缓存
        force    : True 跳过缓存强制刷新（会真实扣费）
        confirm  : 写操作必须传 True
        use_cache: False 完全绕过缓存读写
        """
        if name not in ENDPOINTS:
            raise ApiError(f"未知接口别名: {name}")
        method, path = ENDPOINTS[name]
        if name in WRITE_ENDPOINTS and not confirm:
            raise ConfirmRequired(
                f"{name} 是会扣费的写操作（约 {self.cost_of(name):.0f} 积分/次），"
                f"必须显式传 confirm=True")
        if self._fused:
            raise CreditExhausted("积分耗尽熔断中，拒绝新请求")

        cost = self.cost_of(name)
        key = self._cache_key(name, method, path, body)
        cache_on = (use_cache and self.cfg["cache"].get("enabled", True)
                    and name != "review_task" and (ttl or self.ttl_of(name)) > 0)

        # 1) 缓存命中：不发起网络请求，不扣积分
        if cache_on and not force:
            hit = self.store.cache_get(key)
            if hit is not None:
                self.store.log_call(path, method, True, 200, True, 0, 0)
                return Result(data=hit, cached=True, code=200, path=path, name=name)

        # 2) 预算校验
        self._check_budget(name, cost)

        # 3) 真实调用 + 重试
        started = time.time()
        payload, attempts, last_err = None, 0, ""
        for attempt in range(self.max_retries + 1):
            attempts = attempt + 1
            self._wait_turn()
            try:
                payload = self._http(method, path, body)
                last_err = ""
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "ignore")[:300]
                except Exception:
                    pass
                last_err = f"HTTP {e.code} {detail}"
                if e.code == 429 or e.code >= 500:
                    if attempt < self.max_retries:
                        time.sleep(self._sleep_for(attempt, long=True))
                        continue
                elif e.code in (401, 403):
                    raise AuthError(f"{path} 鉴权/权限失败: {last_err}")
                raise ApiError(f"{path} 请求失败: {last_err}")
            # IncompleteRead / RemoteDisconnected 属于 http.client.HTTPException，
            # 不是 OSError；实测响应体读到一半会断，必须一并纳入重试。
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError,
                    http.client.HTTPException) as e:
                last_err = f"{type(e).__name__}: {e}"
                if attempt < self.max_retries:
                    time.sleep(self._sleep_for(attempt))
                    continue
                raise ApiError(f"{path} 网络错误（已重试 {self.max_retries} 次）: {last_err}")

            # HTTP 200 但业务码可能仍是错误
            code = payload.get("code")
            if code == 200:
                break
            if code == 429:
                last_err = "业务码 429 限流"
                if attempt < self.max_retries:
                    time.sleep(self._sleep_for(attempt, long=True))
                    continue
                raise ApiError(f"{path} 限流重试耗尽")
            if code == 8000:
                self._fused = True
                raise CreditExhausted("API Key 积分耗尽（code=8000），已熔断；请充值或更换 Key")
            if code in (401, 403):
                raise AuthError(f"{path} 返回 {code}: {payload.get('msg')}")
            if code == 500:
                last_err = f"业务码 500: {payload.get('msg')}"
                if attempt < self.max_retries:
                    time.sleep(self._sleep_for(attempt))
                    continue
                raise ApiError(f"{path} 服务端错误重试耗尽: {last_err}")
            raise ApiError(f"{path} 返回 code={code}: {payload.get('msg')}")

        if payload is None:
            raise ApiError(f"{path} 无响应: {last_err}")

        data = payload.get("data")
        elapsed = int((time.time() - started) * 1000)
        self.run_cost += cost
        self.store.log_call(path, method, True, 200, False, elapsed, cost)

        if cache_on:
            self.store.cache_put(key, path, body, data, ttl or self.ttl_of(name))

        # 响应钩子：顺带把 categoryInfo 沉淀进本地类目字典（不额外花积分）
        for hook in self.on_response:
            try:
                hook(name, data)
            except Exception:
                pass

        return Result(data=data, cached=False, elapsed_ms=elapsed, code=200,
                      path=path, name=name, cost=cost,
                      request_id=str(payload.get("requestId") or ""), attempts=attempts)

    def _sleep_for(self, attempt, long=False):
        base = self.backoff[min(attempt, len(self.backoff) - 1)]
        if long:
            base += 2
        return base + random.uniform(0, 1.5)

    def _http(self, method, path, body):
        data = None
        if method == "POST":
            data = dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self.key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "seerfar-selector/1.0",
            },
        )
        with self.opener.open(req, timeout=self.timeout) as r:
            text = r.read().decode("utf-8", "ignore")
        try:
            return json.loads(text)
        except ValueError:
            raise ApiError(f"{path} 返回非 JSON: {text[:200]}")

    # ---------- 便捷方法 ----------
    def quota(self, force=False) -> Result:
        r = self.call("quota", None, ttl=60, force=force)
        if isinstance(r.data, dict):
            self._server_used = r.data.get("creditUsed")
            self._server_limit = r.data.get("creditLimit")
        return r

    def estimate(self, calls: list[tuple[str, Any]]) -> dict:
        """预估一批调用的积分成本，并标出哪些能命中缓存（用于批量前确认）。"""
        live, cached, cost = 0, 0, 0.0
        for name, body in calls:
            method, path = ENDPOINTS.get(name, ("POST", name))
            key = self._cache_key(name, method, path, body)
            if self.cfg["cache"].get("enabled", True) and self.store.cache_get(key) is not None:
                cached += 1
            else:
                live += 1
                cost += self.cost_of(name)
        return {"total": len(calls), "live": live, "cached": cached,
                "estimated_credit": round(cost, 1)}

    def stats(self) -> dict:
        q = {}
        try:
            r = self.quota()
            q = r.data or {}
        except Exception as e:
            q = {"error": str(e)}
        calls = self.store.calls_today()
        return {
            "quota": q,
            "today_spent_local": round(self.store.spent_today(), 1),
            "today_calls": calls,
            "run_cost": round(self.run_cost, 1),
            "cache": self.store.cache_stats(),
            "products": self.store.product_count(),
            "keywords": self.store.keyword_count(),
            "categories": self.store.category_stats(),
            "budget": self.cfg["budget"],
            "fused": self._fused,
        }


# 全局单例
CLIENT = None


def get_client() -> SeerfarClient:
    global CLIENT
    if CLIENT is None:
        CLIENT = SeerfarClient()
    return CLIENT
