---
type: discussion-session
visibility: internal
session-status: completed
started-at: 2026-07-23
source-repository: https://github.com/CUBRID/cubrid.git
source-branch: develop
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
---

# Main iteration 종료와 post-processing 경계

## 시작 의견

사용자가 기존 후속 주제 큐의 `Main iteration 종료와 post-processing 경계`를 선택해 인터뷰를 시작했다. 이전 세션에서 보류한 `qexec_end_mainblock_iterations()`의 실행 구간 분류와 analytic function의 processing 중 평가 예외를 검증한다.

Source checkout은 사용자 변경이 있어 갱신하지 않았다. 기준 commit은 `e1e81d600f604d0fc22ded3066186a1a9aaec184`이며, 확인 시점에 `origin/develop`보다 11 commit 뒤에 있다.

## 질문과 합의

### Q1. `qexec_end_mainblock_iterations()`의 canonical 단계명

- 사용자 의견: `qexec_end_mainblock_iterations()`를 독립적인 `main iteration 종료` 단계로 정의하는 권장안에 동의했다.
- 권장안: `scan block iteration` 자체에는 포함하지 않고, `intprt_fnc` 뒤와 `post-processing` 앞에 놓인 독립 단계 `main iteration 종료`로 부른다. 필요하면 `scan block iteration의 종료 처리`가 아니라 `main iteration 결과 확정 단계`라고 설명한다.
- 합의: `scan block iteration`은 `intprt_fnc` 내부의 반복으로 한정한다. `qexec_end_mainblock_iterations()`는 `intprt_fnc` 뒤의 독립적인 `main iteration 종료` 단계이며, 그 다음부터 `post-processing`이다.
- 근거: `qexec_execute_mainblock_internal()`은 일반 경로에서 `qexec_end_mainblock_iterations()` 호출 직후 `Post_processing` comment 아래 GROUP BY, analytic function, ORDER BY/DISTINCT를 실행한다. `qexec_end_mainblock_iterations()`는 proc type에 따라 result list close, `BUILDVALUE` aggregate finalize, merge/hash join 결과 생성, UNION/DIFFERENCE/INTERSECTION list 결합을 수행한다.

### Q2. Analytic 최적화의 단계 설명

- 사용자 의견: analytic function은 논리적 후처리 연산이지만 최적화에 따라 `end-one-iteration`에서 처리될 수도 있다고 문서화해 달라고 했다. 현업에서는 `qexec_end_one_iteration()`을 `end-one-iteration`이라는 이름으로 직접 부르며, 한 row에 대한 평가가 끝난 뒤 결과 row 하나를 처리하는 함수라는 의미다.
- 권장안: analytic function을 무조건 `post-processing`에만 속한다고 설명하지 않고, 기본 경로와 최적화 경로를 나눈다. 기본 경로는 post-processing에서 평가하며, `XASL_ANALYTIC_USES_LIMIT_OPT` 또는 `XASL_ANALYTIC_SKIP_SORT` 경로는 `intprt_fnc`에서 row별 상태를 누적하고 post-processing에서 후속 처리를 수행한다고 설명한다.
- 합의: analytic function은 논리적으로 post-processing 연산이다. 다만 최적화가 적용되면 실제 평가는 `intprt_fnc`가 qualified candidate row를 `end-one-iteration`으로 넘길 때 수행될 수 있다. `XASL_ANALYTIC_SKIP_SORT`는 `end-one-iteration`에서 row별 상태를 누적하고 post-processing에서 결과를 확정하며, `XASL_ANALYTIC_USES_LIMIT_OPT`는 analytic 평가의 대부분을 `end-one-iteration`에서 수행하고 post-processing의 analytic executor는 실질 작업을 건너뛴다.
- 근거: `qexec_end_one_iteration()`은 두 flag 중 하나가 있으면 `qexec_analytic_eval_in_processing()`을 호출한다. 이후 post-processing의 `qexec_execute_analytic()`은 항상 호출되지만, limit optimization이면 즉시 wrapup하고, skip-sort이면 누적한 상태와 기존 list를 이용해 group 결과를 확정한다.

### Q3. `end-one-iteration`과 `main iteration 종료`의 이름 충돌 방지

- 사용자 의견: 두 종료 단위를 구분하는 데 동의했다.
- 권장안: 두 용어를 반드시 실행 단위와 함께 병기한다. `end-one-iteration`은 qualified candidate row 하나의 결과 처리이고, `main iteration 종료`는 전체 `intprt_fnc`가 끝난 뒤 main procedure block 결과를 확정하는 단계다.
- 합의: `end-one-iteration`과 `main iteration 종료`를 명확히 구분한다. 처음 설명할 때는 각각 row 단위와 main procedure block 단위임을 병기하고, 이후에도 두 이름을 바꾸어 쓰지 않는다.
- 근거: `qexec_intprt_fnc()`은 qualified row마다 `qexec_end_one_iteration()`을 호출한다. 반면 `qexec_execute_mainblock_internal()`은 scan 함수가 모두 끝난 뒤 `qexec_end_mainblock_iterations()`을 한 번 호출한다.

### Q4. `post-processing`의 canonical 정의

- 사용자 의견: `post-processing`을 source 제어 구간으로 정의하는 데 동의했고, 논리적 연산과 실제 계산 시점의 차이를 한글로 상세히 기록해 달라고 했다.
- 권장안: `post-processing`을 “모든 GROUP BY·analytic·ORDER BY/DISTINCT 계산이 물리적으로 실행되는 배타적 위치”가 아니라, `qexec_end_mainblock_iterations()` 뒤에서 시작하는 main block의 source 제어 구간으로 정의한다. 연산의 논리적 소속과 최적화된 실제 실행 위치는 별도로 설명한다.
- 합의: `post-processing`은 `main iteration 종료` 뒤에서 시작하는 source의 제어 구간이다. GROUP BY·analytic·ORDER BY/DISTINCT는 논리적 후처리 연산이지만, 최적화가 적용되면 계산 일부 또는 대부분이 row 단위 `end-one-iteration`으로 앞당겨질 수 있다. 논리적 소속과 물리적 실행 위치를 동일시하지 않는다.
- 근거: Source는 `qexec_end_mainblock_iterations()` 다음에 `Post_processing` comment를 두지만, analytic skip-sort/limit optimization과 hash GROUP BY·Top-N 같은 최적화는 일부 계산을 `end-one-iteration`으로 앞당긴다.

### Q5. 단계 모델의 적용 범위

- 사용자 의견: 일반 SELECT 계열 경로에 한정하고 전용 executor에는 같은 단계명을 강제로 적용하지 않는 데 동의했다.
- 권장안: 이번에 합의한 `pre-processing → intprt_fnc/end-one-iteration → main iteration 종료 → post-processing` 모델은 `qexec_execute_mainblock_internal()`의 일반 SELECT 계열 경로를 설명하는 canonical model로 한정한다. `CONNECT BY`와 `BUILD_SCHEMA_PROC`의 전용 executor까지 같은 단계명에 억지로 맞추지 않는다.
- 합의: 단계 모델은 `qexec_execute_mainblock_internal()`의 일반 SELECT 계열 경로에 한정한다. 공통 helper를 호출한다는 이유만으로 전용 executor의 자체 반복과 후속 처리에 동일한 단계명을 적용하지 않는다.
- 근거: `qexec_execute_connect_by()`, `qexec_execute_build_indexes()`, `qexec_execute_build_columns()`도 `qexec_end_mainblock_iterations()`를 호출하지만, 각 전용 loop와 별도 후속 처리를 가지며 공통 `Post_processing` 제어 구간을 그대로 통과하지 않는다.

### Q6. 주제 완료

- 사용자 의견: 현재 주제를 완료하는 데 동의했다.
- 권장안: 정의, 정상·최적화 시나리오, code path와 최소 excerpt, 공식 release 기반 시대 분류, 사실·추론 분리, 미확인 사항, wikilink, 사용자 용어와 정정이 모두 갖춰졌으므로 현재 주제를 완료한다.
- 합의: 현재 주제를 `completed`로 전환한다. 이후 반대 근거나 새 질문이 나오면 `reopened`로 되돌린다.
- 근거: `WORKFLOW.md`의 8개 완료 조건을 모두 점검했다.

## 정정 및 충돌

- 이전 세션의 권장안은 `qexec_end_mainblock_iterations()`까지를 “scan block iteration의 종료 처리”로 보는 것이었다. 함수가 scan이 없는 set operation과 merge/hash join에도 쓰인다는 점을 고려하면 `scan block iteration`에 종속된 이름은 범위가 좁을 수 있어 재검토한다.
- Repository tag `v11.4.5.1898`을 공식 release tag `v11.4.5`와 동일시하지 않는다. Analytic skip-sort와 limit optimization은 현재 checkout의 develop 동작으로 검증했지만 공식 release 포함 여부는 확정하지 않았으므로 `recent`로 분류하지 않는다.

## 생성·갱신한 지식

- [[Query executor의 main block 실행]] — `scan block iteration`, row 단위 `end-one-iteration`, 독립적인 `main iteration 종료`, `post-processing`의 경계와 analytic 최적화 예외를 보강했다.

## 미해결 사항

- 현재 주제의 핵심 경계에 관한 미해결 사항은 없다.
- Analytic 최적화의 세부 함수별 frame semantics와 stop condition은 이번 경계 주제 밖의 구현 세부다.

## 나중에 다룰 주제

- 없음.

## 재개 위치

현재 주제는 완료했다. 반대 근거나 새 질문이 생기면 `reopened`로 전환한다.

## 다음 후보

1. **Engine:** Broker의 CAS 할당과 연결 인계 — depth 1, 남은 가장 얕은 engine frontier이며 3-tier 접속 흐름을 완성한다.
2. **Development:** C/C++ compiler portability와 GCC-Clang 차이 — depth 1, P1이며 최근 compiler 호환성 변경과 직접 연결된다.
3. **Operations:** CUBRID 구성과 서버 생명주기 — depth 0, 아직 완료되지 않은 가장 얕은 operations 기반 주제다.
