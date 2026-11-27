# Apache Fineract: 다른 지점 고객 문서를 찾아 읽고 바꾸고 삭제한 재현

**2026-11-27 검증 | Apache Fineract `develop` 커밋 [`b033c13637123574a2242e39ce5e6aef29f58fdb`](https://github.com/apache/fineract/commit/b033c13637123574a2242e39ce5e6aef29f58fdb) | 로컬 합성 데이터**

## 핵심 결과

**A지점 비관리자 계정은 B지점 고객 상세를 볼 수 없었다(`404`). 그런데 같은 고객의 문서 ID를 API에서 직접 찾아 첨부 파일을 읽고, 문서 이름을 바꾸고, 다른 문서를 삭제했다.** 수정·삭제 요청은 실제 문서 소속과 일치하는 **B고객 URL**로 보냈다. 삭제 뒤에는 문서 조회가 `404`였고 데이터베이스 행과 실제 파일도 사라졌다.

| 검증 단계 | A지점 제한 계정의 결과 |
| --- | --- |
| 합성 고객 ID 1~16에서 B문서 ID 탐색 | B고객의 문서 목록 `200`; 대상 문서 ID 7·8 발견 |
| B고객 상세와 문서 첨부 대조 | 고객 상세 `404`; 문서 세부·첨부 `200`, 첨부 해시는 준비한 합성 파일과 일치 |
| 수정 권한 계정으로 B문서 7 이름 변경 | `PUT /clients/2/documents/7` → `200`; 재조회한 이름이 변경됨 |
| 삭제 권한 계정으로 B문서 8 삭제 | `DELETE /clients/2/documents/8` → `200`; 재조회 `404`, DB 행과 물리 파일 모두 없음 |

두 계정은 A지점 소속이며 공통으로 `READ_CLIENT`·`READ_DOCUMENT`를 가졌다. 한 계정에는 `UPDATE_DOCUMENT`, 다른 계정에는 `DELETE_DOCUMENT`만 추가했다. 관리자는 합성 지점·고객·문서와 계정 생성에만 사용했고, 위 탐색·열람·수정·삭제에는 제한 계정의 인증 정보를 사용했다. [요청별 결과](lab/evidence/document_office_single_account_chain_fresh_b033_regen_20261127.json)와 [역할·문서 소속 DB 대조](lab/evidence/document_office_single_account_chain_fresh_b033_regen_db_20261127.txt)를 공개했다.

## 재현의 강점

- **대상 ID를 제한 계정이 찾았다.** 운영자가 공격 단계에 B문서 ID를 넘겨주지 않았다. 합성 고객 ID 1~16을 API로 조회해 대상 문서 두 개를 골랐다.
- **결과를 서버 상태로 확인했다.** HTTP `200`만 기록한 것이 아니라 수정 후 이름, 삭제 후 조회 `404`, DB 행 부재와 물리 파일 삭제를 대조했다.
- **정상·차단 대조를 함께 실행했다.** [자기 지점 문서 작업](lab/evidence/document_office_same_office_control_fresh_b033_regen_20261127.json)은 성공했고, [문서 권한이 0개인 계정](lab/evidence/document_office_scope_b033_basic_zero_role_control_20261127.json)의 문서 세부·첨부·수정·삭제는 `403`이었다. 별도의 [합성 OIDC 실행](lab/evidence/document_office_scope_b033_oidc_write_20261127.json)에서 계정에 없는 반대 쓰기 권한도 `403`이었다.
- **실행한 코드를 고정했다.** 빈 데이터베이스에서 위 `develop` 커밋을 직접 빌드·기동하고, 재생성한 QueryDSL 소스로 재검증했다. [빌드·서버 출처](lab/evidence/document_office_single_account_chain_fresh_b033_regen_provenance_20261127.json)를 보존했다.

## 이 결과가 보여주는 것

고객 상세 조회가 적용하는 지점 범위와 문서 API가 적용하는 범위가 서로 다르게 동작했다. 문서 메서드 권한을 확인하는 최신 코드에서도 이 차이가 남았다. 쓰기 서비스가 URL의 부모 고객 ID와 실제 문서 소속을 대조하지 않는 현상도 별도로 재현했다. 교차 지점 작업은 **올바른 B고객 URL로도 성공했으므로**, 잘못된 부모 ID를 넣는 방법이 필수 조건은 아니다.

실험은 직접 소유한 로컬 서버의 합성 고객·PNG 문서에서 수행했다. 문서 권한이 원래 지점별인지 테넌트 전체인지에 대한 제품 정책은 확인이 필요하다. 버전별 수정 범위와 보안 분류 조건은 [전체 검증 현황](DOCUMENT_OFFICE_VERIFICATION_STATUS_20261127.md), [읽기 보고서](DOCUMENT_OFFICE_SCOPE_REPORT_KO.md), [쓰기 보고서](DOCUMENT_OFFICE_WRITE_SCOPE_REPORT_KO.md)에 분리했다.
