---
type: concept
visibility: internal
learning-status: completed
knowledge-status: partially-verified
code-era: historical
rationale-evidence: mixed
source-release: "2008 R2.1 or earlier"
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-23
---

# Scan block

`execute_mainblock` 문맥의 scan block은 main XASL과 `scan_ptr`로 연결된 각 후행 `SCAN_PROC`에서 **현재 선택한 access target의 전체 scan**이다. Partitioned class에서는 현재 partition 하나의 scan이 scan block 하나가 된다.

NL join에서는 main XASL의 앞쪽 scan block 하나를 고정하고, `scan_ptr`가 가리키는 뒤쪽 `SCAN_PROC`의 scan block을 하나씩 바꾸어 가며 join할 조합을 만든다. 뒤쪽 scan block을 모두 사용하면 앞쪽의 다음 scan block을 고르고, 뒤쪽 `SCAN_PROC`는 첫 scan block부터 다시 시작한다. 이 전개를 수학적으로 표현하면 각 XASL node가 공급하는 scan block sequence에 대한 Cartesian product다.

## 초심자를 위한 설명

혼란의 원인은 `scan_next_scan_block()`과 `qexec_next_scan_block()`이 서로 다른 계층을 담당하면서 둘 다 scan block이라는 말을 사용한다는 데 있다.

```text
scan manager
scan_next_scan_block()
  → grouped_scan == false이면 현재 SCAN_ID 전체를 한 block으로 제공

query executor
qexec_next_scan_block()
  → 현재 SCAN_ID block 종료
  → partitioned class이면 다음 partition으로 scan close/open
  → 새 partition의 SCAN_ID 전체를 다음 block으로 제공
```

현재 source의 `ACCESS_SPEC_TYPE::grouped_scan`에는 `it is never true!!!`라는 comment가 있고, XASL 복원과 parallel clone 경로도 false로 설정한다. 따라서 현재 동작을 설명할 때 grouped scan을 상정하지 않는다.

| `qexec_next_scan_block()`이 선택한 현재 target | `execute_mainblock`에서 한 scan block |
|---|---|
| Non-partitioned heap/index `ACCESS_SPEC_TYPE` | 해당 table/index scan 전체 |
| Partitioned heap/index `ACCESS_SPEC_TYPE` | `spec->curent`가 가리키는 현재 partition scan 전체 |
| List `ACCESS_SPEC_TYPE` | 해당 list scan 전체 |
| `spec->next`의 다음 access spec | 새 access spec scan 전체 |

따라서 “scan block = partition”은 일반 정의로는 좁지만, **partitioned class의 현재 active path에서는 `1 partition scan = 1 scan block`으로 대응한다**. Query executor가 partition 전환을 scan block sequence 안에 숨기기 때문이다.

## 구체적인 시나리오

`t1(p1, p2)`와 `t2(p1, p2)`를 `t1 → scan_ptr → t2`의 NL join으로 실행한다고 하자. Main XASL은 `t1`을 scan하고, `scan_ptr`가 가리키는 `SCAN_PROC`는 `t2`를 scan한다.

```text
main XASL
  t1 blocks = [t1p1 scan, t1p2 scan]
       │
       └─ scan_ptr → SCAN_PROC
                       t2 blocks = [t2p1 scan, t2p2 scan]
```

`qexec_next_scan_block_iterations()`은 먼저 앞쪽 table에서 `t1p1`을 고정한다. 그 상태에서 뒤쪽 table의 `t2p1`, `t2p2`를 차례로 골라 join할 조합을 만든다. 뒤쪽 partition을 모두 사용하면 앞쪽 table을 `t1p2`로 바꾸고, 뒤쪽 table은 다시 `t2p1`부터 고른다.

```text
1. t1p1 - t2p1
2. t1p1 - t2p2
3. t1p2 - t2p1
4. t1p2 - t2p2
```

각 조합 안에서는 `intprt_fnc`가 row와 predicate를 평가한다. 예를 들어 `t1p1-t2p1`에서는 `t1p1`의 앞쪽 row마다 `t2p1` block을 reset하고 `t2p1` row를 다시 평가한다. `t2p1` block 조합이 끝나면 뒤쪽 `SCAN_PROC`만 `t2p2`로 전진하고, 앞쪽 block인 `t1p1`을 reset한다.

`t2p2`까지 끝나면 뒤쪽 partition을 모두 사용한 것이다. 앞쪽 table은 `t1p2`를 고르고, 뒤쪽 table은 `t2p1`부터 다시 고른다. 즉 이 함수는 **앞에서 하나, 뒤에서 하나를 골라 join할 조합을 만들고, 뒤쪽을 먼저 바꾸는 반복**을 수행한다.

단, 위 4개 순서는 각 앞쪽 block에 후행 `scan_ptr`를 구동할 row가 하나 이상 있는 정상 시나리오다. 실제 iterator는 `qualified_block`을 이용해 현재 앞쪽 partition과 뒤쪽 partition들을 더 조합해 볼 필요가 없을 때 그 나머지를 건너뛴다.

## `qualified_block`: 현재 scan block의 상태

`qualified_block`은 “현재 block에서 최종 join result가 나왔다”는 flag가 아니다. **현재 XASL node의 scan block에서 조건 평가를 통과하여, `scan_ptr`가 가리키는 후행 `SCAN_PROC`를 구동한 row가 하나라도 있었는지**를 나타내는 flag다.

### 한눈에 보는 전체 구조

```text
scan_ptr chain

  main XASL                               scan_ptr가 가리키는 SCAN_PROC
  t1: [t1p1] [t1p2]   ─── scan_ptr ───>  t2: [t2p1] [t2p2]
      partition scans                           partition scans


scan block iteration                     intprt_fnc / qexec_execute_scan

  "어떤 partition scan끼리 볼까?"          "선택된 block 안에서 어떤 row가 통과할까?"

  qexec_next_scan_block_iterations()       scan_next_scan()
                │                                  │
                │ 선택한 block 조합                ├─ bptr_list 평가
                └─────────────────────────────────>├─ dptr_list 실행
                                                   ├─ after_join_pred 평가
                                                   ├─ if_pred 평가
                                                   └─ fptr_list 평가
                                                            │
                                 후행 SCAN_PROC를 구동하는 row?│
                              ┌───────────────────────────────┴────────────────┐
                              │ YES                                            │ NO
                              v                                                v
                    qualified_block = true                           false 그대로 유지
                              │                                                │
                              v                                                v
                  inner block 조합을 계속 평가                    suffix block 조합 가지치기
```

즉 scan block iteration과 row 평가는 별개 loop이지만 독립적이지 않다. `intprt_fnc`/`qexec_execute_scan`이 row를 평가한 결과를 `qualified_block`에 남기고, 다음 `qexec_next_scan_block_iterations()`이 그 값을 읽어 Cartesian product를 계속 펼칠지 가지치기할지 결정한다.

```text
새 scan block 선택
  → qualified_block = false

현재 XASL node의 row 평가
  ├─ 후행 scan_ptr를 구동할 row가 하나 이상 있음
  │    → qualified_block = true
  │    → 현재 block과 더 깊은 block들의 조합을 계속 평가
  └─ 그런 row가 하나도 없음
       → qualified_block = false 유지
       → 현재 block을 prefix로 하는 더 깊은 block 조합을 모두 생략
       → 현재 XASL node의 다음 block으로 직접 전진
```

`true`는 후행 scan에서 최종 join row가 생성됐다는 뜻도 아니다. 앞쪽 XASL node의 row가 조건 평가를 통과해 후행 `SCAN_PROC`를 호출하면 앞쪽 block은 `true`가 된다. 그 뒤 모든 뒤쪽 partition에서 join 결과가 0건이어도 앞쪽 block의 `qualified_block`은 이미 `true`다.

반대로 물리 scan이 row를 읽었다는 사실만으로는 `true`가 되지 않는다. 현재 XASL node의 평가를 통과해 후행 `SCAN_PROC`를 구동할 지점까지 도달해야 한다. `scan_ptr == NULL`인 마지막 `SCAN_PROC`에는 더 뒤에 조합할 scan이 없으므로, 이 flag를 “각 scan의 결과 존재 여부”로 일반화하면 안 된다.

### Partition NL join에서의 가지치기

`t1p1`의 모든 row가 main XASL의 조건에서 탈락했다고 하자.

```text
모든 outer block이 qualified인 경우

  t1p1 ─┬─ t2p1   평가
        └─ t2p2   평가
  t1p2 ─┬─ t2p1   평가
        └─ t2p2   평가

  실제 순서: (t1p1,t2p1) → (t1p1,t2p2)
                         → (t1p2,t2p1) → (t1p2,t2p2)


t1p1.qualified_block == false인 경우

  t1p1 ─┬─ t2p1   첫 block은 이미 open됐을 수 있지만 row scan을 구동하지 않음
        └─ t2p2   X  이 조합으로 전개하지 않음
          └────────────── prefix t1p1 아래의 suffix product를 가지치기

  t1p2 ─┬─ t2p1   평가
        └─ t2p2   평가

  실질 평가 순서: (t1p2,t2p1) → (t1p2,t2p2)
```

초기화 과정에서 첫 후행 block인 `t2p1`은 이미 선택·open됐을 수 있다. 그러나 `t1p1`의 row가 뒤쪽 `SCAN_PROC`를 한 번도 구동하지 않으며, 다음 iteration은 `t2p2`로 전개하지 않고 main XASL의 다음 block인 `t1p2`로 직접 전진한다. Main XASL의 block sequence까지 끝났으면 후행 active scan들을 닫는다.

이를 전진 규칙만 떼어 보면 다음과 같다.

```text
현재 XASL node의 block 평가 종료
              │
              v
      qualified_block ?
          /         \
       true         false
        │             │
        v             v
 후행 SCAN_PROC의  현재 XASL node의
 다음 block으로    다음 block으로
 (inner-fastest)   (suffix skip)
        │             │
        └──────┬──────┘
               v
       해당 scan이 S_END이면
       앞쪽 XASL node로 carry
```

따라서 더 정확한 정의는 다음과 같다.

> Scan block iteration은 main XASL과 `scan_ptr`로 연결된 후행 `SCAN_PROC`들이 공급하는 scan block 조합을 뒤쪽부터 바꾸어 가며 순회한다. 현재 XASL node의 `qualified_block == false`이면, 그 node의 현재 block과 더 뒤쪽 `SCAN_PROC` block들을 조합하는 나머지 실행을 건너뛴다.

## 관찰된 사실

- `ACCESS_SPEC_TYPE::grouped_scan`의 현재 comment는 `it is never true!!!`라고 명시한다.
- XASL 복원은 `grouped_scan = false`로 설정한다.
- `scan_reset_scan_block()`은 non-grouped heap/index/list scan을 scan 시작 위치로 되감는다.
- Non-grouped heap/index/list 계열의 `scan_next_scan_block()`은 `position == S_BEFORE`일 때 한 번 `S_SUCCESS`를 반환하고 scan이 끝난 뒤 `S_END`를 반환한다. 따라서 현재 open된 scan 전체가 하나의 block이다.
- Query executor의 `qexec_next_scan_block()`은 현재 scan에서 `S_END`를 받은 뒤 `qexec_init_next_partition()`을 호출하고, 다음 partition scan을 다음 block으로 반환한다.
- `qexec_next_scan_block_iterations()`은 후행 `SCAN_PROC`의 block을 먼저 전진시키고, 끝나면 앞쪽 XASL node의 block을 전진시킨 뒤 후행 `SCAN_PROC`를 첫 block부터 다시 시작한다.
- 따라서 partitioned table 두 개의 NL join은 정상 시나리오에서 partition scan block의 Cartesian product를 inner-fastest 순서로 평가한다.
- 새 scan block을 시작할 때 `qualified_block`은 `false`로 초기화된다.
- 현재 XASL node에서 평가를 통과한 row가 `scan_ptr`의 후행 `SCAN_PROC`를 구동할 때 `qualified_block`이 `true`가 된다.
- `qexec_next_scan_block_iterations()`은 `qualified_block == false`인 현재 XASL node의 block과 더 뒤쪽 `SCAN_PROC` block들의 조합을 더 실행하지 않고, 현재 XASL node의 다음 block으로 직접 전진한다.
- `SCAN_ID::qualified_block`의 “initially set to true” comment는 현재 구현의 `false` 초기화와 일치하지 않는다.

## 코드 근거

**출처:** `src/query/xasl.h:ACCESS_SPEC_TYPE`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
bool grouped_scan; /* grouped or regular scan? it is never true!!! */
```

**출처:** `src/query/scan_manager.c:scan_next_scan_block`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
if (!s_id->grouped)
  {
    return (s_id->position == S_BEFORE) ? S_SUCCESS : S_END;
  }
```

**출처:** `src/query/scan_manager.c:scan_reset_scan_block`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
case S_HEAP_SCAN:
  s_id->position = S_BEFORE;
  break;

case S_INDX_SCAN:
  s_id->position = S_BEFORE;
  BTREE_RESET_SCAN (&s_id->s.isid.bt_scan);
  break;
```

**출처:** `src/query/query_executor.c:qexec_next_scan_block`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
sb_scan = scan_next_scan_block (thread_p, &xasl->curr_spec->s_id);
if (sb_scan == S_END)
  {
    SCAN_CODE s_parts =
      qexec_init_next_partition (thread_p, xasl->curr_spec, xasl);
    if (s_parts == S_SUCCESS)
      {
        continue;
      }
  }
```

**출처:** `src/query/query_executor.c:qexec_next_scan_block_iterations`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
if (last_xptr->curr_spec == NULL)
  {
    qexec_next_scan_block (thread_p, prev_xptr);
    qexec_next_scan_block (thread_p, prev_xptr->scan_ptr);
  }
else
  {
    scan_reset_scan_block (thread_p, &prev_xptr->curr_spec->s_id);
  }
```

**출처:** `src/query/scan_manager.c:scan_next_scan_block`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
s_id->single_fetched = false;
s_id->null_fetched = false;
s_id->qualified_block = false;
```

**출처:** `src/query/query_executor.c:qexec_intprt_fnc`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
/* current scan block has at least one qualified item */
xasl->curr_spec->s_id.qualified_block = true;

/* handle the scan procedure */
xasl->scan_ptr->next_scan_on = false;
scan_reset_scan_block (thread_p, &xasl->scan_ptr->curr_spec->s_id);
```

**출처:** `src/query/query_executor.c:qexec_next_scan_block_iterations`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
/* if there are no qualified items in the current scan block, this scan block will make no contribution with other
 * possible scan block combinations from following classes. Thus, directly move to the next scan block in this class. */
if (last_xptr->curr_spec && last_xptr->curr_spec->s_id.status == S_STARTED
    && !last_xptr->curr_spec->s_id.qualified_block)
  {
    xs_scan = qexec_next_scan_block (thread_p, last_xptr);
  }
```

## 추론한 설계 의도

### 관찰

NL join은 inner scan의 현재 block을 `scan_reset_scan_block()`으로 outer row마다 반복한다. 현재 active path에서 block은 open된 scan 전체다.

### 설계 의도 추론

Partition, access spec과 scan-manager 내부 scan이라는 서로 다른 target을 모두 “다음 block” protocol로 평탄화하고, main XASL과 여러 후행 `SCAN_PROC`의 block 조합을 공통 제어하려는 추상화로 보인다. `qualified_block`은 이 공통 iterator가 row 평가 결과를 받아 불필요한 후행 `SCAN_PROC` block 조합을 제거하는 feedback flag로 보인다.

### 대안 가설

Partition 조합 자체가 주목적이고 여러 scan type을 함께 다루는 것은 부수 효과일 수 있다.

### 반증 조건

Active path에서 `grouped_scan`이 true가 되는 경로가 발견되거나, partition scan block 조합과 다른 정상 NL partition 순회 경로가 발견되면 설명을 수정한다.

### 신뢰도

중간

## 미확인 사항

- Parallel scan 내부 worker range와 executor 관점의 단일 scan block 관계
- `grouped_scan` code가 유지되는 역사적 이유와 제거 가능성
- Outer/semi/anti NL join에서 `qualified_block`, `single_fetch`, null-padding이 함께 만드는 조기 종료 규칙

## 관련 지식

- 선수 지식: [[CAS와 server의 SELECT 처리 경계]]
- 후속 지식: Scan manager와 access method 실행
- 관련 지식: [[Query executor의 main block 실행]]
- 토론 기록: [[2026-07-23-003 Query executor main block]]
