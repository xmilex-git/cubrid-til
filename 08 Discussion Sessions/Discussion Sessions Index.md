---
type: index
visibility: internal
---

# Discussion Sessions Index

사용자 의견이 질문, 검증과 합의를 거쳐 canonical knowledge로 정제된 이력을 연결한다.

## Active

진행 중인 세션이 없다.

## Completed

- [[2026-07-22-001 CUBRID 전체 구조]] — CAS–broker–server 3-tier, 실제 접속 흐름과 CAS–server의 `SELECT` 처리 경계를 확정했다.
- [[2026-07-23-001 SELECT SQL 실행 경로]] — CAS의 SQL compile 단계와 server의 XASL 실행 경계를 검증해 canonical note로 정제했다.
- [[2026-07-23-002 CUBRID 개발 테스트 흐름]] — JIRA issue부터 release까지의 lifecycle과 CTP 중심 테스트 계층을 확정했다.
- [[2026-07-23-003 Query executor main block]] — partitioned NL join의 scan block 조합, 세 child pointer, 현업 실행 용어와 `qualified_block`을 정리했다.
- [[2026-07-23-004 PR 기반 후속 주제 우선순위 재정비]] — 최근 본인 PR과 현재 코드를 대조해 후속 큐를 P0–P3로 재정렬하고 BFS 선수 관계를 보강했다.
- [[2026-07-23-005 Buffer manager page fix와 latch]] — 두 fix count, atomic-latch READ fast path, waiter barrier, promotion caller와 dirty 책임을 코드로 검증했다.

## Related

- [[Learning State]]
