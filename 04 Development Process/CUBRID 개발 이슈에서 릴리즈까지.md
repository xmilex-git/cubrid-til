---
type: process
aliases: [JIRA, issue lifecycle, release, code review, squash merge, daily regression]
visibility: internal
learning-status: completed
knowledge-status: partially-verified
code-era: not-applicable
rationale-evidence: mixed
source-release: unknown
source-commit: e1e81d600f604d0fc22ded3066186a1a9aaec184
last-verified: 2026-07-23
---

# CUBRID 개발 이슈에서 릴리즈까지

CUBRID engine 개발은 JIRA issue 선별에서 시작해 분석·개발, 두 build mode의 로컬 CTP, engine/testcase PR과 CI, code review·squash merge, daily regression을 거쳐 release 후보에 누적되는 흐름이다. 이 과정에서 개발자의 로컬 검증, PR 단위 검증, merge 후 daily regression은 서로 다른 시점과 범위의 결함을 찾는다.

## 초심자를 위한 설명

현재 합의한 기본 lifecycle은 다음과 같다.

1. 외부 요청이나 개발자 판단으로 CUBRID JIRA(ORG)에 issue를 작성한다.
2. JIRA에서 `To-triage`를 거쳐 진행 여부를 선별하고 담당 개발자에게 할당한다.
3. 담당자는 issue를 `Analysis`로 바꾸어 원인·영향·해법을 분석하고, 분석이 끝나면 `Develop`로 전환한다.
4. 공식 CUBRID 저장소를 개인 저장소로 fork하고 topic branch에서 engine 변경을 작성한다.
5. 대상 branch를 기준으로 `release`, `optdebug` build를 만들고 개발자가 로컬에서 CTP SQL·medium을 실행한다.
6. 로컬 검증을 통과하고 testcase 변경 범위를 파악하면 개인 branch에서 `CUBRID/cubrid:develop` 대상으로 engine PR을 연다.
7. PR comment `/run all`로 SQL·medium·shell CI를 요청한다. PR 번호에 대응하는 testcase branch와 draft PR이 공개·비공개 testcase 저장소에 자동 생성된다.
8. 공용 CI 인프라가 shell 전체를 병렬 실행한다. 실패한 shell case는 개발자가 로컬 focused runner로 다시 실행해 원인을 좁힌다. 재현되지 않으면 CircleCI REST API로 원 실행을 분석하거나 failed-case rerun을 사용하고, `develop`에서도 발생하는 공용 baseline failure면 사내 Teams 게시판에 제보한다. 보통 QA 조치를 기다린 뒤 각 저장소의 `develop`을 engine PR branch와 두 TC branch에 merge하고 CI를 다시 실행한다.
9. CI 결과로 engine 변경 때문에 기존 TC의 예상 결과나 동작을 바꿔야 하는 범위를 확인한다. 이 단계의 testcase PR은 새 issue 전용 TC 추가가 아니라 기존 TC의 정합성 조정을 담당한다.
10. engine과 기존 TC 변경의 CI·code review를 통과시키고 testcase PR을 먼저 처리한 다음 engine PR을 squash merge한다.
11. merge 직후 JIRA issue를 `Resolved`로 전환한다. 이 상태부터 issue의 주된 ownership은 개발에서 QA 검증으로 넘어간다.
12. QA가 해당 issue의 검증을 시작할 때 `Test`로 전환한다. 이때 issue의 새 동작·결함을 직접 검증하는 신규 회귀 TC를 category에 맞게 준비하고, 수정 build에서 실제로 성공하는지 확인한다. 작동이 확인된 신규 TC만 testcase repository에 merge하며, issue 검증을 완료하면 `Closed`로 전환한다.
13. `Test` 과정에서 검증·merge한 TC는 일회성 검증 후 폐기하지 않고 daily regression suite의 지속적인 회귀 자산으로 편입한다.
14. merge된 변경과 누적 TC는 이후 build의 daily regression에서 Function·Performance·MemoryLeak·Verify Status 관점으로 매일 검증된다.
15. daily regression에서 신규 회귀가 발견되면 QA가 CUBRID JIRA(ORG)에 regression issue를 등록한다.
16. 검증된 변경들이 release scope와 안정화 과정을 거쳐 정식 release에 포함된다. 정확한 release 선별·branch·승인 절차는 아직 미확인이다.

## 구체적인 시나리오

정상 시나리오에서는 기능 issue가 triage에서 채택되고 개발자가 engine을 변경한다. 로컬 `release`·`optdebug` CTP를 통과한 뒤 engine PR을 열면 `tc/pr-<PR 번호>` branch가 두 testcase 저장소에 만들어진다. `/run all`에서 기존 TC의 expected result나 동작이 새 specification과 맞지 않는 부분을 찾아 bot 연계 testcase PR에서 조정한다. 이 기존 TC 변경과 engine review를 통과시키고 testcase PR을 먼저 처리한 뒤 engine PR을 squash merge하며 issue를 `Resolved`로 넘긴다. 이후 QA가 `Test`에서 해당 issue를 위한 신규 category TC를 별도로 만들고 수정 build에서 검증한다. 작동하는 신규 TC만 testcase repository에 merge하고 검증 완료 후 `Closed`로 전환하며, 신규 TC는 이후 매일 daily regression에서 실행된다.

장애 시나리오에서는 어떤 issue가 `Closed`된 뒤에도 그때 등록한 TC가 훗날 다른 engine 변경으로 실패할 수 있다. 이 경우 과거 issue를 단순히 끝난 기록으로만 보지 않고, daily regression이 회귀를 탐지하면 QA가 별도 regression JIRA issue를 등록해 새 개발 lifecycle을 시작한다는 것이 사용자 경험이다.

## 관찰된 사실

### 공식 문서와 repository automation

- `CONTRIBUTING.md`는 개인 fork, topic branch, 공식 저장소로의 PR, base `develop` 흐름을 문서화한다.
- GitHub comment workflow는 `/run all`, `/run shell`, `/run sql`, `/run medium`을 허용하고 CircleCI parameter로 변환한다.
- engine PR이 열리면 `tc/pr-<PR 번호>` branch와 draft PR을 `cubrid-testcases`, `cubrid-testcases-private-ex`에 자동 생성한다.
- CircleCI는 engine PR test에서 같은 번호의 testcase branch를 우선 찾고, 없으면 testcase `develop`로 fallback한다.
- open testcase PR이 있으면 engine PR의 TC merge gate는 실패한다. bot 안내도 testcase PR을 먼저 merge한 뒤 engine PR을 merge하라고 명시한다.
- 두 testcase 저장소의 `.github/CODEOWNERS`는 suite path별 owner rule을 둔다. 공개 저장소는 `/sql/`, `/medium/`, `/isolation/`, private-ex는 `/shell/`, `/shell_heavy/` 변경에 code owner review를 연결한다.
- 현재 CircleCI source는 release와 optdebug build job을 병렬 실행하고 SQL·medium·shell suite를 parameter에 따라 실행한다.
- Shell 전체는 공용 CI 인프라에서 병렬 실행하고, 개발자는 실패한 case만 로컬 focused CTP로 재현한다.
- 로컬 재현이 되지 않으면 CircleCI REST API로 원 실행을 분석하거나 failed-case rerun을 사용한다. PR과 무관하게 `develop`에서도 실패하는 case로 의심되면 baseline을 비교하고 사내 Teams 게시판에 공용 문제로 제보한다.
- 기존 baseline failure가 확인돼도 일반적으로 현재 PR merge를 계속하지 않는다. QA가 문제를 처리하면 engine `develop`과 각 testcase 저장소 `develop`을 각각 engine PR branch와 공개·비공개 TC branch에 merge한 뒤 다시 실행한다.
- SQL·shell CI는 testcase `develop` 자체가 아니라 `tc/pr-<PR 번호>` branch를 우선 사용한다.
- 예외적으로 repository 관리 책임자가 failing gate를 우회해 merge하도록 판정하는 경우를 현업에서 “강제 머지”라고 부른다. Repository 관리자만 수행할 수 있고 일반 개발자는 실행할 수 없으며, Git의 force push와는 다른 branch-protection 예외 merge다.

### PR #7516 사례

- engine PR #7516은 2026-07-22 `develop` 대상으로 열렸다.
- 공개 testcase PR #3107은 29초 뒤, 비공개 testcase PR #3715는 약 4분 뒤 `tc/pr-7516`에서 `develop` 대상으로 draft 생성되었다.
- 두 PR의 최초 commit message는 `chore: Initialize TC branch for PR #7516`이고, 확인 시점에는 testcase file 변경이 없었다. 즉 자동화가 PR 시점의 testcase base에서 작업 branch와 빈 초기화 commit을 먼저 준비한다는 사례다.
- engine PR bot comment는 두 testcase PR link를 제공했고, open testcase PR 때문에 TC merge gate가 실패한 실행도 확인되었다.
- 확인 시점에 engine PR과 두 testcase PR은 모두 open 상태였으므로 이후 merge 결과의 사례로 사용하지 않는다.

### 사용자 현업 경험

- issue 유입은 외부 요청과 개발자 자체 판단 모두 가능하다.
- JIRA의 실무 상태 흐름은 `To-triage → Analysis → Develop`이다.
- 로컬 사전 검증은 대상 branch 기준 `release`, `optdebug` build에서 SQL·medium CTP를 실행한다.
- PR CI와 testcase 변경을 모두 통과시키고 engine/testcase code review 후 squash merge한다.
- Squash merge 직후 issue를 `Resolved`로 만들며 이때부터 QA 작업으로 넘어간다. QA가 issue 검증을 시작하면 `Test`, 검증을 완료하면 `Closed`로 전환한다.
- Engine PR과 연결된 pre-merge testcase PR은 engine 변경으로 인해 기존 TC를 수정해야 하는 경우를 처리한다. 해당 issue의 신규 회귀 TC는 engine merge와 `Resolved` 이후 QA `Test` 단계에서 별도로 처리한다.
- Pre-merge 기존 TC 변경 PR에는 변경 path의 CODEOWNER가 자동 reviewer로 추가된다. 개발자가 변경을 제안하고 code owner review를 거쳐 merge한다.
- QA는 `Test` 과정에서 변경 성격에 맞는 category TC를 수정 build로 검증한다. 실제로 작동하는 TC만 testcase repository에 merge하며, 이 TC는 issue를 닫기 위한 일회성 산출물이 아니라 이후 daily regression에서 매일 반복 실행되는 지속적인 회귀 자산이다.
- merge 후 QA Home daily regression이 기능, 성능, memory leak 회귀를 검증하며 신규 회귀는 QA가 JIRA issue로 되돌린다.
- Daily regression에서 `Fail Total`은 known failure를 포함한 전체 실패, `Fail New`는 기준 build 대비 새 regression 후보이며 QA가 `Fail New`를 우선 확인한다.
- QA는 `Fail New`를 분석해 실제 engine regression이면 새 JIRA issue를 만들고, 불규칙한 testcase 문제는 unstable case, 환경·인프라 문제는 test error로 분류한 뒤 Verify Status에 판정 결과를 반영한다.

이 항목들은 사용자의 CUBRID 개발 경험으로 기록했으며, repository source가 직접 규정하지 않는 team convention을 포함한다.

## 코드 근거

**출처:** `CONTRIBUTING.md:How to submit a pull request`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```text
* Fork CUBRID project.
* Make a topic branch. Make your changes to this branch.
* Issue a pull request on CUBRID repository. Base branch for a pull request would be develop.
```

**출처:** `.github/workflows/comment_trigger.yml:run_test`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```bash
TEST_TYPES="shell sql medium"
# /run all이면 세 suite의 pipeline parameter를 모두 true로 만든다.
```

**출처:** `.github/workflows/tc-branch-sync.yml:sync-tc-branch`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```bash
BRANCH_NAME="tc/pr-${PR_NUMBER}"
git commit --allow-empty -m "chore: Initialize TC branch for PR #${PR_NUMBER}"
```

**출처:** `.circleci/config.yml:resolve-testcases`
**기준 commit:** `e1e81d600f604d0fc22ded3066186a1a9aaec184`

```bash
TC_BRANCH="tc/pr-${CIRCLE_BRANCH//[^0-9]/}"
# 해당 branch가 없으면 testcase develop로 fallback한다.
```

## Process 참고 근거

- `cubrid-jira-issue-write/SKILL.md`, workspace commit `eb2d1152`: bug, 기능·성능 개선·개발·refactoring, 내부 관리 작업별 JIRA Description template과 작성 원칙
- `ctp-parallel/SKILL.md`, workspace commit `eb2d1152`: build와 testcase checkout을 입력으로 받아 CTP SQL을 top-level `_*` bulk 단위로 병렬 실행하고 결과를 합치는 로컬 실행 절차
- `cubrid-shell-run/SKILL.md`, workspace commit `eb2d1152`: CI 실패 shell case만 현재 CUBRID install 또는 고정 OptDebug install로 focused 재현하는 절차
- GitHub engine PR #7516 및 연결된 testcase PR #3107, private-ex PR #3715의 2026-07-23 상태
- `cubrid-testcases/.github/CODEOWNERS` blob `25361e8d`, `cubrid-testcases-private-ex/.github/CODEOWNERS` blob `61a0901f`: suite path별 code owner rule. 실제 owner 계정·팀 이름은 저장하지 않았다.

내부 JIRA와 QA 운영 주소, 인증정보, 계정명은 저장하지 않았다.

## 추론한 설계 의도

로컬 CTP, PR CI, issue별 QA 검증, daily regression을 중복 실행하는 이유는 같은 검사를 반복하기보다 피드백 속도와 검증 범위를 단계적으로 넓히기 위한 것으로 추론한다. 로컬 검증은 개발자가 빠르게 obvious regression을 제거하고, PR CI는 engine과 같은 번호의 testcase 변경을 결합하며, issue별 QA는 acceptance를 판정하고 category TC를 회귀 자산으로 등록한다. Daily regression은 이렇게 누적된 TC로 merge된 여러 변경과 더 넓은 기능·성능·memory leak 조합을 계속 검증한다.

`Resolved`를 merge 직후 사용하고 그 뒤 `Test → Closed`를 QA가 진행하는 상태 모델은 code completion과 verification completion을 분리한다. 즉 merge는 개발 구현의 완료이지 issue lifecycle 전체의 완료가 아니다.

사용자의 “TC는 평생 돈다”는 표현은 TC가 일회성 검증과 함께 버려지지 않고 daily regression corpus에 누적된다는 의미로 해석한다. 사양 폐기, 중복, 불안정성 등의 이유로 TC를 비활성화하거나 제거하는 예외 정책은 아직 확인하지 않았으므로 literal한 영구 보장을 뜻하지는 않는다.

Testcase 저장소를 engine과 분리하면서 PR 번호로 branch를 결합한 것은 testcase의 별도 review/history를 유지하면서 engine 변경과 정확한 test baseline을 맞추려는 설계로 보인다.

Pre-merge TC 경로와 post-merge QA TC 경로를 나눈 것은 두 위험을 분리한다. 전자는 engine 변경이 기존 regression corpus를 의도치 않게 깨뜨리거나 specification 변경으로 expected result가 달라지는 문제를 merge 전에 정리한다. 후자는 구현이 merge된 뒤 QA가 issue의 acceptance를 독립적으로 확인하고 재발 방지 TC를 새로 축적한다.

기존 TC와 expected result 변경에 CODEOWNER review를 요구하는 구조는 engine 작성자가 자신의 동작 변경을 스스로 정상으로 확정하지 못하게 하는 독립 검증 경계로 해석한다. 이는 specification 변화에 필요한 TC 갱신과 실제 regression을 가리는 변경을 구분하는 데 중요하다.

### 대안 가설

- 두 testcase 저장소 분리는 test 성격보다 공개 범위와 실행 인프라 제약이 주된 이유일 수 있다.
- local release·optdebug 이중 검증은 공식 필수 gate가 아니라 담당자나 변경 위험도에 따라 달라지는 관례일 수 있다.
- release 포함 여부는 daily regression 결과보다 별도 roadmap·backport·release branch 정책이 더 크게 결정할 수 있다.

### 반증 조건

- 공식 process 문서에서 다른 필수 build mode나 suite를 규정하면 로컬 검증 단계를 수정해야 한다.
- branch protection과 CI 설정에서 testcase PR 처리 순서가 바뀌면 merge 순서를 수정해야 한다.
- release 운영 문서가 issue 상태와 release 포함 절차를 명시하면 마지막 단계를 그 근거로 대체해야 한다.

### 신뢰도

중간

## 버전별 차이

- `tc/pr-<PR 번호>` 동기화는 2026-03-13 commit `d90111c4`, TC merge gate는 2026-04-23 commit `175442fc`에서 도입된 최근 process 변화다. 공식 product release에 포함되는 기능이 아니라 repository workflow이므로 product의 `recent`/`historical` 분류는 적용하지 않았다.
- 그 이전 PR의 testcase 연결 방식은 아직 확인하지 않았다.

## 미확인 사항

- CODEOWNER review의 필수 승인 수와 branch protection 세부 조건
- 누적 TC를 비활성화·수정·삭제할 수 있는 예외와 승인 정책
- `To-triage`, `Analysis`, `Develop`, `Resolved`, `Test`, `Closed`의 transition 권한과 자동화 여부
- local SQL·medium 이외에 변경 유형별로 요구되는 suite
- Unstable case의 반복성 기준, test error의 세부 범위와 Verify Status 값별 의미
- 관리자 예외 merge의 승인 기록과 사후 추적 방식
- 사내 Teams 제보의 필수 정보와 후속 ownership
- release scope 선별, release branch, 안정화와 최종 승인 절차

## 관련 지식

- 선수 지식: [[CUBRID 3-tier 구조]]
- 후속 지식: [[CUBRID 개발 변경의 테스트 계층과 PR 흐름]]
- 관련 지식: [[CAS와 server의 SELECT 처리 경계]]
- 토론 기록: [[2026-07-23-002 CUBRID 개발 테스트 흐름]]
