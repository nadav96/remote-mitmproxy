"""mitmproxy addon for upstream OAuth / portal flows.

You asked for two behaviors:

A) Guardrail on OAuth authorize requests:
   If a client submits /sharing/oauth2/authorize with redirect_uri (or state JSON)
   pointing at the proxy (proxy.example.com), rewrite those *query param values*
   to the upstream host (https://upstream.example.com).

B) Redirect rewriting on responses:
   For ANY redirect response (301/302/303/307/308) going back to the client,
   rewrite Location so it points to the proxy over https, e.g.
     Location: https://upstream.example.com/home/index.html
       ->      https://proxy.example.com/home/index.html

Run:
  mitmproxy -s addon.py
  (or mitmweb -s ...)

Tip: If you want to verify it triggers, set DEBUG = True.
"""

from __future__ import annotations

import json
from typing import List, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mitmproxy import http

# ----------------- Config -----------------
DEBUG = False

PROXY_HOST = "proxy.example.com"
PROXY_BASE = f"https://{PROXY_HOST}"

TARGET_HOST = "upstream.example.com"
TARGET_BASE_HTTPS = f"https://{TARGET_HOST}"
TARGET_BASE_HTTP = f"http://{TARGET_HOST}"


# ----------------- Helpers -----------------

def _proxy_to_target(s: str) -> str:
    """Rewrite proxy host occurrences -> upstream host (https)."""
    if not isinstance(s, str) or not s:
        return s

    out = s
    out = out.replace(PROXY_BASE, TARGET_BASE_HTTPS)
    out = out.replace(f"http://{PROXY_HOST}", TARGET_BASE_HTTPS)
    out = out.replace(PROXY_HOST, TARGET_HOST)

    return out


def _target_to_proxy(s: str) -> str:
    """Rewrite upstream host occurrences -> proxy host (https)."""
    if not isinstance(s, str) or not s:
        return s

    out = s
    out = out.replace(TARGET_BASE_HTTPS, PROXY_BASE)
    out = out.replace(TARGET_BASE_HTTP, PROXY_BASE)
    out = out.replace(TARGET_HOST, PROXY_HOST)

    return out


def _rewrite_state_param(state_value: str, direction_fn) -> str:  # noqa: kept as-is
    """Decode JSON in state, rewrite string fields, re-encode compact JSON."""
    try:
        obj = json.loads(state_value)
    except Exception:
        return direction_fn(state_value)

    def walk(x):
        if isinstance(x, str):
            return direction_fn(x)
        if isinstance(x, list):
            return [walk(i) for i in x]
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        return x

    obj2 = walk(obj)
    return json.dumps(obj2, separators=(",", ":"), ensure_ascii=False)


def _rewrite_query_params_proxy_to_target(params: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for k, v in params:
        if k == "state":
            out.append((k, _rewrite_state_param(v, _proxy_to_target)))
            continue
        if k == "redirect_uri":
            out.append((k, _proxy_to_target(v)))
            continue
        out.append((k, _proxy_to_target(v)))
    return out


# ----------------- Client Tracking -----------------

_ip_to_user: dict[str, str] = {}
_user_counter = 0


def _get_client_id(flow: http.HTTPFlow) -> tuple[str, str]:
    """Extract real client IP from X-Forwarded-For and assign a stable user ID."""
    global _user_counter
    xff = flow.request.headers.get("X-Forwarded-For", "")
    client_ip = xff.split(",")[0].strip() if xff else "unknown"

    if client_ip not in _ip_to_user:
        _user_counter += 1
        _ip_to_user[client_ip] = f"user-{_user_counter}"

    return client_ip, _ip_to_user[client_ip]


# ----------------- Addon -----------------

class OAuthRewriter:
    def request(self, flow: http.HTTPFlow) -> None:
        req = flow.request

        # Tag every request with client identity
        client_ip, client_id = _get_client_id(flow)
        req.headers["X-Client-IP"] = client_ip
        req.headers["X-Client-ID"] = client_id

        # Guardrail applies to OAuth endpoints where redirect_uri appears
        # 1) /sharing/oauth2/authorize  (query params)
        # 2) /sharing/rest/oauth2/token (form body)

        # ---------------- Authorize (query) ----------------
        if req.path.startswith("/sharing/oauth2/authorize"):
            split = urlsplit(req.url)
            if not split.query:
                return

            params = parse_qsl(split.query, keep_blank_values=True)

            # Only act if redirect_uri points to the proxy
            redirect_uri_vals = [v for (k, v) in params if k == "redirect_uri"]
            if not any(PROXY_HOST in v for v in redirect_uri_vals):
                return

            new_params = _rewrite_query_params_proxy_to_target(params)
            new_query = urlencode(new_params, doseq=True)
            new_url = urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))

            if new_url != req.url:
                if DEBUG:
                    flow.log.info(f"[request authorize] {req.url} -> {new_url}")
                req.url = new_url
            return

        # ---------------- Token (form body) ----------------
        if req.path.startswith("/sharing/rest/oauth2/token"):
            ctype = (req.headers.get("content-type") or "").lower()
            if "application/x-www-form-urlencoded" not in ctype:
                return

            # mitmproxy gives you body bytes; decode as utf-8 (safe for form encoding)
            raw = req.get_text(strict=False)  # preserves original bytes if possible
            if not raw:
                return

            form = parse_qsl(raw, keep_blank_values=True)
            redirect_uri_vals = [v for (k, v) in form if k == "redirect_uri"]
            if not any(PROXY_HOST in v for v in redirect_uri_vals):
                return

            new_form: List[Tuple[str, str]] = []
            for k, v in form:
                if k == "redirect_uri":
                    new_form.append((k, _proxy_to_target(v)))
                else:
                    new_form.append((k, v))

            new_body = urlencode(new_form, doseq=True)
            if new_body != raw:
                if DEBUG:
                    flow.log.info(f"[request token] redirect_uri rewritten")
                req.set_text(new_body)
            return

        # Not an endpoint we care about
        return

    def response(self, flow: http.HTTPFlow) -> None:
        """Rewrite *any* redirect Location back to the proxy (https)."""
        resp = flow.response
        if resp is None:
            return

        if resp.status_code not in (301, 302, 303, 307, 308):
            return

        loc = resp.headers.get("Location") or resp.headers.get("location")
        if not loc:
            return

        new_loc = loc

        # Relative redirects -> absolute proxy URL
        if new_loc.startswith("/"):
            new_loc = PROXY_BASE + new_loc

        # If it points to upstream host, rewrite to proxy
        if TARGET_HOST in new_loc or new_loc.startswith(TARGET_BASE_HTTPS) or new_loc.startswith(TARGET_BASE_HTTP):
            new_loc = _target_to_proxy(new_loc)

        if new_loc != loc:
            if DEBUG:
                flow.log.info(f"[response {resp.status_code}] Location {loc} -> {new_loc}")
            resp.headers["Location"] = new_loc


addons = [OAuthRewriter()]
