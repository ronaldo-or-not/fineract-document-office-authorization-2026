#!/usr/bin/env python3
"""Local-only Fineract document/office-scope probe with synthetic data."""

import base64
import hashlib
import json
import os
import ssl
import struct
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path


BASE = os.getenv("FINERACT_LAB_BASE_URL", "https://localhost:8447/fineract-provider/api/v1")
if not BASE.startswith(("https://localhost:", "https://127.0.0.1:")):
    raise SystemExit("This probe only sends requests to loopback HTTPS")

ADMIN = os.getenv("FINERACT_LAB_ADMIN_CREDS", "mifos:password")
PASSWORD = os.getenv("FINERACT_LAB_PROBE_PASSWORD", "DocScope#2026Test9!")
REPLAY_ONLY = os.getenv("FINERACT_LAB_REPLAY_ONLY", "false").lower() in ("1", "true", "yes")
STATE = Path(os.getenv("FINERACT_LAB_STATE_PATH", Path(__file__).parent / "evidence" / "document_office_scope_state.json"))
RESULT = Path(os.getenv("FINERACT_LAB_RESULT_PATH", Path(__file__).parent / "evidence" / "document_office_scope_result.json"))
STATE.parent.mkdir(parents=True, exist_ok=True)
RESULT.parent.mkdir(parents=True, exist_ok=True)
state = json.loads(STATE.read_text()) if STATE.exists() else {}
tls = ssl._create_unverified_context()  # Only the local lab uses a self-signed certificate.


def request(method, path, credentials, payload=None, content_type="application/json"):
    headers = {"Fineract-Platform-TenantId": "default", "Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()}
    if payload is not None:
        headers["Content-Type"] = content_type
    data = json.dumps(payload).encode() if isinstance(payload, dict) else payload
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=tls, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def json_request(method, path, credentials, payload=None):
    code, raw = request(method, path, credentials, payload)
    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        body = raw[:300].decode(errors="replace")
    return code, body


def save_state():
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def create(key, path, payload):
    if key in state:
        return state[key]
    if REPLAY_ONLY:
        raise RuntimeError(f"Missing seeded resource in replay-only mode: {key}")
    code, body = json_request("POST", path, ADMIN, payload)
    if code not in (200, 201) or not isinstance(body, dict) or "resourceId" not in body:
        raise RuntimeError(f"Creating {key} failed: HTTP {code}, {body}")
    state[key] = body["resourceId"]
    save_state()
    return state[key]


def ensure_office(key, name):
    if key in state:
        return state[key]
    if REPLAY_ONLY:
        raise RuntimeError(f"Missing seeded office in replay-only mode: {key}")
    code, body = json_request("GET", "/offices", ADMIN)
    if code != 200 or not isinstance(body, list):
        raise RuntimeError(f"Listing offices failed: HTTP {code}, {body}")
    existing = next((item["id"] for item in body if item.get("name") == name), None)
    if existing is not None:
        state[key] = existing
        save_state()
        return existing
    return create(key, "/offices", {"name": name, "parentId": 1, "openingDate": "01 November 2026",
                                     "dateFormat": "dd MMMM yyyy", "locale": "en"})


def upload_document(key, client_id, label):
    if key in state:
        return state[key]
    if REPLAY_ONLY:
        raise RuntimeError(f"Missing seeded document in replay-only mode: {key}")
    marker = f"SYNTHETIC DOCUMENT FOR {label}; NO REAL CUSTOMER DATA".encode()
    def png_chunk(kind, contents):
        return struct.pack(">I", len(contents)) + kind + contents + struct.pack(">I", zlib.crc32(kind + contents))
    image = (b"\x89PNG\r\n\x1a\n"
             + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
             + png_chunk(b"tEXt", b"Comment\x00" + marker)
             + png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
             + png_chunk(b"IEND", b""))
    boundary = "fineract-docscope-synthetic-20261126"
    chunks = []
    for name, value in (("name", f"Synthetic {label} ID check"), ("description", "Local security lab file")):
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"synthetic-{label}.png\"\r\nContent-Type: image/png\r\n\r\n".encode() + image + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    code, raw = request("POST", f"/clients/{client_id}/documents", ADMIN, b"".join(chunks), f"multipart/form-data; boundary={boundary}")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = raw[:300].decode(errors="replace")
    if code not in (200, 201) or not isinstance(body, dict) or "resourceId" not in body:
        raise RuntimeError(f"Uploading {key} failed: HTTP {code}, {body}")
    state[key] = body["resourceId"]
    save_state()
    return state[key]


def ensure_role(key, name, permissions):
    if REPLAY_ONLY:
        if key not in state:
            raise RuntimeError(f"Missing seeded role in replay-only mode: {key}")
        return state[key]
    role_id = create(key, "/roles", {"name": name, "description": "Synthetic branch-scope security lab"})
    if not permissions:
        return role_id
    code, body = json_request("PUT", f"/roles/{role_id}/permissions", ADMIN, {"permissions": permissions})
    if code != 200:
        raise RuntimeError(f"Setting role permissions failed: HTTP {code}, {body}")
    return role_id


def make_user(key, username, role_id, office_id):
    return create(key, "/users", {
        "username": username, "firstname": "Synthetic", "lastname": "Reader", "email": f"{username}@example.invalid",
        "officeId": office_id, "roles": [role_id], "sendPasswordToEmail": False,
        "password": PASSWORD, "repeatPassword": PASSWORD,
    })


def observe(name, path, credentials, binary=False):
    code, raw = request("GET", path, credentials)
    entry = {"http": code, "bytes": len(raw)}
    if code == 200 and binary:
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
        entry["synthetic_marker"] = b"SYNTHETIC DOCUMENT FOR " in raw
    elif code == 200:
        try:
            body = json.loads(raw)
            entry["count"] = len(body) if isinstance(body, list) else None
            entry["ids"] = [item.get("id") for item in body] if isinstance(body, list) else []
        except json.JSONDecodeError:
            entry["parse_error"] = True
    observations[name] = entry
    print(f"{name}: {json.dumps(entry, sort_keys=True)}")


def main():
    office_a = ensure_office("office_a", "Scope Lab Branch A")
    office_b = ensure_office("office_b", "Scope Lab Branch B")
    reader_role = ensure_role("reader_role", "Synthetic Doc Scope Reader 20261126", {"READ_CLIENT": True, "READ_DOCUMENT": True})
    nodoc_role = ensure_role("nodoc_role", "Synthetic Client Only 20261126", {"READ_CLIENT": True})
    zero_role = ensure_role("zero_role", "Synthetic Zero Permission 20261126", {})
    make_user("reader_user", "doc_scope_reader_20261126", reader_role, office_a)
    make_user("nodoc_user", "doc_scope_nodoc_20261126", nodoc_role, office_a)
    make_user("zero_user", "doc_scope_zero_20261126", zero_role, office_a)
    a = create("client_a", "/clients", {"officeId": office_a, "legalFormId": 1, "firstname": "Synthetic", "lastname": "DocscopeA", "active": True,
                                         "activationDate": "20 November 2026", "dateFormat": "dd MMMM yyyy", "locale": "en"})
    b = create("client_b", "/clients", {"officeId": office_b, "legalFormId": 1, "firstname": "Synthetic", "lastname": "DocscopeB", "active": True,
                                         "activationDate": "20 November 2026", "dateFormat": "dd MMMM yyyy", "locale": "en"})
    a_doc = upload_document("document_a", a, "BRANCH-A")
    b_doc = upload_document("document_b", b, "BRANCH-B")

    reader = "doc_scope_reader_20261126:" + PASSWORD
    nodoc = "doc_scope_nodoc_20261126:" + PASSWORD
    zero = "doc_scope_zero_20261126:" + PASSWORD
    observe("reader_own_client", f"/clients/{a}", reader)
    observe("reader_other_client", f"/clients/{b}", reader)
    observe("reader_own_doc_list", f"/clients/{a}/documents", reader)
    observe("reader_other_doc_list", f"/clients/{b}/documents", reader)
    observe("reader_other_doc_meta", f"/clients/{b}/documents/{b_doc}", reader)
    observe("reader_own_attachment", f"/clients/{a}/documents/{a_doc}/attachment", reader, True)
    observe("reader_other_attachment", f"/clients/{b}/documents/{b_doc}/attachment", reader, True)
    observe("reader_wrong_parent", f"/clients/{a}/documents/{b_doc}/attachment", reader, True)
    observe("nodoc_other_doc_list", f"/clients/{b}/documents", nodoc)
    observe("nodoc_other_doc_meta", f"/clients/{b}/documents/{b_doc}", nodoc)
    observe("nodoc_other_attachment", f"/clients/{b}/documents/{b_doc}/attachment", nodoc, True)
    observe("zero_other_client", f"/clients/{b}", zero)
    observe("zero_other_doc_list", f"/clients/{b}/documents", zero)
    observe("zero_other_doc_meta", f"/clients/{b}/documents/{b_doc}", zero)
    observe("zero_other_attachment", f"/clients/{b}/documents/{b_doc}/attachment", zero, True)
    RESULT.write_text(json.dumps({"source": BASE, "ids": state, "observations": observations}, indent=2, sort_keys=True) + "\n")
    print(f"Evidence: {RESULT}")


observations = {}
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
