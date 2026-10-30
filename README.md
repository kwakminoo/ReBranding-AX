# ReBranding-AX

Windows Codex 앱에서 페르소나·자료·고객별 작업 상태를 필요한 만큼 읽고, 선택형 안내창으로 새 채팅에 이어가는 로컬 운영 패키지입니다. 모델 재학습이나 모든 대화의 자동 기억을 제공하는 제품은 아닙니다.

## 다른 PC에서 시작하기

**공개 코드와 비공개 데이터 묶음이 모두 필요합니다.** 저장소만 내려받으면 도구는 있지만 실제 페르소나·지식·작업 기록은 없습니다. 개인 자료 ZIP을 공개 GitHub, Release, 이슈에 올리지 마세요. 짧게 공개한 뒤 삭제해도 공개된 자료의 복제본을 회수할 수는 없습니다.

1. 이 저장소를 clone하거나 Code → Download ZIP으로 내려받아 압축을 풉니다. 예: `D:\Work\ReBranding-AX`.
2. 별도로 전달받은 `AX-private-*.zip`을 USB/비공개 저장소로 그 PC에 옮깁니다. 이 ZIP은 암호화되지 않았습니다.
3. Codex 앱을 설치하고 사용할 계정으로 로그인한 뒤, 내려받은 **ReBranding-AX 폴더 자체**를 프로젝트로 엽니다. 부모 폴더가 아닌 이 폴더를 여세요.
4. Codex에 아래 문구를 입력하거나 PowerShell에서 설치 명령을 실행합니다.

> 이 저장소 README를 따라 설치해줘. 비공개 데이터 묶음은 D:\Transfer\AX-private-20261031.zip에 있어. 기존 파일은 보존하고 필요한 Python과 프로젝트 스킬을 준비한 뒤 doctor와 테스트를 실행해줘. 훅의 신뢰 확인이 필요한 단계는 안내해줘.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Bundle 'D:\Transfer\AX-private-20261031.zip' -Hooks -InstallPython
```

`ExecutionPolicy Bypass`는 이 실행 프로세스에만 적용되며 시스템 정책을 영구 변경하지 않습니다. 조직 정책상 실행이 막히면 정책을 우회하지 말고 승인된 설치 경로를 사용하세요. Python이 있으면 재설치하지 않습니다. 없을 때 `-InstallPython`은 WinGet의 Python 3.14 사용자 설치를 요청합니다. WinGet이 없으면 [Python 공식 Windows 설치 안내](https://docs.python.org/3/using/windows.html)를 따릅니다. 별도 pip/npm 패키지는 필요 없습니다. [Microsoft의 WinGet Python 설치 안내](https://learn.microsoft.com/en-us/windows/python/beginners)

5. 스킬이 목록에 나타나지 않으면 프로젝트/앱을 다시 엽니다. 훅은 Codex가 해당 프로젝트와 훅 정의를 신뢰한 후에만 동작합니다. CLI에서는 이 폴더에서 `codex`를 열고 `/hooks`로 정의를 확인할 수 있습니다. 앱에서 동일한 검토 UI가 제공되지 않으면 CLI에서 검토하거나 훅 없이 사용하세요. 신뢰를 우회하는 옵션은 사용하지 않습니다.
6. `python scripts/ax.py doctor`에서 `ready: true`, `missing_sources: []`를 확인하고 아래 일상 사용 시험을 합니다. ready는 로컬 파일 준비 상태이며 앱 버튼/훅 신뢰까지 보증하지 않습니다.

원본 Claude export 폴더로 처음 설치할 때는 `-Bundle` 대신 `-Source 'D:\Private\Claude-export'`를 사용합니다. Source에는 `projects/*.json`, 선택적으로 `conversations.json`과 통화 Markdown이 있어야 합니다. 설치/복원은 다른 기존 데이터와 충돌하면 멈춥니다. 먼저 새 폴더에서 복원하세요.

## 일상 사용

> Anima 그룹에서 client-a의 제안서를 시작하자. 목표는 고객 요구에 맞는 제안 방향 정리야. 필요한 페르소나만 사용해줘.

> 민은정 관점만으로 이 이름을 검토해줘. 다른 페르소나는 추가하지 마.

> 지금까지 확정한 조건과 다음 작업을 저장하고, 새 채팅에서 이어가자.

Codex는 공통 스킬과 선택된 관점 카드, 현재 고객 상태, 관련 자료만 읽습니다. 실제 인물을 대신하는 것이 아니라 원자료에 정의된 관점을 적용합니다. Study/Writers/Conti는 별도 scope이며 Anima의 15인 규칙을 무조건 적용하지 않습니다.

이어가기는 **상태 저장 → 선택형 안내(이미 명시적으로 요청했다면 생략) → 새 채팅 생성 → 인계 파일 읽기 → 채팅 열기**로 동작하도록 스킬에 구성했습니다. 앱 도구가 없는 환경에서는 인계 문구를 복사해 같은 프로젝트의 새 채팅에 붙여넣습니다. 기존 채팅으로 이동하는 것은 새 컨텍스트 생성과 다릅니다.

## 설치되는 것

| 요소 | 구현 |
| --- | --- |
| 페르소나 | 원문 섹션을 개별 카드로 분리하고 `.agents/skills/ax-persona-*` 생성. 가져온 원문은 비공개 |
| 업무 스킬 | ax-work, ax-continue. 원본은 이 저장소의 skills/에 보관 |
| 검색 | Python 표준 라이브러리 키워드 검색. 그룹·고객 필터, 출처·줄 번호, 최대 10건의 짧은 발췌 |
| 상태 | 고객별 brief, state, decisions, sources, outputs |
| 인계 | 크기 제한·필수 항목 검증·SHA-256 체크포인트·목적지 중복 연결 방지 |
| 안내 | 턴 시작 시 추정 사용량 확인, 선택형 안내창, 선택 시 채팅 도구 사용 |
| 선택적 훅 | UserPromptSubmit 경고/모델 맥락, PreCompact 안내. 설치 후 별도 신뢰 검토 필요 |
| 이전 | 체크섬을 포함한 비공개 ZIP, 다른 파일 충돌 시 복원 거부 |

외부 MCP 서버, QMD, Basic Memory, 벡터 DB, 파인튜닝은 필수 의존성이 아니며 설치하지 않습니다. 이번 기준선은 Markdown 지식 운영과 범위 제한 키워드 검색입니다. 검색 실패 사례가 쌓이면 그 사례로 의미 검색 도입 효과를 먼저 비교하세요.

## 파일 구조

```text
AGENTS.md / skills/ / scripts/ / tests/ / docs/   공개 코드·사용법
.agents/skills/                                  설치/생성된 스킬 (Git 제외)
.codex/hooks.json                                PC별 절대경로 훅 (Git 제외)
.local/
  config.json                                   추정 안내 기준 (기본 0.75)
  knowledge/index.json                          그룹·문서·페르소나 출처 목록
  knowledge/<scope>/                            프로젝트 지침과 지식 원문
  knowledge/personas/                           선택해서 읽는 개별 관점 원문
  archive/                                      원본 프로젝트/대화 JSON, 표시 텍스트, 통화
  clients/<id>/                                 고객별 brief/state/decisions/sources/outputs
  handoffs/<id>/                                고정된 인계와 전달 목적지
  runtime/                                      이 PC의 임시 경고 상태 (이전 제외)
```

index에 등재된 현재 가져오기 버전만 검색합니다. 과거 원본은 남기지만 승인된 최신 사실로 취급하지 않습니다. HTML 산출물·폰트·외부 첨부 파일 전체를 복제하는 도구는 아닙니다. 원본 프로젝트/대화 JSON과 본문·통화 자료를 보존하며, JSON 밖의 기존 첨부/산출물은 원본 폴더를 별도로 보관하거나 필요한 고객의 sources/outputs로 가져오세요. 로그인 기록·사용자 계정 JSON은 가져오지 않습니다.

## 명령과 확인

```powershell
python scripts/ax.py doctor
python -m unittest discover -s tests -v
python scripts/ax.py init-client client-a --scope anima --goal '제안 방향 정리'
python scripts/ax.py search '핵심경험' --scope anima --client client-a
python scripts/ax.py context
python scripts/ax.py checkpoint client-a
python scripts/ax.py pack 'D:\Transfer\AX-private-latest.zip'
```

checkpoint 전에 Codex가 state의 `next_actions`와 현재 조건을 채워야 합니다. 산출물 경로는 해당 고객 폴더 기준입니다. 기존 ID로 init-client를 반복하면 데이터를 보존하고 거부합니다. pack은 저장소 밖의 새 ZIP 경로만 허용합니다. 복원은 `python scripts/ax.py restore <ZIP>` 후 `setup`입니다. 다른 PC의 경로를 다시 생성하므로 `.codex`/`.agents`를 이전할 필요가 없습니다.

## 검증 범위와 한계

테스트·실측 결과와 다음 PC 확인표는 [docs/VALIDATION.md](docs/VALIDATION.md)에 있습니다. 정확한 순간의 75% 경고, 앱 기본 화면의 영구 버튼, 모든 기기에서의 버튼 동작, 페르소나의 완전한 재현을 보장하지 않습니다. 이 계정의 앱에서는 선택형 안내 → 기존 시험 채팅 내용 전달 → 화면 전환을 실측했습니다. 이는 제품 패키지 설치 후 모든 앱 버전에서 같은 결과를 보증하지 않습니다.

훅은 마지막 입력/한도의 **추정치**가 갱신되어 기준 이상이면 안내하며, 오래된 수치/누락은 unknown/stale입니다. API 요금·주간 사용 한도가 아닙니다. PreCompact 경고는 저장 완료를 뜻하지 않습니다. 핵심 결정은 큰 작업 단계마다 저장하세요. [Codex Hooks](https://learn.chatgpt.com/docs/hooks), [Skills](https://learn.chatgpt.com/docs/build-skills)

## 공개 저장소 관리

`.local`, `.agents`, `.codex`, ZIP과 원본 연구자료는 공개 커밋에 넣지 않습니다. 공개 파일만 명시적으로 stage한 뒤 `python scripts/check_public.py`로 Git index를 검사하고 실제 diff를 읽으세요. 자동 검사만으로 모든 개인 정보 탐지를 보장하지 않습니다.

다른 PC의 코드·비공개 데이터·작업 결과를 확인하고 별도 백업한 뒤 GitHub 저장소를 삭제해도 로컬 사용은 계속됩니다. 이후 수정은 각 PC의 파일을 직접 옮기거나 다른 비공개 전달 수단이 필요합니다. 저장소 삭제가 PC 간 동기화를 제공하지는 않습니다.
