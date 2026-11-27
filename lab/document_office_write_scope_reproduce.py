#!/usr/bin/env python3
"""One-shot, loopback-only Fineract document write-scope probe on synthetic clients."""

import base64
import hashlib
import json
import os
import ssl
import struct
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path


BASE = os.getenv("FINERACT_LAB_BASE_URL", "https://localhost:8455/fineract-provider/api/v1")
if not BASE.startswith(("https://localhost:", "https://127.0.0.1:")):
    raise SystemExit("Only loopback HTTPS is permitted")

ADMIN = os.getenv("FINERACT_LAB_ADMIN_CREDS", "mifos:password")
PASSWORD = os.getenv("FINERACT_LAB_PROBE_PASSWORD", "DocScope#2026Test9!")
ORIGINAL_STATE = Path(os.getenv("FINERACT_LAB_STATE_PATH", Path(__file__).parent / "evidence/document_office_scope_state.json"))
RESULT = Path(os.getenv("FINERACT_LAB_RESULT_PATH", Path(__file__).parent / "evidence/document_office_write_scope_develop.json"))
state = json.loads(ORIGINAL_STATE.read_text())
client_a, client_b = state["client_a"], state["client_b"]
tls = ssl._create_unverified_context()  # Self-signed localhost test certificate.
tag = str(int(time.time()))
record = {"source": BASE, "tag": tag, "ids": {"client_a": client_a, "client_b": client_b}, "observations": {}}


def call(method, path, creds, payload=None, content_type=None):
    headers = {
        "Fineract-Platform-TenantId": "default",
        "Authorization": "Basic " + base64.b64encode(creds.encode()).decode(),
    }
    if content_type:
        headers["Content-Type"] = content_type
    data = json.dumps(payload).encode() if isinstance(payload, dict) else payload
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, context=tls, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def call_json(method, path, creds, payload=None):
    status, raw = call(method, path, creds, payload, "application/json" if payload is not None else None)
    try:
        return status, json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return status, None


def create(path, payload):
    status, body = call_json("POST", path, ADMIN, payload)
    if status not in (200, 201) or not isinstance(body, dict) or "resourceId" not in body:
        raise RuntimeError(f"Fixture creation failed: {path}: {status}, {body}")
    return body["resourceId"]


def role_and_user(suffix, permissions):
    role = create("/roles", {"name": f"Synthetic Docscope {suffix} {tag}", "description": "Local document write scope probe"})
    status, body = call_json("PUT", f"/roles/{role}/permissions", ADMIN, {"permissions": permissions})
    if status != 200:
        raise RuntimeError(f"Role permissions failed: {status}, {body}")
    username = f"docscope_{suffix}_{tag}"
    user = create("/users", {
        "username": username, "firstname": "Synthetic", "lastname": "Writer",
        "email": f"{username}@example.invalid", "officeId": state.get("office_a", 2),
        "roles": [role], "sendPasswordToEmail": False,
        "password": PASSWORD, "repeatPassword": PASSWORD,
    })
    return {"role": role, "user": user, "username": username}, username + ":" + PASSWORD


def png(marker):
    def chunk(kind, content):
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"tEXt", b"Comment\x00" + marker.encode())
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
            + chunk(b"IEND", b""))


def multipart(fields, file_bytes=None, file_name=None):
    boundary = "docscope-" + tag
    body = b""
    for name, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    if file_bytes is not None:
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
                 'Content-Type: image/png\r\n\r\n').encode() + file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def upload(client_id, label):
    image = png(f"SYNTHETIC DOCUMENT FOR {label}; NO REAL CUSTOMER DATA")
    body, content_type = multipart({"name": f"Synthetic {label}", "description": "Disposable write-scope target"}, image,
                                   f"synthetic-{label}.png")
    status, raw = call("POST", f"/clients/{client_id}/documents", ADMIN, body, content_type)
    result = json.loads(raw) if raw else None
    if status not in (200, 201) or not isinstance(result, dict) or "resourceId" not in result:
        raise RuntimeError(f"Fixture upload failed: {label}: {status}, {result}")
    return result["resourceId"], hashlib.sha256(image).hexdigest()


def observe(name, method, path, creds, payload=None, content_type=None):
    status, raw = call(method, path, creds, payload, content_type)
    item = {"http": status}
    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        body = None
    if isinstance(body, dict):
        item["resource_id"] = body.get("resourceId")
        item["name"] = body.get("name")
    record["observations"][name] = item
    return item


def require(name, status):
    got = record["observations"][name]["http"]
    if got != status:
        raise RuntimeError(f"{name}: expected HTTP {status}, got {got}")


def main():
    update_identity, updater = role_and_user("update", {"READ_CLIENT": True, "UPDATE_DOCUMENT": True})
    delete_identity, deleter = role_and_user("delete", {"READ_CLIENT": True, "DELETE_DOCUMENT": True})
    reader = "doc_scope_reader_20261126:" + PASSWORD
    record["ids"].update({"updater": update_identity, "deleter": delete_identity})
    update_id, update_hash = upload(client_b, "B-UPDATE-" + tag)
    delete_id, delete_hash = upload(client_b, "B-DELETE-" + tag)
    record["ids"].update({"update_target": update_id, "delete_target": delete_id,
                          "original_b_document": state["document_b"]})
    record["fixture_sha256"] = {"update_target": update_hash, "delete_target": delete_hash}

    observe("updater_b_client", "GET", f"/clients/{client_b}", updater)
    observe("deleter_b_client", "GET", f"/clients/{client_b}", deleter)
    observe("updater_b_doc_read", "GET", f"/clients/{client_b}/documents/{update_id}", updater)
    observe("deleter_b_doc_read", "GET", f"/clients/{client_b}/documents/{delete_id}", deleter)
    observe("reader_b_doc_before", "GET", f"/clients/{client_b}/documents/{update_id}", reader)
    observe("reader_delete_doc_before", "GET", f"/clients/{client_b}/documents/{delete_id}", reader)
    for name in ("updater_b_client", "deleter_b_client"):
        require(name, 404)
    for name in ("updater_b_doc_read", "deleter_b_doc_read"):
        require(name, 403)
    for name in ("reader_b_doc_before", "reader_delete_doc_before"):
        require(name, 200)

    observe("updater_wrong_permission_delete", "DELETE", f"/clients/{client_a}/documents/{delete_id}", updater)
    require("updater_wrong_permission_delete", 403)
    observe("deleter_wrong_permission_update", "PUT", f"/clients/{client_a}/documents/{update_id}", deleter,
            *multipart({"name": "Should Not Change"}))
    require("deleter_wrong_permission_update", 403)

    new_name = "Changed by A office with mismatched parent " + tag
    observe("updater_wrong_parent_update", "PUT", f"/clients/{client_a}/documents/{update_id}", updater,
            *multipart({"name": new_name}))
    require("updater_wrong_parent_update", 200)
    observe("reader_b_doc_after_update", "GET", f"/clients/{client_b}/documents/{update_id}", reader)
    require("reader_b_doc_after_update", 200)
    if record["observations"]["reader_b_doc_after_update"].get("name") != new_name:
        raise RuntimeError("B document name did not change")

    observe("deleter_wrong_parent_delete", "DELETE", f"/clients/{client_a}/documents/{delete_id}", deleter)
    require("deleter_wrong_parent_delete", 200)
    observe("reader_b_doc_after_delete", "GET", f"/clients/{client_b}/documents/{delete_id}", reader)
    require("reader_b_doc_after_delete", 404)
    observe("reader_original_b_doc_unchanged", "GET", f"/clients/{client_b}/documents/{state['document_b']}", reader)
    require("reader_original_b_doc_unchanged", 200)
    RESULT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(RESULT)
    print(json.dumps(record["observations"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
