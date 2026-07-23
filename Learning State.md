---
type: learning-state
visibility: internal
updated-at: 2026-07-23
active-session: null
sync-status: clean
---

# Learning State

## 현재 세션

진행 중인 세션이 없다. 최근 완료 세션은 [[2026-07-23-005 Buffer manager page fix와 latch]]다.

## BFS Frontier

| 주제 | 트랙 | 깊이 | 선수 주제 | 우선순위 | 추천 횟수 | 상태 |
|---|---|---:|---|---|---:|---|
| CUBRID 전체 구조 | engine | 0 | - | - | 1 | completed |
| [[Page fix와 page latch]] | engine | 1 | CUBRID 전체 구조 | P0 | 2 | completed |
| Broker의 CAS 할당과 연결 인계 | engine | 1 | CUBRID 전체 구조 | P2 | 3 | frontier |
| SELECT SQL 실행 경로 | engine | 1 | [[CAS와 server의 SELECT 처리 경계]] | - | 1 | completed |
| [[Query executor의 main block 실행]] | engine | 2 | [[CAS와 server의 SELECT 처리 경계]] | - | 1 | completed |
| CUBRID 개발·테스트 흐름 | development | 0 | - | - | 3 | completed |
| C/C++ compiler portability와 GCC-Clang 차이 | development | 1 | [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]] | P1 | 2 | frontier |
| CTP suite별 책임과 testcase 형식 | development | 1 | [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]] | P2 | 1 | frontier |
| CUBRID 구성과 서버 생명주기 | operations | 0 | - | P1 | 5 | frontier |

## 후속 주제 큐

우선순위는 `P0`(최근 본인 구현과 직접 연결) → `P1`(직접 구현의 선수·관찰 주제) → `P2`(기존 BFS의 일반 확장) → `P3`(현재 관심 코드와 거리가 있는 process 세부) 순이다. 우선순위와 BFS 승격 가능 여부는 별개다.

| 주제 | 트랙 | 예상 깊이 | 우선순위 | 발견 세션 | 다룰 이유 | 선수 주제 | 언급 횟수 | 상태 |
|---|---|---:|---|---|---|---|---:|---|
| Parallel query executor | engine | 3 | P0 | [[2026-07-23-003 Query executor main block]], [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | `px_scan`의 worker/task, 결과 병합, worker 부족·부적격 scan의 직렬 fallback을 PR #6512·#7062와 현재 코드에서 검증한다. | [[Query executor의 main block 실행]], Scan manager와 access method 실행 | 2 | queued |
| Parallel index scan의 optimizer–server 이중 게이트 | engine | 3 | P0 | [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #7516의 histogram provenance 기반 후보 선정과 실행 직전 실제 index page 기반 fallback 경계를 검증한다. | Optimizer cost와 join enumeration, Scan manager와 access method 실행, Parallel query executor | 1 | queued |
| Parallel bulk index build의 external-sort 구간 분할 | engine | 2 | P0 | [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #7011·#7504에서 run 정렬, key-space 분할, leaf 작성과 상위 level 조립의 병렬 구조를 검증한다. | [[Page fix와 page latch]], B-tree와 external sort 기본 구조 | 1 | queued |
| No-redo bulk index build의 durability barrier와 backup 경계 | operations | 2 | P0 | [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #7504의 page redo 생략, write-through, `RVBT_BULK_BUILD_DURABLE`, crash recovery와 restoredb 제약을 구분한다. | CUBRID 구성과 서버 생명주기, Parallel bulk index build의 external-sort 구간 분할, WAL과 media recovery 기본 모델 | 1 | queued |
| Page buffer atomic latch의 `waiter_exists` 불변식과 hang 진단 | operations | 2 | P0 | [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #6704·#7487을 통해 flush waiter dequeue 뒤 stale bit가 idle-grant CAS 무한 spin으로 이어지는 조건과 진단법을 검증한다. | [[Page fix와 page latch]], CUBRID 구성과 서버 생명주기 | 1 | queued |
| Cached heap scan의 page-copy 후 PEEK read mode | engine | 3 | P0 | [[2026-07-23-003 Query executor main block]], [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #7441의 `qexec_is_cached_scan_eligible()`, scan-local page copy, latch-free PEEK와 COPY fallback 계약을 검증한다. | [[Query executor의 main block 실행]], Scan manager와 access method 실행, [[Page fix와 page latch]] | 3 | queued |
| Uncorrelated scalar subquery의 eager precompute와 worker value injection | engine | 3 | P0 | [[2026-07-23-003 Query executor main block]], [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #7316의 `precomp_owner_regu`, main-thread 1회 평가와 worker clone 주입이 lazy 의미를 어디까지 바꾸는지 검증한다. | [[Query executor의 main block 실행]], Parallel query executor | 2 | queued |
| NL join memoization | engine | 3 | P0 | [[2026-07-23-003 Query executor main block]], [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #6555·#6652·#6877을 따라 cache key, hit-ratio 비활성화, storage 정리와 partition 전환 조건을 검증한다. | [[Query executor의 main block 실행]] | 2 | queued |
| Explicit SEMI/ANTI JOIN과 subquery unnesting 기반 | engine | 2 | P0 | [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #7252의 parser·semantic·optimizer·NL executor 경계를 따라 EXISTS 계열 rewrite의 실행 기반을 검증한다. | [[CAS와 server의 SELECT 처리 경계]], [[Query executor의 main block 실행]] | 1 | queued |
| [[Page fix와 page latch]] | engine | 1 | P0 | [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]], [[2026-07-23-005 Buffer manager page fix와 latch]] | PR #7441·#7487을 이해하는 선수 지식으로 BCB, fix/unfix, latch, waiter queue의 정상 상태 전이를 먼저 정리한다. | CUBRID 전체 구조 | 2 | completed |
| Optimizer cost와 join enumeration | engine | 2 | P1 | [[2026-07-23-001 SELECT SQL 실행 경로]], [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | cardinality·cost·join 순서와 함께 PR #7516의 histogram 선택도 provenance 및 access-path 병렬화 판정을 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 2 | queued |
| Scan manager와 access method 실행 | engine | 2 | P1 | [[2026-07-23-001 SELECT SQL 실행 경로]], [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | `qexec_open_scan()` 아래 heap/index/list scan의 open·next·close와 parallel/cached scan 승격 지점을 검증한다. | [[CAS와 server의 SELECT 처리 경계]], [[Page fix와 page latch]] | 2 | queued |
| Parallel scan trace와 직렬 fallback 진단 | operations | 2 | P1 | [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #7018·#7043·#7219의 trace 노출 조건과 worker 통계가 없는 정상 fallback·오류 상태를 구분한다. | Parallel query executor, CUBRID 구성과 서버 생명주기 | 1 | queued |
| C/C++ compiler portability와 GCC-Clang 차이 | development | 1 | P1 | [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | PR #7446의 C++로 컴파일되는 `.c`, VLA 초기화 차이와 multi-compiler 검증 범위를 정리한다. | [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]] | 1 | frontier |
| NL join 종류별 scan block 종료 | engine | 3 | P1 | [[2026-07-23-003 Query executor main block]], [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | outer/semi/anti join에서 `qualified_block`, `single_fetch`, null-padding이 만드는 조기 종료·결과 생성 규칙을 PR #7252와 함께 검증한다. | [[Query executor의 main block 실행]], [[Scan block]], Explicit SEMI/ANTI JOIN과 subquery unnesting 기반 | 2 | queued |
| Grouped scan legacy code와 fixed scan 정책 | engine | 3 | P2 | [[2026-07-23-003 Query executor main block]], [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | 항상 false인 grouped scan 경로의 역사와 page fix 수명, driving/inner scan 제약을 cached scan과 분리해 검증한다. | [[Query executor의 main block 실행]], Scan manager와 access method 실행, [[Page fix와 page latch]] | 2 | queued |
| DDL/DML의 CAS–server 처리 변형 | engine | 2 | P2 | [[2026-07-22-001 CUBRID 전체 구조]] | SELECT와 다른 generation·execution 경로를 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| XASL cache hit와 recompile 생명주기 | engine | 2 | P2 | [[2026-07-22-001 CUBRID 전체 구조]] | prepare/cache timing과 plan 재사용·무효화 조건을 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| View query pushability 판단 | engine | 2 | P2 | [[2026-07-23-001 SELECT SQL 실행 경로]] | `mq_is_pushable_subquery()`의 direct merge와 derived-table 보존 조건을 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| Main iteration 종료와 post-processing 경계 | engine | 3 | P2 | [[2026-07-23-003 Query executor main block]] | `qexec_end_mainblock_iterations()`을 어느 실행 구간에 포함할지와 analytic function 최적화 예외를 검증한다. | [[Query executor의 main block 실행]] | 1 | queued |
| Result fetch pagination과 overflow tuple | engine | 2 | P2 | [[2026-07-23-001 SELECT SQL 실행 경로]] | `CAS_FC_FETCH`의 page 추가 요청, cursor buffer와 overflow tuple 처리를 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| CTP suite별 책임과 testcase 형식 | development | 1 | P2 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | SQL·medium·shell·CCI category의 책임과 testcase 작성 단위를 검증한다. | [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]] | 1 | frontier |
| QA Home Verify Status와 unstable 판정 기준 | operations | 1 | P2 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | 신규 failure의 unstable·test error·engine regression 판정과 상태값 의미를 검증한다. | [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]], CUBRID 구성과 서버 생명주기 | 1 | queued |
| Transaction lock timeout과 page latch zero-wait 전달 경로 | operations | 2 | P1 | [[2026-07-23-005 Buffer manager page fix와 latch]] | `lock_timeout_in_secs`, client/CAS의 `lock_timeout`, SQL hint와 `LOG_TDES::wait_msecs`가 `pgbuf_fix()`의 conditional 전환에 도달하는 설정·전파 경로를 검증한다. | [[Page fix와 page latch]], CUBRID 구성과 서버 생명주기 | 1 | queued |
| Buffer pool LRU·victim 선정과 dirty page flush | engine | 2 | P1 | [[2026-07-23-005 Buffer manager page fix와 latch]] | bcb fix count 0 이후 replacement 후보화, dirty victim의 WAL flush와 BCB 재사용 경계를 검증한다. | [[Page fix와 page latch]] | 1 | queued |
| B-tree split·merge의 page latch ordering | engine | 2 | P1 | [[2026-07-23-005 Buffer manager page fix와 latch]] | promotion caller에서 발견한 parent/child/sibling 다중 latch 순서, ONLY_READER 실패와 WRITE traversal restart가 교착을 피하는 경계를 검증한다. | [[Page fix와 page latch]], B-tree 기본 구조 | 1 | queued |
| 누적 testcase lifecycle과 retirement | development | 2 | P3 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | Daily regression에 누적된 TC의 수정·비활성화·삭제 조건을 검증한다. | CTP suite별 책임과 testcase 형식 | 1 | queued |
| 관리자 예외 merge 승인·사후 추적 | development | 2 | P3 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | Branch-protection 예외 merge의 승인 근거와 사후 기록을 검증한다. | [[CUBRID 개발 이슈에서 릴리즈까지]] | 1 | queued |
| Release scope·stabilization·approval | development | 2 | P3 | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | Closed issue가 정식 release에 포함되는 선별·branch·안정화·승인 과정을 검증한다. | [[CUBRID 개발 이슈에서 릴리즈까지]] | 1 | queued |

`queued` 주제는 선수 지식이 완료되고 해당 BFS 깊이가 열릴 때 frontier로 승격한다. 같은 개념을 다시 언급하면 새 행을 만들지 않고 발견 세션과 언급 횟수를 갱신한다.

## 완료 주제

| 주제 | 완료 세션 | 지식 상태 |
|---|---|---|
| [[CUBRID 3-tier 구조]] | [[2026-07-22-001 CUBRID 전체 구조]] | partially-verified |
| [[CAS와 server의 SELECT 처리 경계]] | [[2026-07-23-001 SELECT SQL 실행 경로]] | partially-verified |
| [[CUBRID 개발 이슈에서 릴리즈까지]] | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | partially-verified |
| [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]] | [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | partially-verified |
| [[Query executor의 main block 실행]] | [[2026-07-23-003 Query executor main block]] | partially-verified |
| [[Scan block]] | [[2026-07-23-003 Query executor main block]] | partially-verified |
| [[Page fix와 page latch]] | [[2026-07-23-005 Buffer manager page fix와 latch]] | partially-verified |
| [[Page latch promotion 호출 경로]] | [[2026-07-23-005 Buffer manager page fix와 latch]] | partially-verified |

## 이전 추천 결과

| 세션 | 후보 | 트랙 | 결과 |
|---|---|---|---|
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 전체 구조 | engine | selected |
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 개발·테스트 흐름 | development | deferred |
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 구성과 서버 생명주기 | operations | deferred |
| [[2026-07-23-001 SELECT SQL 실행 경로]] | SELECT SQL 실행 경로 | engine | selected |
| [[2026-07-23-002 CUBRID 개발 테스트 흐름]] | CUBRID 개발·테스트 흐름 | development | selected |
| [[2026-07-23-003 Query executor main block]] | [[Query executor의 main block 실행]] | engine | selected |
| [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | Buffer manager의 page fix와 latch 기본 모델 | engine | deferred |
| [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | C/C++ compiler portability와 GCC-Clang 차이 | development | deferred |
| [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] | CUBRID 구성과 서버 생명주기 | operations | deferred |
| [[2026-07-23-005 Buffer manager page fix와 latch]] | [[Page fix와 page latch]] | engine | selected |

결과는 `selected`, `deferred`, `rejected` 중 하나이며 이력에서 삭제하지 않는다.

## 보류 및 미해결 질문

- 진행 중인 session 질문은 없다. `pgbuf_wakeup_reader_writer()`의 “head readers” 주석과 WRITE를 건너뛰는 loop 동작의 의도는 미확인이다.
- `PGBUF_PROMOTE_SHARED_READER`가 기다리는 동안 page 내용이 바뀔 때 caller별 재검증 범위와 workload별 promotion 빈도는 미확인이다.
- PR #7516과 #7504는 2026-07-23 기준 open이므로 merge 전후 구현 변화와 공식 release 포함 여부를 각 주제 학습 시 다시 확인한다.
- source checkout `e1e81d600f604d0fc22ded3066186a1a9aaec184`는 `origin/develop`보다 10 commit 뒤처지고 사용자 변경이 있어 pull하지 않았다. PR #7487 merge 결과도 이 checkout에는 아직 반영되지 않았다.
