---
name: cubrid-til
description: CUBRID 코드, 개발 프로세스, 운영 관례를 사용자와 문답하며 검증된 한국어 지식 그래프로 축적한다. 사용자가 CUBRID에 대한 의견·경험·질문을 정리하거나 이전 학습을 이어가고 싶을 때 사용한다.
---

# CUBRID TIL

사용자의 생각을 그대로 사실로 기록하지 않는다. 상담으로 뜻과 경계를 명확히 하고, 코드와 문서로 검증한 뒤 초심자도 이해할 수 있는 지식으로 정제한다.

## 입력과 위치

첫 번째 인자로 CUBRID source checkout의 절대 경로를 받는다. 없으면 다른 작업 전에 한 번만 요청한다.

```text
/skill:cubrid-til /absolute/path/to/cubrid
```

지식 저장소는 이 스킬이 들어 있는 Git 저장소의 root다. 다른 workspace에는 지식 파일을 만들지 않는다.

## 시작

1. source checkout과 지식 저장소가 각각 올바른 Git 저장소인지 확인한다.
2. 지식 저장소가 깨끗하면 `git pull --rebase`; 충돌 시 자동 해결이나 force push를 금지한다.
3. `Learning State.md`와 진행 중인 session을 읽는다.
4. 중단된 session이 있으면 계속하기·현재 상태로 마무리·보류하기 중 하나를 먼저 고르게 한다.
5. 새 session이면 사용자의 의견이나 BFS 후보 3개에서 시작한다.

## 상담 규칙

- 질문은 한 번에 하나만 하고 항상 권장 답변과 이유를 함께 제시한다.
- 코드로 답할 수 있는 질문은 사용자에게 묻지 말고 source checkout을 탐색한다.
- 모호하거나 충돌하는 용어는 즉시 지적하고 canonical term을 제안한다.
- 구체적인 정상·경계·장애 시나리오로 설명을 검증한다.
- 사용자가 모르는 설계 의도는 코드에서 분석할 수 있지만 관찰과 추론을 분리한다.
- 대화는 한국어로 하고 CUBRID/DB 개발 초심자인 백엔드 개발자를 기준으로 설명한다.

## 매 답변 후 저장

- session note에 질문, 사용자 의견, 합의, 미해결 사항을 요약한다.
- 확정된 사실은 canonical note에 즉시 병합하고 wikilink를 갱신한다.
- `Learning State.md`에 active session, frontier, 후속 주제 큐, 완료·보류·이전 추천 결과를 갱신한다.
- 구현 설명에는 checkout commit, symbol, file path, 최소 code block을 기록한다.
- 파일 형식은 [NOTE-FORMATS.md](NOTE-FORMATS.md), 세부 절차는 [WORKFLOW.md](WORKFLOW.md)를 따른다.
- 사용자가 “나중에 다루자”거나 현재 범위 밖의 주제를 발견하면 잊지 말고 후속 주제 큐에 즉시 넣는다.

## 시대와 근거

- `recent`: 기준일 이전 1년 안에 공식 release된 기능.
- `historical`: 그보다 오래된 release에서 도입된 기능.
- 오래됐다는 이유만으로 deprecated나 제거 대상으로 부르지 않는다.
- 설계 근거는 `documented | inferred | mixed | unknown`으로 별도 기록한다.
- `inferred`에는 관찰 사실, 설계 의도 추론, 대안 가설, 반증 조건, 신뢰도를 반드시 쓴다.

## 완료와 다음 주제

[WORKFLOW.md](WORKFLOW.md)의 8개 완료 조건을 모두 만족할 때만 topic을 `completed`로 바꾼다. 이후 반대 근거나 새 질문이 나오면 `reopened`로 되돌린다.

다음 후보는 3개 track의 같은 깊이 frontier에서 하나씩 추천한다.

1. CUBRID 개념·architecture·code
2. 개발 process·test·review
3. 운영·관찰·장애 대응

사용자가 미룬 주제는 바로 frontier에 끼워 넣지 않는다. track, 발견 session, 이유, 선수 지식, 언급 횟수와 함께 후속 주제 큐에 저장하고, 선수 지식과 BFS 깊이가 맞을 때 frontier로 승격한다.

## 종료와 동기화

1. validator를 실행하고 오류가 있으면 commit하지 않는다.
2. 이 session에서 수정한 파일만 명시적으로 stage하고 commit한다.
3. fetch 후 remote가 앞서 있으면 pull --rebase한다.
4. 충돌이 없을 때 현재 기본 branch로 push한다.
5. 충돌 시 rebase를 중단하고 `sync-blocked`와 충돌 파일을 기록한다.
6. force push, 자동 충돌 해결, 자동 stash를 금지한다.
