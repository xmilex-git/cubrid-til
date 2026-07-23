---
type: concept
aliases: [buffer manager, page buffer, page fix, page pin, pgbuf_fix, pgbuf_unfix, BCB, PGBUF_BCB, page latch, PGBUF_LATCH_READ, PGBUF_LATCH_WRITE]
visibility: internal
learning-status: completed
knowledge-status: partially-verified
code-era: historical
rationale-evidence: mixed
source-release: "10.0 or earlier"
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-23
---

# Page fix와 page latch

`page fix`는 특정 database page를 buffer pool에서 접근 가능한 상태로 빌리고, 사용 중 교체되지 않게 참조를 유지하며, 요청한 READ/WRITE page latch를 함께 얻는 CUBRID의 page 접근 계약이다. `unfix`까지의 수명을 이해해야 page pointer의 유효 범위와 동시 접근 대기를 올바르게 판단할 수 있다.

## 초심자를 위한 설명

초기 mental model은 `pgbuf_fix()`가 page를 “메모리에 올려 두기만 하는 pin”이 아니라 다음 결과를 한 번에 제공한다고 보는 것이다.

1. `VPID`에 해당하는 page의 buffer frame과 `PGBUF_BCB`를 찾거나 확보한다.
2. 요청한 `PGBUF_LATCH_READ` 또는 `PGBUF_LATCH_WRITE`를 얻는다.
3. BCB의 **bcb fix count**를 올리고, 현재 thread의 holder에도 **thread-holder fix count**로 이 thread가 보유한 fix reference를 기록한다.
4. latch로 보호된 page memory를 가리키는 `PAGE_PTR`을 반환한다.

호출자는 사용이 끝나면 같은 횟수만큼 `pgbuf_unfix()`해야 한다. page latch는 메모리 안 page의 물리적 일관성을 짧게 보호하는 장치이며 transaction lock과 같은 논리적 데이터 잠금이 아니다.

## 구체적인 시나리오

Thread A와 B가 같은 page를 READ fix하면 latch mode는 `READ`, bcb fix count는 2이고 각 thread-holder fix count는 1이다. Thread C가 WRITE fix를 요청하면 waiter queue에서 기다린다.

1. A가 unfix하면 bcb fix count는 `2→1`이지만 READ latch는 유지된다.
2. B가 마지막 unfix하면 `1→0`과 함께 latch가 `PGBUF_NO_LATCH`로 바뀐다.
3. 이 경계에서 waiter wake-up이 실행되고 C가 WRITE latch를 얻는다.

현재 atomic fast path에서는 waiter가 없는 1번의 `2→1`은 BCB mutex 없이 처리할 수 있지만, latch mode 변경과 waiter wake-up이 필요한 2번의 `1→0`은 BCB mutex 경로로 간다.

## 관찰된 사실

- public latch mode는 `READ`, `WRITE`, `FLUSH`가 있지만 `pgbuf_fix()` 호출자는 `READ` 또는 `WRITE`만 요청할 수 있다. `FLUSH`는 내부 block mode다.
- `PGBUF_BCB::atomic_latch` 하나에 `latch_mode`, `waiter_exists`, 한 page에 걸린 fix reference의 합계인 **bcb fix count** `fcnt`가 함께 저장된다. 정상 READ/WRITE fix 경로에서는 동일 thread와 다른 thread의 fix가 모두 이 값에 합산된다.
- 별도로 thread-owned `PGBUF_HOLDER::fix_count`는 **thread-holder fix count**로서, 해당 thread가 같은 BCB에 보유한 fix reference 수를 추적한다. 정확히는 thread와 page의 조합마다 존재하는 값이다.
- 마지막 fix가 unfix되어 전체 `fcnt`가 0이 되면 latch mode는 `PGBUF_NO_LATCH`로 바뀌고 대기 thread를 깨우는 경로로 간다.

### Atomic-latch READ fast path

현재 코드는 다음 중간 상태 전이를 `atomic_latch` CAS로 처리하며 BCB mutex를 잡지 않는다.

| 동작 | 필요 조건 | 상태 전이 |
|---|---|---|
| READ fix | 대상 BCB가 resident, latch가 `READ`, waiter 없음, bcb fix count `n≥1`, 허용된 fetch mode와 unconditional request | `n→n+1` |
| READ unfix | latch가 `READ`, waiter 없음, bcb fix count `n≥2` | `n→n-1` |

READ fix fast path는 `pgbuf_search_hash_chain_no_bcb_lock()`도 사용하므로 BCB mutex뿐 아니라 hash anchor mutex도 잡지 않는다. CAS 성공 전후에 latch tuple과 VPID 조건을 검사하며, fix count가 0인 BCB는 이 경로에 들어오지 않는다.

thread-holder fix count의 증감은 현재 thread가 소유한 holder list에서 처리한다. unfix는 먼저 thread-holder fix count를 감소시킨 뒤 `pgbuf_lockfree_unfix_ro()`로 bcb fix count의 atomic 감소를 시도한다.

### BCB mutex가 관여하는 slow path

다음은 atomic-only fast path에서 제외되어 BCB mutex 경로가 관여한다.

- 최초 READ holder가 되는 `0→1`: `NO_LATCH→READ` mode 전환과 BCB 상태 확인이 필요하다.
- 마지막 READ holder가 나가는 `1→0`: `READ→NO_LATCH`, waiter wake-up과 LRU 처리가 필요하다.
- WRITE latch 획득·해제와 READ/WRITE 충돌.
- `waiter_exists`가 설정된 상태: queue 및 grant 순서를 BCB mutex 아래에서 조정한다.
- conditional request, page miss, BCB claim/적재, fast path가 허용하지 않는 fetch mode.

slow path에서도 `atomic_latch` tuple의 실제 변경은 CAS로 수행되지만, queue·latch 경계·BCB 부가 상태를 함께 조정하기 위해 BCB mutex를 보유한다.

### Conditional과 unconditional latch

`PGBUF_LATCH_CONDITION`은 충돌 시 기다릴지를 정한다.

- `PGBUF_CONDITIONAL_LATCH`: latch를 즉시 grant할 수 없으면 waiter queue에서 기다리지 않고 실패한다.
- `PGBUF_UNCONDITIONAL_LATCH`: 즉시 grant할 수 없으면 `pgbuf_block_bcb()`를 통해 waiter queue와 timed sleep 경로로 간다.

예외로 transaction의 현재 wait 시간이 `LK_ZERO_WAIT` 또는 `LK_FORCE_ZERO_WAIT`이면, 호출자가 unconditional을 요청했더라도 `pgbuf_fix()`가 이를 conditional로 바꾼다.

```cpp
if (wait_msecs == LK_ZERO_WAIT || wait_msecs == LK_FORCE_ZERO_WAIT)
  {
    condition = PGBUF_CONDITIONAL_LATCH;
  }
```

`LK_ZERO_WAIT`은 값 0이며 “즉시 timeout하고 기다리지 않음”을 뜻한다. `pgbuf_find_current_wait_msecs()`는 현재 transaction의 `LOG_TDES::wait_msecs`를 반환하므로, 여기서 zero-wait은 page buffer 전용 설정이 아니라 현재 transaction이 충돌 대기를 하지 않도록 가진 wait 정책이다.

### 같은 thread의 중첩 READ fix

같은 thread가 이미 READ fix한 page를 다시 READ fix할 수 있다. 이때 새 BCB나 새 thread-holder를 만들지 않고 두 count를 각각 증가시킨다.

- bcb fix count: page 전체의 fix reference가 하나 늘어난다.
- thread-holder fix count: 현재 thread가 이 BCB에 가진 fix reference가 하나 늘어난다.

```cpp
if (holder != NULL)
  {
    holder->fix_count++;
    holder->perf_stat.hold_has_read_latch = 1;
  }
```

각 `pgbuf_fix()`에는 matching `pgbuf_unfix()`가 필요하다. 첫 unfix는 두 count를 하나씩 줄일 뿐 holder와 READ latch를 유지하고, 해당 thread의 마지막 unfix에서 thread-holder가 제거된다. BCB 전체의 마지막 unfix일 때만 bcb fix count가 0이 되면서 latch가 `PGBUF_NO_LATCH`로 전환된다.

### READ에서 WRITE로 promotion

이미 READ fix한 page를 변경해야 할 때 `pgbuf_promote_read_latch()`로 WRITE latch 승격을 시도할 수 있다.

- 현재 thread가 유일한 holder이면 BCB mutex 아래에서 latch mode만 `READ→WRITE`로 바꾸는 in-place promotion을 한다. bcb fix count와 thread-holder fix count는 유지된다.
- 다른 holder가 있고 `PGBUF_PROMOTE_ONLY_READER`이면 기다리지 않고 `ER_PAGE_LATCH_PROMOTE_FAIL`을 반환한다.
- 다른 holder가 있고 `PGBUF_PROMOTE_SHARED_READER`이면 현재 thread의 fix를 bcb fix count에서 잠시 빼고 thread-holder를 제거한 뒤, queue의 첫 promoter로 WRITE latch를 기다린다. 성공하면 기존 thread-holder fix count를 복원한다.
- 이미 다른 promoter가 queue 앞에 있으면 promotion은 실패한다.

실제 source에는 file 자동 확장과 B-tree split·merge에서 이 API를 호출하는 12개 직접 호출식이 있다. 상세 선행 READ fix, trigger, 실패 처리와 WRITE 후 mutation은 [[Page latch promotion 호출 경로]]에서 설명한다.

### WRITE latch, dirty mark와 unfix

WRITE latch는 page memory를 배타적으로 변경할 권한이다. WRITE fix 또는 READ→WRITE promotion 자체가 BCB를 dirty로 만들지는 않는다.

caller가 실제 page 내용을 변경했다면 `pgbuf_set_dirty()`를 명시적으로 호출해야 한다.

```cpp
pgbuf_set_dirty_buffer_ptr (thread_p, bufptr);

if (free_page == FREE)
  {
    pgbuf_unfix (thread_p, pgptr);
  }
```

`pgbuf_set_dirty_buffer_ptr()`는 현재 latch가 WRITE이고 current thread-holder가 존재한다고 assert한 뒤 BCB dirty flag와 holder의 `dirtied_by_holder` 통계를 갱신한다.

따라서 세 책임을 구분한다.

1. WRITE latch: 다른 thread와 충돌 없이 page를 변경할 권한
2. dirty mark: memory page가 disk image보다 새로워 flush가 필요하다는 기록
3. unfix: 현재 thread가 빌린 page reference와 latch ownership을 반납

`pgbuf_set_dirty(..., FREE)`와 `pgbuf_set_dirty_and_free()`는 dirty mark 뒤 unfix까지 결합한 편의 경로지만, 개념적 책임은 여전히 둘이다.

### Waiter barrier와 queue grant

`waiter_exists`가 true이면 신규 reader는 atomic-latch READ fast path에서 거절되고 BCB mutex slow path로 간다. slow path에서도 현재 thread가 이 BCB의 기존 holder가 아니면 queue에서 기다린다. 기존 holder의 중첩 READ fix는 허용되는데, 보유 중인 작업이 자기 자신이 기다리며 멈추는 상황을 피하는 동작으로 볼 수 있다.

이 규칙을 **waiter barrier**라고 부른다. 다만 다음 wake-up 규칙 때문에 strict FIFO나 일반적인 writer fairness 보장과 같지는 않다.

- page가 idle이고 첫 grant가 WRITE이면 WRITE latch를 설정한 뒤 뒤의 waiter grant를 멈춘다.
- READ가 먼저 grant되어 latch가 READ가 되면 queue에서 다른 READ waiter를 더 찾아 함께 grant할 수 있다.
- 이 탐색은 중간의 WRITE waiter를 남겨둔 채 뒤쪽 READ를 grant할 수도 있다.

따라서 관찰 가능한 보장은 “waiter가 생기면 신규 reader가 active READ latch에 atomic CAS로 즉시 합류하지 않는다”까지다. writer starvation을 완전히 방지한다는 주장은 별도 workload와 queue 진행성 검증이 필요하다.

#### 코드로 증명하는 `READ₁ → WRITE → READ₂`

일반 latch waiter는 `pgbuf_block_bcb()`에서 queue tail에 append된다. 따라서 WRITE latch가 잡힌 동안 READ₁, WRITE, READ₂ 순으로 요청하면 이 배열이 만들어질 수 있다.

```cpp
/* append cur_thrd_entry to the BCB waiting queue */
cur_thrd_entry->next_wait_thrd = NULL;
thrd_entry = bufptr->next_wait_thrd;
if (thrd_entry == NULL)
  {
    bufptr->next_wait_thrd = cur_thrd_entry;
  }
else
  {
    while (thrd_entry->next_wait_thrd != NULL)
      {
        thrd_entry = thrd_entry->next_wait_thrd;
      }
    thrd_entry->next_wait_thrd = cur_thrd_entry;
  }
```

WRITE holder의 마지막 unfix 뒤 `pgbuf_wakeup_reader_writer()`는 `NO_LATCH`, bcb fix count 0에서 시작한다. 다음 두 분기가 핵심이다.

```cpp
if (impl.impl.latch_mode == PGBUF_NO_LATCH
    || (impl.impl.latch_mode == PGBUF_LATCH_READ
        && thrd_entry->request_latch_mode == PGBUF_LATCH_READ))
  {
    can_grant = true;
    impl_new.impl.fcnt += thrd_entry->request_fix_count;
    impl_new.impl.latch_mode =
      (PGBUF_LATCH_MODE) (uint16_t) thrd_entry->request_latch_mode;
  }
else if (impl.impl.latch_mode == PGBUF_LATCH_READ)
  {
    /* Look for other readers. */
    prev_thrd_entry = thrd_entry;
    break;
  }
```

grant된 entry는 아래 코드로 queue에서 제거된다.

```cpp
if (can_grant)
  {
    if (prev_thrd_entry == NULL)
      {
        bufptr->next_wait_thrd = next_thrd_entry;
      }
    else
      {
        prev_thrd_entry->next_wait_thrd = next_thrd_entry;
      }
    thrd_entry->next_wait_thrd = NULL;
    pgbuf_wakeup (thrd_entry);
  }
```

상태를 순서대로 대입하면 다음과 같다.

1. `READ₁`: 현재 `NO_LATCH`이므로 grant된다. latch는 `READ`가 되고 READ₁은 queue에서 제거된다.
2. `WRITE`: 현재 latch가 `READ`라 호환되지 않는다. `prev_thrd_entry = WRITE`만 설정하고 outer `for`는 다음 entry로 계속된다. `should_stop`은 설정되지 않는다.
3. `READ₂`: 현재 latch `READ`와 호환되므로 grant된다. 이때 `prev_thrd_entry`가 WRITE이므로 `WRITE->next = READ₂->next`가 되어 READ₂만 제거되고 WRITE는 queue에 남는다.

따라서 현재 코드에는 뒤쪽 reader가 앞선 writer보다 먼저 wake-up되는 실행 경로가 있다. 이 note는 실제 실행 loop를 source of truth로 삼아 이 동작을 현재 구현 사실로 설명한다.

반면 함수 머리의 주석은 READ wake-up을 “all readers at the head of the list”라고 설명한다. queue 중간의 WRITE를 남기고 뒤쪽 READ까지 grant하는 loop와 맞지 않으므로 **현재 구현 기준으로 이상하고 검토가 필요한 주석**이다. 구현이 의도된 reader batching인지, loop 또는 주석 중 하나의 결함인지는 미확인으로 유지한다.

## 코드 근거

**출처:** `src/storage/page_buffer.c:pgbuf_fix_release`, `pgbuf_fix_debug`, `pgbuf_latch_bcb_upon_fix`, `pgbuf_unfix`, `pgbuf_unlatch_bcb_upon_unfix`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
if (pgbuf_latch_bcb_upon_fix (thread_p, bufptr, request_mode,
                              buf_lock_acquired, condition, &is_latch_wait)
    != NO_ERROR)
  {
    return NULL;
  }

CAST_BFPTR_TO_PGPTR (pgptr, bufptr);
```

```cpp
impl_new.impl.fcnt--;
if (impl_new.impl.fcnt == 0)
  {
    impl_new.impl.latch_mode = PGBUF_NO_LATCH;
  }
```

**출처:** `src/storage/page_buffer.c:pgbuf_lockfree_fix_ro`, `pgbuf_lockfree_unfix_ro`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
if (impl.impl.latch_mode != PGBUF_LATCH_READ
    || impl.impl.waiter_exists || impl.impl.fcnt == 0)
  {
    return NULL;
  }
new_impl.impl.fcnt++;
```

```cpp
if (impl.impl.latch_mode != PGBUF_LATCH_READ
    || impl.impl.waiter_exists || impl.impl.fcnt == 1)
  {
    return false;
  }
new_impl.impl.fcnt--;
```

**출처:** `src/storage/page_buffer.c:pgbuf_latch_bcb_upon_fix`, `pgbuf_wakeup_reader_writer`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
if (holder == NULL)
  {
    can_latch = false;
  }
```

```cpp
else if (impl.impl.latch_mode == PGBUF_LATCH_READ)
  {
    /* Look for other readers. */
    prev_thrd_entry = thrd_entry;
    break;
  }
```

## 추론한 설계 의도

### 관찰 사실

fix의 성공 경로가 BCB 확보, latch 획득, thread holder 등록, `PAGE_PTR` 반환을 하나의 API 경계로 묶는다.

### 설계 의도 추론

호출자가 “memory residency pin”과 “page latch”를 별도로 조합하다가 보호되지 않은 page pointer를 사용하거나 unfix 수명을 어긋나게 하는 위험을 줄이려는 계약으로 보인다.

`waiter_exists`로 신규 reader의 CAS 합류를 막는 것은 이미 대기 중인 충돌 요청에 page가 idle해질 기회를 주려는 장치로 추론한다. 다만 wake-up이 strict FIFO가 아니므로 writer starvation 방지를 완전히 보장한다고 확대하지 않는다.

### 대안 가설

이 결합은 안전성 설계라기보다 오래된 API 형태를 유지한 결과일 수 있다.

waiter barrier의 주목적은 공정성보다 atomic fast path와 mutex-protected queue 상태를 안전하게 연결하는 것일 수 있다.

### 반증 조건

일반 storage 호출 경로에서 latch 없이 유효한 `PAGE_PTR`을 직접 얻고 별도의 public latch API로 보호하는 방식이 주된 계약임이 확인되면 이 추론은 약해진다.

설계 문서나 PR에서 `waiter_exists`의 목적과 queue fairness를 명시하거나, 모든 queue 배열에서 writer의 유한 대기를 증명하는 불변식이 확인되면 waiter 관련 추론을 수정한다.

### 신뢰도

중간

## 버전별 차이

기본 fix/unfix 계약은 historical로 보이지만 최초 공식 release는 확인 중이다.

BCB mutex를 READ 중간 전이에서 제거한 **atomic-latch READ fast path**는 commit `58cef8e01fcf121acbe3a35b7249deda54217532`의 `[CBRD-26425] Replace bcb mutex lock into atomic_latch (#6704)`에서 성능 개선 목적으로 도입되었다.

이 기능은 공식 CUBRID 11.4 Patch 5에 포함되지 않는다. `v11.4.5` tag의 `src/storage/page_buffer.c`에는 `atomic_latch`, `pgbuf_lockfree_fix_ro()`, `pgbuf_lockfree_unfix_ro()`가 없으며, 지정 checkout의 `develop`은 `VERSION` 11.5.0이다. 따라서 기준일 현재 **unreleased 11.5 develop 기능**이며 공식 release 기준 `recent | historical` 분류를 아직 부여하지 않는다.

초기 확인에서 `v11.4.5.1898` tag가 해당 commit을 포함하는 것을 공식 `v11.4.5` release 포함으로 잘못 해석했다. 공식 release tag와 build 형태의 tag를 분리해 확인해야 한다.

## 미확인 사항

- 기본 모델에 latch promotion을 어디까지 포함할지.
- READ-to-WRITE promotion 경로에서 page fix count와 holder fix count가 유지하는 정확한 불변식.
- no-lock hash-chain traversal과 concurrent victimization/VPID 재사용 사이의 안전성 불변식.
- `pgbuf_wakeup_reader_writer()`의 “head readers만 wake” 주석과 WRITE를 건너뛰는 loop 동작 중 어느 것이 의도인가.
- `lock_timeout_in_secs`, client/CAS `lock_timeout`, SQL hint가 `LOG_TDES::wait_msecs`와 page latch zero-wait으로 이어지는 정확한 설정·전파 경로. 후속 주제 큐에서 다룬다.
- waiter queue의 grant 순서와 reader/writer 공정성.
- 최초 도입 release 및 현재 atomic latch 구조가 도입된 release.

## 관련 지식

- 선수 지식: [[CUBRID 3-tier 구조]]
- 후속 지식: Page buffer atomic latch의 `waiter_exists` 불변식과 hang 진단
- 후속 지식: Transaction lock timeout과 page latch zero-wait 전달 경로
- 관련 지식: [[Page latch promotion 호출 경로]]
- 관련 지식: Cached heap scan의 page-copy 후 PEEK read mode
- 토론 기록: [[2026-07-23-005 Buffer manager page fix와 latch]]
