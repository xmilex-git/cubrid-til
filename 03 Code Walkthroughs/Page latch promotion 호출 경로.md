---
type: code-walkthrough
aliases: [pgbuf_promote_read_latch, page latch promotion, PGBUF_PROMOTE_ONLY_READER, PGBUF_PROMOTE_SHARED_READER, btree latch promotion]
visibility: internal
learning-status: completed
knowledge-status: partially-verified
code-era: historical
rationale-evidence: mixed
source-release: "10.0"
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-23
---

# Page latch promotion 호출 경로

`pgbuf_promote_read_latch()`는 이미 READ fix한 page를 구조 변경 직전에 WRITE latch로 승격하는 API다. 현재 checkout에는 12개 직접 호출식이 있으며, numerable file 자동 확장과 B-tree insert/delete의 split·merge 같은 실제 production 경로에서 사용된다.

## 초심자를 위한 설명

대표 패턴은 “탐색은 READ로 넓게 허용하고, 실제 page 구조 변경이 필요해진 순간에만 WRITE로 전환”하는 것이다.

```text
READ fix로 탐색
  → 구조 변경 필요 없음: READ 상태로 계속
  → 구조 변경 필요:
      ├─ 유일 reader: in-place READ→WRITE
      ├─ ONLY_READER + 다른 reader: 즉시 실패
      └─ SHARED_READER + 다른 reader: own fix를 잠시 반납하고 첫 promoter로 대기
```

promotion 실패를 정상 경쟁 결과로 처리하는 호출자는 page를 unfix한 뒤 WRITE mode로 traversal을 다시 시작하거나, 선택적인 merge를 생략한다.

## 구체적인 시나리오

긴 B-tree key를 insert하는 첫 traversal은 root를 READ로 fix한다. key가 page 내부 최대 길이를 넘고 overflow key file이 아직 없으면 root를 WRITE로 promotion한다. 성공 후 overflow file을 만들고 root header의 `ovfid`를 갱신한다. 경쟁 때문에 promotion하지 못하면 root를 unfix하고 WRITE로 다시 fix한 뒤, 다른 thread가 이미 overflow file을 만들었는지 조건을 재검사한다.

## 관찰된 사실

### 공통 promotion 상태 전이

**출처:** `src/storage/page_buffer.c:pgbuf_promote_read_latch_release`, `pgbuf_promote_read_latch_debug`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
if (holder->fix_count == impl.impl.fcnt)
  {
    /* we're the single holder of the read latch, do an in-place promotion */
    impl_new.impl.latch_mode = PGBUF_LATCH_WRITE;
  }
else if (condition == PGBUF_PROMOTE_ONLY_READER
         || (bufptr->next_wait_thrd != NULL
             && bufptr->next_wait_thrd->wait_for_latch_promote))
  {
    rv = ER_PAGE_LATCH_PROMOTE_FAIL;
  }
else
  {
    impl_new.impl.fcnt -= holder->fix_count;
    impl_new.impl.waiter_exists = true;
    need_block = true;
  }
```

- thread-holder fix count와 bcb fix count가 같으면 현재 thread가 유일한 holder이므로 latch mode만 WRITE로 바꾼다. fix count는 보존된다.
- 다른 holder가 있을 때 `PGBUF_PROMOTE_ONLY_READER`는 즉시 `ER_PAGE_LATCH_PROMOTE_FAIL`이다.
- `PGBUF_PROMOTE_SHARED_READER`는 own fix를 bcb fix count에서 빼고 thread-holder를 제거한 뒤 queue의 첫 promoter로 대기한다. 성공하면 기존 thread-holder fix count를 복원한 WRITE holder가 된다.
- 이미 promotion waiter가 queue 앞에 있으면 두 condition 모두 실패한다.

### 직접 호출식 12개

| 호출자와 시나리오 | 직접 호출 위치 | condition | WRITE latch가 필요한 후속 동작 |
|---|---|---|---|
| `file_numerable_find_nth()` — numerable file 자동 확장 | `file_manager.c:8251` | SHARED | `file_alloc()`을 통한 allocation bitmap/statistics와 user page table 변경 |
| `btree_fix_root_for_insert()` — 긴 key의 overflow key file 생성 | `btree.c:27346` | SHARED | overflow file 생성, root `ovfid` 갱신 |
| `btree_split_node_and_advance()` — insert root 변경 | `btree.c:27639` | SHARED | root max-key-length 변경 또는 root split |
| 같은 함수 — parent split 준비 | `btree.c:27912` | ONLY | parent와 split child 변경 |
| 같은 함수 — child split·max-key 변경 | `btree.c:27942` | SHARED | child header 변경 또는 child split |
| `btree_merge_node_and_advance()` — single-page root leaf delete | `btree.c:30982` | SHARED | traversal의 `key_function`이 leaf record 변경 |
| 같은 함수 — root merge의 root | `btree.c:31096` | ONLY | `btree_merge_root()` |
| 같은 함수 — root merge의 left child | `btree.c:31101` | SHARED | root merge 후 child deallocation |
| 같은 함수 — root merge의 right child | `btree.c:31105` | SHARED | root merge 후 child deallocation |
| 같은 함수 — 일반 right merge의 parent | `btree.c:31343` | ONLY | parent와 left child 변경 |
| 같은 함수 — 일반 right merge의 child | `btree.c:31349` | 실행 시 SHARED | `btree_merge_node()` |
| 같은 함수 — 일반 right merge의 right sibling | `btree.c:31353` | 실행 시 SHARED | merge 후 right sibling deallocation |

마지막 두 호출은 source 표현상 `promote_cond` 변수를 넘긴다. 그러나 `promote_cond == PGBUF_PROMOTE_ONLY_READER`인 level-2 case는 child를 처음부터 WRITE fix하므로 `child_latch != PGBUF_LATCH_WRITE` guard가 false다. 따라서 실제 promotion 호출이 실행될 때 child와 right sibling의 condition은 SHARED다.

### 대표 caller 1: numerable file 자동 확장

**출처:** `src/storage/file_manager.c:file_numerable_find_nth`

```cpp
page_fhead = pgbuf_fix (thread_p, &vpid_fhead, OLD_PAGE,
                        PGBUF_LATCH_READ, PGBUF_UNCONDITIONAL_LATCH);

if (auto_alloc
    && nth == (fhead->n_page_user - fhead->n_page_mark_delete))
  {
    error_code = pgbuf_promote_read_latch (
      thread_p, &page_fhead, PGBUF_PROMOTE_SHARED_READER);
  }
```

경쟁으로 promotion에 실패하면 page를 unfix하고 WRITE로 다시 fix한 뒤 allocation 필요 여부를 다시 검사한다. 정적 호출 경로에서는 `external_sort.c`가 `auto_alloc=true`로 이 함수를 사용한다.

### 대표 caller 2: 긴 B-tree key의 overflow file

**출처:** `src/storage/btree.c:btree_fix_root_for_insert`

```cpp
if (key_len >= BTREE_MAX_KEYLEN_INPAGE
    && VFID_ISNULL (&btid_int->ovfid))
  {
    error_code = pgbuf_promote_read_latch (
      thread_p, root_page, PGBUF_PROMOTE_SHARED_READER);

    error_code = btree_create_overflow_key_file (thread_p, btid_int);
    VFID_COPY (&root_header->ovfid, &btid_int->ovfid);
    pgbuf_set_dirty (thread_p, *root_page, DONT_FREE);
  }
```

### 대표 caller 3: insert parent split

**출처:** `src/storage/btree.c:btree_split_node_and_advance`

```cpp
if (need_split
    && insert_helper->nonleaf_latch_mode == PGBUF_LATCH_READ
    && !insert_helper->is_crt_node_write_latched)
  {
    error_code = pgbuf_promote_read_latch (
      thread_p, crt_page, PGBUF_PROMOTE_ONLY_READER);
  }
```

다른 reader가 있으면 기다리지 않고 parent와 child를 unfix한 뒤 traversal을 WRITE mode로 다시 시작한다. 여러 page를 보유한 상태에서 promotion 대기로 인한 latch 교착을 피하려는 동작이라는 코드 주석이 있다.

### Helper를 통한 production call path

```text
btree_insert_internal()
  → btree_search_key_and_apply_functions()
    → btree_fix_root_for_insert()
    → btree_split_node_and_advance()

btree_delete_internal()
  → btree_search_key_and_apply_functions()
    → btree_fix_root_for_delete()
    → btree_merge_node_and_advance()

btree_online_index_list_dispatcher()
  → btree_search_key_and_apply_functions()
    → insert 또는 delete callback 조합
```

이 callback binding과 generic traversal의 callback 실행은 현재 source에 존재하며 관련 호출부는 `#if`로 비활성화되어 있지 않다. 정적으로 production-reachable하지만 실제 workload별 호출 빈도는 동적 계측 없이 알 수 없다.

## 추론한 설계 의도

### 관찰 사실

caller들은 non-leaf page 또는 file header를 READ로 탐색하고, split·merge·allocation 같은 page mutation이 필요한 조건에서만 promotion을 시도한다.

### 설계 의도 추론

일반 탐색의 reader concurrency는 유지하면서 드문 구조 변경 구간만 WRITE로 직렬화하려는 최적화로 보인다. `PGBUF_PROMOTE_ONLY_READER`를 parent page에 사용하는 경로는 여러 page latch를 보유한 채 기다리는 교착 위험을 피하고 traversal restart를 선택한다.

### 대안 가설

promotion은 성능 최적화보다 기존 B-tree latch ordering을 유지하면서 refix에 따른 상태 재검사를 줄이기 위한 API일 수 있다.

### 반증 조건

동적 trace에서 caller들이 항상 처음부터 WRITE mode로 들어와 promotion이 실행되지 않거나, 설계 문서에서 다른 목적을 명시하면 추론을 수정한다.

### 신뢰도

중간

## 버전별 차이

promotion mechanism은 commit `40b817bec2a7984e03071c3b1d9cae27d7d2bf4c`의 `[CUBRIDSUS-15376] added latch promotion mechanism for btree insert and delete routines`에서 2015-01-14 도입되었다. 이 commit을 포함하는 최초 official release tag는 `v10.0`이며 기준일 1년보다 오래된 `historical` 기능이다.

`file_numerable_find_nth()` caller는 commit `3d0aeca1e3b544472ca556f1b3ec9011c19e251f`의 `[CUBRIDSUS-16092] promote read latch to write latch when compactdb`에서 2015-03-02 추가되었다.

## 미확인 사항

- 실제 workload에서 12개 caller별 실행 빈도와 promotion 성공·대기·restart 비율.
- root merge 중 일부 page promotion만 성공한 뒤 후속 promotion이 실패할 때, 이미 WRITE로 승격된 page가 concurrency에 미치는 비용.
- `PGBUF_PROMOTE_SHARED_READER`가 own fix를 반납하고 기다리는 동안 page 내용이 바뀌었을 때 caller별 재검증 범위.

## 관련 지식

- 선수 지식: [[Page fix와 page latch]]
- 후속 지식: B-tree split과 merge의 latch ordering
- 관련 지식: Transaction lock timeout과 page latch zero-wait 전달 경로
- 토론 기록: [[2026-07-23-005 Buffer manager page fix와 latch]]
