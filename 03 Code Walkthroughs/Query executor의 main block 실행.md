---
type: code-walkthrough
aliases: [execute_mainblock, qexec_execute_mainblock, query executor, NL join, scan, aptr_list, dptr_list, qexec_end_one_iteration, end-one-iteration]
visibility: internal
learning-status: completed
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
   │     └─ row·predicate 평가
   │        └─ end-one-iteration: qualified candidate row의 결과 처리
   ├─ main iteration 종료
   └─ post-processing
      ├─ GROUP BY
      ├─ analytic function
      └─ ORDER BY / DISTINCT
```

이 구분은 모든 statement type에 똑같이 적용되는 별도 subsystem이 아니다. `UPDATE_PROC`, `DELETE_PROC`, `INSERT_PROC` 등은 type switch에서 전용 executor로 빠지고, 위 흐름은 `BUILDLIST_PROC`, `BUILDVALUE_PROC` 같은 SELECT 계열 main block을 이해할 때 가장 직접적이다.

이 단계 모델의 canonical 적용 범위는 `qexec_execute_mainblock_internal()`의 일반 SELECT 계열 경로다. `CONNECT BY`와 `BUILD_SCHEMA_PROC`의 전용 executor도 `qexec_end_one_iteration()` 또는 `qexec_end_mainblock_iterations()` 같은 helper를 재사용하지만 자체 반복과 후속 처리 흐름을 가진다. 공통 helper 호출만을 근거로 전용 executor를 위 단계 모델에 억지로 맞추지 않는다.

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

`scan block iteration`은 `intprt_fnc` 내부의 반복으로 한정한다. `qexec_end_mainblock_iterations()`는 그 반복의 일부나 단순 scan cleanup이 아니라, `intprt_fnc` 뒤에서 proc type별 결과를 확정하는 독립적인 **`main iteration 종료`** 단계다. Source의 `Post_processing`은 이 함수가 성공한 다음 시작한다.

이름이 비슷한 두 종료 단위는 다음처럼 구분한다.

| 현업 용어 | 실제 symbol | 실행 단위 | 호출 시점 |
|---|---|---|---|
| `end-one-iteration` | `qexec_end_one_iteration()` | qualified candidate row 한 건 | row의 predicate 평가가 끝난 뒤 결과 tuple을 처리할 때 |
| `main iteration 종료` | `qexec_end_mainblock_iterations()` | main procedure block 전체 | `intprt_fnc`와 scan close가 끝난 뒤 proc별 결과를 확정할 때 |

두 이름을 바꾸어 쓰지 않는다. 특히 `end-one-iteration`의 `iteration`은 row 한 건의 처리 단위이고, `main iteration 종료`의 `iteration`은 main procedure block의 전체 실행 반복을 가리킨다.

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

#### end-one-iteration

현업에서는 `qexec_end_one_iteration()`을 **`end-one-iteration`**이라는 이름으로 직접 부른다. 이는 전체 scan block iteration이나 main procedure block의 종료가 아니라, `intprt_fnc`에서 **한 candidate row의 predicate 평가가 끝나고 qualified된 뒤 결과 row 하나를 처리하는 함수**다.

주요 순서는 다음과 같다.

```text
candidate row scan
  → dptr / after_join_pred / if_pred / fptr 평가
  → qualified
  → inst_num predicate 평가
  → end-one-iteration
      ├─ 최적화된 analytic function의 row별 평가
      ├─ tuple descriptor 생성
      ├─ Top-N 또는 hash GROUP BY 처리
      └─ result list에 tuple 생성·추가
```

Source 주석도 이를 `Processing to be accomplished when a candidate row has been qualified`라고 정의한다. 특히 analytic 최적화 flag가 있으면 `qexec_analytic_eval_in_processing()`이 tuple descriptor 생성과 result list 삽입보다 먼저 호출된다.

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

`intprt_fnc`가 끝난 뒤 `qexec_end_mainblock_iterations()`가 list close, BUILDVALUE aggregate finalize, set operation 결합과 merge/hash join 결과 생성 등 main iteration 결과를 확정한다. 이 호출은 `scan block iteration`에 포함하지 않고 `main iteration 종료`라는 독립 단계로 구분한다.

### post-processing

`post-processing`은 `qexec_end_mainblock_iterations()`가 성공한 뒤 source의 `Post_processing` comment부터 시작하는 **main block의 제어 구간**이다. 모든 후처리 계산이 오직 이 위치에서만 수행된다는 뜻은 아니다.

1. `GROUP BY`
2. analytic function
3. `ORDER BY`와 `DISTINCT`

여기서는 다음 두 관점을 분리한다.

- **논리적 소속:** main iteration이 만든 row 집합 전체를 기준으로 GROUP BY, analytic, 정렬, 중복 제거 같은 최종 결과 변환을 수행하므로 후처리 연산이다.
- **실제 계산 위치:** 최적화가 없으면 post-processing 제어 구간에서 계산하지만, 입력 순서나 LIMIT 조건을 이용할 수 있으면 row 단위 `end-one-iteration`에서 상태 누적이나 결과 계산을 미리 수행할 수 있다.

즉, 최적화가 실행 위치를 앞당겨도 해당 연산의 논리적 의미가 scan predicate나 NL join으로 바뀌지는 않는다. 반대로 source의 `Post_processing` 구간에 함수 호출이 남아 있다는 사실만으로 모든 계산이 그 시점에 처음 시작된다고 볼 수도 없다.

Analytic function은 이 차이를 보여 주는 대표 사례다.

- 기본 경로: post-processing의 `qexec_execute_analytic()`에서 입력 list를 scan·sort하고 analytic 결과 list를 만든다.
- `XASL_ANALYTIC_SKIP_SORT`: 입력이 analytic sort 순서를 이미 만족하므로, `end-one-iteration`의 `qexec_analytic_eval_in_processing()`에서 row별 상태를 누적한다. Post-processing의 `qexec_execute_analytic()`은 누적 상태와 기존 list를 이용해 group 결과를 확정한다.
- `XASL_ANALYTIC_USES_LIMIT_OPT`: `ROW_NUMBER`, `RANK`, `DENSE_RANK`와 제한된 `FIRST_VALUE`처럼 허용된 function을 `end-one-iteration`에서 평가한다. Post-processing에서도 `qexec_execute_analytic()` 호출 자체는 남지만 limit optimization flag를 보고 실질적인 analytic list 처리 없이 wrapup으로 이동한다.

| 경로 | `end-one-iteration` | `main iteration 종료` 뒤의 post-processing |
|---|---|---|
| 기본 analytic | 결과 row를 list에 기록 | list를 scan·sort하며 analytic 값을 계산하고 결과 list로 교체 |
| analytic skip-sort | 입력 순서를 따라 analytic 상태를 row마다 누적 | 남은 group을 확정하고 누적 결과를 기존 list에 반영 |
| analytic limit optimization | 허용된 analytic function을 row마다 평가하며 필요한 row까지만 읽을 수 있게 함 | analytic executor 호출은 남지만 실질적인 list scan·sort를 건너뜀 |

구체적으로 `ROW_NUMBER() OVER (ORDER BY c1)`을 생각할 수 있다.

1. 적합한 index 순서를 활용하지 않는 기본 경로에서는 `end-one-iteration`이 candidate row를 result list에 쌓는다.
2. `main iteration 종료`가 list를 닫아 main result를 확정한다.
3. Post-processing의 analytic executor가 list를 정렬·scan해 `ROW_NUMBER` 결과를 만든다.

반대로 optimizer가 index 순서가 analytic sort 순서를 만족한다고 판단하면 `XASL_ANALYTIC_SKIP_SORT`가 설정될 수 있다. 이때는 각 qualified candidate row가 `end-one-iteration`에 들어올 때 analytic 상태를 누적하므로 별도 analytic sort가 필요 없다. LIMIT 최적화까지 가능하면 `ROW_NUMBER`, `RANK`, `DENSE_RANK`와 조건을 만족하는 `FIRST_VALUE`는 필요한 row 범위까지만 읽도록 `end-one-iteration`에서 평가할 수 있다.

```cpp
/* qexec_end_one_iteration(): qualified candidate row의 결과 처리 */
if (XASL_IS_FLAGED (xasl, XASL_ANALYTIC_USES_LIMIT_OPT)
    || XASL_IS_FLAGED (xasl, XASL_ANALYTIC_SKIP_SORT))
  {
    qexec_analytic_eval_in_processing (thread_p, xasl, xasl_state);
  }

/* 그 다음 tuple descriptor 생성과 result list 처리가 이어진다. */
```

따라서 “analytic function은 항상 post-processing에서 실행된다”라고 설명하지 않는다. **논리적으로는 후처리 연산이지만, 최적화에 따라 실제 analytic 평가는 row 단위 `end-one-iteration`에서 처리될 수 있다.** 이 단계 용어들은 모든 SQL 연산을 배타적인 물리 실행 위치에 가두는 pipeline이 아니라 main block의 주 제어와 일반 책임을 설명한다.

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
- `qexec_end_one_iteration()`은 qualified candidate row 하나에 대해 analytic 최적화 평가, tuple descriptor 생성, Top-N·hash GROUP BY와 result list tuple 처리를 수행한다.
- `XASL_ANALYTIC_USES_LIMIT_OPT` 또는 `XASL_ANALYTIC_SKIP_SORT`가 설정되면 `qexec_end_one_iteration()` 안에서 `qexec_analytic_eval_in_processing()`이 호출된다.
- Post-processing의 `qexec_execute_analytic()`은 limit optimization 경로에서는 analytic state 초기화 뒤 실질적인 list 처리 없이 wrapup하고, skip-sort 경로에서는 processing 중 누적한 상태를 사용해 결과를 확정한다.
- `qexec_execute_connect_by()`, `qexec_execute_build_indexes()`, `qexec_execute_build_columns()`도 공통 iteration 종료 helper를 호출하지만 일반 SELECT 계열의 공통 `Post_processing` 제어 구간과 다른 전용 흐름을 사용한다.

## 코드 근거

**출처:** `src/query/xasl.h:XASL_NODE`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
/* end main block iterations */
if (qexec_end_mainblock_iterations (thread_p, xasl, xasl_state, &tplrec) != NO_ERROR)
  {
    ...
  }

/*
 * Post_processing
 */
```

이 순서와 `qexec_end_mainblock_iterations()`의 proc type별 switch를 근거로 `main iteration 종료`와 `post-processing`을 구분한다.

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
- Analytic evaluation을 `qexec_end_one_iteration()`으로 앞당기는 기반은 commit `a2a897eb29106c57abdd7b4f18cb35afd5adce32`(2026-01-08)에 추가됐다.
- Analytic skip-sort는 commit `1cdd023033bf7284b16242f790ad6e4e373a1918`(2026-03-11), limit optimization은 commit `f868d03d5cf94ea6b6f48a9d463d5ceb11050076`(2026-04-01)에 추가됐다.
- 두 최적화 commit은 repository tag `v11.4.5.1898`에 포함되지만, 이 tag를 공식 release tag `v11.4.5`와 동일시하지 않는다. 현재 확인한 공식 release에는 포함 여부를 확정할 수 없으므로 analytic 최적화 세부 동작은 release 기반 `recent`로 분류하지 않고 **unreleased develop 변화**로 기록한다. Main block의 기본 실행 구조 자체는 historical이다.

## 관련 지식

- 선수 지식: [[CAS와 server의 SELECT 처리 경계]]
- 후속 지식: Scan manager와 access method 실행
- 관련 지식: NL join memoization
- 관련 지식: Parallel query executor
- 관련 지식: Fixed/grouped/cached scan 정책
- 관련 지식: NL join 종류별 scan block 종료
- 관련 지식: [[Scan block]]
- 토론 기록: [[2026-07-23-003 Query executor main block]]
- 토론 기록: [[2026-07-23-006 Main iteration 종료와 post-processing 경계]]
