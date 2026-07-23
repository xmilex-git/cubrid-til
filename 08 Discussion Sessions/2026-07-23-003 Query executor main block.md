---
type: discussion-session
visibility: internal
session-status: completed
started-at: 2026-07-23
source-repository: https://github.com/CUBRID/cubrid
source-branch: develop
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
---

# Query executor main block

## 시작 의견

사용자는 `execute_mainblock`을 중심으로 query executor를 정리하고 싶다. 이번 세션의 우선 범위는 다음 세 가지다.

1. 파티션이 있는 두 table의 NL join
2. `aptr_list`, `dptr_list`, `scan_ptr`의 의미
3. `Pre_processing`, `Processing`, `Post_processing`의 차이

범위를 벗어난 발견은 본문으로 확장하지 않고 `Learning State.md`의 후속 주제 큐에 기록한다.

## 질문과 합의

### Q1. 파티션 table 두 개의 NL join을 어떤 실행 단위로 이해할 것인가

- 사용자 의견: `scan block 조합 순회 → block 내부 row NL join`의 두 단계 모델을 canonical 설명으로 삼는 데 동의했다.
- 권장안: “optimizer가 partition 조합별 join node를 미리 만드는 것”이 아니라 “`scan_ptr` chain은 유지되고, executor가 inner-fastest 순서로 scan block 조합을 순회하며 각 access spec이 자기 partition list에서 다음 물리 partition으로 전환한다”로 이해한다.
- 합의: 두 단계 모델을 canonical 설명으로 확정한다. SQL 의미를 설명할 때는 row NL join으로 요약할 수 있지만, executor 제어를 설명할 때는 상위 scan block 조합 순회를 생략하지 않는다.
- 근거: `qexec_execute_mainblock_internal()`은 `scan_ptr` chain의 scan을 열고 NL interpreter를 구성한다. `qexec_next_scan_block_iterations()`은 후행 scan block을 먼저 전진시키고 끝나면 선행 block을 전진시킨다. `qexec_next_scan_block()`은 현재 access spec의 block이 끝나면 `qexec_init_next_partition()`을 호출해 같은 spec의 다음 물리 partition으로 scan을 교체한다.

### Q2. `aptr`와 `dptr` 약어를 추정해서 풀어 쓸 것인가

- 사용자 의견: 공식 근거 없는 약어 expansion은 피하고 실행 의미로 설명하는 데 동의했다.
- 권장안: 약어의 원형은 `unknown`으로 남기고, canonical 설명은 field의 생성·실행 의미인 “주로 비상관/선행 실행 child list”와 “상관/row-dependent child list”를 사용한다.
- 합의: `aptr_list`, `dptr_list`를 canonical term으로 쓰고 약어 원형은 `unknown`으로 기록한다.
- 근거: 현재 source와 2008년 공개 이력은 각각 uncorrelated/correlated subquery라는 역할을 명시하지만 `a`와 `d`의 공식 expansion은 발견되지 않았다. 또한 `aptr_list`는 CTE, join proc child, DML용 SELECT 등에도 재사용되어 단순히 “uncorrelated subquery pointer”로만 풀면 실제 용도를 모두 설명하지 못한다.

### Q3. 최근 변경으로 lazy `aptr_list`가 모두 사라졌는가

- 사용자 의견: 최근 자신이 `aptr_list`를 eager 실행하도록 변경한 기억이 있어, lazy 실행되는 `aptr_list`가 이제 없는 것 같다고 제안했다. 코드 확인 후 scalar 범위와 `TYPE_LIST_ID` 예외 구분을 확정했다.
- 권장안: “uncorrelated scalar subquery `aptr`는 eager precompute로 바뀌었지만 `TYPE_LIST_ID` regu_var로 연결된 `IN 절`, `EXISTS 절`의 lazy 경로는 남아 있다”로 범위를 한정한다.
- 합의: 일반 `aptr`는 eager, scalar regu-linked `aptr`도 현재 develop에서는 별도 precompute로 eager, `TYPE_LIST_ID` regu_var로 연결된 `IN 절`, `EXISTS 절`은 lazy 가능하다고 확정한다.
- 근거: commit `978b628c8a`는 `pt_make_regu_subquery()`에서 `is_single_tuple`인 subquery에만 `precomp_owner_regu`를 설정한다. `qexec_execute_mainblock_internal()`의 precompute loop도 이 field가 `NULL`이면 건너뛴다. `UNBOX_AS_TABLE`은 `TYPE_LIST_ID`를 만들며 field를 설정하지 않고, `query_evaluator.c`의 `IN`·`EXISTS` 등은 여전히 `EXECUTE_REGU_VARIABLE_XASL`을 호출한다.

### Q4. 세 processing phase를 어떤 경계로 설명할 것인가

- 사용자 의견: `Pre = scan 준비`, `Processing = scan/NL join과 main result 생성`, `Post = result list 후처리`라는 제안을 거부했다. 현업에서는 `pre-processing`, `scan block iteration`, `intprt_fnc (interpreter function)`, `post-processing`이라는 용어를 사용한다.
- 권장안: 사용자가 제시한 네 용어를 canonical term으로 사용하고, `scan block iteration`은 `intprt_fnc` 내부의 반복 제어라는 코드상 포함 관계를 함께 설명한다.
- 합의: 현업 용어 네 개는 확정했다. 포함 관계 설명은 다음 질문에서 확인한다.
- 근거: main block은 `func_vector[0]`에 `qexec_intprt_fnc`를 설정해 호출한다. `qexec_intprt_fnc()` 내부에서 `while (qexec_next_scan_block_iterations(...) == S_SUCCESS)`가 scan block 조합을 반복한다. `post-processing`은 `qexec_end_mainblock_iterations()` 뒤의 GROUP BY·analytic·ORDER BY·DISTINCT 처리다.

### Q5. `scan block iteration`과 `intprt_fnc`의 관계

- 사용자 의견: 현업 용어 네 개를 유지하면서 `scan block iteration`이 `intprt_fnc` 내부 반복이라는 포함 관계로 설명하는 데 동의했다.
- 권장안: 실행 순서를 `pre-processing → intprt_fnc { scan block iteration → row evaluation/NL recursion } → post-processing`으로 설명한다.
- 합의: `intprt_fnc`가 주 interpreter function이고 그 안에서 `scan block iteration`이 수행된다고 확정한다.
- 근거: `qexec_intprt_fnc()`가 `qexec_next_scan_block_iterations()`를 직접 호출하므로 둘은 병렬적인 sibling phase가 아니라 interpreter function 안에 scan block iteration loop가 들어 있는 관계다.

### Q6. 파티션 전환 책임을 어떤 용어 경계에 둘 것인가

- 사용자 의견: 책임 경계를 확정하기 전에 scan block 자체의 정의가 필요하다고 지적하고, scan block이 partition인지 질문했다.
- 권장안: partition 전환은 `scan block iteration`의 책임으로, 현재 block의 row·`dptr_list`·predicate·`scan_ptr` 평가는 `intprt_fnc`의 책임으로 구분한다.
- 합의: Scan block 정의를 먼저 확정할 때까지 보류한다.
- 근거: `qexec_next_scan_block_iterations()`가 `qexec_next_scan_block()`을 호출하고, 이 함수가 현재 scan block 종료 시 `qexec_init_next_partition()`을 호출한다. 반면 `qexec_intprt_fnc()`의 row loop는 `scan_next_scan()` 뒤 `dptr_list`, predicate, 후행 `scan_ptr`와 tuple 생성을 처리한다.

### Q7. Scan block의 정의

- 사용자 의견: scan block의 정의가 우선이며 partition과 같은 것인지 질문했다. Grouped scan은 dead code이므로 현재 정의에서 상정하지 말라고 정정했다. 이어 `scan block next`가 실제로 다음 partition으로 전환하며, 두 partition table의 NL join에서 `t1p1-t2p1`, `t1p1-t2p2`, `t1p2-t2p1`, `t1p2-t2p2`가 된다는 점이 핵심이라고 지적했다.
- 권장안: `execute_mainblock` 문맥의 scan block을 “main XASL과 `scan_ptr`로 연결된 각 후행 `SCAN_PROC`에서 현재 선택한 access target의 전체 scan”으로 정의한다. Partitioned class의 active path에서는 `spec->curent`가 가리키는 한 partition scan이 한 block이다.
- 합의: scan block을 일반적으로 partition 자체라고 정의하지 않는다. Main XASL과 각 후행 `SCAN_PROC`가 현재 선택한 access target의 전체 scan이며, partitioned class의 active path에서는 한 partition scan과 한 scan block이 1:1로 대응한다고 확정했다.
- 근거: `qexec_next_scan_block()`은 scan manager block이 끝나면 `qexec_init_next_partition()`을 호출하고 다음 partition scan을 같은 block sequence의 다음 원소로 반환한다. `qexec_next_scan_block_iterations()`은 후행 `SCAN_PROC`의 block을 먼저 전진시키고, 모두 사용하면 앞쪽 XASL node의 block을 전진한 뒤 후행 `SCAN_PROC`를 첫 block부터 다시 시작한다.

### Q8. Partition scan block Cartesian product를 canonical model로 둘 것인가

- 사용자 의견: 두 partition table의 NL join에서 네 partition 조합이 scan block iteration으로 만들어지는 부분이 가장 난해하고 핵심이라고 했다.
- 권장안: main XASL에서 앞쪽 partition 하나를 고정하고 `scan_ptr`의 후행 `SCAN_PROC`에서 뒤쪽 partition을 하나씩 골라 join할 조합을 만드는 모델로 설명한다. `qexec_next_scan_block_iterations()`은 뒤쪽 partition을 먼저 바꾸고, `intprt_fnc`는 선택된 block 안의 row·predicate를 평가한다.
- 합의: partitioned NL join의 scan block iteration을 앞쪽 partition 하나와 뒤쪽 partition 하나를 골라 join할 조합을 만드는 반복으로 설명한다. 단, Q9의 `qualified_block` 가지치기를 포함한다.
- 근거: `t2` block이 끝나기 전에는 `t1` block을 reset하고, `t2` sequence가 끝나면 `t1`을 다음 block으로 전진한 뒤 `t2`를 첫 block부터 다시 시작한다. `qualified_block == false`인 경우에는 결과 없는 조합을 생략할 수 있다.

### Q9. `qualified_block`은 무엇이며 scan block iteration을 어떻게 바꾸는가

- 사용자 의견: scan block이 qualified됐을 때와 아닐 때 실행되는 경로가 다르므로, 이 개념을 별도 설명에 그치지 않고 전체 모델에 반영해야 한다고 지적했다.
- 설명 형식: block 선택과 row 평가의 feedback 관계, `true`/`false` 분기, 두 partition table의 전개·가지치기를 ASCII-art로 표현해 한눈에 비교할 수 있게 해 달라고 요청했다.
- 용어 정정: 두 partition을 한 단어로 묶어 부르는 압축 표현은 사용하지 않는다. “앞쪽 table에서 partition 하나를 고르고, 뒤쪽 table에서 partition 하나를 골라 join할 조합을 만든다”라고 풀어 설명한다.
- 용어 정정: `per-level`, `scan level`은 source 용어가 아니며 무엇을 가리키는지 불명확하므로 사용하지 않는다. 구조는 “main XASL의 앞쪽 scan + `scan_ptr`로 연결된 후행 `SCAN_PROC`”로 부른다. `scan_ptr` 이후 node는 `SCAN_PROC`지만 첫 scan을 수행하는 root는 `BUILDLIST_PROC`일 수 있으므로 전체를 `SCAN_PROC`라고 부르지는 않는다.
- 권장안: `qualified_block`을 “현재 XASL node의 scan block에서 조건 평가를 통과해 `scan_ptr`가 가리키는 후행 `SCAN_PROC`를 구동한 row가 하나라도 있었음”으로 정의한다. `true`이면 후행 `SCAN_PROC`의 다른 block과 조합을 계속 실행하고, `false`이면 그 나머지 조합을 건너뛴다.
- 합의: 권장안을 확정했다. `per-level`·`scan level` 같은 추상 표현은 사용하지 않고, main XASL의 앞쪽 scan과 `scan_ptr`가 가리키는 후행 `SCAN_PROC`로 실행 주체를 명시한다.
- 근거: `scan_next_scan_block()`은 새 block에서 `qualified_block = false`로 초기화한다. `qexec_intprt_fnc()`과 `qexec_execute_scan()`은 qualified row가 후행 `SCAN_PROC`를 구동하기 직전에 이를 `true`로 설정한다. `qexec_next_scan_block_iterations()`은 started block의 flag가 `false`이면 더 뒤쪽 `SCAN_PROC`의 block 조합을 실행하지 않고 현재 XASL node의 다음 block으로 직접 이동한다.
- 용어 주의: 이 flag는 final join result 존재 여부도, physical scan이 row를 하나 읽었다는 뜻도 아니다. 더 뒤쪽 scan이 최종 결과 0건을 만들 수 있으며, `scan_ptr == NULL`인 마지막 `SCAN_PROC`에는 후행 조합을 가지치기할 용도가 없다.

### Q10. Scan block iteration 종료와 post-processing의 경계

- 권장안: `intprt_fnc`가 끝난 뒤 호출되는 `qexec_end_mainblock_iterations()`까지를 scan block iteration의 종료 처리로 본다. 그 뒤 result list에 적용되는 GROUP BY·analytic·ORDER BY/DISTINCT를 `post-processing`으로 구분한다.
- 합의: 이번 세션에서는 확정하지 않고 `Main iteration 종료와 post-processing 경계`라는 후속 주제로 큐에 올려 나중에 별도로 검증한다.
- 근거: `qexec_execute_mainblock_internal()`은 scan 함수 실행과 scan close 뒤 `qexec_end_mainblock_iterations()`를 호출하고, 이후 GROUP BY·analytic·ORDER BY/DISTINCT 경로로 진행한다.
- 예외: 일부 analytic function은 limit 최적화 때문에 `intprt_fnc` 안에서 평가될 수 있으므로, 모든 analytic evaluation이 물리적으로 이 경계 뒤에 있다고 일반화하지 않는다.

## 정정 및 충돌

- `aptr`, `dptr`는 일반 C pointer 종류가 아니라 `XASL_NODE`의 child list 역할명이다. canonical term은 실제 field인 `aptr_list`, `dptr_list`를 사용한다. 약어 expansion은 근거를 찾기 전까지 단정하지 않는다.
- source comment가 현재 의미를 직접 명시한다: `aptr_list`는 CTE와 uncorrelated subquery, `dptr_list`는 correlated subquery, `scan_ptr`는 `SCAN_PROC` 연결이다.
- 현업 canonical term은 `pre-processing`, `scan block iteration`, `intprt_fnc (interpreter function)`, `post-processing`이다. source의 `Processing` comment를 별도 현업 단계명으로 확장하지 않는다.
- 사용자 경험상 `list-valued`는 현업에서 사용하지 않는다. 코드 자료구조는 `TYPE_LIST_ID` regu_var, SQL 표현은 `IN 절`, `EXISTS 절`이라는 용어를 사용한다.
- `intprt_fnc`는 함수명에 따라 `interpreter function`이라고 부르지만, 실제 동작을 한국어로 설명할 때는 row를 “해석한다”가 아니라 row와 predicate를 “평가한다”고 표현한다.
- Scan block iteration은 단순 Cartesian product가 아니라 `qualified_block` feedback으로 결과 없는 prefix의 suffix product를 생략하는 qualification-aware Cartesian-product iteration이다.

## 생성·갱신한 지식

- [[Query executor의 main block 실행]]
- [[Scan block]]

## 미해결 사항

- partition pruning으로 한쪽 partition list가 비거나 일부만 남을 때의 구체적인 예
- `TYPE_LIST_ID` regu_var로 연결된 `IN 절`, `EXISTS 절`이 실제로 `aptr_list`에 배치되는 testcase 확인
- 세 동작의 최초 공식 release

## 나중에 다룰 주제

- Scan manager와 access method 실행 — `scan_open_scan()`, `scan_next_scan_block()`, heap/index별 `scan_next_scan()` 세부 구현은 별도 주제로 유지한다.
- NL join memoization — `memoize_storage`의 key와 partition 전환 시 무효화 조건은 현재 세 포인터와 phase 구분을 잡은 뒤 다룬다.
- Parallel query executor — `px_executor`가 `aptr_list`와 scan 실행을 병렬화하는 규칙은 직렬 실행 의미를 먼저 확정한 뒤 다룬다.
- Fixed/grouped/cached scan 정책 — page fix 수명과 driving/inner scan 제약은 main block의 기본 제어를 확정한 뒤 다룬다.
- Grouped scan legacy code — 현재 `grouped_scan`이 항상 false인 이유, 남은 `HEAP_SCANRANGE`·grouped index code의 역사와 제거 가능성을 별도로 검증한다.
- NL join 종류별 scan block 종료 — outer/semi/anti join에서 `qualified_block`, `single_fetch`, null-padding이 결합하는 규칙은 기본 inner NL join 모델을 확정한 뒤 다룬다.
- Main iteration 종료와 post-processing 경계 — `qexec_end_mainblock_iterations()`을 어느 실행 구간에 포함할지와 analytic function 최적화 예외를 별도로 검증한다.

## 종료 상태

원래 범위였던 partitioned NL join의 scan block 조합, `aptr_list`·`dptr_list`·`scan_ptr`, 현업 실행 용어와 `qualified_block`의 의미를 canonical note에 반영했다. Q10은 후속 주제로 이관하고 세션을 완료한다.

## 다음 후보

- engine: Broker의 CAS 할당과 연결 인계
- development: CTP suite별 책임과 testcase 형식
- operations: CUBRID 구성과 서버 생명주기
