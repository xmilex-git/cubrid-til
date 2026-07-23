---
type: architecture
aliases: [3-tier, CAS, broker, cub_cas, cub_broker, cub_server, architecture]
visibility: internal
learning-status: completed
knowledge-status: partially-verified
code-era: historical
rationale-evidence: documented
source-release: "2008 R2.1 or earlier"
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-22
---

# CUBRID 3-tier 구조

CUBRID 개발 현업에서는 핵심 process 영역을 **CAS–broker–server 3-tier**라고 부른다. JDBC driver를 포함한 application client는 이 세 영역과 별도로 구분하며, 실제 접속 순서와 tier 명칭을 혼동하지 않아야 한다.

## 초심자를 위한 설명

현업의 3-tier 명칭은 다음과 같다. 이는 구성요소/영역을 나열한 이름이며 요청 순서를 뜻하지 않는다.

```text
CAS | broker | server
```

각 canonical process는 `cub_cas`, `cub_broker`, `cub_server`다. JDBC driver는 이 3-tier에 포함해 부르지 않는 별도 구현 영역이다.

한편 source와 공식 문서에서 확인되고 사용자가 동의한 정상 SQL 접속 흐름은 다음과 같다.

```text
application + driver
        ↓
cub_broker → cub_cas (CAS)
        ↓
cub_server (server)
```

- **JDBC driver/application:** 3-tier 밖의 별도 client 구현 영역이다.
- **broker:** `cub_broker`가 application 접속을 중계하고 CAS pool을 관리한다.
- **CAS:** 할당된 `cub_cas`가 application 요청을 처리하고 database client로 동작한다.
- **server:** `cub_server`가 storage, transaction, concurrency를 담당한다.

### `client`가 두 가지를 뜻하는 이유

- application ↔ broker 경계에서는 application/driver가 client이고 CAS는 middleware의 worker다.
- CAS ↔ server 경계에서는 `cub_cas`가 CUBRID client library를 사용하는 **database client process**이고 `cub_server`가 server다.

따라서 “client는 CAS라고 부른다”는 현업 표현은 **engine의 client/server 구조를 설명하는 문맥**에서 맞다. 문맥 없이 `client`만 쓰면 외부 application client와 혼동되므로, canonical note에서는 `application client`와 `CAS(database client process)`를 구분한다.

또한 용어는 다음처럼 엄격히 구분한다.

- **JDBC driver:** application이 CUBRID protocol로 요청을 보내게 하는 Java client driver 영역
- **broker:** 접속 중계와 CAS pool 관리 영역 및 `cub_broker` process
- **CAS:** application 요청 처리와 database client 역할을 맡는 `cub_cas` process
- **server:** database server인 `cub_server` process

## 구체적인 시나리오

JDBC application이 SQL을 실행하면 driver가 broker endpoint로 접속한다. `cub_broker`는 사용 가능한 `cub_cas`로 연결을 중계하고, CAS는 database client로서 `cub_server`에 연결해 SQL 처리 작업을 수행한 뒤 결과를 application으로 돌려준다.

경계 시나리오로 CAS가 비정상 종료되면 broker는 해당 연결 요청에 오류를 반환하고 CAS를 재시작할 수 있다. 기존 요청의 성공을 보장하는 것이 아니라 새 연결을 받을 수 있는 정상 대기 상태로 복구하는 동작이다.

## 관찰된 사실

1. 공식 11.4 manual은 CUBRID를 application과 database server 사이를 broker middleware가 중계하는 3-tier DBMS로 설명한다.
2. 공식 manual은 `cub_cas`를 server에 연결하는 client process의 대표 사례로 명시한다.
3. source build에서 `cub_cas` executable은 client/server client library인 `cubridcs`를 링크한다.
4. CAS의 database 연결 경로는 client type을 `DB_CLIENT_TYPE_BROKER`로 정하고 `db_restart_ex()`를 호출한다.
5. 사용자 경험상 CUBRID 개발자들은 engine 문맥에서 CAS를 `client`, `cub_server`를 `server`라고 부른다.
6. 사용자 경험상 CAS는 CAS, broker는 broker이며 JDBC driver도 별도 영역이다. 세 용어를 서로 포괄하거나 대체해서 사용하지 않는다.
7. 사용자 경험상 CUBRID 개발 현업에서는 CAS, broker, server의 세 영역을 `CAS–broker–server 3-tier`라고 부른다.
8. `CAS–broker–server`는 구성 영역을 나열한 명칭이지 접속 순서가 아니다. 실제 접속 흐름은 driver → broker → CAS → server다.

## 코드 근거

**출처:** `broker/CMakeLists.txt:cub_cas target`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cmake
add_executable(cub_cas WIN32 ${CUB_CAS_SOURCES})
target_link_libraries(cub_cas LINK_PRIVATE cas_common_lib cubridcs)
```

**출처:** `src/broker/cas_execute.c:ux_database_connect`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
client_type = DB_CLIENT_TYPE_BROKER;
err_code = db_restart_ex (program_name, db_name, db_user, db_passwd, NULL, client_type);
```

**출처:** `src/broker/broker.c:broker_worker`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cpp
as_index = find_idle_cas ();
srv_sock_fd = connect_srv (shm_br->br_info[br_index].name, as_index);
ret_val = send_fd (srv_sock_fd, cur_job.clt_sock_fd, ip_addr, cur_job.driver_info);
```

broker가 idle CAS를 고르고 CAS socket에 연결한 뒤 application의 client socket을 전달하는 흐름이므로, 접속 순서는 broker → CAS임을 확인할 수 있다.

## 공식 문서 근거

- [CUBRID 11.4 System Parameters](https://www.cubrid.org/manual/en/11.4/admin/config.html) — server에 연결하는 client process로 broker application server인 `cub_cas`를 명시한다.
- [CUBRID 11.4 HA](https://www.cubrid.org/manual/en/11.4/ha.html) — application과 database server 사이에 broker middleware가 있는 3-tier DBMS로 설명한다.
- [CUBRID 10.0 System Architecture](https://www.cubrid.org/manual/en/10.0/intro.html) — application client, `cub_broker`, `cub_cas`, `cub_server`의 역할을 각각 설명한다.

공식 manual의 “application–broker middleware–database server” 설명과 현업의 “CAS–broker–server” 명칭은 관점이 다르다. 전자는 외부 application을 포함한 논리 서비스 구조이고, 후자는 CUBRID 내부의 주요 process/구현 영역을 구분하는 사용자 경험 용어로 기록한다.

## 추론한 설계 의도

직접 문서 근거가 있으므로 별도의 설계 의도 추론은 하지 않는다.

## 버전별 차이

3-tier와 CAS의 database client 역할은 적어도 공식 2008 R2.1 manual부터 확인되는 historical architecture다. 정확한 최초 도입 release는 아직 확인하지 않았다.

## 미확인 사항

- 3-tier architecture의 정확한 최초 도입 release는 미확인이다.

## 관련 지식

- 선수 지식: 없음
- 후속 지식: [[CAS와 server의 SELECT 처리 경계]]
- 관련 지식: [[Architecture Index]], [[Learning State]]
- 토론 기록: [[2026-07-22-001 CUBRID 전체 구조]]
