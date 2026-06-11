# Game QA Companion

게임 플레이 세션(스크린샷 시퀀스)을 입력받아 **룰 기반 신호 추출 → LLM 판단**으로 결함 후보를 찾고, 근거 스크린샷이 첨부된 Markdown 리포트와 자연어 질의를 제공하는 스탠드얼론 분석 도구.

## 핵심 아이디어 — 분석은 실행과 독립이다

게임 QA 자동화의 실행 스택(자동화 플랫폼·플레이 봇)은 게임·플랫폼마다 다르지만, **세션이 남긴 화면과 기록을 분석하는 레이어는 실행 방식과 무관하게 동일**할 수 있다. 이 도구는 실행을 하지 않는다 — 무엇이 플레이했든(자동화 플랫폼이든 사람이든) 그 결과를 받아 분석만 전담한다.

```
[입력 3경로]                          [공통 세션 포맷]         [분석 레이어]
 ① 기존 자동화 플랫폼 산출물  ─┐                            룰 기반 신호 추출 (OpenCV)
 ② PC 클라이언트 화면 캡처    ─┼─→  frames/ + manifest.json ─→  · 화면 정체(stall) 탐지
 ③ 모바일 ADB 화면 캡처      ─┘                                · 수치 급변 (OCR 시계열)
                                                                      ↓ 후보만 선별
                                                              LLM 판정 (Claude, 근거 첨부)
                                                                      ↓
                                                              report.md + 자연어 질의(ask)
```

설계 원칙:
- **관찰 전용** — 입력 주입 없음. 캡처는 매 호출 독립(stateless)이라 장시간 세션에서도 안 죽는다.
- **룰이 1차, LLM은 2차** — 모든 프레임을 LLM에 넣지 않는다. OpenCV 신호 필터를 통과한 후보당 근거 3장만 LLM이 판정. 비용·오탐 통제.
- **LLM 출력은 검증 가능한 형태로만** — 판정에는 근거 스크린샷이 항상 첨부되고, 리포트는 사람 검수를 전제로 한다.
- **게임 추가 = config 1개** — 게임별 차이(캡처 대상 창·OCR 영역·템플릿·분석 프롬프트)는 YAML로만. 코어 코드에 게임명이 없다.
- **API 비용 0** — LLM은 Claude Code 구독 연동(claude-agent-sdk)만 사용. 종량 과금 API key가 설정돼 있으면 실행을 거부한다.

## Quickstart

요구사항: Python 3.11+, [uv](https://docs.astral.sh/uv/), Claude Code(로그인 상태). 한글 출력이 깨지면 `chcp 65001`.

```powershell
uv sync

# 1) PC 게임 관찰 (관찰 전용 — 30분 플레이를 2초 간격 캡처)
uv run companion capture --source windows --game configs\my_game.yaml --interval 2 --duration 1800

# 2) 모바일 (ADB)
uv run companion capture --source adb --game configs\my_game.yaml --interval 2 --duration 600

# 3) 기존 자동화 플랫폼 산출물 변환
uv run companion import-artifacts --src <스크린샷 디렉토리> --game-name "My Game"

# 분석 + 리포트 (개발 중 드라이런은 --provider fake)
uv run companion analyze --session sessions\<세션> --game configs\my_game.yaml

# 자연어 질의
uv run companion ask --session sessions\<세션> "플레이 중 정체 구간이 있었나?"
```

## 게임 config

```yaml
name: "My Game"
type: "mmorpg"
capture:
  window_title: "GAME WINDOW"   # PC: 창 제목 부분 일치 (suffix 변동 흡수)
  adb_serial: null              # 모바일: 기기 시리얼 (단일 기기면 null)
ocr_regions:                    # 선택 — 수치 추적 (uv sync --extra ocr 필요)
  - id: "hp"
    region: [50, 100, 300, 150]
    numeric: true
analysis_prompts:
  detect_anomaly: "이 게임은 ○○ 장르다. 전투·이동·UI 흐름에서 이상 징후를 판단하라."
```

## 한계 (정직하게)

- **탐지 신호는 화면 기반 휴리스틱** — 화면 정체·수치 급변 등 외형 신호만 본다. 게임 내부 상태(메모리·로그 스트림)는 모른다.
- **LLM 판정은 보조** — 오판 가능. 그래서 모든 판정에 근거 스크린샷을 강제하고 리포트에 사람 검수 전제를 명시한다.
- **iOS 미지원** — 비침투 캡처 통로가 없다 (Appium/WDA 계열이 필요해지는 영역).
- **실시간 게임 부적합** — 캡처 간격(초 단위) 기반이라 프레임 단위 이슈는 못 잡는다.
- **OCR은 선택 설치** — `uv sync --extra ocr` (PaddleOCR, 용량 큼).

## 데모

(추가 예정 — `demo/` 디렉토리)

## 개발

```powershell
uv run pytest -q   # 29 tests
```

AI 코딩 에이전트(Claude Code)와 협업해 개발했다. 요구사항 정의·아키텍처 선택·실기기 검증은 사람의 몫이다.
