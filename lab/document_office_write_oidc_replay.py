#!/usr/bin/env python3
"""Loopback-only external OIDC replay of synthetic Fineract document writes."""

import base64
import http.server
import json
import os
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE = os.getenv("FINERACT_LAB_BASE_URL", "https://localhost:8456/fineract-provider")
if not BASE.startswith(("https://localhost:", "https://127.0.0.1:")):
    raise SystemExit("Only loopback HTTPS is permitted")
ISSUER = "http://127.0.0.1:8181/docscope"
JWKS = {}
HERE = Path(__file__).parent
FIXTURE = json.loads(Path(os.getenv("FINERACT_LAB_OIDC_FIXTURE_PATH", HERE / "evidence/document_office_write_scope_oidc_fixture.json")).read_text())
STATE = json.loads(Path(os.getenv("FINERACT_LAB_STATE_PATH", HERE / "evidence/document_office_scope_state.json")).read_text())
CHAIN_RESULT_PATH = os.getenv("FINERACT_LAB_CHAIN_RESULT_PATH")
if CHAIN_RESULT_PATH:
    CHAIN_RESULT = json.loads(Path(CHAIN_RESULT_PATH).read_text())
    UPDATER_NAME = CHAIN_RESULT["setup"]["actors"]["update"]["username"]
    DELETER_NAME = CHAIN_RESULT["setup"]["actors"]["delete"]["username"]
    WRITER_DOCUMENT_READ_HTTP = 200
else:
    BASIC_RESULT = json.loads(Path(os.getenv("FINERACT_LAB_BASIC_RESULT_PATH", HERE / "evidence/document_office_write_scope_develop.json")).read_text())
    UPDATER_NAME = BASIC_RESULT["ids"]["updater"]["username"]
    DELETER_NAME = BASIC_RESULT["ids"]["deleter"]["username"]
    WRITER_DOCUMENT_READ_HTTP = 403
CLIENT_A, CLIENT_B = STATE["client_a"], STATE["client_b"]
RESULT = Path(os.getenv("FINERACT_LAB_RESULT_PATH", HERE / "evidence/document_office_write_scope_oidc_develop.json"))
tls = ssl._create_unverified_context()  # Self-signed localhost test certificate.


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class JwksHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/jwks":
            self.send_error(404)
            return
        data = json.dumps(JWKS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


def token_for(key, username):
    now = int(time.time())
    header = {"alg": "RS256", "kid": "docscope-write-20261126", "typ": "JWT"}
    claims = {"iss": ISSUER, "sub": "synthetic-" + username, "preferred_username": username,
              "aud": "fineract", "iat": now, "nbf": now - 5, "exp": now + 300}
    signing_input = (b64u(json.dumps(header, separators=(",", ":")).encode()) + "."
                     + b64u(json.dumps(claims, separators=(",", ":")).encode())).encode()
    signature = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key)], input=signing_input,
                               capture_output=True, check=True).stdout
    return signing_input.decode() + "." + b64u(signature)


def request(method, path, auth, body=None, content_type=None):
    headers = {"Authorization": auth, "Fineract-Platform-TenantId": "default"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=tls, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def multipart_name(name):
    boundary = "docscope-oidc-write"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="name"\r\n\r\n{name}\r\n'
            f'--{boundary}--\r\n').encode()
    return body, f"multipart/form-data; boundary={boundary}"


def main():
    with tempfile.TemporaryDirectory(prefix="fineract-docscope-write-oidc-") as temp:
        key = Path(temp) / "issuer-key.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                        "-out", str(key)], capture_output=True, check=True)
        modulus = subprocess.check_output(["openssl", "rsa", "-in", str(key), "-noout", "-modulus"],
                                          stderr=subprocess.DEVNULL).decode().strip().split("=", 1)[1]
        JWKS.update({"keys": [{"kty": "RSA", "kid": "docscope-write-20261126", "use": "sig", "alg": "RS256",
                               "n": b64u(bytes.fromhex(modulus)), "e": "AQAB"}]})
        server = http.server.HTTPServer(("127.0.0.1", 8181), JwksHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            updater_name = UPDATER_NAME
            deleter_name = DELETER_NAME
            auth = {
                "updater": "Bearer " + token_for(key, updater_name),
                "deleter": "Bearer " + token_for(key, deleter_name),
                "reader": "Bearer " + token_for(key, "doc_scope_reader_20261126"),
            }
            update_id, delete_id = FIXTURE["update_document_id"], FIXTURE["delete_document_id"]
            results = {"source": BASE, "issuer": ISSUER, "fixture_ids": {"update": update_id, "delete": delete_id},
                       "users": {"updater": updater_name, "deleter": deleter_name}, "observations": {}}

            def check(label, method, path, actor, expected, body=None, content_type=None):
                status, raw = request(method, path, auth[actor], body, content_type)
                entry = {"http": status}
                if status == 200 and method == "GET":
                    try:
                        value = json.loads(raw)
                        if isinstance(value, dict):
                            entry["name"] = value.get("name")
                    except json.JSONDecodeError:
                        pass
                results["observations"][label] = entry
                if status != expected:
                    raise RuntimeError(f"{label}: expected {expected}, got {status}")

            check("updater_b_client", "GET", f"/api/v1/clients/{CLIENT_B}", "updater", 404)
            check("deleter_b_client", "GET", f"/api/v1/clients/{CLIENT_B}", "deleter", 404)
            check("updater_b_doc_read", "GET", f"/api/v1/clients/{CLIENT_B}/documents/{update_id}", "updater", WRITER_DOCUMENT_READ_HTTP)
            check("deleter_b_doc_read", "GET", f"/api/v1/clients/{CLIENT_B}/documents/{delete_id}", "deleter", WRITER_DOCUMENT_READ_HTTP)
            check("reader_update_before", "GET", f"/api/v1/clients/{CLIENT_B}/documents/{update_id}", "reader", 200)
            check("reader_delete_before", "GET", f"/api/v1/clients/{CLIENT_B}/documents/{delete_id}", "reader", 200)
            check("updater_denied_delete", "DELETE", f"/api/v1/clients/{CLIENT_A}/documents/{delete_id}", "updater", 403)
            body, content_type = multipart_name("Should Not Change")
            check("deleter_denied_update", "PUT", f"/api/v1/clients/{CLIENT_A}/documents/{update_id}", "deleter", 403,
                  body, content_type)
            changed = "OIDC A-office changed B document " + str(int(time.time()))
            body, content_type = multipart_name(changed)
            check("updater_wrong_parent_update", "PUT", f"/api/v1/clients/{CLIENT_A}/documents/{update_id}", "updater", 200,
                  body, content_type)
            check("reader_update_after", "GET", f"/api/v1/clients/{CLIENT_B}/documents/{update_id}", "reader", 200)
            if results["observations"]["reader_update_after"].get("name") != changed:
                raise RuntimeError("B document name did not change")
            check("deleter_wrong_parent_delete", "DELETE", f"/api/v1/clients/{CLIENT_A}/documents/{delete_id}", "deleter", 200)
            check("reader_delete_after", "GET", f"/api/v1/clients/{CLIENT_B}/documents/{delete_id}", "reader", 404)
            basic = "Basic " + base64.b64encode(b"mifos:password").decode()
            basic_status, _ = request("GET", f"/api/v1/clients/{CLIENT_A}", basic)
            results["observations"]["basic_only_control"] = {"http": basic_status}
            if basic_status != 401:
                raise RuntimeError(f"Basic-only control expected 401, got {basic_status}")
            RESULT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
            print(RESULT)
            print(json.dumps(results["observations"], indent=2, sort_keys=True))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
