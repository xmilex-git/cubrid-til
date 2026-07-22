# CUBRID TIL Repository

이 저장소는 CUBRID 코드, 개발 프로세스, 운영 관례를 한국어로 축적하는 개인 Obsidian 지식베이스다. 대상 독자는 백엔드와 DB 운영 경험은 있지만 CUBRID 및 DBMS 개발 경험은 없는 개발자다.

## Source of truth

- 지식 파일과 학습 상태는 이 저장소에만 저장한다.
- CUBRID 구현 확인에는 사용자가 지정한 별도 source checkout을 사용한다.
- 상담 workflow는 `.agents/skills/cubrid-til/SKILL.md`를 따른다.
- `Learning State.md`가 세션 간 학습 상태의 단일 기준이다.

## Writing rules

- 한국어로 쓰되 실제 C/C++ symbol과 CUBRID 공식 용어는 원문을 유지한다.
- 사실, 사용자 경험, 설계 의도 추론을 구분한다.
- 코드 설명에는 정확한 commit, file, symbol과 최소 excerpt를 포함한다.
- 공식 release 날짜 기준 1년 이내는 `recent`, 이전은 `historical`로 분류한다.
- 개념별 canonical note는 하나만 두고 의미 있는 version 차이만 별도 note로 분리한다.
- 폴더는 안정적인 tree, wikilink는 횡단 graph로 사용한다.
- 사용자가 나중에 다루자고 한 주제는 `Learning State.md`의 후속 주제 큐에 즉시 기록한다.

## Git and confidentiality

- 기본 visibility는 `internal`이다.
- 인증정보, 개인정보, 고객 식별정보, 실제 운영 주소와 계정명은 기록하지 않는다.
- 공개되지 않은 보안 취약점은 `restricted`로 표시하며 자동 push하지 않는다.
- 자동 동기화는 현재 기본 branch에 commit, pull --rebase, push 순서로 수행한다.
- force push, 자동 stash, 자동 충돌 해결을 금지한다.
