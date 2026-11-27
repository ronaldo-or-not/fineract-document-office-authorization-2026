# Fineract 문서 권한 검증 현황 — 2026-11-27

이 문서는 **제품에서 실제로 실행해 본 결과**와 **제보 판정에 필요한 외부 사실**을 분리한다. 모든 요청은 로컬 서버와 합성 고객·문서에만 보냈다. 실제 금융기관이나 타인의 서버는 시험하지 않았다.

검증 순서는 제한된 문서 권한 계정의 교차 지점 쓰기 → **반대 메서드 권한도 차단되는지 대조** → 예상과 다른 릴리스의 DELETE 성공 → 권한 0개 계정으로 독립 재현 → 공개 수정 PR과 새 HEAD의 차단 결과 확인이었다. 이 순서 때문에 릴리스의 넓은 권한 누락과 최신 코드의 객체 범위 문제를 같은 취약점으로 합치지 않았다.

| 질문 | 확인한 결과 | 증거와 해석 |
| --- | --- | --- |
| 공식 안정 릴리스의 쓰기 경로도 실행했나? | 예. Apache 공식 1.16.1 아카이브 SHA-512를 대조하고 JAR를 빈 DB에 실행했다. A지점 제한 계정이 API에서 B문서 ID를 찾아 올바른 B고객 경로로 수정·삭제했다. 삭제 전 파일과 삭제 후 DB·파일 부재를 확인했다. | [배포본 출처](lab/evidence/document_office_official_1161_write_artifact_provenance_20261127.json), [실행 출처](lab/evidence/document_office_official_1161_write_provenance_20261127.json), [연쇄 재현](lab/evidence/document_office_single_account_chain_official_1161_20261127.json), [역할 DB 대조](lab/evidence/document_office_official_1161_write_db_20261127.txt), [자기 지점 대조](lab/evidence/document_office_same_office_control_official_1161_20261127.json) |
| 릴리스에서 문서 권한이 꼭 필요한가? | 아니었다. **권한 0개**인 로그인 계정도 B고객 문서 세부·파일을 읽고, 이름을 바꾸고, 파일과 DB 행을 삭제했다. 고객 조회·문서 목록은 `403`; 미로그인·잘못된 암호는 `401`이었다. | [독립 합성 문서 재현](lab/evidence/document_office_official_1161_zero_role_nested_document_20261127.json). 이는 릴리스의 문서 하위 URL 권한 매처 누락과 일치하며 [공개 PR #6935](https://github.com/apache/fineract/pull/6935)가 이후 다뤘다. **신규 미공개 취약점으로 주장하지 않는다.** |
| 최신 `develop` HEAD에서 넓은 권한 누락은 막혔나? | 예. 2026-11-27 원격 HEAD `b033c1363…`의 권한 0개 A지점 계정은 B고객 문서 세부·첨부·PUT·DELETE 모두 `403`이었고 대상 문서는 유지됐다. | [음성 대조](lab/evidence/document_office_scope_b033_basic_zero_role_control_20261127.json), [소스·서버 출처](lab/evidence/document_office_scope_b033_basic_zero_role_provenance_20261127.json) |
| 최신 HEAD에서 다른 지점 문서에 무슨 일이 가능한가? | `READ_CLIENT`+`READ_DOCUMENT`+`UPDATE_DOCUMENT` 또는 `DELETE_DOCUMENT`를 가진 A지점 계정은 B고객 상세 `404`를 받으면서 B문서 ID를 API에서 찾고 정확한 B고객 경로로 수정·삭제했다. 반대 쓰기 메서드는 `403`, 자기 지점 작업은 `200`이었다. | [빈 DB·새 스키마 빌드 출처](lab/evidence/document_office_single_account_chain_fresh_b033_regen_provenance_20261127.json), [연쇄 재현](lab/evidence/document_office_single_account_chain_fresh_b033_regen_20261127.json), [역할·소속](lab/evidence/document_office_single_account_chain_fresh_b033_regen_db_20261127.txt), [자기 지점 대조](lab/evidence/document_office_same_office_control_fresh_b033_regen_20261127.json). **문서 권한의 지점 범위가 의도된 정책인지가 보안 분류의 결정점이다.** |
| 새 HEAD의 외부 OIDC 경로도 확인했나? | 예. 서명된 합성 Bearer 토큰으로 B고객 `404`, 잘못된 메서드 `403`, B문서 수정·삭제 `200`을 확인했다. 같은 API에 Basic만 보내면 `401`이었다. | [OIDC 응답](lab/evidence/document_office_scope_b033_oidc_write_20261127.json), [실행 출처](lab/evidence/document_office_scope_b033_oidc_provenance_20261127.json). Basic 설정 플래그는 `true`지만 API에는 OIDC 체인이 적용됐다. |
| Basic을 끈 OIDC 단독 구성은? | 새 HEAD에서 서버가 시작하지 않았다. `ForgotPasswordServiceImpl`이 요구하는 `PasswordEncoder` 빈이 없다. | [정확한 플래그·오류·로그 해시](lab/evidence/document_office_scope_b033_oidc_only_startup_20261127.json). 따라서 OIDC 단독의 문서 요청 결과는 시험할 수 없다. 이것은 별도의 기동 결함 후보이며 성공한 OIDC 실험의 구성을 바꾸어 쓰지 않는다. |

## 지금 내릴 수 있는 판정

1. **1.16.1 릴리스의 권한 0개 문서 읽기·수정·삭제는 입증된 제품 권한 결함이다.** 하지만 2026-11-22 공개 수정과 겹친다. 현재 안정 릴리스에 남아 있다는 사실은 운영 위험을 설명할 수 있어도, 그 자체로 새로운 제보나 CVE를 보장하지 않는다.
2. **최신 HEAD의 교차 지점 문서 읽기·수정·삭제는 입증된 동작이다.** A지점 계정에 문서 권한이 필요하고, 그 권한이 원래 테넌트 전역이라면 이 동작만으로 무단 접근이라고 할 수 없다. [공식 지점 계층 문서](https://github.com/apache/fineract/blob/b033c13637123574a2242e39ce5e6aef29f58fdb/fineract-doc/src/docs/en/chapters/architecture/office-hierarchy-access.adoc)는 일반적인 자기 지점·하위 지점 범위를 설명하지만 문서 권한의 예외 여부를 명시하지 않는다. [공개 정책 질문](DOCUMENT_OFFICE_POLICY_QUESTION_EN.md)은 작성했으며, 게시 전 벤더 보안팀에는 보내지 않았다.
3. **실제 금융기관의 배포 버전·역할 부여 빈도·고객 문서 종류는 로컬 제품 실험만으로 알 수 없다.** 특정 기관의 사고나 전산 마비, `Critical`은 이 증거로 주장할 수 없다. 제품 결함의 존재와 금융권 실제 확산은 별개 질문이다.

남은 결정점은 유지보수자의 **문서 권한이 지점별인지 테넌트 전역인지**에 대한 답과 비공개 선행 신고 중복 확인이다. 그 답이 지점별이라면 최신 HEAD의 재현은 해당 경계 위반을 직접 보인다. 테넌트 전역이라면 최신 교차 지점 행위의 보안 분류를 다시 해야 한다. 어느 경우든 릴리스의 공개 수정된 권한 매처 문제와 섞어 신규성이나 심각도를 부풀리지 않는다.
