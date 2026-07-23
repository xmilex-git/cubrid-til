---
type: code-walkthrough
aliases: [execute_mainblock, qexec_execute_mainblock, query executor, NL join, scan, aptr_list, dptr_list]
visibility: internal
learning-status: in-progress
knowledge-status: partially-verified
code-era: historical
rationale-evidence: mixed
source-release: "2008 R2.1 or earlier"
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-23
---

# Query executor의 main block 실행

`qexec_execute_mainblock()`은 한 `XASL_NODE` main procedure block의 실행 wrapper이고, 실제 단계 제어는 `qexec_execute_mainblock_internal()`이 담당한다. SELECT 계열의 핵심 흐름은 선행 child 실행과 초기화, scan/NL join 반복, 결과 list에 대한 후처리로 나뉜다.

## 초심자를 위한 설명

현재 확인된 큰 흐름은 다음과 같다.

```text
qexec_execute_mainblock()
└─ qexec_execute_mainblock_internal()
   ├─ pre-processing
   │  ├─ LIMIT 사전 검사
   │  ├─ aptr_list 실행
   │  └─ main block/list/aggregate 초기화
   ├─ intprt_fnc (interpreter function)
   │  └─ scan block iteration
   │     ├─ main XASL의 앞쪽 scan
   │     ├─ scan_ptr의 후행 SCAN_PROC를 통한 NL join
   │     └─ row·predicate 평가와 tuple 생성
   ├─ main iteration 종료
   └─ post-processing
      ├─ GROUP BY
      ├─ analytic function
      └─ ORDER BY / DISTINCT
```

이 구분은 모든 statement type에 똑같이 적용되는 별도 subsystem이 아니다. `UPDATE_PROC`, `DELETE_PROC`, `INSERT_PROC` 등은 type switch에서 전용 executor로 빠지고, 위 흐름은 `BUILDLIST_PROC`, `BUILDVALUE_PROC` 같은 SELECT 계열 main block을 이해할 때 가장 직접적이다.

### 세 child pointer의 실행 의미

| Field | 주된 내용 | 실행 시점과 반복 단위 |
|---|---|---|
| `aptr_list` | CTE, uncorrelated subquery와 main block보다 먼저 필요한 auxiliary XASL | 일반 node는 scan open 전 실행한다. regu-linked scalar subquery는 현재 develop에서 별도 precompute loop가 scan open 전에 eager 실행한다. `TYPE_LIST_ID` regu_var로 연결된 `IN 절`, `EXISTS 절`은 expression 평가 시 lazy 실행될 수 있다. |
| `dptr_list` | 현재 XASL node가 scan한 row의 값에 의존하는 correlated subquery | 현재 scan row가 잡히고 `bptr_list`를 통과한 뒤 실행한다. 이전 correlated result list를 비우므로 row-dependent 실행이다. regu variable에 연결된 node는 expression fetch가 실행을 담당한다. |
| `scan_ptr` | 같은 join path의 다음 `SCAN_PROC` | Scan block iteration 전에 전체 chain의 scan을 열고, scan block 조합과 row 단위 NL join을 구성한다. 후행 `SCAN_PROC`는 앞쪽 row마다 현재 뒤쪽 block을 reset한다. |

`aptr_list`는 이름과 현재 대표 comment보다 실제 용도가 넓다. CTE와 uncorrelated subquery 외에도 `MERGELIST_PROC`·`HASHJOIN_PROC`의 input child와 DML을 위해 생성된 SELECT XASL 등 auxiliary child 연결에 사용된다. 따라서 “비상관 subquery만 담는 list”라고 정의하지 않고, **main block 전에 결과가 필요한 child list이며 일반 SELECT에서 대표적으로 비상관 subquery와 CTE를 담는다**고 설명한다.

`a`와 `d`가 각각 어떤 영단어의 약자인지는 현재 source comment, 2008년 공개 이력과 Git history에서 공식 근거를 찾지 못했다. `dptr`를 dependent pointer 등으로 추측할 수는 있지만 canonical 사실로 기록하지 않는다.

### Scalar `aptr` eager precompute와 남아 있는 lazy 경로

2026-07-03의 commit `978b628c8a`는 uncorrelated **scalar** subquery의 regu와 XASL 연결에 `precomp_owner_regu`를 추가했다. `qexec_execute_mainblock_internal()`은 `aptr_list`를 따라 이 marker가 있는 subquery를 scan open 전에 `fetch_peek_dbval()`로 한 번 평가한다.

```text
scalar subquery: UNBOX_AS_VALUE
  → is_single_tuple = true
  → TYPE_CONSTANT
  → precomp_owner_regu 설정
  → main block에서 scan open 전 eager precompute

IN 절, EXISTS 절: UNBOX_AS_TABLE
  → is_single_tuple = false
  → TYPE_LIST_ID
  → precomp_owner_regu = NULL
  → predicate가 값을 요구할 때 EXECUTE_REGU_VARIABLE_XASL
```

따라서 다음 두 문장은 구분해야 한다.

- “현재 develop에서 uncorrelated scalar `aptr`의 정상 실행은 eager다” — 관찰된 사실
- “모든 regu-linked `aptr`의 lazy 실행이 제거됐다” — 사실이 아니다. `IN 절`, `EXISTS 절`과 list comparison을 지원하는 `TYPE_LIST_ID` regu_var의 lazy caller가 현재도 존재한다.

첫 문장의 eager 실행도 lazy용 `fetch_peek_dbval()` 경로를 재사용한다. 그러므로 macro와 lazy code가 남아 있다는 사실 자체는 scalar 실행 시점이 여전히 lazy라는 뜻이 아니다.

### 현업 용어

사용자 경험에 따라 `list-valued subquery`라는 표현은 사용하지 않는다.

- 코드 자료구조를 말할 때: `TYPE_LIST_ID` regu_var
- SQL을 말할 때: `IN 절`, `EXISTS 절`

이는 현업 용어에 대한 사용자 경험이며 source code가 강제하는 공식 명칭이라는 뜻은 아니다.

## Main block 실행의 현업 용어

사용자 경험에 따라 main block 실행은 `pre-processing`, `scan block iteration`, `intprt_fnc (interpreter function)`, `post-processing`으로 설명한다. Source의 `Processing` comment를 독립적인 현업 단계명으로 번역하지 않는다. `scan block iteration`은 `intprt_fnc` 안에 포함되는 반복 제어다.

관계는 다음과 같다.

```text
pre-processing
  → qexec_start_mainblock_iterations()
  → intprt_fnc (interpreter function)
      └─ scan block iteration
          ├─ outer row evaluation
          └─ scan_ptr를 통한 inner scan/NL recursion
  → qexec_end_mainblock_iterations()
  → post-processing
```

### pre-processing

`intprt_fnc`를 호출하기 전에 입력과 실행 상태를 준비한다.

1. `LIMIT`을 평가해 결과가 비는지 확인한다.
2. proc type별 shortcut 또는 전용 executor 분기를 처리한다.
3. aggregate·analytic context와 lock 관련 상태를 준비한다.
4. `scan_ptr` chain의 일반 `aptr_list`를 실행하고 parallel aptr job을 기다린다.
5. `precomp_owner_regu`가 있는 scalar `aptr`를 eager precompute한다.
6. `qexec_start_mainblock_iterations()`로 result list, aggregate와 numbering 상태를 초기화한다.

### intprt_fnc (interpreter function)

`qexec_execute_mainblock_internal()`은 일반 scan path의 `func_vector[0]`에 `qexec_intprt_fnc`를 넣어 호출한다. `intprt_fnc`는 scan block의 row와 predicate를 평가해 main result를 만드는 주 interpreter function이다.

### scan block iteration

`qexec_intprt_fnc()` 안의 다음 loop를 가리킨다.

여기서 [[Scan block]]은 main XASL과 `scan_ptr`로 연결된 각 후행 `SCAN_PROC`에서 현재 선택한 access target의 전체 scan이다. 현재 `grouped_scan`은 항상 false이므로 partitioned class에서는 `spec->curent`가 가리키는 한 partition scan이 한 block이다.

```cpp
while ((xb_scan = qexec_next_scan_block_iterations (thread_p, xasl)) == S_SUCCESS)
  {
    while ((ls_scan = scan_next_scan (thread_p, &xasl->curr_spec->s_id)) == S_SUCCESS)
      {
        // dptr, predicate, scan_ptr, result tuple 처리
      }
  }
```

바깥 loop는 `scan_ptr` chain의 scan block 조합을 inner-fastest 순서로 전진시킨다. 안쪽 loop는 현재 outer block의 row와 predicate를 평가하고, 후행 `scan_ptr`가 있으면 inner block을 reset한 뒤 interpreter function을 재귀적으로 호출해 NL join을 수행한다.

두 loop는 `qualified_block`으로 연결된다. 새 block에서는 이 flag가 `false`다. 현재 XASL node에서 조건 평가를 통과한 row가 `scan_ptr`의 후행 `SCAN_PROC`를 구동하는 순간 `true`가 된다. 따라서 이 flag는 “최종 join result 존재 여부”가 아니라 “현재 XASL node의 scan block에서 후행 `SCAN_PROC`를 구동한 row가 하나 이상 있었는가”를 나타낸다.

```text
qexec_next_scan_block_iterations()             intprt_fnc
┌───────────────────────────────┐               ┌──────────────────────────┐
│ 앞쪽 block 하나 선택          │               │                          │
│ 뒤쪽 block 하나 선택          │ ────────────> │ 선택한 block의 row 평가  │
│ 예: t1p1 - t2p1              │               │ predicate / dptr / fptr  │
└───────────────▲───────────────┘               └─────────────┬────────────┘
                │                                             │
                │             qualified_block                 │
                ├──────── true: 후행 block 조합 계속 <────────┤
                └─ false: 현재 앞쪽 선택 아래의 뒤쪽 조합 생략 <─┘
```

이때 partition 전환은 바깥 `scan block iteration` 경로에 속한다.

```text
qexec_next_scan_block_iterations()
  → qexec_next_scan_block()
    → 현재 partition의 scan block 종료
      → qexec_init_next_partition()
```

`intprt_fnc`의 row loop가 partition OID/HFID를 직접 선택하는 것은 아니다. 다음 partition의 scan block을 공급받은 뒤 현재 block의 row, `dptr_list`, predicate와 후행 `scan_ptr`를 평가한다.

#### 두 partition table의 NL join

```text
t1 blocks = [t1p1, t1p2]
t2 blocks = [t2p1, t2p2]

1. 앞쪽 table에서 t1p1을 고정
   ├─ 뒤쪽 table에서 t2p1 선택 → t1p1과 t2p1을 join
   └─ 뒤쪽 table에서 t2p2 선택 → t1p1과 t2p2를 join

2. 앞쪽 table을 t1p2로 변경
   ├─ 뒤쪽 table을 t2p1부터 다시 선택 → t1p2와 t2p1을 join
   └─ 뒤쪽 table에서 t2p2 선택       → t1p2와 t2p2를 join
```

`qexec_next_scan_block_iterations()`은 앞쪽 table에서 partition scan block 하나를 고정한 뒤, 뒤쪽 table의 partition scan block을 하나씩 선택해 join할 조합을 만든다. 각 조합 안에서는 `intprt_fnc`가 앞쪽 block의 row마다 뒤쪽 block을 reset하고 row·predicate를 평가한다. 뒤쪽 partition scan block을 모두 사용하면 앞쪽 table의 다음 partition scan block을 선택하고, 뒤쪽 table은 첫 partition scan block부터 다시 시작한다.

따라서 scan block iteration은 단순히 “각 table을 한 번 scan한다”는 loop가 아니다. **앞쪽에서 partition 하나, 뒤쪽에서 partition 하나를 선택해 join할 조합을 만들고, 가능한 조합을 뒤쪽 partition부터 차례로 바꾸어 가며 평가하는 상위 반복**이다. 이 가능한 조합 전체가 수학적으로는 Cartesian product에 해당한다.

다만 실제 순회는 qualification-aware Cartesian-product iteration이다.

```text
                          t2p1
                        /
t1p1 (qualified=true) ─<
                        \
                          t2p2

                          t2p1  (이미 open됐을 수 있으나 구동되지 않음)
                        /
t1p1 (qualified=false) ─<
                        \
                          t2p2  X (전개 생략)

t1p2                  ───> t2p1 → t2p2
```

예를 들어 `t1p1`의 모든 row가 `t1` level에서 탈락하면, 초기화 과정에서 `t2p1`이 이미 선택·open됐더라도 그 row scan은 구동되지 않는다. 다음 iteration도 `t1p1-t2p2`로 전개하지 않는다. `qexec_next_scan_block_iterations()`은 `t1p1.qualified_block == false`를 보고 `t1p2`로 직접 전진한다. 반면 `t1p1`에서 한 row라도 inner scan을 구동했다면 `qualified_block == true`다. `t2`에서 최종 join row가 한 건도 나오지 않더라도 `t1p1`과 각 `t2` partition block의 조합은 평가 대상이 될 수 있다.

scan 종료 후 `qexec_end_mainblock_iterations()`가 list close, BUILDVALUE aggregate finalize, set operation 결합과 merge/hash join 결과 생성 등 main iteration을 마감한다.

### post-processing

main iteration이 만든 result list를 최종 형태로 변환한다.

1. `GROUP BY`
2. analytic function
3. `ORDER BY`와 `DISTINCT`

일부 최적화는 이 도식의 경계를 넘는다. 예를 들어 analytic function 일부는 limit 최적화를 위해 `intprt_fnc` 안에서 평가될 수 있다. 따라서 이 용어들은 모든 SQL 연산을 배타적으로 분류하는 보편 pipeline이 아니라 main block의 주 제어를 설명한다.

## 구체적인 시나리오

outer table `p_outer`와 inner table `p_inner`가 각각 여러 물리 partition을 가진 NL join이라고 하자. 현재 코드에서 XASL의 논리 scan chain은 다음처럼 유지된다.

```text
BUILDLIST_PROC: p_outer access spec
└─ scan_ptr → SCAN_PROC: p_inner access spec
```

각 `ACCESS_SPEC_TYPE`의 pruning 결과는 `parts` list에 놓인다. 실행 반복은 두 겹이다.

```text
바깥 반복: qexec_next_scan_block_iterations()
  inner scan block을 먼저 전진
  inner가 끝나면 outer scan block을 전진하고 inner를 처음 block으로 복귀

안쪽 반복: qexec_intprt_fnc() / qexec_execute_scan()
  현재 outer block의 row 하나
    → 현재 inner block을 reset
    → inner block의 row들을 NL 방식으로 대조
```

scan block을 공급하던 현재 물리 partition이 끝나면 `qexec_next_scan_block()`은 `qexec_init_next_partition()`을 호출한다. 남은 partition이 있으면 같은 access spec의 class OID/HFID/BTID와 scan을 다음 partition 기준으로 다시 열고 block 순회를 계속한다.

따라서 기본 mental model은 “optimizer가 join할 두 partition을 위한 별도 NL join node를 조합마다 미리 생성한다”가 아니다. 고정된 `scan_ptr` chain에서 executor가 앞쪽 table의 partition 하나와 뒤쪽 table의 partition 하나를 그때그때 선택해 join할 조합을 만든다. 뒤쪽 partition을 먼저 바꾸고, 뒤쪽을 모두 사용하면 앞쪽 partition을 바꾼 뒤 뒤쪽을 처음부터 다시 선택한다. SQL 의미로는 두 논리 table의 NL join이지만, 실제 제어 단위는 row뿐 아니라 그 위의 scan block 선택과 조합까지 포함한다.

## 관찰된 사실

- `aptr_list`의 현재 source comment는 CTE와 uncorrelated subquery라고 명시한다.
- `dptr_list`의 현재 source comment는 correlated subquery list라고 명시한다.
- `scan_ptr`의 현재 source comment는 `SCAN_PROC` pointer라고 명시한다.
- `qexec_execute_mainblock_internal()`은 `xasl → xasl->scan_ptr` chain을 순회하며 각 node의 `aptr_list`를 scan open 전에 실행한다.
- main scan loop에서 `dptr_list`는 현재 scan item이 qualified된 뒤 실행되며, 실행 전에 correlated subquery의 list file을 비운다.
- `XASL_LINK_TO_REGU_VARIABLE` node는 일반 `aptr_list`·`dptr_list` eager loop에서 건너뛴다.
- 현재 develop의 uncorrelated scalar `aptr`는 `precomp_owner_regu`가 설정되어 별도 precompute loop가 scan open 전에 `fetch_peek_dbval()`을 호출하므로 정상 경로에서 eager 실행된다.
- `UNBOX_AS_TABLE`인 `IN 절`, `EXISTS 절`의 node는 `TYPE_LIST_ID` regu_var가 되고 `precomp_owner_regu`가 설정되지 않는다. `query_evaluator.c`의 list comparison, `IN`/`ALL`/`SOME`, `EXISTS` 경로는 `EXECUTE_REGU_VARIABLE_XASL`로 필요 시 실행한다.
- 2008-11-24 공개 commit에도 `aptr_list`는 “first uncorrelated subquery”, `dptr_list`는 “corr. subquery list”, `scan_ptr`는 “SCAN_PROC pointer”로 존재하며 현재 main block의 세 실행 구간과 기본 scan 제어도 이미 존재한다.
- Main XASL에는 `qexec_intprt_fnc`, `scan_ptr`로 연결된 각 후행 `SCAN_PROC`에는 `qexec_execute_scan`이 배정되며 `SCAN_PROC`마다 NL join 통계가 증가한다.
- partitioned access spec은 현재 partition scan이 끝날 때 `qexec_init_next_partition()`으로 다음 partition scan을 연다.
- `qexec_next_scan_block_iterations()`은 후행 `scan_ptr`의 block을 먼저 전진시키고, 후행이 끝나면 선행 block을 전진시킨 뒤 후행 scan을 다시 시작한다.
- `qexec_intprt_fnc()`은 현재 outer block의 각 qualified row마다 현재 inner block을 `scan_reset_scan_block()`하고 후행 scan 함수를 반복 호출한다.
- `scan_start_scan()`과 `scan_next_scan_block()`은 `qualified_block = false`로 초기화한다.
- `qexec_intprt_fnc()`과 `qexec_execute_scan()`은 현재 XASL node의 row가 `scan_ptr`의 후행 `SCAN_PROC`를 구동하기 직전에 현재 `SCAN_ID::qualified_block = true`로 설정한다.
- `qexec_next_scan_block_iterations()`은 `qualified_block == false`인 현재 block이 더 뒤쪽 `SCAN_PROC`의 어떤 block과 조합되어도 기여하지 못한다고 보고, 현재 XASL node의 다음 block으로 직접 이동한다.
- 따라서 `qualified_block`은 final join output flag나 단순 physical-row-exists flag가 아니라, 현재 XASL node의 block 아래에서 후행 `SCAN_PROC` block 조합을 계속 실행할지 결정하는 flag다.

## 코드 근거

**출처:** `src/query/xasl.h:XASL_NODE`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
XASL_NODE *aptr_list; /* CTEs and uncorrelated subquery */
XASL_NODE *dptr_list; /* corr. subquery list */
XASL_NODE *scan_ptr;  /* SCAN_PROC pointer */
```

**출처:** `src/query/query_executor.c:qexec_execute_mainblock_internal`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
for (xptr = xasl; xptr; xptr = xptr->scan_ptr)
  {
    for (xptr2 = xptr->aptr_list; xptr2; xptr2 = xptr2->next)
      {
        qexec_execute_mainblock (thread_p, xptr2, xasl_state, NULL);
      }
  }
```

`XASL_LINK_TO_REGU_VARIABLE`, cache, parallel execution 등 실제 분기는 생략한 최소 excerpt다.

**출처:** `src/query/query_executor.c:qexec_intprt_fnc`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
for (xptr = xasl->dptr_list; xptr != NULL; xptr = xptr->next)
  {
    qexec_clear_head_lists_with_truncate (thread_p, xptr);
qexec_execute_mainblock (thread_p, xptr, xasl_state, NULL);
  }
```

`dptr_list` 실행은 현재 row의 값을 사용하는 `after_join_pred`와 `if_pred` 평가보다 앞에 위치한다.

**출처:** `src/query/xasl.h:EXECUTE_REGU_VARIABLE_XASL`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
if (XASL_IS_FLAGED (_x, XASL_LINK_TO_REGU_VARIABLE))
  {
    if (IS_XASL_INITIAL_STATUS ((_x)->status))
      {
        qexec_execute_mainblock (thread_p, _x, v->xasl_state, NULL);
      }
  }
```

**출처:** `src/parser/xasl_generation.c:pt_make_regu_subquery`, `src/query/query_executor.c:qexec_execute_mainblock_internal`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`
**도입 commit:** `978b628c8a948ba8c6e4b8fa034532637bc197ac`

```cpp
if (xasl->is_single_tuple)
  {
    regu->type = TYPE_CONSTANT;
    xasl->precomp_owner_regu = regu;
  }
else
  {
    regu->type = TYPE_LIST_ID;
  }
```

```cpp
if (subq->precomp_owner_regu != NULL)
  {
    fetch_peek_dbval (thread_p, subq->precomp_owner_regu, ...);
  }
```

**출처:** `src/query/query_executor.c:qexec_next_scan_block`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
SCAN_CODE s_parts = qexec_init_next_partition (thread_p, xasl->curr_spec, xasl);
if (s_parts == S_SUCCESS)
  {
    continue;
  }
```

**출처:** `src/query/query_executor.c:qexec_intprt_fnc`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
scan_reset_scan_block (thread_p, &xasl->scan_ptr->curr_spec->s_id);
while ((xs_scan = (*next_scan_fnc) (thread_p, xasl->scan_ptr,
                                    xasl_state, tplrec,
                                    next_scan_fnc + 1)) == S_SUCCESS)
  {
    qexec_end_one_iteration (thread_p, xasl, xasl_state, tplrec);
  }
```

**출처:** `src/query/query_executor.c:qexec_next_scan_block_iterations`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
if (last_xptr->curr_spec && last_xptr->curr_spec->s_id.status == S_STARTED
    && !last_xptr->curr_spec->s_id.qualified_block)
  {
    qexec_next_scan_block (thread_p, last_xptr);
  }
```

**출처:** `src/query/query_executor.c:qexec_intprt_fnc`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
/* current scan block has at least one qualified item */
xasl->curr_spec->s_id.qualified_block = true;
xasl->scan_ptr->next_scan_on = false;
scan_reset_scan_block (thread_p, &xasl->scan_ptr->curr_spec->s_id);
```

## 추론한 설계 의도

### 관찰

파티션 전환은 `XASL_NODE` join 구조가 아니라 `ACCESS_SPEC_TYPE`의 현재 scan 상태를 바꾼다.

### 설계 의도 추론

상위 query executor가 partition 유무와 무관하게 동일한 논리 scan/NL join 제어를 사용하고, partition의 물리 class 전환을 access layer 경계 안에 감추려는 구조로 보인다.

### 대안 가설

단순 추상화 목적이 아니라 pruning 결과와 lock/statistics 처리를 한 위치에 모으기 위한 구현 편의가 주된 이유일 수 있다.

### 반증 조건

일반 SELECT NL join에서 앞쪽·뒤쪽 partition 조합마다 별도 `XASL_NODE`가 생성되거나, join executor가 partition identity를 직접 조합하는 경로가 발견되면 이 추론을 수정한다.

### 신뢰도

중간

## 미확인 사항

- partition pruning으로 한쪽의 `parts`가 비거나 하나만 남을 때의 구체적 실행 예
- `TYPE_LIST_ID` regu_var로 연결된 `IN 절`, `EXISTS 절`이 실제로 `aptr_list`에 배치되는 testcase 검증
- `aptr`와 `dptr` 약어의 공식 expansion
- Outer/semi/anti NL join에서 `qualified_block`, `single_fetch`, null-padding의 상호작용

## 버전별 차이

- `978b628c8a` 이전: regu-linked uncorrelated scalar subquery는 predicate가 값을 fetch할 때 lazy 실행됐다.
- `978b628c8a` 이후 현재 develop: `precomp_owner_regu`가 있는 scalar `aptr`는 consuming scan open 전에 main thread에서 eager precompute된다. 이 commit은 현재 checkout 기준 아직 공식 release 번호를 확인하지 않았으므로 release 기반 `recent` 분류 대신 unreleased develop 변화로 기록한다.

## 관련 지식

- 선수 지식: [[CAS와 server의 SELECT 처리 경계]]
- 후속 지식: Scan manager와 access method 실행
- 관련 지식: NL join memoization
- 관련 지식: Parallel query executor
- 관련 지식: Fixed/grouped/cached scan 정책
- 관련 지식: NL join 종류별 scan block 종료
- 관련 지식: [[Scan block]]
- 토론 기록: [[2026-07-23-003 Query executor main block]]
