#!/usr/bin/env python3
"""Read-only local document probe using Fineract's built-in OAuth2 authorization-code flow."""

import base64
import hashlib
import http.cookiejar
import json
import os
import secrets
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE = os.getenv("FINERACT_LAB_BASE_URL", "https://localhost:8450/fineract-provider")
if not BASE.startswith(("https://localhost:", "https://127.0.0.1:")):
    raise SystemExit("Local loopback HTTPS only")
USER = os.getenv("FINERACT_LAB_OAUTH_USER", "doc_scope_zero_20261126")
PASSWORD = os.getenv("FINERACT_LAB_PROBE_PASSWORD", "DocScope#2026Test9!")
RESULT = Path(os.getenv("FINERACT_LAB_RESULT_PATH", Path(__file__).parent / "evidence" / "document_office_scope_oauth2_result.json"))
RESULT.parent.mkdir(parents=True, exist_ok=True)
CALLBACK = "http://localhost:3000/callback"


class StopAtCallback(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if newurl.startswith(CALLBACK):
            return None
        return super().redirect_request(request, fp, code, msg, headers, newurl)


opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
    StopAtCallback(),
)


def send(method, path, data=None, headers=None):
    request = urllib.request.Request(BASE + path, data=data, headers=headers or {}, method=method)
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, response.headers, response.read(), response.geturl()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read(), error.geturl()


def get_token():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urllib.parse.urlencode({
        "response_type": "code", "client_id": "frontend-client", "redirect_uri": CALLBACK,
        "scope": "read", "state": secrets.token_urlsafe(12),
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    status, _, body, url = send("GET", "/oauth2/authorize?" + query)
    if status != 200 or "/login" not in url:
        raise RuntimeError(f"Authorization start failed: HTTP {status}, path {urllib.parse.urlparse(url).path}, body bytes {len(body)}")

    form = urllib.parse.urlencode({"username": USER, "password": PASSWORD, "tenantId": "default"}).encode()
    status, headers, body, url = send("POST", "/login", form, {"Content-Type": "application/x-www-form-urlencoded"})
    location = headers.get("Location", "")
    if status != 302 or not location.startswith(CALLBACK):
        raise RuntimeError(f"Login/authorization failed: HTTP {status}, path {urllib.parse.urlparse(url).path}, "
                           f"location path {urllib.parse.urlparse(location).path}, body bytes {len(body)}")
    code = urllib.parse.parse_qs(urllib.parse.urlparse(location).query).get("code", [None])[0]
    if code is None:
        raise RuntimeError("Authorization callback had no code")

    token_form = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "redirect_uri": CALLBACK,
        "client_id": "frontend-client", "code_verifier": verifier,
    }).encode()
    status, _, body, _ = send("POST", "/oauth2/token", token_form, {"Content-Type": "application/x-www-form-urlencoded"})
    if status != 200:
        raise RuntimeError(f"Token exchange failed: HTTP {status}, body bytes {len(body)}")
    token = json.loads(body)["access_token"]
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return token, {"sub": claims.get("sub"), "scope": claims.get("scope"), "role": claims.get("role"), "tenant": claims.get("tenant")}


def main():
    token, claims = get_token()
    headers = {"Authorization": "Bearer " + token, "Fineract-Platform-TenantId": "default"}
    paths = {"client": "/api/v1/clients/3", "doc_list": "/api/v1/clients/3/documents",
             "doc_meta": "/api/v1/clients/3/documents/2", "attachment": "/api/v1/clients/3/documents/2/attachment"}
    results = {}
    for name, path in paths.items():
        status, _, body, _ = send("GET", path, headers=headers)
        entry = {"http": status, "bytes": len(body)}
        if name == "attachment" and status == 200:
            entry["sha256"] = hashlib.sha256(body).hexdigest()
            entry["synthetic_marker"] = b"SYNTHETIC DOCUMENT FOR BRANCH-B" in body
        elif name == "doc_list" and status == 200:
            try:
                data = json.loads(body)
                entry["document_ids"] = [item.get("id") for item in data] if isinstance(data, list) else None
            except json.JSONDecodeError:
                entry["parse_error"] = True
        results[name] = entry
    out = {"authentication": "Fineract built-in OAuth2 authorization code with PKCE", "user": USER, "claims": claims,
           "results": results}
    RESULT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
