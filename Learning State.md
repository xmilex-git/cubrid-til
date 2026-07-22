---
type: learning-state
visibility: internal
updated-at: 2026-07-22
active-session: null
sync-status: clean
---

# Learning State

## 현재 세션

진행 중인 세션이 없다.

## BFS Frontier

| 주제 | 트랙 | 깊이 | 선수 주제 | 추천 횟수 | 상태 |
|---|---|---:|---|---:|---|
| CUBRID 전체 구조 | engine | 0 | - | 1 | completed |
| Broker의 CAS 할당과 연결 인계 | engine | 1 | CUBRID 전체 구조 | 1 | frontier |
| CUBRID 개발·테스트 흐름 | development | 0 | - | 2 | frontier |
| CUBRID 구성과 서버 생명주기 | operations | 0 | - | 2 | frontier |

## 후속 주제 큐

| 주제 | 트랙 | 예상 깊이 | 발견 세션 | 다룰 이유 | 선수 주제 | 언급 횟수 | 상태 |
|---|---|---:|---|---|---|---:|---|
| DDL/DML의 CAS–server 처리 변형 | engine | 2 | [[2026-07-22-001 CUBRID 전체 구조]] | SELECT와 다른 generation·execution 경로를 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |
| XASL cache hit와 recompile 생명주기 | engine | 2 | [[2026-07-22-001 CUBRID 전체 구조]] | prepare/cache timing과 plan 재사용·무효화 조건을 검증한다. | [[CAS와 server의 SELECT 처리 경계]] | 1 | queued |

`queued` 주제는 선수 지식이 완료되고 해당 BFS 깊이가 열릴 때 frontier로 승격한다. 같은 개념을 다시 언급하면 새 행을 만들지 않고 발견 세션과 언급 횟수를 갱신한다.

## 완료 주제

| 주제 | 완료 세션 | 지식 상태 |
|---|---|---|
| [[CUBRID 3-tier 구조]] | [[2026-07-22-001 CUBRID 전체 구조]] | partially-verified |
| [[CAS와 server의 SELECT 처리 경계]] | [[2026-07-22-001 CUBRID 전체 구조]] | partially-verified |

## 이전 추천 결과

| 세션 | 후보 | 트랙 | 결과 |
|---|---|---|---|
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 전체 구조 | engine | selected |
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 개발·테스트 흐름 | development | deferred |
| [[2026-07-22-001 CUBRID 전체 구조]] | CUBRID 구성과 서버 생명주기 | operations | deferred |

결과는 `selected`, `deferred`, `rejected` 중 하나이며 이력에서 삭제하지 않는다.

## 보류 및 미해결 질문

없음.
