#!/usr/bin/env python3
"""Prepare fresh synthetic documents and a local IdP config for the OIDC replay."""

import json
import os
from pathlib import Path

import document_office_write_scope_reproduce as probe


def main():
    output = Path(os.environ["FINERACT_LAB_OIDC_FIXTURE_PATH"])
    status, _ = probe.call_json("GET", "/tenants/default/oidc-config", probe.ADMIN)
    if status != 404:
        raise RuntimeError(f"Expected disposable tenant without OIDC config, got {status}")
    update_id, update_hash = probe.upload(probe.client_b, "HEAD-OIDC-B-UPDATE-" + probe.tag)
    delete_id, delete_hash = probe.upload(probe.client_b, "HEAD-OIDC-B-DELETE-" + probe.tag)
    issuer = "http://127.0.0.1:8181/docscope"
    jwks_uri = "http://127.0.0.1:8181/jwks"
    status, body = probe.call_json("POST", "/tenants/default/oidc-config", probe.ADMIN, {
        "providerType": "GENERIC",
        "issuerUri": issuer,
        "jwksUri": jwks_uri,
        "clientId": "synthetic-docscope-head",
        "usernameClaim": "preferred_username",
        "enabled": True,
    })
    if status not in (200, 201):
        raise RuntimeError(f"OIDC fixture config failed: {status}, {body}")
    fixture = {
        "update_document_id": update_id,
        "delete_document_id": delete_id,
        "update_sha256": update_hash,
        "delete_sha256": delete_hash,
        "issuer": issuer,
        "jwks_uri": jwks_uri,
        "oidc_config_http": status,
    }
    output.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
    print(output)
    print(json.dumps(fixture, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
