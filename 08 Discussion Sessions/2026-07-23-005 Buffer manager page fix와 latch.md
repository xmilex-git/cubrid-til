---
type: discussion-session
visibility: internal
session-status: completed
started-at: 2026-07-23
source-repository: https://github.com/CUBRID/cubrid.git
source-branch: develop
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
---

# Buffer manager의 page fix와 latch 기본 모델

## 시작 의견

사용자는 이전 학습의 큐 1순위인 **Buffer manager의 page fix와 latch 기본 모델**을 선택했다. 이 주제는 최근 page buffer 및 cached scan 변경을 이해하기 위한 engine depth 1 선수 지식이다.

source checkout에는 사용자 변경이 있으며 `origin/develop`보다 10 commit 뒤이므로 pull하지 않고 지정 commit을 읽기 전용 기준으로 삼는다.

## 질문과 합의

### Q1. `page fix`의 첫 mental model을 어디까지 묶을 것인가

- 사용자 의견: fix를 pin과 latch 획득이 결합된 대여 계약으로 보는 데에는 대부분 동의한다. 다만 “thread별 fix count”라는 표현은 부정확하다. `pgbuf_fix()`를 호출한 주체가 동일 thread인지 다른 thread인지와 무관하게 호출할 때마다 fix count가 증가한다는 점이 먼저 드러나야 한다.
- 권장안: `pgbuf_fix()`를 “buffer frame에 page를 고정(pin)하는 동작”으로만 보지 않고, **page를 buffer pool에서 찾거나 적재하고, 요청한 READ/WRITE page latch를 얻고, 현재 thread의 holder/fix count를 등록한 뒤 접근 가능한 `PAGE_PTR`을 빌리는 동작**으로 이해한다.
- 합의: 기본 mental model에는 동의하되, count를 하나처럼 부르지 않는다. BCB의 `atomic_latch.fcnt`는 page에 걸린 fix reference를 합산한 **page fix count**이고, thread-owned `PGBUF_HOLDER::fix_count`는 해당 thread가 같은 BCB에 보유한 reference를 세는 **holder fix count**다.
- 근거: `pgbuf_fix_release()`/`pgbuf_fix_debug()`는 hash lookup 또는 BCB claim 뒤 `pgbuf_latch_bcb_upon_fix()`를 호출하고, 성공하면 thread별 `PGBUF_HOLDER`와 BCB의 `atomic_latch.fcnt`가 증가한 상태로 `PAGE_PTR`을 반환한다. `pgbuf_unfix()`는 holder와 전역 fix count를 각각 감소시키고 마지막 fix가 풀리면 latch를 `PGBUF_NO_LATCH`로 바꾸며 대기자를 깨운다.

### Q2. 두 fix count의 canonical 용어

- 사용자 의견: 최종적으로 `atomic_latch.fcnt`와 `PGBUF_HOLDER::fix_count`를 각각 **bcb fix count**, **thread-holder fix count**라고 부르기로 제안했다.
- 권장안: 동의한다. 두 용어가 실제 소유 구조체와 직접 대응하며 `global`, `thread-local`의 범위 모호성을 피한다.
- 합의: **bcb fix count**와 **thread-holder fix count**를 canonical 용어로 확정했다.
- 근거: 전자는 BCB에 하나뿐이며 서로 다른 thread의 성공한 fix도 모두 더한다. 후자는 `PGBUF_HOLDER_ANCHOR`의 thread-owned holder에 있어 같은 thread의 중첩 fix와 최종 holder 제거를 관리한다.

### Q3. 두 reader 뒤의 writer는 언제 latch를 얻는가

- 사용자 의견: 권장한 정상 상태 전이에 동의했다.
- 권장안: Thread A와 B가 같은 page를 READ fix하여 bcb fix count가 2인 상태에서 Thread C가 WRITE fix를 요청하면 C는 waiter queue에서 기다린다. A의 unfix로 count가 1이 될 때는 아직 READ latch가 유지되고, B의 마지막 unfix로 count가 0이 될 때 `PGBUF_NO_LATCH`로 전환된 뒤 C가 깨워져 WRITE latch를 얻는다고 이해한다.
- 합의: writer는 첫 reader의 unfix가 아니라 마지막 reader의 unfix 뒤 latch를 얻는 정상 모델에 합의했다.
- 근거: `pgbuf_unlatch_bcb_upon_unfix()`는 매 unfix마다 `atomic_latch.fcnt`를 감소시키고, 0일 때만 latch mode를 `PGBUF_NO_LATCH`로 바꾼 뒤 `pgbuf_wakeup_reader_writer()`를 호출한다.

### Q4. BCB mutex 적용 범위와 atomic-only 범위

- 사용자 의견: 고동시성을 위해 READ끼리는 `0→1`, `1→0` 경계 전환이 아닌 경우 atomic으로 처리하므로, BCB mutex 미적용 범위와 적용 범위를 구분해야 한다. 경로 이름은 **atomic-latch READ fast path**로 하자고 정정했다.
- 권장안: 동의한다. 이미 READ latch이고 waiter가 없을 때의 bcb fix count `n→n+1`(`n≥1`)과 `n→n-1`(`n≥2`)은 `atomic_latch` CAS와 thread-holder 갱신으로 처리한다. 반면 `0→1`, `1→0`, WRITE, waiter 존재, conditional request, miss/BCB claim은 BCB mutex가 관여하는 slow path로 구분한다.
- 합의: **atomic-latch READ fast path**를 canonical term으로 확정했다. 이름의 `atomic-latch`는 BCB latch tuple 전환 방식을 뜻하며, 전체 함수가 atomic 연산만 수행한다는 뜻은 아니다.
- 근거: `pgbuf_lockfree_fix_ro()`는 `READ && !waiter_exists && fcnt>0`에서 CAS로 `fcnt++`하고, `pgbuf_lockfree_unfix_ro()`는 `READ && !waiter_exists && fcnt!=1`에서 CAS로 `fcnt--`한다. 조건이 맞지 않으면 false/NULL을 반환해 `pgbuf_fix()`/`pgbuf_unfix()`의 BCB mutex 경로로 fallback한다.

### Q5. writer waiter 뒤의 신규 reader 처리

- 사용자 의견: waiter가 선 뒤 신규 reader의 fast path를 차단하는 규칙을 기본 모델에 포함하는 데 동의했다.
- 권장안: writer가 waiter queue에 들어가 `waiter_exists`가 true이면 새 reader도 atomic-latch READ fast path를 사용하지 못하고 slow path로 간다. 기존 holder의 재진입 READ는 허용될 수 있지만 새 reader는 BCB queue에 들어간다는 관찰 사실까지 기본 모델에 포함한다.
- 합의: `waiter_exists`가 신규 reader의 atomic-latch READ fast path를 닫는 **waiter barrier**라는 데 합의했다. 다만 이를 strict FIFO 또는 writer starvation 방지 보장이라고 부르지는 않는다.
- 근거: fast path는 `waiter_exists`에서 즉시 실패한다. `pgbuf_latch_bcb_upon_fix()`의 READ-on-READ slow path도 waiter가 있으면 `holder == NULL`인 새 reader를 block하고 기존 holder만 regrant한다.

### Q6. waiter barrier와 공정성 보장을 분리할 것인가

- 사용자 의견: WRITE waiter를 건너뛰어 뒤의 READ까지 grant할 수 있다는 설명에 의문을 제기하고, 실제 코드 인용과 증명을 요구했다. 증명 확인 후, 의도는 미확인으로 유지하되 문서는 실제 코드 구현을 근거로 작성하고 “이쪽 주석이 이상하다”는 점을 남기자고 했다.
- 권장안: 기본 모델에는 `waiter_exists`를 **waiter barrier**로 기록하되, “writer fairness”나 “writer starvation 방지 보장”으로 확대하지 않는다. page가 idle일 때 queue의 첫 grant가 WRITE면 뒤를 멈추지만, READ가 먼저 grant된 경우 `pgbuf_wakeup_reader_writer()`는 queue 안의 다른 READ를 더 찾아 함께 grant할 수 있어 strict FIFO가 아니다.
- 합의: 현재 동작 설명은 실행되는 loop를 source of truth로 삼는다. `READ₁ → WRITE → READ₂`에서 READ₂가 WRITE를 건너뛰어 grant될 수 있다고 문서화한다. 이것이 의도된 정책인지 결함인지는 미확인으로 두며, 함수 머리의 “all readers at the head of the list” 주석은 현재 구현과 맞지 않아 이상하고 검토가 필요한 주석으로 기록한다.
- 근거: `pgbuf_block_bcb()`는 일반 waiter를 queue tail에 append하므로 `READ₁ → WRITE → READ₂` 배열이 가능하다. wake-up loop는 `READ₁`을 grant해 latch를 READ로 만든 뒤 WRITE에서 `prev_thrd_entry`만 갱신하고 “Look for other readers” 경로로 outer loop를 계속한다. `READ₂`는 현재 READ latch와 호환되어 grant되고, `prev_thrd_entry == WRITE`이므로 `WRITE->next`를 갱신해 READ₂만 queue에서 제거한다. 결과적으로 WRITE는 남고 READ₂가 먼저 깨어난다.

## 정정 및 충돌

- “Buffer manager”는 넓게는 적재·교체·dirty/flush까지 포함한다. 이번 canonical 범위에는 그중 page 접근 수명과 동시성 계약인 `fix/unfix` 및 READ/WRITE page latch만 포함하고, LRU·victim·WAL flush 정책은 관련 지식으로만 연결하는 것을 권장한다.
- CUBRID 코드의 canonical public term은 `PGBUF_LATCH_READ`, `PGBUF_LATCH_WRITE`인 **page latch**다. transaction lock과 구분한다.
- “thread별 fix count”, “page-global fix count”, “thread-local fix count”라는 표현은 철회한다. `PGBUF_BCB::atomic_latch.fcnt`는 **bcb fix count**, `PGBUF_HOLDER::fix_count`는 **thread-holder fix count**로 부른다.
- “READ fix가 atomic-only다”라고 넓게 표현하지 않는다. 이미 READ latch가 유지되는 중간 count 전이이고 waiter가 없는 경우만 BCB mutex를 건너뛴다.
- atomic-latch READ fast path가 CUBRID 11.4 Patch 5에 포함되었다는 이전 판단은 철회한다. 공식 `v11.4.5` tag에는 `atomic_latch`, `pgbuf_lockfree_fix_ro()`, `pgbuf_lockfree_unfix_ro()`가 없고, 현재 `develop`의 `VERSION`은 `11.5.0`이다. 혼동 원인은 공식 release tag와 이름이 비슷한 `v11.4.5.1898` tag가 commit `58cef8e01f`을 포함한다는 점이었다.
- `waiter_exists`가 새 reader를 slow path로 보내는 것은 관찰 사실이지만, 전체 waiter queue가 strict FIFO이거나 writer starvation을 완전히 방지한다는 결론은 철회한다.
- `pgbuf_wakeup_reader_writer()` 주석은 “all readers at the head of the list”라고 설명하지만 현재 loop는 중간 WRITE를 건너뛰어 뒤의 READ도 grant할 수 있다. 구현 관찰과 주석이 충돌하므로 의도된 reader batching인지 결함인지는 미확인으로 둔다.

### Q7. conditional/unconditional latch를 기본 모델에 포함할 범위

- 사용자 의견: 권장 범위에 동의했다. 다만 생소한 `zero-wait`의 의미를 물었고, 어떻게 설정하는지는 나중에 살펴보도록 후속 주제 큐에 넣어 달라고 했다.
- 권장안: 두 값의 세부 timeout 정책 전체가 아니라 호출자가 관찰하는 경계만 포함한다. `PGBUF_CONDITIONAL_LATCH`는 즉시 grant할 수 없으면 기다리지 않고 실패하고, `PGBUF_UNCONDITIONAL_LATCH`는 즉시 grant할 수 없으면 waiter queue와 timed sleep 경로로 간다. 단 transaction의 wait 설정이 zero-wait이면 unconditional 요청도 내부에서 conditional로 바뀐다는 예외를 함께 기록한다.
- 합의: 위 호출자 관찰 경계를 기본 모델에 포함한다. `zero-wait`은 transaction descriptor의 `wait_msecs == 0`으로, 충돌 시 기다리지 않고 즉시 timeout/failure 경로로 가게 하는 상태라고 정의한다. 설정 진입점과 전파 경로는 후속 주제로 미룬다.
- 근거: `pgbuf_fix()`는 transaction wait가 `LK_ZERO_WAIT` 또는 `LK_FORCE_ZERO_WAIT`이면 condition을 conditional로 변경한다. `pgbuf_latch_bcb_upon_fix()`는 conditional 충돌 시 `ER_FAILED`, unconditional 충돌 시 `pgbuf_block_bcb()`를 호출한다.

### Q8. 같은 thread의 중첩 fix를 기본 모델에 포함할 범위

- 사용자 의견: 포함하는 데 동의했다.
- 권장안: 같은 thread가 같은 page를 같은 READ mode로 다시 fix하면 bcb fix count와 thread-holder fix count가 모두 증가하고, 동일 횟수의 unfix가 필요하다는 재진입 규칙까지 기본 모델에 포함한다. READ→WRITE promotion의 대기·refix 세부는 다음 단계로 분리한다.
- 합의: 같은 thread의 중첩 READ fix와 matching unfix를 기본 모델에 포함한다.
- 근거: READ-on-READ fast/slow path는 기존 holder의 `fix_count`와 BCB `fcnt`를 각각 증가시키며, `pgbuf_unfix()`는 호출마다 두 count를 하나씩 감소시킨다.

### Q9. READ→WRITE promotion을 기본 모델에 포함할 범위

- 사용자 의견: 실제 READ→WRITE 전환을 수행하는 caller가 있는지 전체 source를 조사해 달라고 했고, 노가다성 작업이므로 `luna` sub-agent를 high effort로 파견하도록 요청했다. 12개 caller와 production call path 근거를 확인한 뒤 세 promotion 경계를 기본 모델에 포함하는 데 동의했다.
- 권장안: 세 가지 경계만 기본 모델에 포함한다. 현재 thread가 유일한 reader이면 BCB mutex 아래에서 in-place `READ→WRITE`가 가능하다. 다른 reader가 있고 `PGBUF_PROMOTE_ONLY_READER`이면 즉시 실패한다. `PGBUF_PROMOTE_SHARED_READER`이면 현재 thread가 가진 fix들을 잠시 반납하고 queue의 첫 promoter로 기다린 뒤 WRITE latch와 동일한 thread-holder fix count를 다시 얻는다. B-tree별 호출 시나리오는 후속으로 미룬다.
- 합의: 세 promotion 경계를 기본 모델에 포함하고, 실제 caller별 세부는 [[Page latch promotion 호출 경로]]에서 관리한다.
- 근거: `pgbuf_promote_read_latch()`는 `holder->fix_count == impl.fcnt`이면 latch mode만 WRITE로 바꾼다. shared 상태에서는 condition에 따라 `ER_PAGE_LATCH_PROMOTE_FAIL`을 반환하거나, own `fix_count`를 BCB `fcnt`에서 빼고 holder를 제거한 뒤 `pgbuf_block_bcb(..., PGBUF_LATCH_WRITE, fix_count, true)`로 기다린다. `luna` 조사와 main-agent 검산에서 직접 호출식 12개를 확인했다. `file_numerable_find_nth()` 1개, `btree_fix_root_for_insert()` 1개, `btree_split_node_and_advance()` 3개, `btree_merge_node_and_advance()` 7개이며 모두 production callback/caller에 정적으로 연결된다.

### Q10. WRITE latch와 dirty mark를 기본 모델에서 분리할 것인가

- 사용자 의견: 포함하는 데 동의했다.
- 권장안: 포함한다. `PGBUF_LATCH_WRITE`는 page memory를 배타적으로 변경할 권한일 뿐 변경 사실이나 flush 필요성을 자동 기록하지 않는다. caller는 실제 변경 후 `pgbuf_set_dirty()` 또는 `pgbuf_set_dirty_and_free()`를 호출해야 하며, matching unfix와는 별도 책임이다.
- 합의: WRITE latch, dirty mark, unfix를 서로 다른 책임으로 기본 모델에 포함한다.
- 근거: promotion caller들은 header/record 변경 후 명시적으로 `pgbuf_set_dirty()`를 호출한다. page buffer는 dirty flag와 `oldest_unflush_lsa`를 별도 BCB 상태로 관리한다.

### Q11. 기본 topic의 완료 경계

- 사용자 의견: 권장한 경계로 현재 topic을 완료하는 데 동의했다.
- 권장안: 이번 topic은 fix/unfix, 두 fix count, READ/WRITE latch, atomic-latch READ fast path, waiter barrier, conditional/unconditional, 중첩 fix, promotion, dirty mark까지로 완료한다. LRU/victim 선정, WAL을 지키는 dirty flush, B-tree split/merge latch ordering은 후속 주제 큐로 분리한다.
- 합의: 현재 topic을 completed로 전환하고 세 확장 주제는 후속 큐에서 관리한다.
- 근거: 현재 범위만으로 backend 개발자 초심자가 page pointer의 유효 수명, 정상 경쟁·대기, 실제 mutation caller와 dirty 책임을 설명할 수 있다. 교체·flush와 다중 page latch ordering은 각각 독립된 상태 전이와 장애 시나리오가 필요한 depth 2 주제다.

## 생성·갱신한 지식

- [[Page fix와 page latch]] — 기본 mental model과 현재 코드 근거를 기록하기 시작했다.
- [[Page latch promotion 호출 경로]] — 12개 direct caller의 선행 READ fix, trigger, condition, 실패 처리와 WRITE 후 mutation을 분류했다.

## 미해결 사항

- `pgbuf_wakeup_reader_writer()`의 “head readers” 주석과 WRITE를 건너뛰는 실제 loop 중 어느 쪽이 의도인가.
- `PGBUF_PROMOTE_SHARED_READER`가 own fix를 반납하고 기다리는 동안 page 내용이 바뀔 때 caller별 재검증 범위.
- workload별 promotion 성공·대기·restart 비율.

## 나중에 다룰 주제

- Page buffer atomic latch의 `waiter_exists` 불변식과 hang 진단 — 기본 상태 전이를 완료한 뒤 장애 경로로 확장한다.
- Cached heap scan의 page-copy 후 PEEK read mode — fix/latch 수명과 page copy의 관계를 선수 지식 이후 검증한다.
- Transaction lock timeout과 page latch zero-wait 전달 경로 — `lock_timeout_in_secs`, client/CAS의 `lock_timeout`, SQL hint와 `LOG_TDES::wait_msecs`가 `pgbuf_fix()` condition에 도달하는 설정·전파 경로를 별도로 검증한다.
- Buffer pool LRU·victim 선정과 dirty page flush — fix count 0 이후 replacement 후보화, dirty victim의 WAL flush와 재사용 경계를 분리해 검증한다.
- B-tree split·merge의 page latch ordering — promotion caller에서 발견한 parent/child/sibling 다중 latch 순서와 restart 규칙을 분리해 검증한다.

## 재개 위치

현재 topic은 완료했다. 반대 근거나 새 질문이 생기면 reopened로 전환한다.

## 다음 후보

1. **Engine:** Broker의 CAS 할당과 연결 인계 — depth 1, 남은 가장 얕은 engine frontier이며 3-tier 접속 흐름을 완성한다.
2. **Development:** C/C++ compiler portability와 GCC-Clang 차이 — depth 1, P1이며 최근 compiler 호환성 변경과 직접 연결된다.
3. **Operations:** CUBRID 구성과 서버 생명주기 — depth 0, 아직 완료되지 않은 가장 얕은 operations 기반 주제다.
