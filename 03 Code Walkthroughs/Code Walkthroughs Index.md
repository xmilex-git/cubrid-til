---
type: index
visibility: internal
---

# Code Walkthroughs Index

구체적인 CUBRID 호출 경로, 자료구조와 동작을 commit 기준으로 해설한다.

## Topics

- [[CAS와 server의 SELECT 처리 경계]] — CAS의 SQL compile과 server의 XASL execute 경계
- [[Query executor의 main block 실행]] — `execute_mainblock`의 child, scan, 후처리 실행 단계
- [[Page latch promotion 호출 경로]] — file 자동 확장과 B-tree split·merge에서 READ latch를 WRITE로 승격하는 12개 caller

## Related

- [[Architecture Index]]
- [[Sources Index]]
