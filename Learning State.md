---
type: learning-state
visibility: internal
updated-at: 2026-07-23
active-session: "[[2026-07-23-003 Query executor main block]]"
sync-status: clean
---

# Learning State

## 현재 세션

[[2026-07-23-003 Query executor main block]] — `execute_mainblock`의 partition NL join, `aptr_list`·`dptr_list`·`scan_ptr`, 세 실행 phase를 검증 중이다.

## BFS Frontier

| 주제 | 트랙 | 깊이 | 선수 주제 | 추천 횟수 | 상태 |
|---|---|---:|---|---:|---|
| CUBRID 전체 구조 | engine | 0 | - | 1 | completed |
| Broker의 CAS 할당과 연결 인계 | engine | 1 | CUBRID 전체 구조 | 2 | frontier |
| SELECT SQL 실행 경로 | engine | 1 | [[CAS와 server의 SELECT 처리 경계]] | 1 | completed |
| [[Query executor의 main block 실행]] | engine | 2 | [[CAS와 server의 SELECT 처리 경계]] | 1 | selected |
| CUBRID 개발·테스트 흐름 | development | 0 | - | 3 | completed |
| CTP suite별 책임과 testcase 형식 | development | 1 | [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]] | 1 | frontier |
| CUBRID 구성과 서버 생명주기 | operations | 0 | - | 3 | frontier |

## 후속 주제 큐

| 주제 | 트랙 | 예상 깊이 | 발견 세션 | 다룰 이유 | 선수 주제 | 언급 횟수 | 상태 |
|---|---|---:|---|---|---|---:|---|
| DDL/DML의 CAS–server 처리 변형 | engine | 2 | [[2026-07-22-001 CUBRID 전체 구조]] | SELECT와 다른 generation·execution 경로를 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| XASL cache hit와 recompile 생명주기 | engine | 2 | [[2026-07-22-001 CUBRID 전체 구조]] | prepare/cache timing과 plan 재사용·무효화 조건을 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| View query pushability 판단 | engine | 2 | [[2026-07-23-001 SELECT SQL 실행 경로]] | `mq_is_pushable_subquery()`의 direct merge와 derived-table 보존 조건을 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| Optimizer cost와 join enumeration | engine | 2 | [[2026-07-23-001 SELECT SQL 실행 경로]] | cardinality/cost 추정, access path 비교와 join 순서 탐색을 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| Scan manager와 access method 실행 | engine | 2 | [[2026-07-23-001 SELECT SQL 실행 경로]] | `qexec_open_scan()` 아래에서 heap/index scan이 열리고 tuple을 탐색·필터링하는 경로를 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| NL join memoization | engine | 3 | [[2026-07-23-003 Query executor main block]] | inner scan 결과 cache의 key, 재사용 조건과 partition 전환 시 무효화를 검증한다. | [[Query executor의 main block 실행]] | 1 | queued |
| Parallel query executor | engine | 3 | [[2026-07-23-003 Query executor main block]] | `px_executor`가 `aptr_list`와 scan 실행을 병렬화할 때 직렬 main block 의미가 어떻게 보존되는지 검증한다. | [[Query executor의 main block 실행]] | 1 | queued |
| Fixed grouped cached scan 정책 | engine | 3 | [[2026-07-23-003 Query executor main block]] | page fix 수명과 driving/inner scan 제약을 검증하고, 항상 false인 grouped scan legacy code의 역사와 제거 가능성을 확인한다. | [[Query executor의 main block 실행]], Scan manager와 access method 실행 | 2 | queued |
| NL join 종류별 scan block 종료 | engine | 3 | [[2026-07-23-003 Query executor main block]] | outer/semi/anti join에서 `qualified_block`, `single_fetch`, null-padding이 만드는 조기 종료·결과 생성 규칙을 검증한다. | [[Query executor의 main block 실행]], [[Scan block]] | 1 | queued |
| Result fetch pagination과 overflow tuple | engine | 2 | [[2026-07-23-001 SELECT SQL 실행 경로]] | `CAS_FC_FETCH`의 page 추가 요청, cursor buffer와 overflow tuple 처리를 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| CTP suite별 책임과 testcase 형식 | development | 1 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | SQL·medium·shell·CCI category의 책임과 testcase 작성 단위를 검증한다. | [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]] | 1 | frontier |
| 누적 testcase lifecycle과 retirement | development | 2 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | Daily regression에 누적된 TC의 수정·비활성화·삭제 조건을 검증한다. | CTP suite별 책임과 testcase 형식 | 1 | queued |
| 관리자 예외 merge 승인·사후 추적 | development | 2 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | Branch-protection 예외 merge의 승인 근거와 사후 기록을 검증한다. | [[CUBRID 개발 이슈에서 릴리즈까지]] | 1 | queued |
| Release scope·stabilization·approval | development | 2 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | Closed issue가 정식 release에 포함되는 선별·branch·안정화·승인 과정을 검증한다. | [[CUBRID 개발 이슈에서 릴리즈까지]] | 1 | queued |
| QA Home Verify Status와 unstable 판정 기준 | operations | 1 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | 신규 failure의 unstable·test error·engine regression 판정과 상태값 의미를 검증한다. | [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]], CUBRID 구성과 서버 생명주기 | 1 | queued |

`queued` 주제는 선수 지식이 완료되고 해당 BFS 깊이가 열릴 때 frontier로 승격한다. 같은 개념을 다시 언급하면 새 행을 만들지 않고 발견 세션과 언급 횟수를 갱신한다.

## 완료 주제

| 주제 | 완료 세션 | 지식 상태 |
|---|---|---|
| [[CUBRID 3-tier 구조]] | [[2026-07-22-001 CUBRID 전체 구조]] | partially-verified |
| [[CAS와 server의 SELECT 처리 경계]] | [[2026-07-23-001 SELECT SQL 실행 경로]] | partially-verified |
| [[CUBRID 개발 이슈에서 릴리즈까지]] | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | partially-verified |
| [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]] | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | partially-verified |

## 이전 추천 결과

| 세션 | 후보 | 트랙 | 결과 |
|---|---|---|---|
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 전체 구조 | engine | selected |
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 개발·테스트 흐름 | development | deferred |
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 구성과 서버 생명주기 | operations | deferred |
| [[2026-07-23-001 SELECT SQL 실행 경로]] | SELECT SQL 실행 경로 | engine | selected |
| [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | CUBRID 개발·테스트 흐름 | development | selected |
| [[2026-07-23-003 Query executor main block]] | [[Query executor의 main block 실행]] | engine | selected |

결과는 `selected`, `deferred`, `rejected` 중 하나이며 이력에서 삭제하지 않는다.

## 보류 및 미해결 질문

- [[2026-07-23-003 Query executor main block]] Q10: `qexec_end_mainblock_iterations()`을 scan block iteration의 종료 처리로 두고, 그 호출 뒤부터 GROUP BY·analytic·ORDER BY/DISTINCT를 `post-processing`으로 구분할지 합의한다.
