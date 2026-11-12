"""纯 HTTP 直连 ozon.ru —— 不启动 Chrome，也不连 CDP。

数据源：`data/ozon_cookies.json`（由 tools/ozon_cookie_export.mjs 从**已运行**的
调试 Chrome 一次性导出，含过完 abt-challenge 的 abt_data / __Secure-ETC 等会话）。
之后所有请求由本模块用 urllib 发出，浏览器可以关掉。

cookie 失效的表现：服务端回 307 且 Location 带 `__rr=N` 无限自增（挑战循环）。
这时抛 CookieExpired，调用方可提示重跑导出脚本。

命令行自检：
    python web/ozon_http.py --probe
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.environ.get("OZON_COOKIE_FILE") or os.path.join(ROOT, "data", "ozon_cookies.json")
API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")

_lock = threading.RLock()
_state = {"by_name": {}, "order": [], "ua": DEFAULT_UA, "meta": {}, "loaded_at": 0.0}


class CookieExpired(RuntimeError):
    """cookie 已失效（Ozon 重新要求过 JS 挑战）。"""


class CookieMissing(RuntimeError):
    """还没有导出过 cookie。"""


def _load_file():
    if not os.path.exists(COOKIE_FILE):
        raise CookieMissing(
            f"缺少 {COOKIE_FILE}。请先在已开着的调试 Chrome 里过一次 Ozon，"
            "再跑 `node tools/ozon_cookie_export.mjs`（不会启动 Chrome）。")
    with open(COOKIE_FILE, encoding="utf-8") as f:
        return json.load(f)


def reload_cookies(force=False):
    """(重新)载入 cookie 快照。同名 cookie 保留最后一条（Chrome 返回顺序里后出现的更具体）。"""
    with _lock:
        if _state["loaded_at"] and not force:
            return
        d = _load_file()
        by_name, order = {}, []
        for c in d.get("cookies") or []:
            if not c.get("name"):
                continue
            if c["name"] not in by_name:
                order.append(c["name"])
            by_name[c["name"]] = {"value": c.get("value", ""), "domain": c.get("domain", ".ozon.ru"),
                                  "path": c.get("path", "/"), "secure": bool(c.get("secure")),
                                  "httpOnly": bool(c.get("httpOnly")),
                                  "expires": c.get("expires", -1)}
        if not by_name:
            raise CookieMissing("cookie 快照是空的，请重跑导出脚本。")
        _state.update({"by_name": by_name, "order": order,
                       "ua": d.get("user_agent") or DEFAULT_UA,
                       "meta": {k: d.get(k) for k in ("exported_at", "source", "browser")},
                       "loaded_at": time.time()})


def cookie_header():
    reload_cookies()
    with _lock:
        return "; ".join(f"{n}={_state['by_name'][n]['value']}" for n in _state["order"])


def user_agent():
    reload_cookies()
    return _state["ua"]


def meta():
    try:
        reload_cookies()
    except (CookieMissing, ValueError):
        return {}
    return dict(_state["meta"], names=list(_state["order"]))


def _parse_set_cookie(headers):
    """从响应里取出服务端新签发的 cookie（例如刷新后的 abt_data / __Secure-ETC）。"""
    out = []
    for raw in headers.get_all("Set-Cookie") or []:
        part = raw.split(";", 1)[0]
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if name and value and value.lower() not in ("deleted",):
            out.append((name, value))
    return out


def _absorb(headers):
    """把服务端下发的 cookie 并回内存 + 落盘，让会话可以续期。"""
    pairs = _parse_set_cookie(headers)
    if not pairs:
        return 0
    with _lock:
        changed = 0
        for name, value in pairs:
            cur = _state["by_name"].get(name)
            if not cur or cur["value"] != value:
                changed += 1
                if not cur:
                    _state["order"].append(name)
                    cur = {"domain": ".ozon.ru", "path": "/", "secure": True,
                           "httpOnly": True, "expires": -1}
                cur["value"] = value
                _state["by_name"][name] = cur
        if not changed:
            return 0
        d = _load_file()
        d["cookies"] = [dict(_state["by_name"][n], name=n) for n in _state["order"]]
        d["last_refreshed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = COOKIE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, COOKIE_FILE)
        _state["loaded_at"] = time.time()
    return changed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不自动跟随 307，便于识别 abt 挑战循环（否则会 curl -L 那样无限打转）。"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)
_opener_cache = {}


def opener(proxy=None):
    """proxy: None=沿用环境代理；''=直连（绕过代理）；字符串=指定 http/https 代理。"""
    key = proxy if isinstance(proxy, str) else "__system__"
    if key == "__system__":
        return _opener
    if key not in _opener_cache:
        ph = (urllib.request.ProxyHandler({}) if proxy == ""
              else urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        _opener_cache[key] = urllib.request.build_opener(ph, _NoRedirect)
    return _opener_cache[key]


def probe_egress(proxy=None, timeout=8):
    """出口可用性探针（两段式）。

    历史坑：旧版拿「robots.txt 是否 200」判出口干净，可是 Ozon 现在对**无 cookie** 的
    robots.txt 也回 307 挑战 —— 于是所有出口都被判成「IP 被封」，而实际上真实原因是
    本机系统代理（127.0.0.1:17891 / 0dcloud）对 ozon.ru 的 HTTPS 直接 SSL 握手超时。

    现在分两段，各答一个问题：
      1. 不带 cookie 打 robots.txt → 能收到任何 HTTP 响应（200/307/403）就说明**网络层通**；
         连接超时 / SSL 失败 = 这个出口根本到不了 Ozon（本地代理挂了最常见）。
      2. 带 cookie 打 robots.txt → 200 说明**会话有效、真的能取数**；
         3xx/403 = cookie 失效（重导即可），**不是 IP 被封**。

    返回 {'ok','status','stage','location','error'}；`ok` 为真 = 该出口能取数。
    """
    ua = user_agent()
    # ---- 第 1 段：网络层 ----
    req = urllib.request.Request("https://www.ozon.ru/robots.txt",
                                 headers={"User-Agent": ua, "Accept": "text/plain,*/*"})
    net_status, loc = 0, ""
    try:
        with opener(proxy).open(req, timeout=timeout) as r:
            r.read()
            net_status = r.status
    except urllib.error.HTTPError as e:
        net_status = e.code
        loc = (e.headers.get("Location") or "")[:120]
    except Exception as e:
        return {"ok": False, "status": 0, "stage": "network", "location": "",
                "error": f"{type(e).__name__}: {str(e)[:100]}"}
    if net_status == 200:
        # 无 cookie 就 200，说明这个出口连会话都不需要（少见，但直接可用）
        return {"ok": True, "status": 200, "stage": "network", "location": "", "error": ""}

    # ---- 第 2 段：会话层（带 cookie）----
    try:
        ck = cookie_header()
    except (CookieMissing, CookieExpired) as e:
        return {"ok": False, "status": net_status, "stage": "cookie_missing",
                "location": loc, "error": str(e)[:120]}
    req2 = urllib.request.Request("https://www.ozon.ru/robots.txt", headers={
        "User-Agent": ua, "Accept": "text/plain,*/*", "Cookie": ck,
        "Referer": "https://www.ozon.ru/",
    })
    try:
        with opener(proxy).open(req2, timeout=timeout) as r:
            r.read()
            if r.status == 200:
                return {"ok": True, "status": 200, "stage": "session", "location": "", "error": ""}
            return {"ok": False, "status": r.status, "stage": "session",
                    "location": "", "error": f"带 cookie 仍 {r.status}"}
    except urllib.error.HTTPError as e:
        loc = (e.headers.get("Location") or "")[:120]
        return {"ok": False, "status": e.code, "stage": "session", "location": loc,
                "error": f"带 cookie 仍 {e.code}，cookie 失效或该出口 IP 被标记"}
    except Exception as e:
        return {"ok": False, "status": 0, "stage": "session", "location": "",
                "error": f"{type(e).__name__}: {str(e)[:100]}"}


def request_raw(path_query, headers=None, timeout=20, proxy=None):
    """发一次请求，返回 (status, headers, body_bytes)。不跟随重定向。"""
    url = API + urllib.parse.quote(path_query, safe="")
    base = {
        "User-Agent": user_agent(),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Referer": "https://www.ozon.ru/",
        "Cookie": cookie_header(),
    }
    if headers:
        base.update(headers)
    req = urllib.request.Request(url, headers=base)
    try:
        with opener(proxy).open(req, timeout=timeout) as r:
            body = r.read()
            return r.status, r.headers, body
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def get_json(path_query, timeout=20, proxy=None):
    """拿 composer-api 的 JSON；307 挑战 / 403 / 空响应统一抛异常。"""
    status, headers, body = request_raw(path_query, timeout=timeout, proxy=proxy)
    if status in (301, 302, 303, 307, 308):
        loc = headers.get("Location") or ""
        if "__rr=" in loc or "abt" in loc.lower():
            raise CookieExpired("Ozon 要求重新过 JS 挑战（307 __rr 循环），cookie 已失效；"
                                "重跑 `node tools/ozon_cookie_export.mjs` 刷新。")
        raise CookieExpired(f"被重定向到 {loc[:120]}，cookie 可能已失效。")
    if status == 403:
        raise CookieExpired("403：会话被拒，重跑 `node tools/ozon_cookie_export.mjs` 刷新 cookie。")
    if status != 200:
        raise RuntimeError(f"ozon HTTP {status}, {len(body)} bytes")
    if len(body) < 3000 or b"Antibot" in body[:2000]:
        raise CookieExpired(f"返回内容异常（{len(body)} bytes / Antibot 页），cookie 可能已失效。")
    # 只在成功响应里吸收服务端续期下发的 cookie，避免 307 挑战页覆盖掉会话
    try:
        _absorb(headers)
    except Exception:
        pass
    return json.loads(body.decode("utf-8", "replace"))


# ------------------------------------------------------------------ 自检
def probe():
    q = "/category/elektronika-15500/?sorting=score&page=1"
    print("cookie 文件:", COOKIE_FILE)
    print("快照:", json.dumps(meta(), ensure_ascii=False))
    print("cookie 头长度:", len(cookie_header()))
    variants = [
        ("最小头 + cookie", {}),
        ("浏览器头 + cookie", {
            "sec-ch-ua": '"Google Chrome";v="156", "Chromium";v="156", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
        }),
    ]
    for label, extra in variants:
        try:
            s, h, b = request_raw(q, headers=extra, timeout=20)
            loc = (h.get("Location") or "")[:90]
            print(f"[{label}] status={s} len={len(b)} loc={loc} head={b[:100]!r}")
        except Exception as e:
            print(f"[{label}] ERR {type(e).__name__}: {e}")
    try:
        s, h, b = request_raw(q, headers={"Cookie": ""}, timeout=20)
        print(f"[无 cookie 对照] status={s} len={len(b)} loc={(h.get('Location') or '')[:90]}")
    except Exception as e:
        print(f"[无 cookie 对照] ERR {e}")


if __name__ == "__main__":
    import sys
    if "--probe" in sys.argv:
        probe()
    else:
        print(__doc__)
