---
type: process
visibility: internal
learning-status: completed
knowledge-status: partially-verified
code-era: not-applicable
rationale-evidence: mixed
source-release: unknown
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-23
---

# CUBRID 개발 변경의 테스트 계층과 PR 흐름

CUBRID engine 변경의 실제 검증 중심은 외부 testcase 저장소와 CTP를 사용하는 기능·비기능 테스트이며, 결과는 내부 QA Home에서 build별로 집계된다. source tree의 `unit_tests/`와 QA Home의 `unittest`, `unittest_debug` category도 존재하지만 각각 4건뿐인 사용자 제공 화면과 현업 경험을 근거로 주된 회귀 검증 경로가 아니라 거의 사장된 보조 경로로 본다.

## 초심자를 위한 설명

백엔드 애플리케이션의 일반적인 test pyramid를 그대로 대입하면 CUBRID의 실제 흐름을 잘못 이해할 수 있다. 현재 확인된 중심 흐름은 다음과 같다.

1. 변경에 대응하는 SQL·medium·shell·CCI testcase를 별도 testcase 저장소에 준비한다.
2. CTP/CI 환경이 CUBRID build와 testcase branch를 결합해 기능 회귀 테스트를 수행한다.
3. QA Home의 Function에서 build별 total/testing/success, 전체·신규 failure, test/fail rate, elapsed time과 unstable case 상태를 확인한다.
4. Performance와 MemoryLeak tab에서 성능 회귀와 memory leak 회귀를 별도로 확인하고, Verify Status에서 판정 상태를 추적한다.
5. engine PR에서는 GitHub Actions 정적 검사와 testcase PR merge gate를 함께 통과한다.

QA가 issue를 검증하면서 준비한 category TC는 수정 build에서 실제 동작과 성공을 확인한 뒤에만 testcase repository에 merge한다. Merge된 TC는 해당 issue의 일회성 증거에 그치지 않고 daily regression corpus에 누적되어 이후 build에서도 반복 실행된다.

Testcase 변경에는 시점과 목적이 다른 두 경로가 있다.

1. **Engine merge 전 기존 TC 조정:** engine PR의 `/run all`과 bot이 만든 `tc/pr-<PR 번호>` branch에서 기존 TC가 새 engine 동작과 맞지 않는 부분을 확인·수정한다. TC merge gate 때문에 이 PR은 engine보다 먼저 처리한다.
2. **Engine merge 후 신규 TC 추가:** issue가 `Resolved → Test`로 넘어가면 QA가 해당 issue를 직접 검증하는 신규 category TC를 만들고, 수정 build에서 작동을 확인한 뒤 testcase repository에 merge한다.

Pre-merge 기존 TC 변경은 개발자가 제안하고, 변경 suite의 CODEOWNER가 PR에 자동 reviewer로 추가되어 review한다.

Shell은 비용과 환경 의존성이 커서 전체 suite를 개발자 PC에서 선실행하지 않는다. PR의 공용 CI 인프라가 shell을 병렬 실행하고, 실패한 case만 개발자가 로컬 focused runner로 재현·분석한다.

`unit_tests/`는 CMake option과 test executable이 남아 있는 구현 경로다. 그러나 이것을 현재 CUBRID 개발 테스트의 첫 단계나 일반적인 PR gate로 설명해서는 안 된다.

## 구체적인 시나리오

예를 들어 SQL 함수의 NULL 처리 규칙을 고친다면, 사용자가 실행하는 SQL의 result와 error를 testcase로 만들고 해당 engine PR과 연결된 testcase branch에서 CTP를 실행하는 것이 현재 확인된 주 흐름이다. 단순 success만 보지 않고 기존 failure인지 새 failure인지, 검증 완료 build가 무엇인지도 QA Home에서 확인한다.

반면 내부 자료구조만 바뀌어 SQL로 안정적으로 재현하기 어려운 경우 실제로 어떤 testcase를 작성하고 어떤 별도 검증을 요구하는지는 아직 미확인이다.

## 관찰된 사실

- 최상위 CMake는 `UNIT_TESTS` 또는 `UNIT_TEST_.*` 값 중 하나가 `ON`일 때만 `unit_tests` subdirectory를 추가한다.
- `unit_tests/CMakeLists.txt`는 Catch2 v2.11.3을 가져오고 module별 executable을 조건부로 build한다.
- 기준 commit의 tracked CMake에서는 `enable_testing()`, `add_test()`, `catch_discover_tests()`를 찾지 못했다. 따라서 `unit_tests/AGENTS.md`의 “CTest에 등록된다”는 설명은 현재 구현과 일치하지 않으며, `ctest`가 이 executable들을 실행한다고 아직 확정할 수 없다.
- 사용자 경험에 따르면 이 `unit_tests` 경로는 거의 사장되었고 일반적인 개발 테스트의 중심이 아니다. 이는 관찰된 코드 사실이 아니라 현업 관례에 대한 사용자 증언이다.
- CircleCI의 `sql`·`medium` test는 `cubrid-testcases`, `shell` test는 `cubrid-testcases-private-ex`를 사용한다.
- CircleCI shell job은 공용 전용 executor에서 test list를 timing 기준으로 분할해 병렬 실행한다.
- PR test 실행 시 CircleCI는 먼저 `tc/pr-<PR 번호>` branch를 찾고, 없으면 testcase 저장소의 `develop`로 fallback한다.
- 따라서 engine PR의 SQL·shell은 testcase `develop`를 직접 고정해 실행하는 것이 아니라, engine PR branch와 같은 번호의 공개·비공개 TC branch를 결합해 실행한다.
- `/run all|shell|sql|medium` 형식의 engine PR comment가 CircleCI pipeline parameter로 변환된다.
- develop 대상 engine PR이 열리면 두 testcase 저장소에 같은 이름의 branch와 draft PR을 만드는 workflow가 있다. 열린 testcase PR이 남아 있으면 merge gate는 실패한다.
- GitHub `check.yml`의 정적 검사는 DB 동작 회귀 테스트와 별개다.
- 2026-07-23 인증 후 자동 추출한 최근 세 build functional summary에서는 `sql`, `sql_debug`, `medium`, `medium_debug`, `shell`, `cci`, `cci_debug`가 공통으로 확인되었다. 이 추출은 전체 category를 포착하지 못했으며, 이후 사용자 제공 화면에서 더 넓은 목록을 확인했다.
- 사용자 제공 QA Home 화면에는 `sql`, `sql_debug`, `medium`, `medium_debug`, `sql_by_cci`, `shell`, `shell_debug`, `shell_heavy`, `shell_long`, `cci`, `cci_debug`, `ha_shell`, `ha_repl`, `ha_repl_debug`, `shell_perf`, `isolation`, `isolation_debug`, `jdbc`, `RQG`, `cdc_repl`, `shell_ext`, `unittest`, `unittest_debug`가 표시된다.
- 같은 화면에서 `unittest`와 `unittest_debug`는 각각 total 4건이다. SQL 계열은 17,442건, shell은 3,433건 등으로 규모 차이가 크므로, unit test가 존재하지 않는 것이 아니라 현재 회귀 suite에서 차지하는 비중이 매우 작다고 정정한다.
- QA Home은 build별로 Function, Performance, MemoryLeak, Verify Status를 구분하며 성능 회귀와 memory leak 회귀도 확인할 수 있다.
- 사용자 현업 경험에 따르면 QA는 issue의 `Test` 단계에서 category에 맞는 TC를 등록하고, 등록된 TC는 이후 daily regression에서 매일 지속적으로 실행된다.
- QA는 TC가 수정 build에서 실제로 작동하는지 확인하며, 검증된 TC만 testcase repository에 merge한다.
- Engine PR 전에 bot branch에서 처리하는 TC 변경은 기존 TC 조정이고, 해당 issue의 신규 regression TC는 engine merge 뒤 QA `Test` 단계에서 별도로 추가한다.
- 공개 testcase 저장소의 CODEOWNERS는 `/sql/`, `/medium/`, `/isolation/`, private-ex는 `/shell/`, `/shell_heavy/` path에 owner rule을 두며, 사용자 경험에 따르면 해당 owner가 PR reviewer로 자동 추가된다.
- 개발자는 공용 CI에서 실패한 shell case만 로컬 `cubrid-shell-run` workflow로 다시 실행한다. 표준 runner는 CTP `ctp.sh shell`이며 현재 PATH의 CUBRID install을 사용하므로 실행 전 `cubrid_rel`로 revision을 확인해야 한다.
- 단일 case나 subtree는 `just shell-debug`, 서로 떨어진 여러 failure는 `just shell-debug-selected`, CircleCI build type과 맞춘 재현은 OptDebug install을 고정하는 `just shell-debug-optdebug`를 사용한다.
- Focused run은 임시 conf에서 testcase 자동 update와 기본 exclude list를 끄므로, debug 도중 checkout이 바뀌거나 조사 대상 case가 조용히 제외되는 일을 막는다.
- 로컬에서 재현되지 않으면 CircleCI REST API로 원 실행의 job·shard·artifact와 환경을 분석하거나 CircleCI의 failed-case rerun 기능으로 실패 case만 다시 실행한다.
- PR 변경과 무관하게 `develop`에서도 실패하는 기존 baseline 문제로 의심되면 develop 결과와 비교하고, 공용 장애로 사내 Teams 게시판에 제보한다.
- 기존 baseline failure는 보통 현재 PR에서 무시하지 않는다. QA가 공용 문제를 수정할 때까지 기다린 뒤 engine 저장소 `develop`은 engine PR branch로, 각 testcase 저장소 `develop`은 대응하는 `tc/pr-<번호>` branch로 merge하고 CI를 재실행한다.
- 예외적으로 repository 관리 책임자의 판정에 따라 failing gate를 우회해 merge하는 경우를 현업에서 “강제 머지”라고 부르지만, repository 관리자만 수행할 수 있으며 일반 개발자는 실행할 수 없다. 이는 `git push --force`가 아니라 branch-protection 예외 merge다.
- Functional Result는 total, testing, success, fail(total/new), rate(test/fail), elapsed time, test date, unstable case(total/new/trend/verified rate)를 표시하고, 실행 중이거나 결과가 없는 category는 `NO RESULT (OR RUNNING)`으로 나타낸다.
- 사용자 현업 경험에 따르면 `Fail Total`은 known failure를 포함한 현재 전체 실패 수이고, `Fail New`는 기준 build 대비 새로 발생한 regression 후보다. QA는 `Fail New`를 우선 triage한다.
- QA는 `Fail New`를 재현·분석한 뒤 실제 engine regression이면 JIRA regression issue를 등록하고, 반복성이 낮은 TC 문제는 unstable case, 환경·인프라 문제는 test error로 분류한다. 조사·판정 결과는 Verify Status에 반영한다.
- Functional report는 sustaining과 regression을 나누며 total, testing, success, fail, rate, test build, verified build를 집계한다.
- Non-functional summary에는 YCSB, SysBench, TPC-C, TPC-W, basic performance, Dots stability 결과가 있다. 별도 report 메뉴에는 unstable case, time trend, test error status, HA replication performance가 있다.

## 코드 근거

**출처:** `CMakeLists.txt:with_unit_tests`, `CMakeLists.txt`의 unit test subdirectory 선택
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```cmake
if(var MATCHES "^(UNIT_TESTS|UNIT_TEST_.*)$")
  if(${${var}} STREQUAL "ON")
    set(${res} 1 PARENT_SCOPE)
  endif()
endif()

if(AT_LEAST_ONE_UNIT_TEST)
  add_subdirectory(unit_tests)
endif()
```

**출처:** `.circleci/config.yml:resolve-testcases`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```bash
TC_BRANCH="tc/pr-${CIRCLE_BRANCH//[^0-9]/}"
# branch가 없으면 아래 로직에서 TC_BRANCH="develop"로 fallback한다.
```

**출처:** `.github/workflows/tc-merge-gate.yml:check-tc-prs`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```bash
BRANCH_NAME="tc/pr-${PR_NUMBER}"
OPEN_PR=$(gh pr list --repo "${OWNER}/${TC_REPO}" --head "${BRANCH_NAME}" --state open ...)
```

**운영 근거:** 내부 QA Home의 최근 build functional/non-functional summary 및 report tree
**확인일:** `2026-07-23`

- 인증정보, session cookie, 실제 계정명과 내부 운영 식별자는 저장하지 않았다.

**로컬 process 근거:** `cubrid-shell-run/SKILL.md`
**workspace 기준 commit:** `eb2d1152bb0724b7e8957b5d0538d90cb9c55b8d`

```text
공용 CI: full shell parallel run
로컬: failed case만 shell-debug 또는 shell-debug-selected로 집중 재현
CI 일치 재현: OptDebug install을 고정하고 shell-debug-optdebug 실행
```

## 추론한 설계 의도

관찰 사실은 source에 module test executable이 남아 있고 QA Home에도 `unittest` 계열이 존재하지만, 사용자 제공 화면에서 각각 4건에 불과한 반면 주요 SQL·shell category는 수천~수만 건이라는 것이다. 사용자 경험까지 합치면 CUBRID는 unit test pyramid보다 설치된 DBMS를 대상으로 한 회귀·지속 검증을 실무 중심에 둔다고 추론한다.

QA 검증 중 만든 TC를 daily regression에 계속 누적하는 구조는 과거 결함의 재발 방지 지식을 실행 가능한 형태로 보존하는 방식으로 해석할 수 있다. JIRA issue는 `Closed`되어도 그 issue에서 얻은 회귀 조건은 TC로 계속 살아남는다.

전체 failure와 신규 failure를 분리하는 것은 daily regression에 이미 알려진 failure가 남아 있더라도 새 engine 변경이 만든 회귀를 빠르게 찾기 위한 것으로 해석한다. 따라서 `Fail Total > 0`만으로 신규 build를 판단하지 않고 `Fail New`를 우선 조사한다.

`Fail New`를 곧바로 engine defect로 확정하지 않고 재현성과 실패 원인을 분류하는 이유는 engine code, testcase 자체, 실행 환경이 모두 실패 원인이 될 수 있기 때문이다. Verify Status는 이 triage 결과를 build report에 되돌리는 역할로 해석한다.

Shell을 공용 CI와 로컬 focused rerun의 두 단계로 나누는 것은 전체 suite의 높은 비용과 환경 격리는 공용 인프라가 담당하고, 개발자의 반복 디버깅은 실패 case에만 집중하려는 구조로 해석한다.

로컬 재현, CircleCI failed-case rerun과 develop baseline 비교를 순서대로 사용하는 것은 PR이 만든 regression, flaky testcase, 공용 인프라 문제와 기존 baseline failure를 분리하기 위한 것으로 해석한다. Teams 제보는 개별 PR 범위를 벗어난 공용 실패를 공유·추적하는 handoff다.

Baseline 문제가 고쳐진 뒤 세 저장소의 `develop`을 각 PR branch에 merge해 다시 실행하는 것은 engine code와 공개·비공개 testcase가 동일한 최신 baseline 위에서 검증되게 만든다. CircleCI가 TC branch를 우선 선택하므로 testcase `develop`의 수정은 해당 TC branch로 가져오지 않으면 PR CI에 반영되지 않는다.

TC branch를 engine PR 번호로 결합한 것은 engine 코드와 testcase 변경을 같은 CI 실행에서 검증하면서도 저장소와 review 권한을 분리하려는 의도로 보인다. workflow comment에는 testcase PR을 먼저 merge하라는 순서가 직접 적혀 있어 이 부분은 documented 근거와 구현 근거가 섞여 있다.

### 대안 가설

- module test가 과거에는 일반적인 개발 gate였으나 자동화 연결이 끊긴 뒤 잔존 코드만 남았을 수 있다.
- QA Home의 4개 `unittest`가 source tree의 어떤 executable과 대응하는지에 따라 실제 사용 범위가 화면의 건수보다 넓거나 좁을 수 있다.
- testcase 저장소 분리는 테스트 계층 설계보다 공개 범위 또는 운영 인프라 제약이 주된 이유일 수 있다.

### 반증 조건

- 최근 engine PR의 필수 check나 build log에서 module test가 지속적으로 실행된다는 증거가 나오면 “거의 사장됨”의 범위를 수정해야 한다.
- 테스트 저장소 분리의 공식 ADR 또는 운영 문서가 별도 이유를 명시하면 계층화 의도 추론을 수정해야 한다.

### 신뢰도

중간

## 버전별 차이

- module unit test CMake 구조는 Git 이력상 2017년부터 존재하지만 정확한 최초 공식 release는 아직 확인하지 않았다.
- `tc/pr-<PR 번호>` 동기화는 2026-03-13 commit `d90111c4`, merge gate는 2026-04-23 commit `175442fc`에서 도입된 것으로 관찰했다. 기준일 현재 공식 release 포함 여부는 미확인이다.

## 미확인 사항

- 과거 unit test가 실제 gate였던 시기와 사장된 계기
- QA Home의 `unittest` 4건과 source tree의 module test executable 사이의 대응 관계
- SQL·medium·shell·CCI suite 각각의 정확한 책임과 testcase 형식
- Unstable case의 반복성 기준, test error의 세부 범위와 Verify Status 값별 의미
- 관리자 예외 merge의 승인 기록과 사후 추적 방식
- 사내 Teams 제보의 필수 정보와 후속 ownership
- 누적 testcase의 비활성화·수정·삭제 정책
- CODEOWNER review의 필수 승인 수와 branch protection 세부 조건
- 변경 유형별 필수 test 선택 규칙이 공식 문서나 team convention으로 존재하는지
- CI/Jenkins/CircleCI와 실제 branch protection 사이의 최종 필수 gate 목록
- 각 테스트 구조가 처음 포함된 공식 release와 release 날짜

## 관련 지식

- 선수 지식: [[CUBRID 3-tier 구조]]
- 상위 process: [[CUBRID 개발 이슈에서 릴리즈까지]]
- 후속 지식: CUBRID testcase 작성과 CTP 실행(아직 canonical note 미생성)
- 관련 지식: [[CAS와 server의 SELECT 처리 경계]]
- 토론 기록: [[2026-07-23-002 CUBRID 개발 테스트 흐름]]
