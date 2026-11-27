# Apache Fineract document API: cross-office reads and writes reproduced

On the tested `develop` commit, two limited A-office users found a B-office client's document IDs through the API, downloaded an attachment, changed one document's name and deleted another. The same users received `404` for that B-client's detail. The write requests used the **correct B-client URL**; after deletion, the document's database row and physical file were gone. The attacker phase used the limited users' own credentials, while an administrator created only the synthetic fixtures.

## 한국어 요약

**고객은 보이지 않았지만, 그 고객의 문서는 발견하고 읽고 바꾸고 삭제할 수 있었다.** A지점 소속 비관리자 계정 두 개에 `READ_CLIENT`·`READ_DOCUMENT`와 각각 `UPDATE_DOCUMENT`·`DELETE_DOCUMENT`만 부여했다. 두 계정은 B지점 고객 상세에서 `404`를 받았지만, 합성 고객 ID 1~16을 API로 조회해 B문서 ID를 직접 찾아냈다. 첨부 파일은 원본과 해시가 일치했고, 올바른 B고객 URL로 보낸 수정 요청은 문서 이름을 바꿨다. 삭제 요청 후에는 문서 조회가 `404`였고, DB 행과 실제 파일도 사라졌다. [요청별 실행 기록](lab/evidence/document_office_single_account_chain_fresh_b033_regen_20261127.json)과 [빌드·실행 출처](lab/evidence/document_office_single_account_chain_fresh_b033_regen_provenance_20261127.json)를 공개한다.

이 결과는 **빈 데이터베이스에서 직접 빌드·기동한 Fineract `develop` 커밋 `b033c1363…`**에서 얻었다. 자기 지점의 정상 작업은 성공했고, 부여되지 않은 반대 쓰기 권한은 `403`으로 차단됐다. 공식 1.16.1 바이너리도 별도로 실행해 버전별 차이를 대조했다. 모든 실험은 직접 소유한 로컬 서버와 합성 고객·PNG만 사용했다.

Research snapshot: **27 November 2026 (KST)**. No financial institution, real customer data or third-party service was tested.

## Findings and their status

| Tested build | Actor and observed behavior | Interpretation |
| --- | --- | --- |
| `develop` commit [`b033c13637123574a2242e39ce5e6aef29f58fdb`](https://github.com/apache/fineract/commit/b033c13637123574a2242e39ce5e6aef29f58fdb), built and run against fresh databases | The zero-permission user's nested requests returned `403`. An A-office non-admin user with `READ_CLIENT`, `READ_DOCUMENT` and either `UPDATE_DOCUMENT` or `DELETE_DOCUMENT` received `404` for B-client detail but `200` for B-document reads and for the permitted write using the **correct B-client URL**. The delete removed both the database row and physical file. | The route fix enforced method permissions, while these document requests still lacked a parent-client office check. |
| Same `develop` commit, write path | A write request with a client ID that did **not** own the document still changed or deleted that document when the document ID was valid; the corresponding GET rejected that parent mismatch. | Reproduced parent-ID consistency defect. The mismatched URL is **not required** for the cross-office write above. |
| Official [Fineract 1.16.1](https://fineract.apache.org/) binary, verified against Apache's SHA-512 | A signed-in A-office user with **zero API permissions** received `200` for a B-office client's document detail and attachment, and for document `PUT` and `DELETE`. Client detail and document listing returned `403`; unauthenticated access returned `401`. | This nested route permission gap was publicly addressed by [upstream PR #6935](https://github.com/apache/fineract/pull/6935), merged on 22 November 2026. The fix was not in the tested 1.16.1 binary. |

The [office hierarchy documentation](https://github.com/apache/fineract/blob/b033c13637123574a2242e39ce5e6aef29f58fdb/fineract-doc/src/docs/en/chapters/architecture/office-hierarchy-access.adoc) describes access to one's own and subordinate offices, but does not explicitly say whether `*_DOCUMENT` permissions are exceptions. That unresolved policy point is decisive for classifying the development-branch behavior as an authorization vulnerability. The default non-admin role did not have document permissions in our test. We did not measure role prevalence in real deployments, large-scale discovery, financial loss, a real data breach or system availability impact.

An external OIDC Bearer path was also exercised with a locally controlled, signed synthetic issuer. This verified token signature validation, mapping to the limited Fineract users and the document requests. It was not a test against a real identity provider. On this commit, setting Basic authentication to `false` while enabling OIDC caused startup to fail due to a missing `PasswordEncoder` bean; the successful Bearer experiment had the Basic flag set to `true`, while Basic-only **API requests** returned `401`.

## Start with the evidence

- [Verification status and unresolved questions (Korean)](DOCUMENT_OFFICE_VERIFICATION_STATUS_20261127.md)
- [Read path, release provenance, controls and limitations (Korean)](DOCUMENT_OFFICE_SCOPE_REPORT_KO.md)
- [Write path, parent mismatch, controls and limitations (Korean)](DOCUMENT_OFFICE_WRITE_SCOPE_REPORT_KO.md)
- [Question about intended document permission scope (English)](DOCUMENT_OFFICE_POLICY_QUESTION_EN.md)
- [Official 1.16.1 zero-permission HTTP and filesystem observations](lab/evidence/document_office_official_1161_zero_role_nested_document_20261127.json)
- [Fresh `b033c1363` source/build provenance](lab/evidence/document_office_single_account_chain_fresh_b033_regen_provenance_20261127.json) and [bounded API discovery through write/delete](lab/evidence/document_office_single_account_chain_fresh_b033_regen_20261127.json)
- [Role and document ownership from the same run](lab/evidence/document_office_single_account_chain_fresh_b033_regen_db_20261127.txt), [same-office positive control](lab/evidence/document_office_same_office_control_fresh_b033_regen_20261127.json), and [zero-permission negative control](lab/evidence/document_office_scope_b033_basic_zero_role_control_20261127.json)
- [OIDC Bearer observations](lab/evidence/document_office_scope_b033_oidc_write_20261127.json) and [OIDC-only startup limitation](lab/evidence/document_office_scope_b033_oidc_only_startup_20261127.json)

The reports link to the remaining evidence files. The JSON and text files record synthetic IDs, HTTP status codes, hashes, role assignments and local runtime provenance. Raw access tokens, private signing keys and real customer documents are not included.

## Reproduction materials

`lab/` contains the Python scripts used for this research. They use the Python standard library and send API requests only to loopback HTTPS. The recorded run used a disposable PostgreSQL master and tenant database, Fineract's default document store and synthetic PNGs. For the development snapshot, check out the exact commit above and supply a running local Fineract server, its disposable tenant database and the matching environment variables. Some scripts require local `psql` access and Fineract's content store to verify that deletion persisted. The [read probe](lab/document_office_scope_reproduce.py) seeds the synthetic offices, roles, clients and documents; the [write probe](lab/document_office_write_scope_reproduce.py) creates limited write users; the [bounded discovery and write probe](lab/document_office_single_account_chain.py) requires `FINERACT_LAB_RESULT_PATH`, `FINERACT_LAB_TENANT_DB` and either `FINERACT_LAB_EXPECTED_HEAD` or a verified release artifact hash. The corresponding reports describe the exact run conditions and controls.

The source checkout and official binary are intentionally not included. This repository is a record of the observed runs, not a one-command Fineract deployment kit. The Docker-backed code-generation path failed locally; for the final development run, QueryDSL sources were generated from this exact commit using a temporary local PostgreSQL adapter, and the adapter was restored before the clean product build and server run. See the [provenance record](lab/evidence/document_office_single_account_chain_fresh_b033_regen_provenance_20261127.json).

## Disclosure and attribution

This is an independent research record, not an Apache Fineract advisory. The findings were not submitted to the Fineract security team before this public release, and the maintainers have not confirmed the intended document permission scope. Fineract [asks that security vulnerabilities be reported privately](https://fineract.apache.org/). Please distinguish the publicly fixed route matcher from the remaining policy question when citing this work.
