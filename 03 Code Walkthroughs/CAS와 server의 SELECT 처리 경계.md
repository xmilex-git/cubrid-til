---
type: code-walkthrough
aliases: [SELECT path, XASL, XASL to stream, prepare, execute, optimizer, query plan, CAS_FC_PREPARE, CAS_FC_EXECUTE]
visibility: internal
learning-status: completed
knowledge-status: partially-verified
code-era: historical
rationale-evidence: mixed
source-release: "2008 R2.1 or earlier"
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-23
---

# CAS와 server의 SELECT 처리 경계

정상적인 client/server mode의 `SELECT`에서 CAS는 SQL을 parse하고 의미를 검사·rewrite·optimize한 뒤 XASL을 생성하고 **XASL to stream**을 수행한다. server는 stream을 cache하고 실행 시 **stream to XASL**을 거쳐 XASL을 실행하며, 필요한 storage·transaction·lock·log 작업을 담당한다.

## 초심자를 위한 설명

`SELECT` 한 건의 책임 경계는 다음처럼 요약할 수 있다.

```text
CAS
SQL text
  → parse tree
  → semantic check
  → rewrite
  → optimizer
  → XASL generation
  → XASL to stream
                 ↓
server
  prepare/cache stream
  → stream to XASL
  → XASL execution
  → scan/storage/transaction
  → result
```

현업에서 사용하는 논리 pipeline은 다음과 같이 대응한다.

```text
parser → semantic check → rewriter → optimizer → XASL generator → executor
```

그러나 wire protocol에서는 한 번에 이어지는 호출이 아니다. 일반적인 prepared SELECT는 다음 두 요청으로 분리된다.

```text
Driver ── CAS_FC_PREPARE ──> CAS
  parser → semantic check → rewriter → optimizer → XASL generator
  └─ NET_SERVER_QM_QUERY_PREPARE ──> server: XASL cache lookup/store, XASL_ID 반환

Driver ── CAS_FC_EXECUTE ──> CAS
  └─ NET_SERVER_QM_QUERY_EXECUTE ──> server: executor, QFILE_LIST_ID 반환
  └─ 선택적으로 ux_fetch()가 첫 row 묶음을 CAS 응답에 추가
```

즉 여섯 단계는 올바른 논리 요약이지만, 앞의 다섯 단계는 주로 CAS의 `PREPARE`, 마지막 `executor`는 server의 `EXECUTE`에 놓인다. plan cache hit이면 optimizer와 XASL generator가 생략될 수 있다.

현업 용어에 가까운 표현은 CAS가 **XASL generation → XASL to stream**을 담당하고 server가 **prepare → stream to XASL → XASL execution**을 담당한다는 것이다. `serialization`, `deserialization`, `XASL compile`보다 이 표현을 우선한다.

현재 source의 정확한 timing에서는 `xqmgr_prepare_query()`가 우선 XASL stream을 cache하고, execute path가 cache entry의 실행용 XASL을 얻을 때 `stx_map_stream_to_xasl()`을 호출한다. 따라서 현업의 `prepare → stream to XASL`은 server-side 준비 책임을 나타내는 큰 단계명이고, 함수 호출 시점은 execute 직전일 수 있다.

“server는 XASL 실행만 한다”는 말은 **SQL compile과 execute의 책임을 나누는 문맥**에서 사용한다. server 전체 기능이 XASL interpreter뿐이라는 뜻은 아니다. server는 XASL cache, 역직렬화, query scheduling, scan, storage, transaction, lock과 log 같은 실행 기반도 담당한다.

## 구체적인 시나리오

### Parser 단계: SQL text에서 `PT_NODE`로

`CAS_FC_PREPARE` 요청의 SQL text는 `fn_prepare_internal()` → `ux_prepare()` → `db_open_buffer()`로 전달된다. `db_open_buffer_local()`은 `PARSER_CONTEXT`를 가진 `DB_SESSION`을 만들고 `parser_parse_string_with_escapes()`를 호출한다. 이 함수는 SQL text를 parser input으로 설정한 뒤 `parser_main()`을 부르고, grammar의 `select_stmt` action은 `parser_new_node(..., PT_SELECT)`로 SELECT parse tree를 구성한다.

이 단계의 출력은 `DB_SESSION::statements`에 저장된 `PT_NODE **`이다. 문법적으로 SELECT node가 만들어졌다는 뜻이지, table·column 이름 해석과 타입 검증까지 끝났다는 뜻은 아니다. 그 작업은 다음 `pt_compile()`의 semantic check에서 진행된다.

### Semantic check 단계: 이름을 bind하고 SELECT 규칙과 타입을 검사

`db_compile_statement_local()`은 parse tree를 `pt_compile()`에 넘기고, `pt_compile()`은 `pt_semantic_check()`를 호출한다. SELECT가 통과하는 핵심 순서는 다음과 같다.

```text
pt_compile()
  → pt_semantic_check()
    → pt_check_with_info()
      → pt_resolve_names()
      → pt_check_where()
      → pt_semantic_check_local()
        → SELECT clause 검사
        → pt_semantic_type()
```

`pt_resolve_names()`는 FROM의 entity spec을 펼치고 `PT_NAME`을 scope 안의 class·attribute에 bind하며 GROUP BY/HAVING alias와 NATURAL JOIN도 정리한다. 이후 SELECT local check는 single-column subquery, INTO, GROUP BY, analytic function, ORDER BY 같은 규칙을 검사하고 `pt_semantic_type()`으로 expression type을 정한다.

현업의 canonical 범위에서도 name resolution은 semantic check에 포함한다. 다만 query 의미를 실제 schema object와 연결하는 중요한 경계이므로, 상세 분석이나 장애 진단에서는 `name resolution`을 나머지 clause validation·type check와 분리해 말할 수 있다.

예를 들어 존재하지 않는 column이나 둘 이상의 FROM item에서 모호한 unqualified column을 참조하면 name resolution에서 error가 등록된다. `pt_compile()`은 `NULL`을 받고 `db_compile_statement_local()`이 실패하므로 rewriter인 `mq_translate()`에는 도달하지 않는다.

### Rewriter 단계: `mq_translate()`로 실행 가능한 query 형태를 만든다

현업에서 rewriter라고 부르는 `mq_translate()`는 semantic check를 통과한 `PT_NODE`를 입력받아 같은 tree 표현을 변형한다. SELECT의 주요 순서는 다음과 같다.

```text
mq_translate()
  → mq_translate_helper()
    → CTE reference count / CTE derived-table rewrite
    → mq_push_paths()                         # path 처리와 CNF 변환
    → mq_translate_local()
      → mq_translate_select()                 # view/virtual class expansion
    → DBLink derived-subquery rewrite
    → mq_rewrite()                            # 일반 query rewrite rules
    → pt_semantic_type()                      # rewrite 뒤 타입 재검사·constant folding
    → pt_for_update_prepare_query()
```

따라서 `rewriter = mq_translate()`이고, optimizer rewriter directory의 `mq_rewrite()`는 그 내부 단계다. 예를 들어 FROM에 view가 있으면 view definition을 바탕으로 base class query 또는 derived table 형태로 바꾼 뒤 일반 predicate/query rewrite를 적용한다. 반대로 단순 base table SELECT라도 `mq_rewrite()`와 rewrite 후 `pt_semantic_type()` 경로는 지난다.

#### View SELECT의 구체적인 치환

다음은 동작을 설명하기 위한 예시다.

```sql
CREATE VIEW active_users AS
SELECT id, name FROM users WHERE active = 1;

SELECT name FROM active_users WHERE id > 10;
```

name resolution이 `active_users`를 view object로 bind한 뒤 rewriter는 다음 순서로 처리한다.

1. `mq_translate_select()`가 parent SELECT의 FROM spec을 `mq_translate_tree()`에 넘긴다.
2. `mq_translate_tree()`가 `mq_translatable_class()`로 view/virtual class임을 판별한다.
3. `mq_fetch_subqueries()`가 `sm_virtual_queries()`의 cached parser에서 view query specification을 가져온다.
4. `mq_substitute_subquery_list_in_statement()` → `mq_substitute_subquery_in_statement()`이 각 view query를 parent SELECT에 적용한다.
5. `mq_is_pushable_subquery()` 결과가 pushable이면 `mq_substitute_select_in_statement()`이 view attribute를 view SELECT expression으로 바꾸고 FROM spec을 base-class 쪽으로 합친다.
6. non-pushable이면 `mq_rewrite_vclass_spec_as_derived()`가 view query를 derived table로 유지한 채 parent query의 spec을 바꾼다.

위 예시가 pushable 조건을 만족하면 개념적으로 `users`를 FROM에 두고 `active = 1`과 `id > 10`을 함께 가진 tree가 된다. DISTINCT, aggregate, UNION, ORDER BY 등으로 안전한 merge가 어렵다면 다음처럼 derived table 경계를 보존할 수 있다.

```sql
SELECT name
FROM (SELECT id, name FROM users WHERE active = 1) active_users
WHERE id > 10;
```

이는 설명용 SQL 등가 형태이며 source가 SQL text를 다시 만드는 것은 아니다. 실제 대상은 계속 `PT_NODE` tree다.

### Optimizer 단계: rewritten `PT_NODE`에서 `QO_PLAN`을 선택한다

논리 pipeline에서는 optimizer가 XASL generator보다 먼저지만, source의 호출 구조에서는 XASL generation 진입점 안에서 optimizer를 호출한다.

```text
parser_generate_xasl()
  → parser_generate_xasl_post()
    → parser_generate_xasl_proc()
      → pt_plan_query()
        → qo_optimize_query()       # PT_SELECT → QO_PLAN
        → pt_to_buildlist_proc()    # QO_PLAN → XASL_NODE
          또는 pt_to_buildvalue_proc()
```

`qo_optimize_query()`는 `qo_env_init()`으로 optimizer environment를 만들고 `qo_optimize_helper()`를 호출한다. helper는 FROM node, predicate term, attribute segment로 query graph를 구성하고 join edge·equivalence class·index·partition·sort/limit 후보를 발견한 다음 `qo_planner_search()`로 plan을 선택한다.

```text
rewritten PT_SELECT
  → QO_ENV
  → nodes / segments / terms / join edges
  → indexes / partitions / sort-limit candidates
  → qo_planner_search()
  → QO_PLAN
```

Optimizer가 설정으로 비활성화됐거나 plan을 만들지 못하면 `qo_optimize_query()`는 `NULL`을 반환한다. `pt_plan_query()`는 그 값을 `pt_to_buildlist_proc()` 또는 `pt_to_buildvalue_proc()`에 전달하므로, `QO_PLAN == NULL`이 곧 XASL generation 중단을 뜻하지는 않는다. 또한 hint가 있는 최적화가 실패하면 hint를 지우고 한 번 재시도한다.

#### 두 table join 사례

다음 query를 예로 든다.

```sql
SELECT o.id, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'PAID';
```

rewriter를 통과한 `PT_SELECT`를 optimizer가 다음 개념으로 바꾼다.

| SQL 요소 | Optimizer 표현 | 예시 |
|---|---|---|
| FROM table/spec | `QO_NODE` | `orders`, `customers` |
| 참조 attribute | `QO_SEGMENT` | `o.id`, `o.customer_id`, `o.status`, `c.id`, `c.name` |
| ON/WHERE conjunct | `QO_TERM` | `c.id = o.customer_id`, `o.status = 'PAID'` |
| table 간 조건 | join edge | `orders ↔ customers` |
| 선택된 실행 전략 | `QO_PLAN` | scan 방식, inner/outer 순서, join 방식 |

`qo_optimize_helper()`는 ON과 WHERE conjunct를 `qo_add_term()`으로 graph에 추가하고 join edge를 분류한다. 이어 index와 partition 후보를 발견한 뒤 `qo_planner_search()`가 후보 plan을 검색한다. 따라서 `orders.status` index를 먼저 사용할지, `customers.id`를 inner index lookup으로 사용할지 같은 선택은 schema 통계와 발견된 index에 따라 달라지며, query text만으로 하나의 plan을 단정할 수 없다.

선택된 plan은 XASL generation에서 다음처럼 소비된다.

```text
QO_PLAN
  → pt_gen_optimized_plan()
    → qo_to_xasl()
      → XASL_NODE.spec_list / scan_ptr / index info
```

`qo_to_xasl()` 변환이 실패하거나 `QO_PLAN`이 없으면 inner join 계열은 `pt_gen_simple_plan()` fallback을 사용할 수 있다. outer join에서 optimized plan generation이 실패하면 동일한 simple fallback을 허용하지 않고 error 처리하는 경계가 있다.

### XASL generator 단계: `QO_PLAN`을 실행 자료구조로 내린다

일반적인 여러-row SELECT에서 `pt_to_buildlist_proc()`는 `BUILDLIST_PROC` type의 root `XASL_NODE`를 만든다. SELECT의 주요 정보는 다음처럼 실행용 필드로 내려간다.

| SELECT/plan 요소 | XASL 표현 | 역할 |
|---|---|---|
| query root | `XASL_NODE.type = BUILDLIST_PROC` | 여러 tuple을 list file로 만드는 root proc |
| SELECT list | `outptr_list` | 출력 tuple에 기록할 expression/value 목록 |
| FROM access | `spec_list`의 `ACCESS_SPEC_TYPE` | 대상 class/list와 scan 방식 |
| index access | `ACCESS_SPEC_TYPE.access`, `indexptr`, `btid` | index scan 정보 |
| predicate | `where_key`, `where_pred`, join predicate fields | key filter와 residual/join 조건 |
| 다음 scan/proc | `scan_ptr` 및 proc별 child | 선택된 join/scan 실행 구조 |
| subquery/CTE | `aptr_list`, `dptr_list` 등 | 비상관·상관 subquery 실행 연결 |

`qo_to_xasl()`은 plan tree에서 access spec collection을 만들고 WHERE predicate를 적절한 access spec에 배치한다. SELECT list expression은 caller인 XASL generation 쪽이 `outptr_list` 등으로 별도 구성한다.

앞의 join 예시는 선택 plan에 따라 개념적으로 다음과 같은 실행 tree가 된다.

```text
BUILDLIST_PROC
├─ outptr_list: o.id, c.name
├─ access/scan: orders
│  └─ predicate: o.status = 'PAID'
└─ access/scan or join child: customers
   └─ join predicate: c.id = o.customer_id
```

이는 고정된 tree shape가 아니다. `QO_PLAN`이 index join, hash join, merge join 등을 고르면 `spec_list`, `scan_ptr`, `HASHJOIN_PROC`, `MERGELIST_PROC` 등의 조합이 달라질 수 있다. Canonical output boundary는 **실행 가능한 `XASL_NODE` tree**다.

NL join에서는 inner, 즉 후행 table의 scan plan을 `gen_inner()`가 처리한다. `init_class_scan_proc()` → `ptqo_to_scan_proc()`가 별도의 `SCAN_PROC`를 만들고, outer generation에 이 node를 넘겨 `add_scan_proc()`가 root에서 시작하는 `scan_ptr` chain 끝에 연결한다.

```text
BUILDLIST_PROC (outer/선행 scan 정보 포함)
└─ scan_ptr → SCAN_PROC (inner/후행 table)
```

join predicate 중 inner scan에 일찍 적용할 수 있는 term은 `gen_inner()` 전에 inner plan의 key-filter/sarg term으로 push될 수 있다.

### XASL to stream과 server prepare

완성된 pointer 기반 `XASL_NODE` tree는 CAS process의 주소를 그대로 server에 보낼 수 없으므로 `xts_map_xasl_to_stream()`이 offset 기반 linear byte stream으로 바꾼다.

```text
XASL_NODE tree
  → xts_map_xasl_to_stream()
  → XASL_STREAM { buffer, buffer_size }
  → prepare_query()
  → qmgr_prepare_query()
  → NET_SERVER_QM_QUERY_PREPARE
  → sqmgr_prepare_query()
  → xqmgr_prepare_query()
  → xcache_insert()
  → XASL_ID 반환
```

stream header에는 host variable 수, creator OID, 참조 class OID와 lock/cardinality 목록 등이 들어가고, body에는 XASL node와 연결 구조가 offset으로 저장된다. `qmgr_prepare_query()`는 SQL hash/user text와 stream size 등의 request metadata, XASL stream data를 server로 보낸다.

정상 cache miss에서 server의 `xqmgr_prepare_query()`는 stream header 일부를 읽고 `xcache_insert()`로 stream을 XASL cache에 저장한 뒤 `XASL_ID`를 반환한다. 이 prepare 시점에는 전체 XASL tree를 실행용 pointer tree로 만들지 않는다. 실제 **stream to XASL**은 execute path가 cache entry의 clone을 준비할 때 수행된다.

### Execute와 executor 진입

Driver의 별도 `CAS_FC_EXECUTE` 요청은 prepare에서 받은 CAS request handle을 지정한다. CAS는 handle에 보관된 `DB_SESSION`, statement id와 `XASL_ID`를 사용한다.

```text
CAS_FC_EXECUTE
→ fn_execute()
→ fn_execute_internal()
→ ux_execute()
→ db_execute_and_keep_statement()
→ do_execute_statement()
→ do_execute_select()
→ execute_query()
→ qmgr_execute_query()
→ NET_SERVER_QM_QUERY_EXECUTE
```

`qmgr_execute_query()`는 `XASL_ID`, bind value 수와 값, query flag, timeout 등을 pack한다. Server의 실행 경로는 다음과 같다.

```text
sqmgr_execute_query()
→ xqmgr_execute_query()
  → xcache_find_xasl_id_for_execute()
    → cache entry lookup 및 관련 class lock
    → cached XASL clone 사용 또는 stx_map_stream_to_xasl()
  → qmgr_process_query()
    → qexec_execute_query()
      → qexec_execute_mainblock()
        → qexec_execute_mainblock_internal()
```

`xcache_find_xasl_id_for_execute()`는 `XASL_ID`의 SHA-1뿐 아니라 `time_stored`도 확인하고 관련 object lock을 얻어 plan validity를 보호한다. 사용 가능한 clone이 없으면 cache entry의 stream에서 실행용 `XASL_NODE` clone을 만든다.

#### NL join executor

`qexec_execute_mainblock_internal()`은 root와 `scan_ptr` chain의 모든 access spec을 `qexec_open_scan()`으로 연다. NL join에서는 function vector의 level 0에 `qexec_intprt_fnc`, inner scan level에 `qexec_execute_scan`을 배치한다.

```text
outer row: qexec_intprt_fnc
  → scan_ptr inner: qexec_execute_scan
  → join/filter 통과
  → output tuple을 root list_id에 생성
  → 다음 outer row에서 inner scan 반복/reset
```

실행이 끝나면 각 scan을 end/close하고 root `QFILE_LIST_ID`가 query manager를 거쳐 network reply로 반환된다.

### 결과 반환: list file에서 CAS row protocol로

Server의 `sqmgr_execute_query()`는 executor가 만든 `QFILE_LIST_ID`를 그대로 row 배열로 바꾸지 않는다. list id를 `or_pack_listid()`로 pack하고, 가능하면 list file의 첫 page도 함께 복사해 execute reply의 별도 data block으로 보낸다.

```text
server QFILE_LIST_ID
→ or_pack_listid() + 첫 list-file page
→ client-side qmgr_execute_query()
  → or_unpack_unbound_listid()
  → QFILE_LIST_ID와 첫 page 복원
→ pt_new_query_result_descriptor()
  → DB_QUERY_RESULT cursor
→ CAS srv_handle->q_result->result
```

CAS의 `ux_execute()`는 이 `DB_QUERY_RESULT`를 request handle에 보관하고 `execute_info_set()`으로 tuple count와 result metadata를 응답 buffer에 기록한다. 실제 column value는 다음 두 방식 중 하나로 전달된다.

- execute request의 `fetch_flag`가 켜져 있으면 `fn_execute_internal()`이 바로 `ux_fetch(..., 1, 50, ...)`를 호출하여 첫 row 묶음을 execute 응답에 붙인다.
- 그렇지 않거나 남은 row가 있으면 driver의 `CAS_FC_FETCH`가 `fn_fetch()` → `ux_fetch()` → `fetch_result()`로 이어진다.

`fetch_result()`는 `db_query_first_tuple()`/`db_query_seek_tuple()`로 cursor 위치를 맞추고, 각 row에서 `cur_tuple()`로 column 값을 `T_NET_BUF`에 기록한 뒤 `db_query_next_tuple()`로 전진한다. Cursor가 현재 보유한 page 밖으로 이동하면 `cursor_get_list_file_page()`가 `qfile_get_list_file_page()`로 server의 다음 list-file page를 요청한다. 완성된 `T_NET_BUF`는 CAS request loop의 `net_write_stream()`으로 driver socket에 전송된다.

따라서 논리 pipeline의 `executor` 출력은 server 내부의 `QFILE_LIST_ID`이고, driver가 보는 SELECT row는 CAS의 별도 fetch/cursor 계층에서 protocol 값으로 변환된 결과다.

### 정상 시나리오: plan cache miss인 SELECT

1. CAS의 request dispatcher가 `CAS_FC_PREPARE`를 `fn_prepare()`에 연결하고, `fn_prepare_internal()`이 SQL text를 꺼내 `ux_prepare()`를 호출한다.
2. `ux_prepare()`에서 `db_open_buffer()`가 SQL text를 parse한다.
3. `db_compile_statement()`가 `pt_compile()`로 semantic check를 수행하고 `mq_translate()` 경로에서 view expansion과 query rewrite를 수행한다.
4. `do_prepare_select()`가 `parser_generate_xasl()`을 호출한다. 이 과정에서 optimizer가 plan을 선택하고 XASL tree를 만든다.
5. CAS는 `xts_map_xasl_to_stream()`으로 **XASL to stream**을 수행해 server prepare 요청으로 보낸다.
6. server prepare는 stream을 XASL cache에 넣고 `XASL_ID`를 반환한다. 실행 path에서 cache entry의 실행용 XASL clone을 얻는다.
7. 별도의 `CAS_FC_EXECUTE` 요청은 `fn_execute()` → `ux_execute()` → `db_execute_and_keep_statement()` → `do_execute_select()`로 이어진다.
8. `do_execute_select()`는 `NET_SERVER_QM_QUERY_EXECUTE`를 보내며, server의 `sqmgr_execute_query()` → `xqmgr_execute_query()` → `qmgr_process_query()` → `qexec_execute_query()` → `qexec_execute_mainblock()`이 XASL을 실행한다.
9. server가 `QFILE_LIST_ID`를 반환하면 CAS가 execute metadata를 응답 buffer에 넣는다. execute의 `fetch_flag`가 켜져 있으면 `ux_fetch()`가 첫 row 묶음도 같은 CAS 응답에 추가한다.
10. 이후 fetch는 `CAS_FC_FETCH` → `fn_fetch()` → `ux_fetch()` → `fetch_result()`로 cursor를 전진시키며, 필요한 list-file page를 server에서 추가로 받아 row를 `T_NET_BUF`에 넣고 driver로 전송한다.

### 경계 시나리오: plan cache hit

server가 query의 XASL cache entry를 반환하면 CAS는 XASL을 다시 생성하지 않을 수 있다. 따라서 “CAS가 매 실행마다 optimizer를 수행한다”는 표현은 틀리며, cache miss 또는 recompile 시점의 compile 책임으로 이해해야 한다.

## 관찰된 사실

1. `cub_cas`가 호출하는 `db_open_buffer()`는 `parser_parse_string_with_escapes()`로 parse tree를 만든다.
2. `db_compile_statement()` 경로는 `pt_compile()`의 semantic check, `mq_translate()`의 view expansion/query rewrite, `do_prepare_statement()`의 XASL generation/prepare 요청을 포함한다.
3. `do_prepare_select()`는 cache miss에서 `parser_generate_xasl()`과 `xts_map_xasl_to_stream()`을 호출한다.
4. `parser_generate_xasl()` 내부의 SELECT XASL 생성 경로는 `qo_optimize_query()`로 optimizer plan을 얻는다.
5. server의 execute request는 `sqmgr_execute_query()` → `xqmgr_execute_query()` → `qexec_execute_query()` → `qexec_execute_mainblock()`으로 이어진다.
6. 사용자 경험상 현업 용어는 `XASL generation`, `XASL to stream`, `stream to XASL`에 가깝다. `serialization`, `deserialization`, `XASL compile`은 우선 용어로 사용하지 않는다.
7. 현재 source에서 server prepare는 stream을 cache하며, `stx_map_stream_to_xasl()`의 실제 호출은 execute path에서 일어난다.
8. CAS protocol의 `PREPARE`와 `EXECUTE`는 각각 `fn_prepare()`와 `fn_execute()`에 dispatch된다.
9. 논리 pipeline의 parser부터 XASL generator까지는 일반적인 cache-miss prepare에서 수행되고, executor는 별도의 server execute 요청에서 수행된다.
10. SELECT row 반환은 executor 자체와 동일한 단계가 아니다. CAS는 execute 후 `fetch_flag`에 따라 `ux_fetch()`로 첫 row 묶음을 응답에 추가하거나 이후 `CAS_FC_FETCH` 요청에서 row를 가져온다.
11. 사용자 경험상 현업 용어 `rewriter`는 source의 `mq_rewrite()` 단일 함수가 아니라 상위 `mq_translate()` 단계를 가리킨다.
12. parser 단계의 직접 출력은 `DB_SESSION::statements`의 `PT_NODE **`이며, SELECT grammar는 `PT_SELECT` node를 만든다. semantic check는 그 다음 `db_compile_statement_local()`에서 시작한다.
13. SELECT semantic check는 `pt_resolve_names()` 후 WHERE와 SELECT clause 규칙을 검사하고 `pt_semantic_type()`으로 타입을 검사한다. parser error가 생기면 `pt_semantic_check()`는 `NULL`을 반환한다.
14. 사용자 경험상 name resolution은 semantic check의 일부이지만 중요하기 때문에 현업 설명에서 별도 하위 단계처럼 구분하기도 한다.
15. SELECT의 `mq_translate()`는 CTE/path/view·virtual class/DBLink 구조 변환 뒤 내부 `mq_rewrite()`를 호출하고, rewrite된 tree에 `pt_semantic_type()`을 다시 적용한다.
16. View SELECT에서 `mq_translate_tree()`는 schema manager의 cached view query를 얻어 parent tree에 적용한다. pushable이면 parent와 합치고, non-pushable이면 derived table로 치환한다.
17. `qo_optimize_query()`는 `parser_generate_xasl()` 내부의 `pt_plan_query()`에서 호출된다. 선택된 `QO_PLAN`은 `pt_to_buildlist_proc()` 또는 `pt_to_buildvalue_proc()`가 XASL로 변환한다.
18. Optimizer가 비활성화되어 `QO_PLAN`이 `NULL`이어도 XASL generation은 계속될 수 있다. hint 적용 plan이 실패하면 hint 없이 optimizer를 재호출한다.
19. Join SELECT에서 FROM spec, attribute, predicate conjunct는 각각 `QO_NODE`, `QO_SEGMENT`, `QO_TERM`으로 graph에 반영된다. 선택된 `QO_PLAN`은 `qo_to_xasl()`이 XASL scan/access 구조로 변환한다.
20. 여러-row SELECT의 root XASL은 보통 `BUILDLIST_PROC`이며, `qo_to_xasl()`은 FROM/WHERE plan을 access spec과 scan/proc 구조로 변환한다. SELECT list는 `outptr_list`로 구성된다.
21. NL join의 inner/후행 table은 `gen_inner()`에서 `SCAN_PROC`로 생성되어 outer/root XASL의 `scan_ptr` chain에 연결된다.
22. `xts_map_xasl_to_stream()`은 pointer 기반 XASL tree를 offset 기반 linear stream으로 바꾼다. Server prepare는 정상 cache miss에서 이 stream을 cache하고 `XASL_ID`를 반환하며, stream to XASL은 execute path에서 일어난다.
23. Server execute의 `xcache_find_xasl_id_for_execute()`가 XASL cache entry와 관련 class lock을 확보하고, cached clone이 없으면 `stx_map_stream_to_xasl()`로 실행용 clone을 만든다.
24. NL join executor는 root와 `scan_ptr` chain의 scan을 열고 outer level의 `qexec_intprt_fnc`와 inner level의 `qexec_execute_scan`을 조합해 반복 실행한다. 결과는 `QFILE_LIST_ID`에 만들어진다.
25. Server execute reply는 packed `QFILE_LIST_ID`와 가능한 경우 첫 list-file page를 함께 보낸다. Client library는 이를 다시 `QFILE_LIST_ID`로 복원하고 `DB_QUERY_RESULT` descriptor로 감싼다.
26. CAS의 일반 SELECT fetch는 `fetch_result()`가 `DB_QUERY_RESULT` cursor를 이동하며 row를 `T_NET_BUF`에 기록한다. Cursor buffer에 없는 page는 `qfile_get_list_file_page()`로 server에서 추가 요청한다.
27. Execute의 `fetch_flag`가 켜지면 첫 row 묶음은 execute 응답에 포함될 수 있고, 나머지는 별도 `CAS_FC_FETCH` 응답으로 전달된다. 최종 CAS 응답 buffer는 `net_write_stream()`으로 driver socket에 전송된다.

## 코드 근거

**출처:** `src/compat/db_vdb.c:db_open_buffer_local`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
session->statements = parser_parse_string_with_escapes (session->parser, buffer, false);
```

**출처:** `src/parser/parse_tree_cl.c:parser_parse_string_with_escapes`, `src/parser/csql_grammar.y:parser_main`, `src/parser/csql_grammar.y:select_stmt`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
tree = parser_main (parser);

rv = yyparse ();

node = parser_new_node (this_parser, PT_SELECT);
```

`parser_main()`은 parser node stack을 `parser->statements` 배열로 정리한다. 이 parse tree가 이후 semantic check와 rewriter가 수정하는 공통 `PT_NODE` 표현이다.

**출처:** `src/parser/compile.c:pt_compile`, `src/parser/semantic_check.c:pt_semantic_check`, `src/parser/semantic_check.c:pt_check_with_info`, `src/parser/semantic_check.c:pt_semantic_check_local`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
statement = pt_semantic_check (parser, statement);

node = pt_resolve_names (parser, node, sc_info_ptr);
node = pt_check_where (parser, node);
node = parser_walk_tree (parser, node, NULL, NULL, pt_semantic_check_local, sc_info_ptr);

case PT_SELECT:
  node = pt_semantic_type (parser, node, info);
  break;
```

**출처:** `src/parser/name_resolution.c:pt_resolve_names`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
statement = parser_walk_tree (parser, statement, pt_flat_spec_pre, &info, pt_continue_walk, NULL);
statement = parser_walk_tree (parser, statement, pt_bind_names, &bind_arg, pt_bind_names_post, &bind_arg);
```

**출처:** `src/parser/view_transform.c:mq_translate`, `src/parser/view_transform.c:mq_translate_helper`, `src/parser/view_transform.c:mq_translate_local`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
node = parser_walk_tree (parser, node, NULL, NULL, mq_rewrite_cte_as_derived, NULL);
node = parser_walk_tree (parser, node, NULL, NULL, mq_push_paths, NULL);
node = parser_walk_tree (parser, node, NULL, NULL, mq_translate_local, NULL);
node = mq_rewrite (parser, node);
node = pt_semantic_type (parser, node, NULL);
```

`mq_translate_local()`의 `PT_SELECT` branch는 `mq_translate_select()`를 호출해 view와 virtual class를 재귀적으로 확장한다.

**출처:** `src/parser/view_transform.c:mq_translate_select`, `src/parser/view_transform.c:mq_translate_tree`, `src/parser/view_transform.c:mq_fetch_subqueries`, `src/parser/view_transform.c:mq_substitute_subquery_in_statement`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
tree = mq_translate_tree (parser, select_statement, from, order_by, DB_AUTH_SELECT);
subquery = mq_fetch_subqueries (parser, entity);
substituted = mq_substitute_subquery_list_in_statement (parser, tree, subquery, entity, order_by, what_for);

is_mergeable = mq_is_pushable_subquery (parser, query_spec, tmp_result, class_spec, true, order_by, class_);
if (is_mergeable == NON_PUSHABLE)
  class_spec = mq_rewrite_vclass_spec_as_derived (parser, tmp_result, class_spec, query_spec, /* ... */);
else
  result = mq_substitute_select_in_statement (parser, tmp_result, query_spec, class_);
```

**출처:** `src/parser/xasl_generation.c:parser_generate_xasl`, `src/parser/xasl_generation.c:parser_generate_xasl_proc`, `src/parser/xasl_generation.c:pt_plan_query`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
xasl = parser_generate_xasl_proc (parser, node, info->query_list);
xasl = pt_plan_query (parser, node);
plan = qo_optimize_query (parser, select_node);
xasl = pt_to_buildlist_proc (parser, select_node, plan);
```

single-tuple SELECT에는 `pt_to_buildvalue_proc()`가 사용된다.

**출처:** `src/optimizer/query_graph.c:qo_optimize_query`, `src/optimizer/query_graph.c:qo_optimize_helper`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
env = qo_env_init (parser, tree);
return qo_optimize_helper (env);

qo_discover_edges (env);
qo_assign_eq_classes (env);
qo_discover_indexes (env);
qo_discover_partitions (env);
plan = qo_planner_search (env);
```

**출처:** `src/parser/xasl_generation.c:pt_gen_optimized_plan`, `src/parser/xasl_generation.c:pt_to_buildlist_proc`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
ret = qo_to_xasl (plan, xasl);

if (qo_plan == NULL || !pt_gen_optimized_plan (parser, select_node, qo_plan, xasl))
  xasl = pt_gen_simple_plan (parser, select_node, qo_plan, xasl);
```

**출처:** `src/optimizer/plan_generation.c:qo_to_xasl`, `src/query/xasl.h:xasl_node`, `src/query/xasl.h:access_spec_node`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
xasl = gen_outer (env, plan, &EMPTY_SET, NULL, NULL, xasl);

PROC_TYPE type;
OUTPTR_LIST *outptr_list;
ACCESS_SPEC_TYPE *spec_list;
XASL_NODE *scan_ptr;

ACCESS_METHOD access;
INDX_INFO *indexptr;
PRED_EXPR *where_key;
PRED_EXPR *where_pred;
```

**출처:** `src/optimizer/plan_generation.c:gen_outer`, `src/optimizer/plan_generation.c:gen_inner`, `src/optimizer/plan_generation.c:add_scan_proc`, `src/parser/xasl_generation.c:ptqo_to_scan_proc`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
scan = gen_inner (env, inner, &predset, &new_subqueries, inner_scans, fetches);
xasl = gen_outer (env, outer, &new_subqueries, scan, NULL, xasl);

if (xasl == NULL)
  xasl = regu_xasl_node_alloc (SCAN_PROC);

xp->scan_ptr = scan;
```

**출처:** `src/query/xasl_to_stream.c:xts_map_xasl_to_stream`, `src/communication/network_interface_cl.c:qmgr_prepare_query`, `src/query/query_manager.c:xqmgr_prepare_query`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
xts_save_xasl_node (xasl_tree);
stream->buffer = xts_Stream_buffer;
stream->buffer_size = xts_Free_offset_in_stream;

net_client_request2 (NET_SERVER_QM_QUERY_PREPARE, /* ... */, stream->buffer, stream->buffer_size, /* ... */);
xcache_insert (thread_p, context, stream, /* ... */, &cache_entry_p);
```

**출처:** `src/broker/cas_function.c:fn_execute_internal`, `src/broker/cas_execute.c:ux_execute`, `src/query/execute_statement.c:do_execute_select`, `src/communication/network_interface_cl.c:qmgr_execute_query`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
ret_code = (*ux_exec_func) (srv_handle, /* ... */);
n = db_execute_and_keep_statement (session, stmt_id, &result);
execute_query (statement->xasl_id, &parser->query_id, /* ... */, &list_id, /* ... */);
net_client_request_with_callback (NET_SERVER_QM_QUERY_EXECUTE, /* ... */);
```

**출처:** `src/communication/network_interface_sr.cpp:sqmgr_execute_query`, `src/query/query_manager.c:xqmgr_execute_query`, `src/query/xasl_cache.c:xcache_find_xasl_id_for_execute`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
list_id = xqmgr_execute_query (thread_p, &xasl_id, &query_id, /* ... */);
xcache_find_xasl_id_for_execute (thread_p, xasl_id_p, &xasl_cache_entry_p, &xclone);
stx_map_stream_to_xasl (thread_p, &xclone->xasl, /* ... */);
```

**출처:** `src/query/query_manager.c:qmgr_process_query`, `src/query/query_executor.c:qexec_execute_query`, `src/query/query_executor.c:qexec_execute_mainblock_internal`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
query_p->list_id = qexec_execute_query (thread_p, xasl_p, dbval_count, dbvals_p, query_p->query_id);
stat = qexec_execute_mainblock (thread_p, xasl, &xasl_state, NULL);

func_vector[0] = (XSAL_SCAN_FUNC) qexec_intprt_fnc;
func_vector[level] = (XSAL_SCAN_FUNC) qexec_execute_scan;
qp_scan = (*func_vector[0]) (thread_p, xasl, xasl_state, &tplrec, &func_vector[1]);
```

**출처:** `src/compat/db_vdb.c:db_compile_statement_local`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
statement_result = pt_compile (parser, statement);
statement_result = mq_translate (parser, statement);
err = do_prepare_statement (parser, statement);
```

`pt_compile()`은 `pt_semantic_check()`를 호출한다. 현업에서는 그 다음 `mq_translate()` 단계를 **rewriter**라고 부르며, SELECT 경로의 `mq_translate()` 내부에서 `mq_rewrite()`도 호출된다. 따라서 `rewriter`와 `mq_rewrite()`를 같은 범위로 혼동하지 않는다.

**출처:** `src/broker/cas.c:server_fn_table`, `src/broker/cas_function.c:fn_prepare_internal`, `src/broker/cas_function.c:fn_execute_internal`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
fn_prepare, /* CAS_FC_PREPARE */
fn_execute, /* CAS_FC_EXECUTE */

srv_h_id = ux_prepare (sql_stmt, flag, auto_commit_mode, net_buf, req_info, /* ... */);
ret_code = (*ux_exec_func) (srv_handle, /* ... */);
if (fetch_flag && ret_code >= 0 && client_cache_reusable == FALSE)
  ux_fetch (srv_handle, 1, 50, 0, 0, net_buf, req_info);
```

**출처:** `src/query/execute_statement.c:do_prepare_select`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
contextp->xasl = parser_generate_xasl (parser, statement);
err = xts_map_xasl_to_stream (contextp->xasl, &stream);
err = prepare_query (contextp, &stream);
```

`parser_generate_xasl()`의 SELECT 처리에서 `qo_optimize_query()`가 호출되어 optimizer plan이 XASL 생성에 반영된다.

**출처:** `src/query/query_manager.c:xqmgr_prepare_query`, `src/query/query_manager.c:qmgr_process_query`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
error_code = xcache_insert (thread_p, context, stream, /* ... */);
stx_map_stream_to_xasl (thread_p, &xasl_p, false, xasl_stream, xasl_stream_size, &xasl_buf_info);
```

prepare는 stream을 cache하고 execute를 위한 query 처리에서 stream을 XASL tree로 변환한다.

**출처:** `src/communication/network_interface_sr.cpp:sqmgr_execute_query`, `src/query/query_executor.c:qexec_execute_query`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
list_id = xqmgr_execute_query (thread_p, &xasl_id, &query_id, /* ... */);
stat = qexec_execute_mainblock (thread_p, xasl, &xasl_state, NULL);
```

client-side `qmgr_execute_query()`는 `NET_SERVER_QM_QUERY_EXECUTE`를 보내고 server-side `sqmgr_execute_query()`가 이를 받는다. 결과는 server 내부의 `QFILE_LIST_ID`로 만들어져 client library와 CAS의 `DB_QUERY_RESULT` descriptor로 연결된다.

**출처:** `src/communication/network_interface_sr.cpp:sqmgr_execute_query`, `src/communication/network_interface_cl.c:qmgr_execute_query`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
page_ptr = qmgr_get_old_page (thread_p, &list_id->first_vpid, list_id->tfile_vfid);
(void) or_pack_listid (replydata, list_id);

ptr = or_unpack_unbound_listid (replydata_listid, (void **) (&list_id));
list_id->last_pgptr = replydata_page;
```

**출처:** `src/compat/db_vdb.c:db_execute_and_keep_statement_local`, `src/broker/cas_execute.c:ux_execute`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
qres = pt_new_query_result_descriptor (parser, statement);

srv_handle->q_result->result = (void *) result;
err_code = execute_info_set (srv_handle, net_buf, client_version, flag);
```

**출처:** `src/broker/cas_execute.c:fetch_result`, `src/query/cursor.c:cursor_get_list_file_page`, `src/broker/cas.c`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
err_code = db_query_first_tuple (result);
err_code = cur_tuple (q_result, srv_handle->max_col_size, sensitive_flag, db_obj, net_buf);
err_code = db_query_next_tuple (result);

ret_val = qfile_get_list_file_page (cursor_id_p->query_id, vpid_p->volid, vpid_p->pageid,
                                    cursor_id_p->buffer_area, &cursor_id_p->buffer_filled_size);
net_write_stream (sock_fd, net_buf->data, NET_BUF_CURR_SIZE (net_buf));
```

## 추론한 설계 의도

### 관찰 사실

Parser와 optimizer는 client-side target에 포함되고, XASL executor는 server-side에 배치된다. CAS는 생성한 XASL을 stream으로 바꾸어 server에 보낸다.

### 설계 의도 추론

Compile을 CAS 쪽에 두면 여러 CAS process가 parse와 optimization 부하를 분담하고 server는 shared data와 transaction을 중심으로 실행을 담당할 수 있다.

### 대안 가설

- 역사적인 object/client API 구조 때문에 parser가 client library에 남았을 수 있다.
- server 확장성보다 기존 client/server protocol과 module 재사용이 더 큰 이유였을 수 있다.

### 반증 조건

공식 설계 문서나 도입 당시 issue/commit에서 parser를 CAS에 둔 직접 이유가 다른 목표였다고 명시되면 이 추론을 수정한다.

### 신뢰도

중간

## 버전별 차이

CAS가 database client로서 query parse와 plan generation을 담당하는 구조는 적어도 공식 2008 R2.1 manual에서 확인되는 historical architecture다. 정확한 최초 도입 release와 이후 단계별 변화는 미확인이다.

## 미확인 사항

- DDL/DML, prepared statement, plan cache hit/recompile의 변형 경로는 별도 후속 주제로 분리했다.
- `qexec_open_scan()` 아래의 heap/index scan manager와 access method별 tuple 탐색은 별도 후속 주제로 분리했다.
- `CAS_FC_FETCH`의 page pagination, cursor buffer와 overflow tuple 세부 처리는 별도 후속 주제로 분리했다.
- client-side compile 배치의 직접적인 역사적 설계 근거는 찾지 못했다.

## 관련 지식

- 선수 지식: [[CUBRID 3-tier 구조]]
- 후속 지식: plan cache hit와 recompile 경로
- 관련 지식: [[Code Walkthroughs Index]], [[Architecture Index]]
- 토론 기록: [[2026-07-22-001 CUBRID 전체 구조]], [[2026-07-23-001 SELECT SQL 실행 경로]]
