#!/usr/bin/env python3
"""Test nested document permissions on a local, synthetic Fineract 1.16.1 tenant."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import document_office_write_scope_reproduce as probe


RESULT = Path(os.environ["FINERACT_LAB_RESULT_PATH"])
TENANT_DB = os.environ["FINERACT_LAB_TENANT_DB"]
ARTIFACT = Path(os.environ["FINERACT_LAB_ARTIFACT_PATH"])
EXPECTED_SHA256 = os.environ["FINERACT_LAB_EXPECTED_ARTIFACT_SHA256"]
ZERO_USERNAME = "doc_scope_zero_20261126"


def sql(statement):
    return subprocess.check_output(
        ["psql", "-U", "root", "-d", TENANT_DB, "-Atc", statement], text=True
    ).strip()


def file_for(document_id):
    location = sql(f"select location from m_document where id={int(document_id)}")
    if not location:
        raise RuntimeError(f"Document {document_id} not in database")
    return Path.home() / ".fineract/DefaultDemoTenant" / location


def require(actual, expected, label):
    if actual != expected:
        raise RuntimeError(f"{label}: expected {expected}, got {actual}")


def main():
    if not TENANT_DB.replace("_", "").isalnum() or not TENANT_DB.islower():
        raise RuntimeError("Unsafe tenant database name")
    actual_hash = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    require(actual_hash, EXPECTED_SHA256, "official artifact SHA-256")
    zero_user_id = int(probe.state["zero_user"])
    zero_role_id = int(probe.state["zero_role"])
    user_rows = sql(
        "select u.office_id||'|'||o.hierarchy||'|'||ur.role_id "
        "from m_appuser u join m_office o on o.id=u.office_id "
        "join m_appuser_role ur on ur.appuser_id=u.id "
        f"where u.id={zero_user_id} and u.username='{ZERO_USERNAME}'"
    ).splitlines()
    require(user_rows, [f"{probe.state['office_a']}|.2.|{zero_role_id}"], "zero role and A office")
    require(sql(f"select count(*) from m_role_permission where role_id={zero_role_id}"), "0", "permission count")
    credentials = ZERO_USERNAME + ":" + probe.PASSWORD
    update_id, update_hash = probe.upload(probe.client_b, "ZERO-ROLE-UPDATE-" + probe.tag)
    delete_id, delete_hash = probe.upload(probe.client_b, "ZERO-ROLE-DELETE-" + probe.tag)
    update_file, delete_file = file_for(update_id), file_for(delete_id)
    require(hashlib.sha256(update_file.read_bytes()).hexdigest(), update_hash, "update file before")
    require(hashlib.sha256(delete_file.read_bytes()).hexdigest(), delete_hash, "delete file before")
    update_path = f"/clients/{probe.client_b}/documents/{update_id}"
    delete_path = f"/clients/{probe.client_b}/documents/{delete_id}"
    observed = {
        "own_client_http": probe.call_json("GET", f"/clients/{probe.client_a}", credentials)[0],
        "other_client_http": probe.call_json("GET", f"/clients/{probe.client_b}", credentials)[0],
        "other_document_list_http": probe.call_json("GET", f"/clients/{probe.client_b}/documents", credentials)[0],
        "other_document_get_http": probe.call_json("GET", update_path, credentials)[0],
    }
    attachment_status, attachment = probe.call("GET", update_path + "/attachment", credentials)
    observed["other_attachment_http"] = attachment_status
    observed["other_attachment_sha256"] = hashlib.sha256(attachment).hexdigest()
    require(observed["own_client_http"], 403, "own client forbidden")
    require(observed["other_client_http"], 403, "other client forbidden")
    require(observed["other_document_list_http"], 403, "document list forbidden")
    require(observed["other_document_get_http"], 200, "specific document")
    require(attachment_status, 200, "attachment")
    require(observed["other_attachment_sha256"], update_hash, "attachment bytes")
    changed_name = "Zero-role account changed B document " + probe.tag
    payload, content_type = probe.multipart({"name": changed_name})
    observed["update_http"] = probe.call("PUT", update_path, credentials, payload, content_type)[0]
    observed["updated_name"] = probe.call_json("GET", update_path, credentials)[1].get("name")
    observed["delete_http"] = probe.call("DELETE", delete_path, credentials)[0]
    observed["deleted_document_get_http"] = probe.call_json("GET", delete_path, credentials)[0]
    observed["delete_db_row_count"] = int(sql(f"select count(*) from m_document where id={delete_id}"))
    observed["delete_file_exists"] = delete_file.exists()
    require(observed["update_http"], 200, "update")
    require(observed["updated_name"], changed_name, "persisted update")
    require(observed["delete_http"], 200, "delete")
    require(observed["deleted_document_get_http"], 404, "deleted GET")
    require(observed["delete_db_row_count"], 0, "deleted database row")
    require(observed["delete_file_exists"], False, "deleted physical file")
    record = {
        "source": probe.BASE,
        "official_jar_sha256": actual_hash,
        "actor": {"user_id": zero_user_id, "username": ZERO_USERNAME, "office_id": probe.state["office_a"],
                  "office_hierarchy": ".2.", "role_id": zero_role_id, "permission_count": 0},
        "target": {"client_id": probe.client_b, "update_document_id": update_id, "delete_document_id": delete_id,
                   "update_file_sha256_before": update_hash, "delete_file_sha256_before": delete_hash},
        "observations": observed,
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(RESULT)
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
