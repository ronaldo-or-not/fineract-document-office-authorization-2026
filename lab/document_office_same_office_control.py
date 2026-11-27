#!/usr/bin/env python3
"""Positive controls for same-office document writes by the chain's limited users."""

import json
import os
import subprocess
from pathlib import Path

import document_office_write_scope_reproduce as probe


def main():
    chain = json.loads(Path(os.environ["FINERACT_LAB_CHAIN_RESULT_PATH"]).read_text())
    result_path = Path(os.environ["FINERACT_LAB_RESULT_PATH"])
    tenant_db = os.environ["FINERACT_LAB_TENANT_DB"]
    db_user = os.getenv("FINERACT_LAB_DB_USER", "root")
    update_user = chain["setup"]["actors"]["update"]["username"] + ":" + probe.PASSWORD
    delete_user = chain["setup"]["actors"]["delete"]["username"] + ":" + probe.PASSWORD
    update_id, _ = probe.upload(probe.client_a, "A-CONTROL-UPDATE-" + probe.tag)
    delete_id, _ = probe.upload(probe.client_a, "A-CONTROL-DELETE-" + probe.tag)
    location = subprocess.check_output([
        "psql", "-U", db_user, "-d", tenant_db, "-Atc",
        f"select location from m_document where id={delete_id}",
    ], text=True).strip()
    delete_file = Path.home() / ".fineract/DefaultDemoTenant" / location
    if not delete_file.is_file():
        raise RuntimeError("Same-office delete fixture file missing before action")
    observations = {}
    for label, credentials in (("update", update_user), ("delete", delete_user)):
        observations[label + "_own_client_http"] = probe.call_json("GET", f"/clients/{probe.client_a}", credentials)[0]
    observations["update_doc_before_http"] = probe.call_json(
        "GET", f"/clients/{probe.client_a}/documents/{update_id}", update_user)[0]
    observations["delete_doc_before_http"] = probe.call_json(
        "GET", f"/clients/{probe.client_a}/documents/{delete_id}", delete_user)[0]
    new_name = "Same-office control changed " + probe.tag
    body, content_type = probe.multipart({"name": new_name})
    observations["update_http"] = probe.call(
        "PUT", f"/clients/{probe.client_a}/documents/{update_id}", update_user, body, content_type)[0]
    status, after = probe.call_json("GET", f"/clients/{probe.client_a}/documents/{update_id}", update_user)
    observations["update_doc_after_http"] = status
    observations["update_doc_after_name"] = after.get("name") if isinstance(after, dict) else None
    observations["delete_http"] = probe.call(
        "DELETE", f"/clients/{probe.client_a}/documents/{delete_id}", delete_user)[0]
    observations["delete_doc_after_http"] = probe.call_json(
        "GET", f"/clients/{probe.client_a}/documents/{delete_id}", delete_user)[0]
    observations["delete_file_exists_after"] = delete_file.exists()
    expected = {"update_own_client_http": 200, "delete_own_client_http": 200,
                "update_doc_before_http": 200, "delete_doc_before_http": 200,
                "update_http": 200, "update_doc_after_http": 200,
                "update_doc_after_name": new_name, "delete_http": 200,
                "delete_doc_after_http": 404, "delete_file_exists_after": False}
    if observations != expected:
        raise RuntimeError(f"Same-office controls failed: {observations}")
    result = {"source": probe.BASE, "client_a": probe.client_a,
              "update_document_id": update_id, "delete_document_id": delete_id,
              "observations": observations}
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result_path)
    print(json.dumps(observations, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
