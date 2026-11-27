# Apache Fineract 문서 수정·삭제: 부모 고객 ID와 지점 범위를 무시하는 경로

작성일: 2026-11-26, 최신 커밋 직접 재검증: 2026-11-27 (KST)<br>
상태: **2026-11-27 확인한 원격 `develop` HEAD `b033c1363…`의 빈 DB에서 Basic·외부 OIDC 경로 재현. 공식 안정 릴리스 1.16.1의 JAR도 새 DB에서 실행해 문서 읽기·수정·삭제를 재현했으나, 이 릴리스에는 이후 공개 수정된 별도의 하위 URL 권한 누락이 있다. 외부 서비스 미시험, 공개 연구 기록.**

## 요약

문서 API의 경로는 `/{entityType}/{entityId}/documents/{documentId}`이지만, 실행한 개발 버전의 수정·삭제 서비스는 `documentId`만으로 대상 문서를 찾았다. A지점의 비관리자 계정에 `READ_CLIENT`와 `UPDATE_DOCUMENT`만 부여하자 B지점 고객은 `404`, B 문서 읽기는 `403`이었다. 그래도 **A고객 ID를 넣은 경로** `PUT /clients/2/documents/3`으로 실제로 B고객 3에게 속한 문서 3의 이름을 바꿨다. 별도 비관리자 계정에 `READ_CLIENT`와 `DELETE_DOCUMENT`만 부여하자 같은 방식의 `DELETE /clients/2/documents/4`로 B고객 문서 4를 삭제했다. 두 요청 모두 `200`을 받았고, B고객 경로에서 수정 전후 이름 변경과 삭제 전 `200`·삭제 후 `404`를 확인했다. 동일한 결과를 외부 발급자의 서명된 OIDC Bearer 토큰으로도 얻었다.

이것은 **한 테넌트 안에서 다른 지점의 합성 고객 문서를 수정·삭제할 수 있다**는 실행 결과다. 이를 제품 정책상 *무단* 접근으로 분류하려면 문서 쓰기 권한의 지점 범위에 대한 유지보수자의 확인이 필요하다. 계정 탈취, 관리자 권한, 실제 금융기관 데이터, 타 테넌트 침범, 금융거래 변조 또는 서버 장애는 입증하지 않았다. 최초 쓰기 전용 계정은 운영자가 준비한 문서 ID를 썼다. 후속 빈 DB 실험에서는 `READ_DOCUMENT`가 있는 A지점 계정이 작은 합성 고객 ID 범위를 직접 조회해 B문서 ID를 얻은 다음 수정·삭제했다. 문서 읽기 권한조차 없는 계정의 독자적인 ID 발견은 여전히 미입증이다.

**경로의 A고객 ID는 공격 성공에 필요하지 않았다.** 최초 실험에서 A ID를 넣은 이유는 URL의 부모 ID와 실제 문서 소속이 불일치해도 처리되는지 확인하기 위해서였다. 후속 최신 HEAD 실험에서는 **올바른 B고객 ID 경로로도** 제한 계정의 수정·삭제가 성공했다. 따라서 “A경로가 지점 검사를 속여서 우회했다”는 인과 설명은 하지 않는다. 부모 ID 불일치는 별도의 API 일관성 결함이며, 지점 범위 문제는 정확한 B 경로에서도 발생한다.

## 왜 보안 경계를 의심했는가

[공식 지점 계층 문서](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-doc/src/docs/en/chapters/architecture/office-hierarchy-access.adoc)는 사용자가 자기 지점과 하위 지점의 자원에 접근하고, 무관한 지점 자원에는 접근하지 못한다고 설명한다. [고객 상세 조회 구현](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-provider/src/main/java/org/apache/fineract/portfolio/client/service/ClientReadPlatformServiceImpl.java#L219-L225)도 로그인 사용자의 `officeHierarchy`를 쓴다. [문서 읽기 구현](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-document/src/main/java/org/apache/fineract/infrastructure/documentmanagement/service/DocumentReadPlatformServiceImpl.java#L40-L65)은 적어도 URL의 부모 종류·ID와 문서 ID의 대응을 확인한다.

반면 [문서 수정·삭제 구현](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-document/src/main/java/org/apache/fineract/infrastructure/documentmanagement/service/DocumentWritePlatformServiceImpl.java#L108-L174)은 두 작업 모두 `findById(request.getId())`로 문서를 조회한다. 수정의 메타데이터 변경과 삭제에는 URL에서 받은 부모 `entityType`·`entityId`가 문서와 맞는지, 부모 고객이 사용자의 지점 범위에 있는지 검사하는 코드가 없다. 삭제는 조회한 문서의 저장 위치에 `storeService.delete`를 호출한 뒤 저장소의 문서 행을 지운다. [현재 `develop`의 API 권한 규칙](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-provider/src/main/java/org/apache/fineract/infrastructure/core/config/ApiAuthorizationRules.java#L111-L116)은 수정·삭제 HTTP 메서드에 각각 `UPDATE_DOCUMENT`·`DELETE_DOCUMENT` 권한을 요구하지만 **객체별 부모·지점 접근은 검사하지 않는다.**

## 검증한 코드와 환경

- 최초 실행 커밋은 `0747fa5fc4a6beb7df501ef02194161d6f14c187` (`1.17.0-SNAPSHOT`)였다. 2026-11-27 00시 당시 원격 `develop` HEAD `4d9557a572b178bd32e1839f81c48204b8fcad49`를 직접 실행해 Basic·OIDC 결과를 재현했다([실행 출처](lab/evidence/document_office_scope_exact_head_provenance_20261127.json)). 그날 원격 HEAD가 `b033c13637123574a2242e39ce5e6aef29f58fdb`로 이동한 뒤 이 커밋도 직접 체크아웃해 Basic 서버를 실행했다. **빈 마스터·테넌트 DB부터** 마이그레이션·합성 데이터 생성·ID 탐색·수정·삭제를 재현했다([새 HEAD와 빈 DB 실행 출처](lab/evidence/document_office_single_account_chain_fresh_b033_provenance_20261127.json)). 각 실행 시점에 `git status`는 깨끗했고 원격 HEAD와 실행 커밋을 대조했다. 이전 [파일별 SHA-256 및 병합 계보](lab/evidence/document_office_scope_source_audit.json)는 최초 코드 동일성 검사 자료다.
- 로컬 PostgreSQL, 루프백 HTTPS, 기본 문서 파일 저장소와 기본 PNG 허용 정책을 썼다. 이미 마이그레이션된 합성 DB를 재사용해 서버 기동 시 Liquibase만 껐고(`FINERACT_LIQUIBASE_ENABLED=false`), 포트·마스터 DB 주소·루프백 바인딩을 실험용으로 지정했다. Docker VM의 QueryDSL 생성 오류를 피하려고 임시 로컬 PostgreSQL 생성 DB를 사용했다. 빌드 후 플러그인 임시 수정은 원복했고, 임시 DB는 삭제했다. 제품 문서 API·권한 규칙·쓰기 서비스 코드는 수정하지 않았다.
- 운영자 준비: 같은 합성 테넌트에 형제 지점 A(`.2.`)·B(`.3.`), 가짜 고객 A(ID 2)·B(ID 3), 일회용 B 문서 4개를 관리자 API로 생성했다. 기존 읽기 재현용 B 문서 ID 2는 건드리지 않았다. 공격 단계에서 관리자는 쓰지 않았다.
- 공격 계정 두 개는 A지점 소속이다. `updater`는 `READ_CLIENT`, `UPDATE_DOCUMENT`만; `deleter`는 `READ_CLIENT`, `DELETE_DOCUMENT`만 가진다. `READ_DOCUMENT`, `ALL_FUNCTIONS`, 관리자 역할은 없다. [DB의 실제 역할·지점·문서 대조](lab/evidence/document_office_write_scope_db_final.txt)를 저장했다.
- Basic 기본 모드에서 한 번, 외부 서명 OIDC 토큰 모드에서 별도 일회용 B 문서 두 개로 한 번 재현했다. OIDC 실험에서는 루프백 합성 발급자의 RS256 공개키를 Fineract 테넌트에 정상 등록했고, 서명된 토큰의 `preferred_username`을 위 기존 제한 계정에 연결했다. 개인키·원본 JWT는 저장하지 않았다. 같은 서버에 Basic 자격증명만 보낸 API 요청은 `401`이었다.

### 공식 1.16.1 및 새 HEAD의 추가 대조

공식 1.16.1 바이너리 아카이브를 [Apache SHA-512](https://downloads.apache.org/fineract/1.16.1/apache-fineract-bin-1.16.1.tar.gz.sha512)와 대조하고, 그 안의 JAR(SHA-256 `bd70aa4033f1121549e921c982db10adf6fab151acd3dc3043b505dcf779308b`)을 **빈 마스터·테넌트 DB**에 `java -jar`로 실행했다([배포본 출처](lab/evidence/document_office_official_1161_write_artifact_provenance_20261127.json), [기동·마이그레이션 출처](lab/evidence/document_office_official_1161_write_provenance_20261127.json)). A지점의 `READ_CLIENT`+`READ_DOCUMENT`+`UPDATE_DOCUMENT` 계정은 B고객 상세 `404`를 확인한 뒤 B문서 ID를 API에서 찾아 올바른 B고객 경로로 이름을 바꿨다. `READ_CLIENT`+`READ_DOCUMENT`+`DELETE_DOCUMENT` 계정도 같은 방법으로 B문서를 삭제했고, 삭제 전 파일과 삭제 후 DB 행·파일을 대조했다([연쇄 재현](lab/evidence/document_office_single_account_chain_official_1161_20261127.json), [역할·지점·문서 DB 대조](lab/evidence/document_office_official_1161_write_db_20261127.txt), [자기 지점 양성 대조](lab/evidence/document_office_same_office_control_official_1161_20261127.json)).

**릴리스의 성공을 최신 코드의 지점 문제에 대한 독립 검증으로 섞어 해석하지 않는다.** 1.16.1에서는 문서 하위 경로의 메서드 권한 자체가 빠져, A지점의 **권한 0개** 로그인 계정도 B문서 첨부를 읽고 이름을 바꾸고 물리 파일과 DB 행을 삭제했다. 같은 계정의 고객·문서 목록은 `403`, 미로그인과 잘못된 비밀번호는 `401`이었다([권한 0개 재현](lab/evidence/document_office_official_1161_zero_role_nested_document_20261127.json)). 이 권한 매처 문제는 릴리스 이후 [공개 PR #6935](https://github.com/apache/fineract/pull/6935)가 다룬 영역이다. 새 HEAD `b033c1363…`에서 권한 0개 계정의 문서 세부·첨부·PUT·DELETE는 전부 `403`이고 문서는 유지됐다([수정 후 음성 대조](lab/evidence/document_office_scope_b033_basic_zero_role_control_20261127.json)). 따라서 **1.16.1의 광범위 권한 누락은 이미 공개 수정된 문제**, **수정 후 남은 교차 지점 쓰기는 문서 권한을 가진 계정의 객체 범위 문제**로 구분한다.

새 HEAD에서도 합성 외부 발급자의 서명된 OIDC Bearer 토큰으로 A지점 제한 계정이 B고객 `404`, 반대 쓰기 메서드 `403`, B문서 수정·삭제 `200`을 재현했다. 같은 API에 Basic만 보내면 `401`이었다([OIDC 응답](lab/evidence/document_office_scope_b033_oidc_write_20261127.json), [실행 출처](lab/evidence/document_office_scope_b033_oidc_provenance_20261127.json)). 단, Basic 플래그를 `false`로 둔 **OIDC 단독 구성**은 같은 새 HEAD에서도 `PasswordEncoder` 빈 누락으로 서버가 시작하지 않았다([기동 실패 출처](lab/evidence/document_office_scope_b033_oidc_only_startup_20261127.json)). 성공한 OIDC 실험은 Basic 플래그를 `true`로 두되 API에서는 OIDC 체인이 적용되는 구성이다.

### 00시 당시 HEAD `4d9557a…`의 빌드·데이터 조건

이 커밋은 별도 로컬 PostgreSQL 마스터·테넌트 DB 복제본에서 실행했다. 해당 스키마의 QueryDSL 소스를 생성할 때 Docker VM의 입출력 오류를 우회하기 위해 **생성 플러그인만 임시로 로컬 PostgreSQL을 사용하도록 바꿨다가 원복**했다. 이후 제품 소스가 깨끗한 상태에서 `:fineract-provider:bootRun`으로 컴파일·기동했고 생성 작업의 재실행만 제외했다. 기본 인증 서버는 `127.0.0.1:8457`, OIDC 서버는 `127.0.0.1:8458`에서 실행했다. 두 서버의 `Started ServerApplication` 로그와 실행 중 소스 상태를 [증거](lab/evidence/document_office_scope_exact_head_provenance_20261127.json)에 기록했다. Liquibase를 기본값으로 실행했다. 두 인증 경로 모두 B지점에 **새 문서**를 만들고 공격 요청을 반복했으며, 원래 재현의 변경된 문서를 다시 사용하지 않았다.

| 당시 HEAD `4d9557a…`의 요청·대조 | Basic: 새 B문서 7·8 | 외부 OIDC: 새 B문서 9·10 |
| --- | --- | --- |
| A지점 `updater`·`deleter`의 B고객 조회 | 각각 `404` | 각각 `404` |
| 각 계정의 B문서 읽기 | 각각 `403` | 각각 `403` |
| 서로 다른 쓰기 권한을 요구하는 요청 | 각각 `403` | 각각 `403` |
| `PUT /clients/2/documents/{B 수정 문서}` | `200`, B문서 7 이름 변경 확인 | `200`, B문서 9 이름 변경 확인 |
| `DELETE /clients/2/documents/{B 삭제 문서}` | `200`, B문서 8의 GET `200` → `404` | `200`, B문서 10의 GET `200` → `404` |
| OIDC 서버에 Basic 자격증명만 제출 | 해당 안 됨 | `401` |

새 역할·사용자와 문서 소속은 [당시 HEAD의 DB 대조](lab/evidence/document_office_write_scope_exact_head_db_20261127.txt)에 있다. `updater`·`deleter`는 A지점이며 허용 권한은 각각 `READ_CLIENT`+`UPDATE_DOCUMENT`, `READ_CLIENT`+`DELETE_DOCUMENT` 두 개뿐이다. 수정 대상은 실제 B고객 3에게 속했고, 삭제 대상은 사후 DB에 존재하지 않는다. [Basic 응답](lab/evidence/document_office_write_scope_exact_head_basic_20261127.json), [OIDC 응답](lab/evidence/document_office_write_scope_exact_head_oidc_20261127.json), [OIDC 준비값](lab/evidence/document_office_write_scope_exact_head_oidc_fixture_20261127.json)을 분리 보존했다. 합성 발급자 설정과 서버는 실험 후 중지·제거했다.

### 새 HEAD `b033c1363…`의 빈 DB·한 계정 연쇄 검증

2026-11-27 원격 `develop` HEAD가 이동한 뒤 [새 커밋을 직접 실행](lab/evidence/document_office_single_account_chain_fresh_b033_provenance_20261127.json)했다. `createdb`로 빈 마스터·테넌트 PostgreSQL DB를 만들었고 Fineract의 기본 마이그레이션이 각각 22·2165개 변경셋을 적용했다. 관리자 API로 **준비 단계에만** A·B지점과 합성 고객·PNG·제한 역할을 생성했다. 새 설치에서는 A고객 ID `1`, B고객 ID `2`다.

공격 단계의 두 계정은 모두 A지점 소속이며 관리자 역할이 없다. 수정 계정의 권한은 `READ_CLIENT`+`READ_DOCUMENT`+`UPDATE_DOCUMENT`, 삭제 계정은 `READ_CLIENT`+`READ_DOCUMENT`+`DELETE_DOCUMENT`다([DB 역할·고객·문서 소속](lab/evidence/document_office_single_account_chain_fresh_b033_db_20261127.txt)). 각 계정의 코드에는 운영자가 만든 대상의 고객 ID·문서 ID·이름을 넘기지 않았다. 계정은 합성 고객 ID **1–16**의 문서 목록을 조회해 B고객 `2`의 목록에서 문서 ID `3`·`4`를 얻었다. 해당 고객 상세는 `404`였지만 문서 메타데이터·첨부는 `200`이었다. 정확한 **B고객 경로** `PUT /clients/2/documents/3`은 `200`이고 문서 이름이 바뀌었다. `DELETE /clients/2/documents/4`도 `200`; 문서 GET은 `200`에서 `404`로 바뀌었고, 운영자 대조에서 삭제 전 존재·해시가 확인된 물리 파일과 DB 행이 모두 사라졌다([전체 요청·전후 파일 대조](lab/evidence/document_office_single_account_chain_fresh_b033_20261127.json)). 동일한 제한 계정이 자기 A지점 문서를 정상 수정·삭제하는 [양성 대조](lab/evidence/document_office_same_office_control_fresh_b033_20261127.json)도 통과했다.

이 탐색은 **ID 1–16의 작은 합성 실험**이다. 실무 배포에서 고객 ID 범위, 요청 제한, 문서 개수, 계정의 업무 권한 부여 빈도는 확인하지 않았다. 기본 설치의 비관리자 `Self Service User` 역할에는 문서 권한이 없었다([기본 역할 대조](lab/evidence/document_office_single_account_chain_fresh_b033_db_20261127.txt)). 이 실험은 관리자나 IdP 자격증명 탈취를 증명하지 않는다. 이 단일 계정의 **ID 탐색→쓰기 연쇄**는 `b033c1363…`의 Basic 모드에서 실행했다. 새 HEAD의 OIDC에서는 같은 ID 탐색을 반복하지 않았지만 별도 B문서의 수정·삭제를 재시험했다([OIDC 결과](lab/evidence/document_office_scope_b033_oidc_write_20261127.json)). 첫 Basic 실행은 직전 HEAD의 QueryDSL 생성 소스를 재사용했다([첫 빌드 출처](lab/evidence/document_office_single_account_chain_b033_provenance_20261127.json)). 이후 **새 HEAD 스키마에서 QueryDSL을 다시 생성**하고 임시 빌드 플러그인 변경을 원복한 뒤, 깨끗한 제품 소스로 서버를 재기동해 [ID 탐색→수정·삭제](lab/evidence/document_office_single_account_chain_fresh_b033_regen_20261127.json), [최종 역할·문서 소속](lab/evidence/document_office_single_account_chain_fresh_b033_regen_db_20261127.txt)과 [자기 지점 양성 대조](lab/evidence/document_office_same_office_control_fresh_b033_regen_20261127.json)를 다시 통과했다([생성·실행 로그 해시](lab/evidence/document_office_single_account_chain_fresh_b033_regen_provenance_20261127.json)).

## 요청별 결과

아래의 `/clients/2`는 공격자의 A고객을 가리키고, 문서 3·4는 실제로 **B고객 3에게 속했다**. OIDC는 새 일회용 B 문서 5·6을 사용했다.

| 요청과 확인 | Basic 개발 서버 | 외부 서명 OIDC 개발 서버 |
| --- | --- | --- |
| `updater`·`deleter` → `GET /clients/3` | 각각 `404` | 각각 `404` |
| 각 쓰기 계정 → `GET /clients/3/documents/{자기 대상 ID}` | 각각 `403` | 각각 `403` |
| `updater` → `DELETE /clients/2/documents/{삭제 대상}` | `403` | `403` |
| `deleter` → `PUT /clients/2/documents/{수정 대상}` | `403` | `403` |
| `updater` → `PUT /clients/2/documents/{실제 B 문서}` | `200`, 문서 3 | `200`, 문서 5 |
| B고객 경로에서 제한된 별도 `reader`가 수정 전후 이름 확인 | `Synthetic B-UPDATE-…` → `Changed by A office…` | `Synthetic OIDC-B-UPDATE-…` → `OIDC A-office changed…` |
| `deleter` → `DELETE /clients/2/documents/{실제 B 문서}` | `200`, 문서 4 | `200`, 문서 6 |
| B고객 경로에서 별도 `reader`가 삭제 전후 확인 | `200` → `404` | `200` → `404` |
| 원래 읽기 재현용 B 문서 2 | 여전히 `200` | 유지됨, 별도 시험에서 미조회 |
| Basic 자격증명만 제출 | 해당 안 됨 | `401` |

[Basic 요청별 JSON](lab/evidence/document_office_write_scope_develop.json), [OIDC 요청별 JSON](lab/evidence/document_office_write_scope_oidc_develop.json), [OIDC 일회용 대상 준비값](lab/evidence/document_office_write_scope_oidc_fixture.json), [사후 DB 확인](lab/evidence/document_office_write_scope_db_final.txt)을 보존했다. 사후 DB에는 B고객 3의 문서 3·5의 변경된 이름이 남고 삭제 대상 4·6은 없다. [사후 로컬 파일 검사](lab/evidence/document_office_write_scope_filesystem_check.json)에서 수정 대상 파일 두 개는 있고 삭제 대상 파일 두 개는 없었다. 파일 시스템의 **삭제 전 스냅샷은 저장하지 않았으므로**, 삭제의 일차 증거는 HTTP 전후 응답과 DB 행 부재다.

## 적대적 검토

| 반론 | 검증 및 결론 |
| --- | --- |
| "슈퍼유저가 한 작업 아닌가" | 관리자는 일회용 데이터를 만들었을 뿐이다. 공격 GET·PUT·DELETE는 A지점 비관리자 계정으로 수행했고 DB에서 해당 역할의 권한 두 개씩만 확인했다. |
| "쓰기 권한 자체가 모든 문서 수정을 허용한다는 뜻 아닌가" | 이 가능성은 유지보수자의 명시적 정책 확인이 필요하다. 다만 [공식 지점 계층 원칙](https://github.com/apache/fineract/blob/4d9557a572b178bd32e1839f81c48204b8fcad49/fineract-doc/src/docs/en/chapters/architecture/office-hierarchy-access.adoc)과 고객 `404`/문서 쓰기 `200`은 충돌한다. [기존 GET 대조](lab/evidence/document_office_scope_result.json)에서는 부모 ID 불일치를 `404`로 거부하는데 PUT·DELETE만 무시한다는 점은 지점 정책과 별개로 재현된 API 객체 식별 불일치다. |
| "A고객 ID가 우회의 원인인가" | 아니다. 서비스 구현은 문서 ID로만 대상을 조회한다. A ID 경로의 성공은 부모 ID 검증 누락을 보여 준다. 후속 빈 DB 실험에서 정확한 B ID 경로도 수정·삭제 `200`이었으므로 A ID가 필요한 우회 수단은 아니다. |
| "권한 검사가 전혀 없는 것 아닌가" | 아니다. `UPDATE_DOCUMENT`만 있는 계정의 DELETE와 `DELETE_DOCUMENT`만 있는 계정의 PUT은 모두 `403`이다. **메서드 권한은 작동하고, 대상 문서의 부모·지점 검사가 빠졌다.** |
| "원래 삭제된 문서였나" | 정상 B고객 경로의 GET `200`을 확인한 뒤 다른 지점 계정의 DELETE `200`, 그 뒤 GET `404`를 확인했다. DB에서도 문서 4·6 행이 없다. |
| "OIDC 실험은 Basic으로 처리됐나" | OIDC 모드의 Basic 자격증명만 제출한 API GET은 `401`; 유효하게 서명된 외부 Bearer 토큰으로만 쓰기 요청이 성공했다. |
| "공개 수정과 중복인가" | [공개 PR #6935](https://github.com/apache/fineract/pull/6935)는 문서 하위 경로의 권한 매처를 고쳤다. 최신 코드·런타임에서 그 권한 검사는 작동한다. 이 보고서는 그 이후에도 남은 부모 객체 식별·지점 범위 검사를 다룬다. [공개 GitHub 이슈·PR의 제한된 검색](lab/evidence/document_office_write_scope_public_search.json)에서 직접 중복은 찾지 못했지만 비공개 선행 신고 여부는 알 수 없다. |

## 적용 조건과 남은 한계

- 같은 테넌트의 로그인 가능한 A지점 사용자에게 문서 수정 또는 삭제 권한이 있어야 한다. 기본 설치의 비관리자 역할에는 문서 권한이 없었고 실제 업무 역할에 이 권한이 얼마나 부여되는지는 확인하지 않았다. `READ_DOCUMENT`까지 있는 계정은 작은 합성 범위에서 대상 ID를 API로 찾아 후속 쓰기까지 연결했지만, 읽기 권한 없는 쓰기 전용 계정의 독립적인 ID 발견, 실제 운영 범위의 탐색 가능성과 대량 피해는 검증하지 않았다.
- 공식 지점 계층 문서는 일반적인 지점 접근 원칙을 말하지만, 문서 API의 `UPDATE_DOCUMENT`·`DELETE_DOCUMENT` 권한이 반드시 지점 범위로 제한된다고 직접 명시하지는 않는다. 만약 유지보수자가 이를 의도적인 테넌트 전역 권한으로 정의했다면, 교차 지점 쓰기의 보안 취약점 분류는 약해진다. 그 경우에도 잘못된 부모 ID를 수용하는 API 동작은 남지만 그 자체의 피해 수준은 별도로 평가해야 한다.
- 새 HEAD `b033c1363…`에서는 빈 DB 설치, 자기 지점 양성 대조, 정확한 B고객 경로 및 물리 파일 삭제를 확인했다. 공식 안정 릴리스 JAR의 쓰기 경로도 새 DB에서 실행했으나, 그 릴리스에는 공개 수정된 **별도 메서드 권한 누락**이 있어 최신 잔여 문제와 동일한 보안 상태라고 볼 수 없다. 다른 문서 저장소 구현, 프록시, 대규모 고객 ID 범위는 확인하지 않았다. 새 HEAD의 QueryDSL 생성 소스까지 새 스키마에서 다시 만들었고 제품 소스가 깨끗한 상태로 서버를 재기동해 재현했다. 생성 과정에서 로컬 Docker 오류를 우회하기 위한 **임시 빌드 플러그인 변경**이 필요했고 실행 전 원복했다. Docker 기반 기본 빌드 경로 자체가 정상 작동했다고 주장하지 않는다.
- 외부 OIDC 검증은 `4d9557a…`와 새 HEAD `b033c1363…`에서 서명 검증·사용자 연결·권한 적용·쓰기 요청까지 수행했다. 실제 Keycloak 로그인 UI나 외부 IdP의 계정 소유 확인은 시험하지 않았다. 실험자가 제어하는 합성 발급자가 기존 제한 계정의 사용자명으로 토큰을 서명했다. Basic 플래그를 끄고 OIDC만 켠 서버는 두 HEAD 모두 `PasswordEncoder` 빈 누락으로 시작하지 않았다([새 HEAD의 정확한 설정·오류·로그 해시](lab/evidence/document_office_scope_b033_oidc_only_startup_20261127.json)). 성공한 OIDC 시험은 Basic 플래그를 `true`로 두었지만 `/api/**`에서는 Basic 자격증명만으로 `401`이었다. 따라서 보안 가이드의 OIDC 단독 설정을 무수정으로 실행했다고 주장하지 않는다.
- 확인된 변경은 문서 **이름 메타데이터**와 **문서 삭제**다. 바이너리 내용 교체, 금융거래 기록 변경, 다른 엔터티 종류, 타 테넌트, 시스템 장애는 시험하지 않았다. 실제 개인정보·금융기관 배포·외부 API는 시험하지 않았다.
- 심각도는 벤더와 배포 환경의 정책에 따라 달라진다. 고객 문서의 무결성과 가용성에 직접 영향이 있지만, 현재 증거만으로 `Critical`이나 금융기관 사고를 주장하지 않는다. 수정·삭제를 하나의 동일 원인 결함으로 볼지, 읽기 지점 범위 누락과 별도 이슈로 볼지도 유지보수자가 판단해야 한다.

이제 가장 중요한 외부 판정은 **문서 권한이 원래 테넌트 전역인지, 지점 범위인지**다. 저장소의 지점 계층 문서는 일반 원칙과 대출·저축 사례를 설명하지만 문서 권한의 정확한 범위를 직접 정의하지 않는다. 전역 권한이 의도라면 교차 지점 동작을 무단 접근으로 단정할 수 없고, 지점 범위가 의도라면 이번 빈 DB 연쇄 재현은 그 경계 위반의 구체적 증거다. 확인 질문과 정확한 조건을 [정책 질문](DOCUMENT_OFFICE_POLICY_QUESTION_EN.md)에 정리했다.

## 수정 수용 기준

1. PUT·DELETE가 문서 ID만 찾지 않고 URL의 부모 `entityType`·`entityId`와 실제 문서 소속을 일치시켜야 한다. 불일치하면 변경·삭제 없이 `404`여야 한다.
2. 일치하는 B고객 경로라도 A지점 사용자가 부모 고객에 접근할 수 없다면 문서 변경·삭제를 거부해야 한다. 고객 외의 문서 부모 종류는 각 자원의 접근 정책을 따라야 한다.
3. 권한이 맞는 자기 지점 문서의 정상 수정·삭제는 계속 성공해야 하며, 권한이 없는 메서드는 `403`이어야 한다. 삭제 실패 뒤 메타데이터와 파일이 모두 남는지 확인해야 한다.

재현 코드는 [Basic 일회용 합성 실험](lab/document_office_write_scope_reproduce.py)과 [외부 OIDC 재실험](lab/document_office_write_oidc_replay.py)에 있다. 이 연구는 벤더 보안팀에 먼저 제출되지 않은 채 공개됐다. Fineract는 [보안 이슈의 비공개 신고](https://fineract.apache.org/index.html)를 안내한다.
