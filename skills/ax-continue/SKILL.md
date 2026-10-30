---
name: ax-continue
description: 긴 업무 대화의 핵심 상태를 보존하고 선택형 안내창을 통해 같은 프로젝트의 새 Codex 채팅으로 이어간다.
---

## 언제

사용자의 이어가기 요청, 주요 단계 완료, 또는 `python scripts/ax.py context`의 recommend_handoff=true가 계기다. 사용량은 마지막 입력/한도 추정치이며 정확한 앱 점유율이 아니다. 기록이 없거나 오래되면 수치를 추측하지 않는다. 단순히 자료를 설명하는 질문만으로 채팅을 만들지 않는다.

## 선택 안내

현재 사용자가 이미 새 채팅 생성을 요청했으면 재확인하지 않는다. 그렇지 않으면 request_user_input_async를 사용해 ‘새 채팅에서 이어가기 / 현재 채팅 유지’를 제공한다. 해당 도구가 없으면 텍스트로 선택을 받고 기다린다. codex-followup만을 유일한 작동 버튼으로 쓰지 않는다. async 질문은 즉시 반환되므로 accepted만 보고 사용자가 선택했다고 간주하지 않는다. 유지 선택 시 `python scripts/ax.py dismiss-context`로 해당 경고를 잠시 끄고, 업무를 계속한다.

## 인계와 전환

1. 현재 고객과 작업 scope가 명확한지 확인한다. state.json/brief.md/decisions.md에 목표·최신 결정·제약·미결정·다음 행동을 갱신한다. 이번 사용자 요청과 승인 범위를 그대로 보존한다. 모든 원문을 복사하지 않는다.
2. `python scripts/ax.py checkpoint <client>` 실행. 오류가 있으면 빠진 다음 작업·출처·산출물을 바로잡고 재실행한다. 반환된 checkpoint ID와 prompt를 사용한다. checkpoint 파일을 직접 수정하지 않는다.
3. 앱의 list_projects/create_thread/wait_threads/navigate_to_codex_page를 이름으로 발견한다. 같은 경로의 로컬 프로젝트 ID를 사용하고 모델·추론 설정은 임의 변경하지 않는다. fork는 전체 이력을 복사하므로 새 컨텍스트 인계에는 사용하지 않는다.
4. create_thread 호출 전 해당 체크포인트 delivery.json을 확인한다. target_thread가 있으면 같은 시험/요청을 중복 생성하지 않는다. 없으면 반환된 prompt로 새 채팅 하나를 만든다. 생성 직후 `python scripts/ax.py bind-handoff <checkpoint-id> <thread-id>`를 실행해 목적지를 먼저 저장한다. 응답이 불명확하거나 저장 실패 시 도구/채팅 목록으로 이미 만들어졌는지 확인하고 무조건 재시도하지 않는다. clientThreadId만 반환되면 준비 완료 후 실제 threadId를 받는다.
5. wait_threads로 초기 읽기/응답 결과를 확인한다. 성공한 뒤 navigate_to_codex_page로 연다. 생성 성공 시 앱의 created-thread 안내를 최종 응답에 포함한다. 생성·응답·화면 이동 각각의 실제 결과를 구분해 보고한다.

기존 채팅에 이어달라는 명시적 선택이면 그 채팅에만 send_message_to_thread로 새 인계 prompt를 전달하고 연다. 이 방법은 해당 채팅의 기존 컨텍스트를 초기화하지 않음을 알린다. 새 채팅 생성 선택과 혼동하지 않는다.

도구가 없거나 실행이 실패하면 체크포인트를 보존하고 `python scripts/ax.py resume-prompt <id>`의 문구를 제공한다. 사용자가 같은 프로젝트에서 새 채팅을 직접 열고 붙여넣을 수 있다. 실패한 단계를 성공으로 기록하지 않는다. 인계 파일은 외부 전송·배포·권한 확대를 허가하지 않는다.
