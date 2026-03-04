# Local Multi-Agent Code Review Bot for GitLab MR

로컬에서 실행되는 CLI 기반 AI 코드리뷰 봇. GitLab MR의 변경점을 수집하고, 2단계 멀티 에이전트가 리뷰를 수행한 뒤 MR에 코멘트를 자동 업로드한다.

> 금융권 망 분리 환경처럼 SaaS AI 도구를 사용할 수 없고, API 토큰이 로컬 IP에서만 호출 가능한 환경을 위해 설계되었다.

---

## 아키텍처

```
MR ID
 ↓  GitLab API (python-gitlab)
Hunk 추출 (diff 파싱, 파일 필터링)
 ↓
Stage 1: Issue Identification (병렬)
 → 각 Hunk마다 Claude 에이전트가 잠재적 이슈를 공격적으로 탐지
 ↓
Stage 2: Issue Validation (병렬)
 → 각 Issue마다 코드베이스를 검색하여 Evidence/Mitigation 기반으로 검증
 ↓
False Positive 필터링 + Severity 필터링
 ↓
GitLab MR에 인라인 코멘트 + 요약 노트 게시
```

### 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **2단계 검증** | Stage 1은 높은 재현율(FP 허용), Stage 2는 레퍼런스 기반 정확도 |
| **StorageTool 패턴** | Tool Call을 데이터 전송 레이어로 활용하여 구조화된 결과 수집 |
| **Agent as Function** | 각 에이전트는 고정 입출력 스키마의 블랙박스 함수 |
| **토큰 절감** | diff 추출은 순수 API 호출, AI는 분석에만 사용 |

---

## 프로젝트 구조

```
review_bot/
├── config.py              # 설정 관리 (Pydantic Settings)
├── cli.py                 # CLI 엔트리포인트 (Typer + Rich)
├── pipeline.py            # 파이프라인 오케스트레이터
├── gitlab/
│   ├── client.py          # MR 정보 조회 + Hunk 추출
│   └── commenter.py       # 인라인 코멘트 + 요약 노트 게시
├── models/
│   ├── hunk.py            # Git diff hunk 데이터 모델
│   └── issue.py           # Issue, ValidatedIssue, Severity
├── agents/
│   ├── base.py            # Claude Agent SDK 래퍼
│   ├── identify.py        # Stage 1: 이슈 탐지 에이전트
│   └── validate.py        # Stage 2: 이슈 검증 에이전트
├── tools/
│   ├── storage.py         # StorageTool (이슈/검증결과 수집용 MCP 서버)
│   └── codebase.py        # 로컬 코드베이스 검색 도구 (MCP 서버)
└── prompts/
    ├── identify.py        # Stage 1 프롬프트 템플릿
    └── validate.py        # Stage 2 프롬프트 템플릿
```

---

## 요구사항

- **Python** 3.11+
- **GitLab** Private Token (MR 읽기/쓰기 권한)
- **Anthropic API Key**
- **ripgrep** (선택, 코드베이스 검색 성능 향상 - 없으면 grep 사용)

---

## 설치

### 1. 저장소 클론

```bash
git clone <repository-url>
cd CodeReviewBot
```

### 2. 가상환경 생성 및 패키지 설치

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -e .
```

개발 의존성까지 설치하려면:

```bash
pip install -e ".[dev]"
```

### 3. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 값을 설정한다:

```env
# 필수
GITLAB_URL=https://gitlab.example.com     # GitLab 인스턴스 URL
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx   # GitLab Private Token
GITLAB_PROJECT_ID=12345                    # 대상 프로젝트 ID

ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx  # Anthropic API Key

# 선택 (기본값 사용 가능)
MAX_HUNKS_PER_FILE=20                      # 파일당 최대 Hunk 수
MAX_FILES_PER_MR=30                        # MR당 최대 파일 수
REVIEW_MODEL=claude-sonnet-4-20250514      # 사용할 Claude 모델
LOG_LEVEL=INFO                             # 로그 레벨
```

#### GitLab Token 발급 방법

1. GitLab → Settings → Access Tokens
2. Scopes: `api` (또는 최소 `read_api`, `write_api`)
3. 생성된 토큰을 `.env`의 `GITLAB_TOKEN`에 입력

#### GitLab Project ID 확인 방법

1. GitLab 프로젝트 메인 페이지 접속
2. 프로젝트명 아래에 표시되는 `Project ID` 확인
3. 또는 Settings → General에서 확인

### 4. 설정 확인

```bash
review-bot check-config
```

GitLab 연결과 API 키 설정이 올바른지 확인한다:

```
Configuration Check

GitLab URL: https://gitlab.example.com
GitLab Project ID: 12345
GitLab Token: ********...xxxx
GitLab connection: OK

Anthropic API Key: ********...xxxx
Review Model: claude-sonnet-4-20250514

Max files per MR: 30
Max hunks per file: 20
```

---

## 사용법

### 기본 리뷰

```bash
review-bot review <MR_ID>
```

MR의 변경점을 분석하고, 발견된 이슈를 GitLab MR에 코멘트로 게시한다.

### Dry Run (코멘트 미게시)

```bash
review-bot review <MR_ID> --dry-run
```

분석만 수행하고 결과를 터미널에 출력한다. GitLab에는 코멘트를 게시하지 않는다. 처음 사용 시 이 모드로 먼저 테스트하는 것을 권장한다.

### 옵션

| 옵션 | 단축 | 기본값 | 설명 |
|------|------|--------|------|
| `--dry-run` | `-n` | `false` | 분석만 수행, 코멘트 미게시 |
| `--severity` | `-s` | `medium` | 최소 보고 심각도 (`critical`/`high`/`medium`/`low`) |
| `--concurrency` | `-c` | `4` | 최대 병렬 에이전트 수 |
| `--repo-root` | `-r` | `.` | 로컬 레포 루트 경로 (Stage 2 코드베이스 검색용) |
| `--verbose` | `-v` | `false` | 상세 로그 출력 |

### 사용 예시

```bash
# CRITICAL, HIGH 이슈만 보고
review-bot review 42 --severity high

# 로컬 레포 경로 지정 + 병렬 2개로 제한
review-bot review 42 --repo-root /path/to/project --concurrency 2

# 상세 로그와 함께 드라이런
review-bot review 42 --dry-run --verbose
```

### 실행 결과 예시

```
Review Bot - MR !42

MR: feat: 사용자 인증 모듈 추가
URL: https://gitlab.example.com/project/-/merge_requests/42
Author: 홍길동

Hunks analyzed: 12
Issues found (Stage 1): 8
False positives (Stage 2): 5
Issues posted: 3

                    Review Issues
┌───┬──────────┬────────┬─────────────────────┬──────────────────────┐
│ # │ Severity │ Code   │ File                │ Title                │
├───┼──────────┼────────┼─────────────────────┼──────────────────────┤
│ 1 │ CRITICAL │ SEC001 │ src/auth.py:45      │ SQL Injection 위험   │
│ 2 │ HIGH     │ TXN001 │ src/service.py:27   │ DB 연결 미닫힘       │
│ 3 │ MEDIUM   │ ERR001 │ src/handler.py:112  │ 예외 삼킴            │
└───┴──────────┴────────┴─────────────────────┴──────────────────────┘
```

---

## GitLab에 게시되는 코멘트

### 인라인 코멘트

diff의 해당 줄에 직접 discussion으로 생성된다:

```
🔴 [HIGH] TXN001: 데이터베이스 연결이 닫히지 않음

문제: line 27에서 열린 DB 연결이 함수 종료 시 닫히지 않아
커넥션 풀 고갈이 발생할 수 있습니다.

수정 제안:
  with db.connect() as conn:
      result = conn.execute(query)
      return result

근거: src/service.py:45에서 동일 패턴이 with 문으로 구현됨

🤖 review-bot (Claude) | False Positive 의심 시 무시하세요
```

### 요약 노트

MR에 전체 결과를 요약한 노트가 추가된다:

```
## 🤖 Review Bot Summary

Found 3 issue(s):
- 🚨 CRITICAL: 1
- 🔴 HIGH: 1
- 🟡 MEDIUM: 1

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | CRITICAL | src/auth.py:45 | SQL Injection 위험 |
| 2 | HIGH | src/service.py:27 | DB 연결 미닫힘 |
| 3 | MEDIUM | src/handler.py:112 | 예외 삼킴 |
```

---

## 기술 스택

| 구성요소 | 기술 |
|---------|------|
| 에이전트 SDK | [Claude Agent SDK](https://docs.anthropic.com/en/docs/agents-and-tools/claude-agent-sdk) (Python) |
| LLM | Claude Sonnet 4 |
| GitLab 연동 | [python-gitlab](https://python-gitlab.readthedocs.io/) |
| CLI | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) |
| 설정 관리 | [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| 코드베이스 검색 | [ripgrep](https://github.com/BurntSushi/ripgrep) (fallback: grep) |

---

## 리뷰 탐지 범위

| 카테고리 | 예시 |
|---------|------|
| 보안 | SQL Injection, XSS, Auth Bypass, 데이터 노출 |
| 버그 | Off-by-one, Null 참조, Race Condition |
| 리소스 | 미닫힌 DB 연결, 롤백 누락, 리소스 누수 |
| 성능 | N+1 쿼리, 무한 루프, 과도한 메모리 할당 |
| 에러처리 | 삼킨 예외, 누락된 에러 케이스 |

**제외:** 코드 스타일, 네이밍 컨벤션, 주석/문서, lock 파일, minified 파일, migrations

---

## 설정 커스터마이징

### 리뷰 모델 변경

```env
REVIEW_MODEL=claude-sonnet-4-20250514
```

### 분석 범위 제한

토큰 비용을 절감하려면 분석 범위를 줄인다:

```env
MAX_FILES_PER_MR=15    # MR당 최대 파일 수 (기본: 30)
MAX_HUNKS_PER_FILE=10  # 파일당 최대 Hunk 수 (기본: 20)
```

### 제외 파일 패턴

`review_bot/gitlab/client.py`의 `SKIP_PATTERNS`를 수정하여 제외할 파일 패턴을 추가할 수 있다:

```python
SKIP_PATTERNS = [
    r".*\.lock$",
    r".*\.min\.js$",
    r".*migrations/.*",
    # 추가 패턴...
]
```

---

## 개발

### 린트

```bash
ruff check review_bot/
ruff format review_bot/
```

### 타입 체크

```bash
mypy review_bot/
```

### 테스트

```bash
pytest
```

---

## 참고

- [하이퍼리즘 기술 블로그 - PR 리뷰 에이전트 개발](https://tech.hyperithm.com/review-agent)
- [기획 문서 (PROPOSAL.md)](docs/PROPOSAL.md)
