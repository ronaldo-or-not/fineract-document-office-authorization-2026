#!/usr/bin/env python3
"""Read-only, loopback-only probe of Fineract's external OIDC Bearer path.

Operator prerequisite: configure the disposable tenant's OIDC issuer as
http://127.0.0.1:8181/docscope with JWKS URI http://127.0.0.1:8181/jwks.
This script runs a short-lived synthetic issuer and signs two lab JWTs. It
does not save private keys or tokens in the evidence JSON.
"""

import base64
import hashlib
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


BASE = os.getenv("FINERACT_LAB_BASE_URL", "https://localhost:8453/fineract-provider")
if not BASE.startswith(("https://localhost:", "https://127.0.0.1:")):
    raise SystemExit("Local loopback HTTPS only")
RESULT = Path(os.getenv("FINERACT_LAB_RESULT_PATH", Path(__file__).parent / "evidence" / "document_office_scope_external_oidc_develop.json"))
ISSUER = "http://127.0.0.1:8181/docscope"
JWKS = {}


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class JwksHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/jwks":
            self.send_error(404)
            return
        raw = json.dumps(JWKS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


def token_for(key_path, username):
    now = int(time.time())
    header = {"alg": "RS256", "kid": "docscope-20261126", "typ": "JWT"}
    claims = {"iss": ISSUER, "sub": "synthetic-" + username,
              "preferred_username": username, "aud": "fineract", "iat": now, "nbf": now - 5, "exp": now + 300}
    signing_input = (b64u(json.dumps(header, separators=(",", ":")).encode()) + "."
                     + b64u(json.dumps(claims, separators=(",", ":")).encode())).encode()
    signature = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key_path)], input=signing_input,
                               capture_output=True, check=True).stdout
    return signing_input.decode() + "." + b64u(signature)


def fetch(path, token):
    request = urllib.request.Request(BASE + path, headers={
        "Authorization": "Bearer " + token, "Fineract-Platform-TenantId": "default"})
    try:
        with urllib.request.urlopen(request, context=ssl._create_unverified_context(), timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main():
    with tempfile.TemporaryDirectory(prefix="fineract-docscope-oidc-") as temp:
        key_path = Path(temp) / "issuer-key.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                        "-out", str(key_path)], check=True, capture_output=True)
        modulus = subprocess.check_output(["openssl", "rsa", "-in", str(key_path), "-noout", "-modulus"],
                                          stderr=subprocess.DEVNULL).decode().strip().split("=", 1)[1]
        JWKS.update({"keys": [{"kty": "RSA", "kid": "docscope-20261126", "use": "sig", "alg": "RS256",
                               "n": b64u(bytes.fromhex(modulus)), "e": "AQAB"}]})
        server = http.server.HTTPServer(("127.0.0.1", 8181), JwksHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            paths = {"client": "/api/v1/clients/3", "doc_list": "/api/v1/clients/3/documents",
                     "doc_meta": "/api/v1/clients/3/documents/2",
                     "attachment": "/api/v1/clients/3/documents/2/attachment"}
            result = {"issuer": ISSUER, "jwks_uri": "http://127.0.0.1:8181/jwks",
                      "authentication": "external signed OIDC Bearer JWT through Fineract federation filter", "users": {}}
            for username in ("doc_scope_nodoc_20261126", "doc_scope_reader_20261126"):
                token = token_for(key_path, username)
                observations = {}
                for name, path in paths.items():
                    status, body = fetch(path, token)
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
                    observations[name] = entry
                result["users"][username] = observations
            RESULT.parent.mkdir(parents=True, exist_ok=True)
            RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            print(json.dumps(result, indent=2, sort_keys=True))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
