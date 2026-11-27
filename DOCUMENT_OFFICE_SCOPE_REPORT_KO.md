# Apache Fineract 문서 API: 공개 수정의 권한 누락과 최신 코드의 타 지점 문서 노출

작성일: 2026-11-26, 최신 커밋 직접 재검증: 2026-11-27 (KST)<br>
상태: **2026-11-27 확인한 원격 `develop` HEAD `b033c1363…`의 빈 DB에서 Basic·외부 OIDC 경로 재현. 공식 1.16.1 JAR의 문서 읽기·수정·삭제도 새 DB에서 확인. 외부 서비스 미시험, 공개 연구 기록**. 1.16.1의 문서 하위 URL 권한 누락은 [2026-11-22 병합된 공개 PR #6935](https://github.com/apache/fineract/pull/6935)가 다룬 영역이므로 신규 미공개 결함으로 제시하지 않는다. 최신 코드의 지점 범위 문제는 그 수정 후에도 남아 있는 별도 후보이며, 비공개 중복 신고 여부는 확인할 수 없다.

같은 문서 API의 **타 지점 문서 수정·삭제와 부모 ID 불일치**는 [별도 재현 보고서](DOCUMENT_OFFICE_WRITE_SCOPE_REPORT_KO.md)에 분리했다. 아래의 CVSS 가늠값은 읽기 노출만 평가한다.

## 결론

서로 관련되지만 원인이 다른 두 가지 결과를 확인했다.

1. **현재 안정 릴리스 1.16.1의 문서 조회 권한 누락 — 공개 수정과 중복.** Apache가 배포한 공식 바이너리의 SHA-512를 공식 체크섬과 대조하고, 공식 배포본의 실행형 JAR를 `java -jar`로 실행했다. A지점 소속이며 API 권한이 **0개**인 로그인 계정이 B지점 고객의 `GET /clients/3/documents/2`와 `GET /clients/3/documents/2/attachment`에서 `200`을 받았다. 기본 Basic 인증에서는 고객 조회와 문서 목록이 `403`이었다. 동일한 JAR를 내장 OAuth2 모드로 실행하고 정상 로그인·PKCE 발급을 거친 토큰(`scope=[]`)으로 요청하자 고객 조회는 `403`인데 문서 목록·세부·첨부는 모두 `200`이었다. 다운로드된 143바이트 PNG의 SHA-256과 합성 표식이 관리자 업로드 파일과 일치했고, 인증 없는 다운로드는 `401`이었다. 별도로 WAR의 라이브러리를 추출해 실행한 결과도 같았다.
2. **1.16.1과 2026-11-27 확인한 최신 `develop`에 남은 지점 범위 누락.** `READ_CLIENT`와 `READ_DOCUMENT`만 가진 A지점 계정은 B지점 고객 상세 조회에서 `404`를 받지만, 그 고객의 문서 목록·세부·첨부 파일에서는 `200`을 받았다. 기본 Basic 인증, 내장 OAuth2, 그리고 외부 서명 OIDC 토큰 경로에서 검증했다. 새 HEAD `b033c1363…`에서는 빈 DB의 Basic 인증과 합성 발급자의 OIDC Bearer 인증을 각각 실행했다. 최신 `develop`은 첫 번째 권한 누락을 `/documents/**` 규칙으로 막지만, 문서 읽기 서비스에 부모 고객의 지점 접근 검사가 없어 두 번째 문제는 남는다. 새 HEAD의 권한 0개 계정은 문서 세부·첨부·수정·삭제 요청에서 모두 `403`을 받았다([음성 대조](lab/evidence/document_office_scope_b033_basic_zero_role_control_20261127.json)).

이 결과는 **A지점 제한 계정이 B지점 고객 문서의 실제 바이트를 받았다**는 사실을 입증한다. 이를 제품 정책상 기밀성 침해로 분류하려면 `READ_DOCUMENT` 권한의 지점 범위에 대한 확인이 필요하다. 파일에는 실제 개인정보를 넣지 않았고, 실제 금융기관의 설치나 사고는 확인하지 않았다. 시스템 장악, 쓰기 권한, 타 테넌트 접근, 전체 고객 파일의 일괄 추출 또는 서버 장애는 주장하지 않는다. 심각도와 CVE 여부는 벤더 판단 사항이며, 이 증거만으로 `Critical`이라고 단정하지 않는다.

## 왜 이 경계를 검사했는가

Fineract는 [고객 정보와 KYC 문서 관리를 제품 기능으로 설명](https://fineract.apache.org/index.html)하며, [공식 위협 모델](https://github.com/apache/fineract/blob/develop/SECURITY.md)은 제한된 권한의 내부 업무 사용자를 공격자 범위에 둔다. 최신 [공식 아키텍처 문서](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-doc/src/docs/en/chapters/architecture/office-hierarchy-access.adoc)는 사용자가 자기 지점과 하위 지점 자원에 접근하고 무관한 지점의 자원에는 접근하지 못한다고 설명한다. 고객 상세 조회도 로그인 사용자의 `officeHierarchy`를 조건으로 사용한다. 따라서 B지점 고객 상세가 보이지 않는 A지점 계정에서 그 고객의 문서가 보이는지 확인했다.

가설은 두 단계로 좁혔다. 먼저 문서 API의 목록·세부·첨부 경로가 같은 권한 검사를 받는지 비교했다. 다음으로 권한 검사가 있더라도 문서 읽기 서비스가 부모 고객의 지점 범위를 확인하는지 비교했다. 현재 `develop`의 [`DocumentReadPlatformServiceImpl`](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-document/src/main/java/org/apache/fineract/infrastructure/documentmanagement/service/DocumentReadPlatformServiceImpl.java#L40-L65)은 `entityType`, `entityId`, `documentId`로 문서를 찾고 파일 저장소에서 바이트를 읽지만 지점 계층을 검사하지 않는다. 반면 [`ClientReadPlatformServiceImpl.retrieveOne`](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-provider/src/main/java/org/apache/fineract/portfolio/client/service/ClientReadPlatformServiceImpl.java#L219-L225)은 로그인 사용자의 지점 계층으로 고객을 찾는다.

## 재현 환경과 계정

- **안정 릴리스:** [공식 사이트가 1.16.1을 현재 안정 릴리스로 표시](https://fineract.apache.org/index.html). `apache-fineract-bin-1.16.1.tar.gz`를 Apache 미러에서 받아 [공식 SHA-512](https://downloads.apache.org/fineract/1.16.1/apache-fineract-bin-1.16.1.tar.gz.sha512)와 일치시켰다. [공식 배포 문서가 권하는 실행형 JAR](https://fineract.apache.org/docs/stable/#_deployment) `fineract-provider-1.16.1.jar`를 Java 25의 `java -jar`로 실행했다. JAR SHA-256은 `bd70aa4033f1121549e921c982db10adf6fab151acd3dc3043b505dcf779308b`다. 앞서 같은 아카이브의 WAR 라이브러리로 얻은 결과도 별도 보존했다. 공식 바이너리의 코드는 수정하지 않았다.
- **개발 버전:** 최초 로컬 커밋 `0747fa5fc4a6beb7df501ef02194161d6f14c187`에서 Basic·내장 OAuth2·외부 서명 OIDC 토큰 모드를 실행했다. 2026-11-27 00시 당시 원격 HEAD `4d9557a572b178bd32e1839f81c48204b8fcad49`를 직접 실행해 Basic·외부 OIDC 결과를 재현했다([실행 출처](lab/evidence/document_office_scope_exact_head_provenance_20261127.json), [OIDC 읽기 응답](lab/evidence/document_office_scope_exact_head_oidc_20261127.json)). 원격 HEAD가 이후 `b033c13637123574a2242e39ce5e6aef29f58fdb`로 이동해, 이 커밋도 **빈 마스터·테넌트 DB**에서 직접 기동·마이그레이션하고 Basic 읽기 결과를 재현했다([실행 출처](lab/evidence/document_office_single_account_chain_fresh_b033_provenance_20261127.json), [읽기 결과](lab/evidence/document_office_scope_fresh_b033_seed_20261127.json)). 새 HEAD의 외부 OIDC도 합성 발급자의 서명된 Bearer 토큰으로 실행해 B문서 조회·수정·삭제와 Basic-only 요청 `401`을 확인했다([OIDC 결과](lab/evidence/document_office_scope_b033_oidc_write_20261127.json), [실행 출처](lab/evidence/document_office_scope_b033_oidc_provenance_20261127.json)). 내장 OAuth2는 최초 커밋에서만 실행했다. 첫 `b033c1363…` 실행은 직전 HEAD의 QueryDSL 생성 소스를 재사용했지만 이후 **새 HEAD 스키마로 재생성**하고 플러그인 임시 변경을 원복한 뒤 제품 소스가 깨끗한 상태에서 서버를 다시 실행해 읽기·쓰기 연쇄를 재확인했다([최종 빌드 출처](lab/evidence/document_office_single_account_chain_fresh_b033_regen_provenance_20261127.json)). 문서·API 권한 파일은 두 원격 HEAD에서 동일하다.
- **설정:** 로컬 PostgreSQL과 루프백 HTTPS, 기본 보안 규칙, 기본 문서 파일 저장소 및 기본 PNG 허용 정책을 사용했다. 포트·실험 DB 이름만 로컬 충돌을 피하려고 지정했다. 문서 허용 목록을 끄거나 파일 유형을 추가하지 않았다. 공식 1.16.1의 Basic 인증 기본 모드와, Basic을 끄고 내장 OAuth2를 켠 모드를 각각 실행했다. OAuth2는 제품의 정상 Authorization Code + PKCE 흐름을 썼다. 별도로 실행한 `develop`에서는 OIDC federation을 켜고 합성 외부 발급자의 RS256 토큰을 JWKS로 검증했다. 이 모드의 정확한 설정·제한은 아래에 별도로 적었다.
- **데이터:** 관리자 API로 A지점 `.2.`, B지점 `.3.`, 각 지점의 가짜 고객 한 명과 1×1 PNG 문서 한 개씩을 준비했다. PNG의 텍스트 청크에는 `SYNTHETIC DOCUMENT FOR BRANCH-B; NO REAL CUSTOMER DATA`라고 적었다. 관리자는 **준비 단계에만** 사용했다. 공격 단계는 A지점의 제한 계정이 자신의 인증 정보로 GET 요청을 보낸 것이다.
- **역할:** `zero` 계정은 API 권한 0개, `nodoc` 계정은 `READ_CLIENT`만, `reader` 계정은 `READ_CLIENT`와 `READ_DOCUMENT`만 가진다. [DB의 지점·역할·고객·문서 대조값](lab/evidence/document_office_scope_db_1_16_1.txt)과 [개발 버전의 대조값](lab/evidence/document_office_scope_db_develop.txt)을 저장했다.

## HTTP 대조 결과

아래의 `B`는 공격자의 A지점과 형제 관계인 B지점의 합성 고객이다. 두 환경에서 고객 ID는 `3`, 문서 ID는 `2`였다.

| 요청 주체와 요청 | 공식 1.16.1 | 실행한 `develop` | 의미 |
| --- | --- | --- | --- |
| `reader` → `GET /clients/3` | `404` | `404` | 고객 상세는 지점 경계를 지킴 |
| `reader` → `GET /clients/3/documents` | `200`, 문서 1건 | `200`, 문서 1건 | `READ_DOCUMENT`가 있어도 지점 경계가 빠짐 |
| `reader` → `GET /clients/3/documents/2/attachment` | `200`, 합성 PNG | `200`, 합성 PNG | 다른 지점 파일 바이트를 수신 |
| `nodoc` → `GET /clients/3/documents` | `403` | `403` | 목록에는 문서 권한 검사 적용 |
| `nodoc` → `GET /clients/3/documents/2/attachment` | **`200`, 합성 PNG** | `403` | 1.16.1의 하위 URL 권한 누락 |
| `zero` → `GET /clients/3` / 문서 목록 | 둘 다 `403` | 미시험 | 읽기 권한 자체가 없는 계정 |
| `zero` → `GET /clients/3/documents/2` / 첨부 | **둘 다 `200`** | 미시험 | 1.16.1은 로그인만으로 세부·첨부 접근 |
| 인증 없음 → B 첨부 | `401` | `401` | 무인증 공개는 아님 |
| `reader` → B 문서 ID를 A 고객 경로에 붙임 | `404` | `404` | 문서·부모 ID의 대응 검사는 작동 |

공식 1.16.1과 개발 버전의 [요청별 상태·바이트 수·SHA-256 결과](lab/evidence/document_office_scope_result_official_1_16_1.json), [개발 버전 결과](lab/evidence/document_office_scope_result.json), [권한 0개 계정 결과](lab/evidence/document_office_scope_zero_permission_official.json), [무인증 대조](lab/evidence/document_office_scope_unauth_official.txt)를 보존했다. `zero` 계정으로 고객 ID 1~3과 문서 ID 1~2의 **6개 조합만** 조회해 A의 `2/1`, B의 `3/2`를 찾은 [범위 제한 탐색 결과](lab/evidence/document_office_scope_bounded_discovery_official.json)도 있다. 이 실험은 로컬 데이터의 작은 순차 ID 범위에서 사전 지식 없이 두 문서를 찾을 수 있음을 보이지만, 실제 배포의 ID 분포나 대량 탐색 가능성을 증명하지는 않는다.

권장 실행형 JAR를 직접 띄워 Basic 인증으로 같은 읽기 요청을 재실행한 [결과](lab/evidence/document_office_scope_result_official_jar_1_16_1.json)는 `zero`의 B 고객·문서 목록 `403`, 문서 세부·첨부 `200`, `reader`의 B 고객 `404`와 B 문서 목록·세부·첨부 `200`을 재확인한다. 이 결과를 공식 WAR 라이브러리 실행과 대조했다.

같은 공식 바이너리의 내장 OAuth2 모드에서는 로그인과 PKCE 코드 교환으로 발급받은 토큰을 사용했다. [권한 0개 계정의 결과](lab/evidence/document_office_scope_oauth2_official_1_16_1.json)는 토큰의 `scope=[]`, 고객 조회 `403`, 문서 목록 `200`(B 문서 ID `2`), 세부 `200`, 첨부 `200`(143바이트, SHA-256 `380f4221eb18e55a81484f3bfd1ffbe1bc4c9fad48f60c8b160a4469f15350f2`)을 기록한다. [문서 읽기 권한 계정의 결과](lab/evidence/document_office_scope_oauth2_reader_official_1_16_1.json)는 B 고객 `404`와 B 문서 목록·세부·첨부 `200`의 지점 범위 불일치를 재확인한다. 토큰 없이 첨부를 요청하면 `401`이었다. 증거 파일에는 원본 토큰을 저장하지 않았다.

같은 OAuth2 흐름을 권장 실행형 JAR에서도 다시 수행했다. [권한 0개 계정](lab/evidence/document_office_scope_oauth2_official_jar_zero.json)과 [문서 읽기 권한 계정](lab/evidence/document_office_scope_oauth2_official_jar_reader.json)의 상태 코드·파일 해시는 앞선 WAR 라이브러리 실행과 같았다.

실행한 `develop`의 내장 OAuth2 모드에서는 [`READ_CLIENT`만 있는 계정](lab/evidence/document_office_scope_oauth2_nodoc_develop.json)이 B 고객 `404`와 B 문서 목록·세부·첨부 `403`을 받았다. 반면 [`READ_CLIENT`와 `READ_DOCUMENT`만 있는 계정](lab/evidence/document_office_scope_oauth2_develop.json)은 B 고객 `404`, B 문서 목록·세부·첨부 `200`을 받았고, 다운로드 해시는 공식 1.16.1의 합성 B 문서와 같았다. 개발 버전의 기존 수정은 문서 권한 누락을 막지만 지점 범위는 막지 않는다는 실행 대조다.

[외부 서명 OIDC 토큰 대조](lab/evidence/document_office_scope_external_oidc_develop.json)도 동일한 결과였다. 루프백에서 잠시 실행한 합성 발급자의 RS256 공개키를 Fineract 테넌트의 정상 OIDC 구성에 등록했다. 두 토큰은 각각 기존 `nodoc`와 `reader` 계정의 `preferred_username`을 담았고, Fineract가 JWKS로 서명을 검증해 기존 역할을 적용했다. `nodoc`는 B 문서 세 경로 `403`, `reader`는 B 고객 `404`와 B 문서 세 경로 `200`이었다. 첨부의 SHA-256은 위와 같았다. 동일 서버에 Basic 자격증명만 보낸 API 요청은 `401`이므로 OIDC 보호 체인이 API를 처리한 것도 대조했다. 합성 발급자의 개인키와 원본 토큰은 증거에 저장하지 않았다.

2026-11-27 00시 당시 HEAD `4d9557a…`로 실행한 [외부 OIDC 읽기 재검증](lab/evidence/document_office_scope_exact_head_oidc_20261127.json)에서도 `nodoc`의 B문서 목록·세부·첨부는 모두 `403`, `reader`의 B고객 상세는 `404`인데 B문서 목록·세부·첨부는 `200`이었다. 첨부 바이트 해시는 기존 합성 PNG와 같았다. 이후 원격 HEAD `b033c1363…`의 [빈 DB Basic 재현](lab/evidence/document_office_scope_fresh_b033_seed_20261127.json)에서도 `reader`의 B고객 상세 `404`, B문서 목록·세부·첨부 `200`, `nodoc`의 문서 세 경로 `403`이었다. 이 버전 적용 여부는 코드 동일성 추정이 아니라 각각 실행 관찰이다.

## 원인과 버전 차이

1.16.1의 [`SecurityConfig`](https://github.com/apache/fineract/blob/1.16.1/fineract-provider/src/main/java/org/apache/fineract/infrastructure/core/config/SecurityConfig.java#L208-L220)는 `GET /api/*/clients/*/documents` 같은 **목록 경로**에 `READ_DOCUMENT`를 요구한다. `GET /documents/{id}`와 `/attachment`는 그 정확한 경로에 맞지 않아 같은 클래스의 [마지막 `/api/**` 규칙](https://github.com/apache/fineract/blob/1.16.1/fineract-provider/src/main/java/org/apache/fineract/infrastructure/core/config/SecurityConfig.java#L404-L408)으로 내려가며, 이 규칙은 인증 여부를 검사한다. [`DocumentApiResource`](https://github.com/apache/fineract/blob/1.16.1/fineract-document/src/main/java/org/apache/fineract/infrastructure/documentmanagement/api/DocumentApiResource.java#L101-L145)의 세부·첨부 핸들러에도 추가 권한 검사가 없다. 이 코드 경로에 대한 추론은 권한 0개 계정의 `403/200` 대조로 확인됐다.

1.16.1의 [내장 OAuth2 보호 체인](https://github.com/apache/fineract/blob/1.16.1/fineract-provider/src/main/java/org/apache/fineract/infrastructure/security/config/AuthorizationServerConfig.java#L165-L179)은 API 요청에 공통으로 로그인 여부만 검사한다. 문서 API의 목록·세부·첨부 메서드에는 자체 `READ_DOCUMENT` 검사가 없어, 권한 0개 토큰이 세 경로에 모두 도달한다. 반면 고객 상세 메서드에는 별도의 권한 검사가 있어 동일 토큰이 `403`을 받는다. 이는 위의 토큰·HTTP 대조와 맞는다.

현재 [`develop` 권한 규칙](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-provider/src/main/java/org/apache/fineract/infrastructure/core/config/ApiAuthorizationRules.java#L111-L115)은 문서 GET에 `/documents/**`를 사용하고, [OAuth2 보호 체인에도 그 규칙을 연결](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-provider/src/main/java/org/apache/fineract/infrastructure/security/config/AuthorizationServerConfig.java#L172-L189)한다. 실제 실행에서도 문서 권한이 없는 계정의 첨부는 Basic·내장 OAuth2 모두 `403`이었다. 하지만 문서 권한이 있는 계정의 **부모 고객 지점 검사**는 여전히 빠져 있다. 문서 ID와 부모 ID가 서로 맞는지만 확인하므로, B 고객에게 실제 붙은 문서에는 접근이 가능하다.

이 권한 경로의 변경은 [공개 PR #6935](https://github.com/apache/fineract/pull/6935)의 설명에 문서 경로와 세 인증 체인의 공통 권한 규칙으로 명시되어 있다. PR의 검증은 요청 경로별 권한 보유 여부를 검사한다. 부모 고객의 지점 범위까지 검증했다고 설명하지 않는다. 따라서 1.16.1의 권한 누락을 신규 발견으로 포장하면 안 되지만, 현재 남은 객체 범위 문제는 별도로 판단할 수 있다.

## 적용 조건과 영향의 경계

첫 번째 결함은 해당 테넌트에 로그인 가능한 계정, 대상 고객·문서 ID, 그리고 저장된 문서가 있으면 성립했다. 권한 0개 역할을 사용했으므로 관리자, `READ_CLIENT`, `READ_DOCUMENT`, 업로드 권한은 공격 단계의 전제조건이 아니다. 두 번째 결함은 `READ_DOCUMENT`가 있는 낮은 권한의 A지점 계정과 다른 지점의 문서가 있으면 성립했다. 기본 설치에서 지원하는 고객 문서와 PNG 파일을 사용했으며, 위험한 선택 설정을 켜지 않았다.

**실제 피해의 종류는 파일 기밀성이다.** 금융기관이 고객 신분증·계약서 등 민감한 문서를 Fineract에 저장하는 경우 이 경로는 그 파일의 무단 열람으로 이어질 수 있다. 우리 실험은 합성 PNG를 완전히 다운로드했다. 이는 단순히 문서 ID나 제목이 보인다는 추정보다 강한 증거다. 다만 어떤 실제 기관이 이 버전을 쓰는지, 그 기관의 문서 내용, 프록시의 추가 객체별 권한 정책, 탐지·속도 제한은 확인하지 않았다.

**권장 외부 IdP 구성의 정확한 한계:** [프로젝트 보안 가이드](https://github.com/apache/fineract/blob/develop/SECURITY.md#10-downstream-responsibilities)는 Basic 대신 별도의 신뢰할 IdP를 권한다. 이 실험은 합성 외부 발급자와 OIDC federation의 JWT 검증·사용자 연결·문서 접근을 실제 실행했지만, Keycloak의 로그인 단계 자체는 검증하지 않았다. 또한 `FINERACT_SECURITY_BASICAUTH_ENABLED=false`로 OIDC만 켜면 `PasswordEncoder` 빈 누락으로 서버가 시작되지 않았다. 이 실패는 **새 HEAD `b033c1363…` 자체에서도 직접 확인**했다([정확한 플래그·오류·로그 해시](lab/evidence/document_office_scope_b033_oidc_only_startup_20261127.json)). 성공한 새 HEAD의 OIDC 실험은 Basic 플래그의 기본값 `true`를 유지했다. 다만 [OIDC 보호 체인은 `/api/**`에서 Basic 체인보다 먼저 적용](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-provider/src/main/java/org/apache/fineract/infrastructure/security/config/OidcFederationSecurityConfig.java#L88-L145)되었고 Basic 자격증명만 보낸 API 요청은 `401`이었다([새 HEAD의 실행 출처](lab/evidence/document_office_scope_b033_oidc_provenance_20261127.json)). 따라서 **API가 외부 토큰으로 보호된 구성에서도 지점 범위 누락이 재현됐지만, 보안 가이드의 모든 설정을 정확히 만족하는 무수정 서버라고 주장하지 않는다.**

**정책 해석의 남은 쟁점:** [공식 지점 계층 문서](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-doc/src/docs/en/chapters/architecture/office-hierarchy-access.adoc)는 무관한 지점의 *자원*에 접근할 수 없다는 일반 원칙을 명시한다. 고객 상세 조회가 이 원칙에 따라 `404`를 반환하는데 같은 고객의 첨부 파일은 내려오는 불일치도 확인했다. 문서 API만 전역 `READ_DOCUMENT` 권한으로 지점 경계를 넘도록 의도했다는 공개 예외는 찾지 못했지만, 위 아키텍처 문서가 문서 API를 직접 열거하지는 않는다. 따라서 **실제 파일 노출은 확정**, 이 동작을 제품 취약점으로 분류하고 별도 CVE를 부여할지는 유지보수자의 정책 확인이 필요하다. 1.16.1의 권한 0개 다운로드는 이 해석과 무관하게 재현됐으나 [이미 공개 수정 PR #6935](https://github.com/apache/fineract/pull/6935)와 겹친다.

새 HEAD `b033c1363…`에서는 **빈 PostgreSQL DB부터** 마이그레이션하고 합성 데이터로 읽기 결과를 반복했다. 같은 A지점 제한 계정이 작은 합성 고객 ID 범위에서 B문서 목록을 조회해 대상 ID를 얻고 정확한 B고객 경로로 문서를 수정하는 [연쇄 경로](lab/evidence/document_office_single_account_chain_fresh_b033_20261127.json)도 재현했다. 별도 최소 권한 계정은 같은 방법으로 대상을 찾아 삭제했다. 두 계정은 각각 `READ_CLIENT`+`READ_DOCUMENT`+`UPDATE_DOCUMENT` 또는 `READ_CLIENT`+`READ_DOCUMENT`+`DELETE_DOCUMENT`를 부여받았다. 기본 설치 비관리자 역할에는 문서 권한이 없었고, 실제 운영 역할의 부여 빈도나 더 큰 고객 ID 공간의 탐색 가능성은 확인하지 않았다([역할·문서 DB 대조](lab/evidence/document_office_single_account_chain_fresh_b033_db_20261127.txt)). 공식 안정 릴리스 JAR의 쓰기 경로도 새 DB에서 재시험했다. 다만 릴리스에는 이후 공개 수정된 **권한 0개 계정의 하위 문서 경로 접근**까지 있어, 수정 후 최신 코드의 지점 범위 문제와 같은 원인으로 묶지 않는다([릴리스 권한 0개 쓰기 결과](lab/evidence/document_office_official_1161_zero_role_nested_document_20261127.json)). 새 HEAD의 외부 OIDC 쓰기도 별도 합성 문서로 재시험했다([결과](lab/evidence/document_office_scope_b033_oidc_write_20261127.json)).

## 적대적 검토: 어디까지 주장할 수 있는가

| 반론 또는 과장 가능성 | 대조한 증거 | 판정 |
| --- | --- | --- |
| "관리자 자격증명으로 파일을 읽은 것 아닌가" | 관리자 API는 합성 지점·고객·문서·제한 계정 생성에만 사용했다. 공격 단계는 `reader` 또는 `zero`의 자체 인증 정보로 GET을 보냈고, 역할·지점은 DB 대조값으로 확인했다. | 관리자 권한은 공격 전제조건이 아님 |
| "B 고객이 원래 없어서 고객 조회만 `404`인 것 아닌가" | 관리자 API가 B 고객과 그 문서를 생성했고 DB에 `CLIENT|3|...|3`, `DOCUMENT|2|clients|3`가 존재한다. A 계정은 자기 고객 조회 `200`, B 고객 조회 `404`, B 문서 다운로드 `200`이었다. | 지점에 따른 고객 조회 차이와 문서 우회가 함께 관찰됨 |
| "문서 ID만 주면 아무 파일이나 내려주는 것 아닌가" | B 문서 ID를 A 고객 경로에 붙이면 `404`; 올바른 B 고객·문서 조합에서는 143바이트 전체와 원본 SHA-256이 일치한다. | 부모 ID의 대응 검사는 작동하지만 지점 범위 검사는 빠짐 |
| "실험용 WAR 실행 방식 때문 아닌가" | SHA-512 검증된 Apache 공식 1.16.1 아카이브의 실행형 JAR를 무수정 `java -jar`로 기동해 Basic·내장 OAuth2 결과를 재현했다. | 1.16.1 배포본에서 재현됨 |
| "최신 코드에서도 권한 0개면 읽는가" | 실행한 `develop`에서 문서 권한 없는 `nodoc`의 세 문서 GET은 `403`; [공개 PR #6935](https://github.com/apache/fineract/pull/6935)가 이 경로의 권한 규칙을 다룬다. | 1.16.1 권한 누락은 신규 미공개 결함으로 신고하지 않음 |
| "권장 외부 IdP 설정을 모두 만족했는가" | 최신 커밋에서 외부 서명 OIDC 토큰 검증 및 제한 역할 적용은 재현했다. 하지만 Basic 플래그까지 끈 OIDC 단독 기동은 `PasswordEncoder` 빈 오류로 실패했다. | 외부 토큰 보호 API에서 성립; 보안 가이드의 정확한 전체 설정은 미입증 |
| "전 금융권 개인정보 유출이나 Critical이 입증됐는가" | 로컬 한 테넌트의 합성 PNG 1개를 완전히 읽었다. 실제 금융기관 배포·데이터·추출 규모·운영 통제는 미시험이다. | 파일 기밀성 침해는 확인, 실제 사고·Critical·금융권 확산은 미확인 |
| "새로운 독립 취약점인가" | 1.16.1 권한 누락은 공개 수정과 중복. 최신 지점 범위는 수정 후에도 남고 공식 지점 정책과 충돌하지만, 비공개 선행 신고와 유지보수자의 문서 권한 해석은 알 수 없다. | 정책 확인 전에는 독립 보안 취약점으로 확정할 수 없음 |

**심각도 가늠값:** 최신 지점 범위 건을 네트워크 API, 낮은 권한의 로그인 사용자, 사용자 개입 없음, 같은 Fineract 보안 범위 안의 **읽기 노출만**으로 평가하면 [FIRST CVSS v3.1 계산식과 등급](https://www.first.org/cvss/v3.1/specification-document)에 따라 `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N`은 **4.3(Medium)**이다. 문서 구성요소의 기밀성이 완전히 침해된다고 *추가로 가정*해 `C:H`를 주어도 **6.5(Medium)**이다. 실제 배포의 문서 종류·양, ID 발견 가능성, 운영 통제와 피해 규모를 확인하지 않았으므로 이 점수를 공식 등급으로 주장하지 않는다. 현 증거로 `Critical`은 뒷받침되지 않는다.

## 수정 방향과 수용 기준

- 안정 릴리스의 모든 문서 GET 하위 경로에 `READ_DOCUMENT` 검사를 적용한다. `develop`의 `/documents/**` 규칙이 비교 기준이다. 권한 0개 역할의 목록·세부·첨부가 모두 거부되고, 권한 있는 자기 문서는 계속 읽혀야 한다.
- 문서 조회의 **부모 엔터티 접근권**을 공통 정책에서 검사한다. 고객 문서라면 고객 상세 조회와 같은 지점 계층 기준을 적용하고, 대출·저축·그룹·직원·고객 식별자 문서는 각 부모 자원의 읽기 범위를 확인해야 한다. A지점 계정의 A 문서 목록·세부·첨부는 `200`, B 문서의 세 경로는 모두 거부되어야 한다. 잘못된 부모·문서 조합도 `404`를 유지해야 한다.
- 회귀 검증은 최소한 **권한 0개 / `READ_CLIENT`만 / `READ_CLIENT+READ_DOCUMENT`**, 자기 지점 / 형제 지점, 목록 / 세부 / 첨부를 교차해야 한다. 서버 설정과 프록시만으로 이 객체별 검사 부재를 해결했다고 간주하지 않는다.

현재는 제품 패치를 적용하거나 수정 후 전체 회귀 테스트를 돌리지 않았다. 이 파일은 재현 결과와 수정 수용 기준을 정리한 공개 연구 기록이다.

## 재현 자료

- [루프백 전용 재현 스크립트](lab/document_office_scope_reproduce.py): 새 로컬 DB에서는 정상 관리자 API로 지점·역할·가짜 고객·PNG를 생성한다. 공격 요청에는 제한 계정만 사용한다. 기존 합성 DB를 다시 검사할 때는 `FINERACT_LAB_REPLAY_ONLY=1`로 쓰기 단계를 생략한다. 공식 바이너리에서는 앞서 준비한 합성 DB를 읽기 모드로 대조한 뒤 권한 0개 계정을 정상 관리자 API로 추가했고, 최종 결과는 읽기 모드로 재확인했다.
- [내장 OAuth2 읽기 재현 스크립트](lab/document_oauth2_replay.py): 정상 로그인과 PKCE를 통해 제한 계정의 토큰을 발급받아 같은 네 경로를 조회한다. 루프백 HTTPS로만 요청하고 결과 JSON에는 토큰을 쓰지 않는다.
- [외부 OIDC 읽기 재현 스크립트](lab/document_external_oidc_replay.py): 합성 외부 발급자의 단기 RSA 키와 JWKS를 루프백에서 제공하고, 기존 제한 계정에 연결된 두 토큰으로 문서 경로를 읽기 대조한다. 실험 테넌트에 발급자의 issuer/JWKS URI를 운영자 준비 단계에서 등록해야 한다.
- [공식 바이너리 체크섬](lab/evidence/document_office_scope_official_artifact.json), [공식 JAR Basic 결과](lab/evidence/document_office_scope_result_official_jar_1_16_1.json), [공식 JAR OAuth2 권한 0개 결과](lab/evidence/document_office_scope_oauth2_official_jar_zero.json), [공식 JAR OAuth2 문서 권한 결과](lab/evidence/document_office_scope_oauth2_official_jar_reader.json), [개발 버전 Basic 결과](lab/evidence/document_office_scope_result.json), [개발 버전 OAuth2 결과](lab/evidence/document_office_scope_oauth2_develop.json), [외부 OIDC 결과](lab/evidence/document_office_scope_external_oidc_develop.json), [DB 권한 대조](lab/evidence/document_office_scope_db_1_16_1.txt), [최신 커밋 직접 실행 출처](lab/evidence/document_office_scope_exact_head_provenance_20261127.json), [최신 커밋 OIDC 읽기 결과](lab/evidence/document_office_scope_exact_head_oidc_20261127.json), [최신 코드 동일성 대조](lab/evidence/document_office_scope_source_audit.json).
- [새 HEAD의 빈 DB 실행 출처](lab/evidence/document_office_single_account_chain_fresh_b033_provenance_20261127.json), [읽기 재현](lab/evidence/document_office_scope_fresh_b033_seed_20261127.json), [ID 탐색→수정·삭제 연쇄](lab/evidence/document_office_single_account_chain_fresh_b033_20261127.json), [역할·문서 소속](lab/evidence/document_office_single_account_chain_fresh_b033_db_20261127.txt), [문서 권한 정책에 관한 공개 질문](DOCUMENT_OFFICE_POLICY_QUESTION_EN.md).
- Apache Fineract의 [공식 비공개 보안 신고 안내](https://fineract.apache.org/index.html)와 [보안 정책](https://github.com/apache/fineract/blob/develop/SECURITY.md). 이 연구는 벤더 보안팀에 먼저 제출되지 않은 채 공개됐다.
