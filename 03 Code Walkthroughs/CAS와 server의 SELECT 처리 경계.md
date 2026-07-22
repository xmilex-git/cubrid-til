---
type: code-walkthrough
visibility: internal
learning-status: completed
knowledge-status: partially-verified
code-era: historical
rationale-evidence: mixed
source-release: "2008 R2.1 or earlier"
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-22
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

현업 용어에 가까운 표현은 CAS가 **XASL generation → XASL to stream**을 담당하고 server가 **prepare → stream to XASL → XASL execution**을 담당한다는 것이다. `serialization`, `deserialization`, `XASL compile`보다 이 표현을 우선한다.

현재 source의 정확한 timing에서는 `xqmgr_prepare_query()`가 우선 XASL stream을 cache하고, execute path가 cache entry의 실행용 XASL을 얻을 때 `stx_map_stream_to_xasl()`을 호출한다. 따라서 현업의 `prepare → stream to XASL`은 server-side 준비 책임을 나타내는 큰 단계명이고, 함수 호출 시점은 execute 직전일 수 있다.

“server는 XASL 실행만 한다”는 말은 **SQL compile과 execute의 책임을 나누는 문맥**에서 사용한다. server 전체 기능이 XASL interpreter뿐이라는 뜻은 아니다. server는 XASL cache, 역직렬화, query scheduling, scan, storage, transaction, lock과 log 같은 실행 기반도 담당한다.

## 구체적인 시나리오

### 정상 시나리오: plan cache miss인 SELECT

1. CAS의 `ux_prepare()` 계열에서 `db_open_buffer()`가 SQL text를 parse한다.
2. `db_compile_statement()`가 `pt_compile()`로 semantic check를 수행하고 `mq_translate()` 경로에서 view expansion과 query rewrite를 수행한다.
3. `do_prepare_select()`가 `parser_generate_xasl()`을 호출한다. 이 과정에서 optimizer가 plan을 선택하고 XASL tree를 만든다.
4. CAS는 `xts_map_xasl_to_stream()`으로 **XASL to stream**을 수행해 server prepare 요청으로 보낸다.
5. server prepare는 stream을 XASL cache에 넣는다. 실행 path에서 `stx_map_stream_to_xasl()`을 거쳐 실행용 XASL을 얻는다.
6. 실행 요청을 받은 server는 `sqmgr_execute_query()`에서 `xqmgr_execute_query()`를 호출하고, 최종적으로 `qexec_execute_query()`와 `qexec_execute_mainblock()`이 XASL을 실행한다.

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

## 코드 근거

**출처:** `src/compat/db_vdb.c:db_open_buffer_local`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
session->statements = parser_parse_string_with_escapes (session->parser, buffer, false);
```

**출처:** `src/compat/db_vdb.c:db_compile_statement_local`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
statement_result = pt_compile (parser, statement);
statement_result = mq_translate (parser, statement);
err = do_prepare_statement (parser, statement);
```

`pt_compile()`은 `pt_semantic_check()`를 호출한다. `mq_translate()`의 SELECT 경로는 `mq_rewrite()`를 호출해 query rewrite를 적용한다.

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
- client-side compile 배치의 직접적인 역사적 설계 근거는 찾지 못했다.

## 관련 지식

- 선수 지식: [[CUBRID 3-tier 구조]]
- 후속 지식: plan cache hit와 recompile 경로
- 관련 지식: [[Code Walkthroughs Index]], [[Architecture Index]]
- 토론 기록: [[2026-07-22-001 CUBRID 전체 구조]]
