# Note Formats

## Canonical knowledge note

```markdown
---
type: concept # concept | architecture | code-walkthrough | process | operation | troubleshooting | glossary
visibility: internal # public | internal | restricted
learning-status: in-progress # in-progress | completed | reopened
knowledge-status: partially-verified # verified | partially-verified | inferred | unknown
code-era: historical # recent | historical | not-applicable
rationale-evidence: inferred # documented | inferred | mixed | unknown
source-release: "11.4"
source-commit: abc1234
last-verified: 2026-07-22
---

# Canonical Korean Title

두 문장 이내의 정의와 이 지식이 필요한 이유.

## 초심자를 위한 설명

## 구체적인 시나리오

## 관찰된 사실

## 코드 근거

**출처:** `src/path/file.cpp:symbol`
**기준 commit:** `abc1234`

```cpp
// 설명에 필요한 최소 코드
```

## 추론한 설계 의도

직접 근거가 없을 때만 작성한다.

### 대안 가설

### 반증 조건

### 신뢰도

높음 / 중간 / 낮음

## 버전별 차이

차이가 의미 있을 때만 별도 version note를 연결한다.

## 미확인 사항

## 관련 지식

- 선수 지식: [[Prerequisite]]
- 후속 지식: [[Follow-up]]
- 관련 지식: [[Related Topic]]
- 토론 기록: [[YYYY-MM-DD-NNN Topic]]
```

`code-era`는 최초 도입 기능이 포함된 공식 release 날짜를 기준으로 한다. 현재 동작 여부는 별도 `lifecycle: active | deprecated | removed | unknown` 필드를 필요할 때 추가한다.

## Discussion session

```markdown
---
type: discussion-session
visibility: internal
session-status: in-progress # in-progress | completed | deferred | interrupted | sync-blocked
started-at: 2026-07-22
source-repository: https://github.com/CUBRID/cubrid
source-branch: develop
source-commit: abc1234
---

# Topic

## 시작 의견

## 질문과 합의

### Q1. 하나의 질문

- 사용자 의견:
- 권장안:
- 합의:
- 근거:

## 정정 및 충돌

## 생성·갱신한 지식

## 미해결 사항

## 나중에 다룰 주제

- [[Deferred Topic]] — 미룬 이유와 필요한 선수 지식

## 재개 위치

## 다음 후보

1. **Engine:** [[Candidate A]] — 깊이와 추천 이유
2. **Development:** [[Candidate B]] — 깊이와 추천 이유
3. **Operations:** [[Candidate C]] — 깊이와 추천 이유
```

## Learning State

State는 현재 상태와 append-only 추천 이력을 함께 가진다.

Required sections:

- `현재 세션`
- `BFS Frontier`
- `후속 주제 큐`
- `완료 주제`
- `이전 추천 결과`
- `보류 및 미해결 질문`

각 frontier row는 track, depth, prerequisite, recommendation count, state를 포함한다. 동일 주제 이름은 기존 canonical note를 가리켜야 하며 새 동의어를 만들지 않는다.

후속 주제 큐의 각 row는 topic, track, tentative depth, source session, reason, prerequisites, mention count, state를 포함한다. `queued` 항목은 선수 지식이 완료되고 해당 BFS depth가 열릴 때만 frontier로 승격한다. 같은 개념을 다시 언급하면 새 row 대신 출처와 언급 횟수를 갱신한다.