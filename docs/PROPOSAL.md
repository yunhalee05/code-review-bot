# 프로젝트 제안서

## Local Multi-Agent Code Review Bot for GitLab MR

---

## 1. 배경 및 문제 정의

금융권 보안 정책과 망 분리 환경으로 인해 SaaS 형태의 AI 코드리뷰 도구(Copilot PR Review, CodeRabbit 등)를 CI 파이프라인에 직접 설치하거나 외부 네트워크에서 토큰을 호출하는 방식으로 연동하기 어렵다. 또한 Anthropic, OpenAI 등 사용 가능한 모델 토큰이 **로컬 IP에서만 호출 가능**하도록 제한되어 있어, GitLab Runner 또는 공용 CI 환경에서 모델 호출이 불가능하다.

그 결과 코드리뷰 자동화는 사람의 수동 노력에 의존하게 되고, 변경점이 복잡해질수록 **리뷰 품질 편차와 리드타임이 증가**한다.

### 핵심 제약 사항

| 제약 | 설명 |
|------|------|
| 망 분리 | SaaS 도구 설치 불가, 외부 네트워크 접근 제한 |
| IP 제한 | AI API 토큰이 로컬 IP에서만 호출 가능 |
| CI 불가 | GitLab Runner에서 모델 호출 불가 |
| 보안 정책 | 코드가 외부 서비스로 전송되는 것을 허용하지 않음 |

---

## 2. 프로젝트 목표

위 제약을 전제로, **로컬에서 실행되는 CLI 기반 리뷰 봇**을 구축한다.

- GitLab MR 단위로 변경점을 수집
- 여러 AI 에이전트가 역할을 분담하여 리뷰를 수행
- MR에 코멘트를 자동 업로드

> "개발자의 실수나 논리 오류를 먼저 걸러내서, 리뷰어가 비즈니스 로직 정확도에 집중"하도록 한다.

---

## 3. 시스템 아키텍처

### 3.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                    review-bot review <MR_ID>                │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  GitLab Client                                              │
│  ┌───────────────────┐  ┌────────────────────────────────┐  │
│  │ MR 정보 조회       │  │ Diff 파싱 → Hunk 추출          │  │
│  │ (제목, 작성자, URL)│  │ (파일 필터링, 개수 제한)        │  │
│  └───────────────────┘  └────────────────────────────────┘  │
└─────────────────┬───────────────────────────────────────────┘
                  │ list[Hunk]
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: Issue Identification (병렬 실행)                    │
│                                                             │
│  각 Hunk마다 독립적인 에이전트가 잠재적 이슈를 탐지           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ Hunk 1  │ │ Hunk 2  │ │ Hunk 3  │ │  ...    │          │
│  │ Agent   │ │ Agent   │ │ Agent   │ │ Agent   │          │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘          │
│       │           │           │           │                 │
│       └───────────┴───────────┴───────────┘                 │
│                       │                                     │
│              StorageTool (report_issue)                      │
└─────────────────┬───────────────────────────────────────────┘
                  │ list[Issue]
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: Issue Validation (병렬 실행)                        │
│                                                             │
│  각 Issue마다 코드베이스를 검색하여 Evidence/Mitigation 수집   │
│  ┌──────────────────────────────────────────────────┐       │
│  │ 코드베이스 검색 도구                                │       │
│  │ - search_code: 패턴 검색                           │       │
│  │ - read_file_lines: 파일 읽기                       │       │
│  │ - list_directory: 디렉토리 탐색                     │       │
│  └──────────────────────────────────────────────────┘       │
│                       │                                     │
│              StorageTool (submit_validated_issue)            │
└─────────────────┬───────────────────────────────────────────┘
                  │ list[ValidatedIssue]
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  필터링                                                      │
│  - False Positive 제거                                       │
│  - Severity 기준 미달 제거                                   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  GitLab Commenter                                           │
│  ┌───────────────────────┐  ┌──────────────────────────┐    │
│  │ 인라인 Discussion      │  │ 요약 노트 (Summary)       │    │
│  │ (diff 줄 단위 코멘트)  │  │ (이슈 테이블 + 통계)      │    │
│  └───────────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 2단계 에이전트 설계

하이퍼리즘 기술 블로그의 "레퍼런스 체크 방식"을 참고하여 설계하였다.

| 단계 | 역할 | 특성 | 목표 |
|------|------|------|------|
| **Stage 1** | Issue Identification | 높은 자율성, 넓은 탐색 | **높은 재현율** (FP 허용) |
| **Stage 2** | Issue Validation | 강한 제약, 근거 기반 | **높은 정확도** (FP 제거) |

> "Naive Prompting만큼 다양하고, Checklist만큼 일관적인 리뷰"

### 3.3 StorageTool 패턴

시스템 프롬프트만으로 구조화된 출력을 강제하기 어렵기 때문에, **Tool Call을 데이터 전송 레이어로 활용**한다.

```python
# 핵심 패턴
storage = IssueStorage(file_path=hunk.file_path)
server = create_issue_storage_server(storage)
agent.run(prompt, tools=[server])
return storage.issues  # Tool Call을 통해 수집된 구조화 데이터
```

에이전트의 텍스트 응답이 아닌 **Tool Call의 인자**로 구조화된 데이터를 수집하므로, 파싱 실패 없이 안정적으로 결과를 얻을 수 있다.

---

## 4. 기술 스택

| 구성요소 | 기술 | 역할 |
|---------|------|------|
| 에이전트 SDK | Claude Agent SDK (Python) | 에이전트 오케스트레이션 |
| LLM | Claude Sonnet 4 | 코드 분석 및 이슈 탐지 |
| GitLab 연동 | python-gitlab | MR 조회, diff 추출, 코멘트 게시 |
| 코드베이스 검색 | ripgrep (rg) / grep | Stage 2 레퍼런스 검색 |
| CLI | Typer + Rich | 사용자 인터페이스 |
| 설정 관리 | Pydantic Settings | 환경변수 기반 설정 |
| 데이터 모델 | Python dataclass | Hunk, Issue, ValidatedIssue |
| 병렬 처리 | asyncio | Semaphore 기반 동시성 제어 |

---

## 5. 데이터 모델

### 5.1 Hunk (변경 블록)

```
file_path: str          # 변경된 파일 경로
new_start_line: int     # 시작 줄 번호
content: str            # diff 원문
added_lines: list[str]  # 추가된 줄
removed_lines: list[str]# 삭제된 줄
```

### 5.2 Issue (탐지된 이슈)

```
file_path: str          # 파일 경로
line_number: int        # 이슈 줄 번호
code: str               # 이슈 코드 (SEC001, BUG002 등)
title: str              # 한 줄 요약
description: str        # 상세 설명
severity: Severity      # critical / high / medium / low
```

### 5.3 ValidatedIssue (검증된 이슈)

```
issue: Issue            # 원본 이슈
is_false_positive: bool # 오탐 여부
evidence: str           # 실제 문제인 근거
mitigation: str         # 오탐일 수 있는 근거
suggestion: str         # 수정 제안
references: list[str]   # 참조 파일/라인
```

### 5.4 Severity 체계

| 등급 | 설명 | 예시 |
|------|------|------|
| 🚨 CRITICAL | 반드시 수정 | 보안 취약점, 데이터 손실 |
| 🔴 HIGH | 강력 권고 | 버그, 트랜잭션 누락 |
| 🟡 MEDIUM | 권고 | 성능 이슈, 코드 품질 |
| 🔵 LOW | 참고 | 개선 제안 |

---

## 6. 리뷰 범위

### 탐지 대상

- 보안 취약점 (Injection, Auth Bypass, XSS, 데이터 노출)
- 버그 및 로직 오류 (Off-by-one, Null 참조, Race Condition)
- 트랜잭션/리소스 관리 (미닫힌 연결, 롤백 누락)
- 성능 이슈 (N+1 쿼리, 무한 루프, 과도한 할당)
- 에러 처리 (삼킨 예외, 누락된 에러 케이스)

### 제외 대상

- 코드 스타일/포매팅
- 네이밍 컨벤션 (명백히 오해를 일으키는 경우 제외)
- 주석/문서 누락
- 테스트 파일 (깨진 assertion 제외)
- lock 파일, minified 파일, migrations, node_modules 등

---

## 7. GitLab 코멘트 전략

### 인라인 Discussion

diff의 특정 줄에 직접 코멘트를 생성하여, 개발자가 컨텍스트를 바로 확인할 수 있다.

```markdown
🔴 **[HIGH] TXN001: 데이터베이스 연결이 닫히지 않음**

**문제:** line 27에서 열린 DB 연결이 함수 종료 시 닫히지 않아
커넥션 풀 고갈이 발생할 수 있습니다.

**수정 제안:**
`with` 문을 사용하여 연결을 자동으로 닫도록 변경하세요.

**근거:** `src/service.py:45`에서 동일 패턴이 `with` 문으로 구현됨

🤖 review-bot (Claude) | False Positive 의심 시 무시하세요
```

### 요약 노트

MR 전체에 대한 리뷰 결과를 테이블 형태로 요약한다.

---

## 8. 보안 고려사항

| 항목 | 대응 |
|------|------|
| 코드 유출 방지 | 로컬 실행, 기존 승인된 프로바이더(Anthropic)만 사용 |
| Path Traversal | 코드베이스 검색 도구에 경로 제한 적용 |
| API 토큰 관리 | .env 파일로 관리, .gitignore 설정 |
| 결과 신뢰성 | 2단계 검증으로 False Positive 최소화 |

---

## 9. 향후 개선 계획

### Phase 2: 고도화

- 비즈니스 로직 리뷰를 위한 도메인 컨텍스트 주입 (JIRA, Slack 연동)
- 프롬프트 튜닝을 통한 False Positive 추가 감소
- 토큰 사용량 모니터링 및 비용 최적화

### Phase 3: 확장

- OpenAI 모델 지원 (멀티 프로바이더)
- 팀/셀별 커스텀 리뷰 규칙 설정
- 리뷰 결과 대시보드 및 통계

### Phase 4: 자율화

- 완전 자율 에이전트 (현재는 Python 스크립트 제어)
- 자동 수정 PR 생성
- CI/CD Webhook 기반 자동 트리거 (망 분리 해제 시)

---

## 10. 참고 자료

- [하이퍼리즘 기술 블로그 - PR 리뷰 에이전트 개발](https://tech.hyperithm.com/review-agent)
- [Claude Agent SDK Documentation](https://docs.anthropic.com/en/docs/agents-and-tools/claude-agent-sdk)
- [python-gitlab Documentation](https://python-gitlab.readthedocs.io/)
