---
name: cubrid-ask
description: 사용자의 CUBRID 질문에 대해 cubrid-til 지식 저장소에서 관련 문서를 찾고, 찾은 문서만을 근거로 답한다. 사용자가 CUBRID 동작·구조·개발 프로세스·운영에 대해 질문하고 새 지식을 쌓기보다 이미 검증된 지식으로 빠른 답을 원할 때 사용한다.
---

# CUBRID Ask

이 스킬은 **읽기 전용 질의응답**이다. 지식 저장소의 문서를 찾아 읽고, 그 문서에 적힌 내용만을 근거로 답한다. 문서에 없는 내용을 아는 것처럼 말하지 않는다.

- 새 지식을 만들거나 코드로 검증하는 작업은 이 스킬의 일이 아니다. 그것은 `cubrid-til` 스킬의 일이다.
- 이 스킬은 저장소의 어떤 파일도 만들거나 수정하지 않고, git 명령도 실행하지 않는다.

## 지식 저장소 위치

이 SKILL.md가 들어 있는 Git 저장소의 root가 지식 저장소다. 다른 경로를 탐색하지 않는다.

## 저장소 지도와 근거 계층

| 대상 | 내용 | 근거로서의 지위 |
|---|---|---|
| `01 Concepts/` ~ `07 Glossary/` | 검증을 거친 canonical note | **1순위 근거. 항상 여기서 먼저 찾는다** |
| `08 Discussion Sessions/` | 문답 세션 기록 | **보조 근거.** canonical note가 없거나 미해결 여부를 확인할 때만. 인용 시 반드시 "세션 합의이며 아직 canonical로 정제되지 않았다"를 명시한다 |
| `Home.md`, 각 폴더의 `* Index.md` | 목차 | 검색 진입점. 그 자체는 근거가 아니다 |
| `Learning State.md` | 학습 진행 상태 | **사용 금지.** 지식이 아니라 상태 파일이다. 열지 않는다 |
| `Templates/`, `.agents/`, `.claude/`, `.github/` | 인프라 | **사용 금지** |

## Frontmatter 읽는 법

모든 note 상단의 frontmatter는 그 문서를 얼마나 믿어도 되는지 알려준다. 답변에 반드시 반영한다.

| 필드 | 값 | 답변에서의 의미 |
|---|---|---|
| `knowledge-status` | `verified` | 코드로 확인된 사실로 전달해도 된다 |
| | `partially-verified` | "코드로 일부 검증됨"이라고 명시한다 |
| | `inferred` | "추론이며 미검증"이라고 명시한다 |
| `learning-status` | `in-progress`, `reopened` | 결론이 바뀔 수 있다고 명시한다 |
| `rationale-evidence` | `inferred` | 설계 의도 설명은 추론임을 명시한다 |
| `code-era` | `historical` | 오래된 코드라는 뜻일 뿐, deprecated라는 뜻이 아니다 |
| `aliases` | 영어 symbol·동의어 목록 | 검색어가 여기 있으면 그 주제의 canonical 진입점이다 |
| `source-commit` | commit hash | 코드 인용 시 이 기준 commit을 함께 적는다 |
| `last-verified` | 날짜 | 문서끼리 충돌하면 최신 쪽을 우선하고 충돌 사실을 답에 명시한다 |

## 절차

### 1단계. 검색어 확장

질문에서 검색어를 2~6개 만든다. 반드시 한국어와 영어를 둘 다 포함한다. note 제목은 한국어지만 본문과 `aliases`에는 C/C++ symbol과 영어 용어가 원문으로 들어 있다.

| 질문에 나온 표현 | 함께 검색할 표현 |
|---|---|
| 실행 계획, 플랜 | XASL, plan, optimizer |
| 브로커, 미들웨어 | broker, CAS |
| 조인 | join, scan |
| 테스트, 회귀 | CTP, regression, testcase |
| 함수명이 나오면 | 함수명 원문 그대로 (예: `execute_mainblock`) |

### 2단계. 문서 찾기

아래 순서대로 시도하고, 충분히 찾으면 다음 단계로 넘어가지 않아도 된다.

1. **제목·aliases 매칭**: 파일 목록과 frontmatter `aliases`에서 검색어가 들어간 note를 찾는다. aliases에 검색어가 있는 note가 그 주제의 canonical 진입점이다.
2. **본문 검색**: content 검색 도구로 `*.md` 전체에서 검색어를 찾는다. `Templates/`, `.agents/`, `.claude/`, `Learning State.md`는 제외한다.
3. **목차 순회**: `Home.md` → 해당 분야 `* Index.md` → note 순서로 내려간다.

찾은 canonical note의 `## 관련 지식` wikilink(선수·후속·관련 지식)를 1-hop 따라가 함께 읽을 후보로 삼는다.

### 3단계. 문서 읽기

- 매칭된 canonical note는 **전체를** 읽는다. 부분만 읽고 답하면 `## 미확인 사항`과 `## 추론한 설계 의도`의 경고를 놓친다.
- 세션 note는 `## 질문과 합의`, `## 정정 및 충돌`, `## 미해결 사항` 위주로 읽는다.
- 문서 안에서 사실과 추론의 경계를 파악한다: `## 관찰된 사실`과 `## 코드 근거`는 사실, `## 추론한 설계 의도`는 추론이다.

### 4단계. 커버리지 판정

| 판정 | 조건 | 행동 |
|---|---|---|
| **전부 커버** | 질문의 답이 문서에 있다 | 문서 근거로만 답한다 |
| **부분 커버** | 일부만 문서에 있다 | 문서 근거 부분과 **[문서 외 지식]** 부분을 나눠서 답한다 |
| **미커버** | 관련 문서가 없다 | 아래 "미커버 질문" 절차를 따른다 |

### 5단계. 답변 작성

한국어로, DB internals 경험이 없는 백엔드 개발자 기준으로 답한다. C/C++ symbol과 CUBRID 공식 용어는 원문을 유지한다. **모든 답변은 예외 없이 아래 3섹션 구조를 지킨다.** 짧은 단답 질문이어도 생략하지 않는다.

```markdown
## 답

(질문에 대한 직접적인 답. 2~6문장. 문서의 설명·비유·시나리오를 적극 재사용한다.)

## 근거 문서

- [[Note 제목]] (`03 Code Walkthroughs/....md`) — knowledge-status: partially-verified, 기준 commit `e1e81d6`
- [[2026-07-23-001 SELECT SQL 실행 경로]] (`08 Discussion Sessions/...`) — 세션 합의, 아직 canonical로 정제되지 않음

## 신뢰도와 한계

(frontmatter 상태, 문서의 미확인 사항, [문서 외 지식]으로 보탠 부분.
 완전 커버면 "문서가 이 질문을 완전히 커버한다" 한 줄.)
```

인용 하드룰:

- 코드 경로·함수명·수치·버전은 **문서에 적힌 것만** 인용하고, 기준 commit을 함께 적는다.
- 문서의 추론(`## 추론한 설계 의도`)을 전달할 때는 문서에 적힌 신뢰도(높음/중간/낮음)와 대안 가설을 함께 전달한다.
- 문서에 없는 일반 지식을 보태야만 답이 되면, 해당 문장 앞에 **[문서 외 지식]** 라벨을 붙이고 검증되지 않았다고 말한다. 라벨 없이 문서 근거와 섞어 말하는 것은 금지다.

## 미커버 질문

관련 문서가 전혀 없으면:

1. `## 답` 첫 문장에서 "지식 저장소에 이 주제의 문서가 아직 없다"고 먼저 말한다.
2. 사용자가 답을 원하므로, 전체를 **[문서 외 지식]**으로 명시하고 일반 지식으로 답한다.
3. `## 근거 문서`에는 가장 가까운 인접 note를 "인접 주제"로 소개한다. 없으면 "없음"이라고 쓴다.
4. `## 신뢰도와 한계` 끝에 아래 고정 포맷으로 큐잉 제안을 붙인다. 사용자가 이 블록을 cubrid-til 세션에 그대로 가져갈 수 있게 하기 위함이다.

```markdown
**cubrid-til 큐잉 제안:** <주제 제목> — <다룰 이유 한 문장> (예상 track: engine|development|operations)
`/skill:cubrid-til` 세션에서 이 주제를 검증·축적할 것을 권한다.
```

## 금지

- 저장소 파일 생성·수정·삭제, git 명령 실행.
- `Learning State.md`를 열거나 인용하는 것.
- 문서에 없는 함수명, 파일 경로, 수치, 버전을 만들어내는 것.
- `inferred`를 사실처럼, `partially-verified`를 `verified`처럼 격상하는 것.
- 문서 근거와 [문서 외 지식]을 라벨 없이 섞어 말하는 것.
- CUBRID source checkout을 탐색해 즉석 검증하는 것. 코드 확인이 필요하면 `/skill:cubrid-til` 세션을 제안한다.

## 예시

질문: "CUBRID에서 SELECT 하면 실행 계획은 누가 만들어?"

1. 검색어: `SELECT`, `실행 계획`, `XASL`, `optimizer`, `CAS`
2. 제목·aliases 매칭: `03 Code Walkthroughs/CAS와 server의 SELECT 처리 경계.md`
3. 문서 전체를 읽고 frontmatter 확인: `knowledge-status: partially-verified`, 기준 commit `e1e81d6`
4. 답: "CAS가 parse → semantic check → rewrite → optimize → XASL 생성까지 담당하고, server는 stream을 받아 cache·역직렬화 후 XASL을 실행한다." + 근거 문서 섹션에 [[CAS와 server의 SELECT 처리 경계]] (partially-verified, `e1e81d6`) + 신뢰도와 한계 섹션.
