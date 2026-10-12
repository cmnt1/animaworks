# 모델 선택・설정 가이드

AnimaWorks의 모델 설정에 관한 종합 가이드.
실행 모드, 지원 모델, 설정 방법, 컨텍스트 윈도우의 구조를 설명한다.

---

## 실행 모드

AnimaWorks는 모델 이름에서 실행 모드를 자동으로 판정한다. 6가지 실행 모드가 있다:

| 모드 | 이름 | 개요 | 대상 모델 예 |
|--------|------|------|-------------|
| **S** | SDK | Claude Agent SDK 경유. 가장 고기능 | `claude-opus-5-5`, `claude-sonnet-5-5` |
| **C** | Codex | Codex CLI 경유 | `codex/o4-mini`, `codex/gpt-4.1` |
| **D** | Cursor Agent | Cursor Agent CLI(`cursor-agent`) 경유. MCP 통합 | `cursor/*` |
| **G** | Gemini CLI | Gemini CLI 경유. MCP 통합 | `gemini/*` |
| **X** | Grok Build | Grok Build CLI 래퍼(ACP stdio) 경유 | `grok/*` |
| **A** | Autonomous | LiteLLM + tool_use 루프 | `openai/gpt-4.1`, `google/gemini-2.5-pro`, `ollama/qwen3:14b` |

### 모드 판정의 우선순위

1. Per-anima `status.json`의 `execution_mode` 명시 지정
2. `~/.animaworks/models.json`(사용자 편집 가능)
3. `config.json` `model_modes`(비권장)
4. 코드 기본값의 패턴 매치
5. 불명 → Mode A

Mode X 이용 전에 `grok` CLI를 설치하고, `grok login`으로 인증해야 한다.

---

## 지원 모델 목록

`animaworks models list`에서 최신 목록을 표시할 수 있다. 주요 모델:

### Claude / Anthropic(Mode S)

| 모델 | 설명 |
|--------|------|
| `claude-opus-5-5` | 최고 성능・추천 |
| `claude-sonnet-5-5` | 밸런스형・추천 |
| `claude-haiku-4-5-20251001` | 경량・고속 |

### OpenAI (Mode A)

| 모델 | 설명 |
|--------|------|
| `openai/gpt-4.1` | 최신·코딩 강함 |
| `openai/gpt-4.1-mini` | 고속·저비용 |
| `openai/o3-2025-04-16` | 추론 특화 |

### Google Gemini (Mode A)

| 모델 | 설명 |
|--------|------|
| `google/gemini-2.5-pro` | 최고 성능 |
| `google/gemini-2.5-flash` | 고속 밸런스 |

### Grok Build (Mode X)

| 모델 | 설명 |
|--------|------|
| `grok/grok-4.5` | ACP stdio 경유의 Grok Build CLI |
| `grok/grok-composer-2.5-fast` | 고속 Grok Build 모델 |

### Azure OpenAI (Mode A)

| 모델 | 설명 |
|--------|------|
| `azure/gpt-4.1-mini` | Azure OpenAI |
| `azure/gpt-4.1` | Azure OpenAI |

### Vertex AI (Mode A)

| 모델 | 설명 |
|--------|------|
| `vertex_ai/gemini-2.5-flash` | Vertex AI Flash |
| `vertex_ai/gemini-2.5-pro` | Vertex AI Pro |

### 로컬 모델 / vLLM / Ollama

| 모델 | 모드 | 설명 |
|--------|--------|------|
| `openai/qwen3.5-35b-a3b` | A | **추천** — Sonnet 동급 성능(벤치마크 검증 완료) |
| `ollama/qwen3:14b` | A | 중형·tool_use 지원 |
| `ollama/glm-4.7` | A | tool_use 지원 |
| `ollama/gemma3:4b` | B | 경량 |

### AWS Bedrock

| 모델 | 모드 | 설명 |
|--------|--------|------|
| `openai/zai.glm-4.7` | A | Bedrock Mantle 경유. 단발 작업에 적합 |
| `bedrock/qwen.qwen3-next-80b-a3b` | A | 툴 호출 능력 부족(비권장) |

---

## 추천 OSS 모델(벤치마크 검증 완료)

### Qwen3.5-35B — 로컬 GPU 추천 모델

`openai/qwen3.5-35b-a3b`(vLLM 경유)는 AnimaWorks Mode A 에이전트로서 벤치마크 검증 완료된 **추천 로컬 모델**.
Claude Sonnet 4.6과 동등한 종합 점수를 기록했으며, **background_model로서 최적**.

#### 벤치마크 데이터 (2026-03-11 실시)

측정 조건: Mode A(LiteLLM tool_use 루프) 통일, 15개 작업×3회 실행/모델

| 모델 | T1 기본 조작 | T2 멀티스텝 | T3 판단·오류 | 종합 | 평균 시간 | 비용 |
|--------|:----------:|:----------------:|:--------------:|:----:|:-------:|:-----:|
| **Qwen3.5-35B (local)** | **100%** | **100%** | 60% | **88%** | 9.6s | **$0** |
| Claude Sonnet 4.6 | 100% | 100% | 60% | 88% | 8.5s | ~$0.015/task |
| GLM-4.7 (Bedrock) | 87% | 33% | 53% | 55% | 5.9s | ~$0.003/task |
| Qwen3-Next 80B (Bedrock) | 40% | 27% | 40% | 35% | 5.2s | ~$0.005/task |

#### 특기 사항

- **T1(기본 조작: 파일 I/O, 툴 호출)**: Sonnet과 완전 일치로 100%
- **T2(멀티스텝: CSV 집계, JSON 파싱→쓰기 등)**: Sonnet과 완전 일치로 100%
- **계산 정밀도(T3-3)**: Qwen3.5가 3/3, Sonnet이 1/3로 Qwen3.5가 우위
- **프롬프트 인젝션 내성(T3-4)**: 전체 모델 0/3(프레임워크 레벨 대책 필요)
- 파라미터 수는 성능에 직결되지 않음(80B의 Qwen3-Next보다 35B의 Qwen3.5가 훨씬 우위)

#### 추천 설정

```bash
# vLLM credential設定
# config.json > credentials に追加:
# "vllm-local": { "api_key": "dummy", "base_url": "http://<vllm-host>:8000/v1" }

# models.json に追加
# "openai/qwen3.5*": { "mode": "A", "context_window": 64000 }

# background_model として設定（Chat=Sonnet, HB/Inbox/Cron=Qwen3.5）
animaworks anima set-background-model {名前} openai/qwen3.5-35b-a3b --credential vllm-local
```

#### vLLM 시작 예

```bash
vllm serve Qwen/Qwen3.5-35B-A3B \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.95 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

#### 용도별 모델 선택 가이드

| 용도 | 추천 모델 | 이유 |
|------|-----------|------|
| background_model(HB/Inbox/Cron） | **Qwen3.5-35B** | 비용 $0로 Sonnet 동급의 안정성 |
| foreground(인간 채팅) | Sonnet 4.6 | 오류 처리의 안정성과 일본어 품질 |
| TaskExec(위임 작업 실행) | Qwen3.5-35B | 비용 $0로 툴 체인이 안정적 |
| 경량 단순 응답(분류·요약) | GLM-4.7 | 최고속이지만 멀티스텝 불가 |

---

## models.json

`~/.animaworks/models.json`에서 모델별 실행 모드와 컨텍스트 윈도우를 정의한다.
fnmatch 와일드카드 패턴 사용 가능.

### 스키마

```json
{
  "パターン": {
    "mode": "S" | "C" | "D" | "G" | "X" | "A" | "B",
    "context_window": トークン数
  }
}
```

### 예

```json
{
  "claude-opus-5-5":    { "mode": "S", "context_window": 1000000 },
  "claude-sonnet-5-5":  { "mode": "S", "context_window": 1000000 },
  "claude-*":           { "mode": "S", "context_window": 200000 },
  "grok/*":             { "mode": "X", "context_window": 500000 },
  "openai/gpt-4.1*":   { "mode": "A", "context_window": 1000000 },
  "openai/*":           { "mode": "A", "context_window": 128000 },
  "ollama/gemma3*":     { "mode": "B", "context_window": 8192 }
}
```

구체적인 패턴이 우선된다. `claude-opus-5-5`은 `claude-*`보다 먼저 매치된다.

### 확인 명령

```bash
animaworks models show       # models.json の内容表示
animaworks models info {モデル名}  # 解決結果の確認
```

---

## 모델 변경 절차

### 특정 Anima의 모델 변경

```bash
# 1. モデル設定（status.json を更新）
animaworks anima set-model {名前} {モデル名}

# 2. credential が必要な場合
animaworks anima set-model {名前} {モデル名} --credential {credential名}

# 3. サーバー起動中なら再起動
animaworks anima restart {名前}
```

### 전체 Anima 일괄 변경

```bash
animaworks anima set-model --all {モデル名}
```

### 현재 설정 확인

```bash
animaworks anima info {名前}    # モデル・実行モード・credential等を表示
animaworks anima list --local   # 全Animaのモデル一覧
```

---

## 컨텍스트 윈도우

### 해결 순서

1. `models.json`의 `context_window`
2. `config.json`의 `model_context_windows`(와일드카드 패턴)
3. 코드의 하드코드 기본값(`MODEL_CONTEXT_WINDOWS`)
4. 최종 폴백: 128,000 토큰

### 임계값의 자동 스케일

컨텍스트 윈도우 크기에 따라 컴팩션 임계값이 자동 조정된다:

- **200K 이상**: 설정값 그대로(기본값 0.50)
- **200K 미만**: 0.98을 향해 선형 스케일

소형 모델에서는 시스템 프롬프트만으로 컨텍스트의 대부분을 차지하므로, 임계값을 높여 오발동을 방지한다.

---

## 프로바이더별 credential 설정

### Anthropic (기본값)

```json
{
  "credentials": {
    "anthropic": {
      "api_key": "sk-ant-..."
    }
  }
}
```

### Azure OpenAI

```json
{
  "credentials": {
    "azure": {
      "api_key": "",
      "base_url": "https://YOUR_RESOURCE.openai.azure.com",
      "keys": { "api_version": "2024-12-01-preview" }
    }
  }
}
```

### Vertex AI

```json
{
  "credentials": {
    "vertex": {
      "keys": {
        "vertex_project": "my-gcp-project",
        "vertex_location": "us-central1",
        "vertex_credentials": "/path/to/service-account.json"
      }
    }
  }
}
```

### vLLM (로컬 GPU 추론)

```json
{
  "credentials": {
    "vllm-local": {
      "api_key": "dummy",
      "base_url": "http://192.168.1.100:8000/v1"
    }
  }
}
```

credential 설정 후, Anima에 연결:

```bash
animaworks anima set-model {名前} {モデル名} --credential {credential名}
```

---

## 백그라운드 모델 (비용 최적화)

Heartbeat / Inbox / Cron은 메인 모델과 별도의 경량 모델로 실행할 수 있다.
`background_model`을 설정하면, 이러한 백그라운드 처리의 비용을 대폭 절감할 수 있다.

### foreground / background 구분

| 구분 | 사용 모델 | 대상 트리거 |
|------|-----------|-------------|
| **foreground** | 메인 모델(`model`) | `chat`(인간과의 대화), `task:*`(TaskExec 실제 작업) |
| **background** | `background_model`(미설정 시 메인 모델) | `heartbeat`, `inbox:*`(Anima 간 DM), `cron:*` |

Heartbeat / Inbox / Cron은 「판단·트리아지」가 주목적이며, 실행은 TaskExec(메인 모델)이 담당한다.

### 해결 순서

1. Per-anima `status.json`의 `background_model`
2. `config.json`의 `heartbeat.default_model`(글로벌 기본값)
3. 메인 모델(`model`)로 폴백

### 설정 방법

```bash
# 特定Animaにbackground_model を設定
animaworks anima set-background-model {名前} claude-sonnet-5-5

# credential が異なるプロバイダの場合
animaworks anima set-background-model {名前} azure/gpt-4.1-mini --credential azure

# 全Animaに一括設定
animaworks anima set-background-model --all claude-sonnet-5-5

# background_model を削除（メインモデルにフォールバック）
animaworks anima set-background-model {名前} --clear

# サーバー起動中なら再起動
animaworks anima restart {名前}
```

### status.json에서의 확인

```json
{
  "model": "claude-opus-5-5",
  "background_model": "claude-sonnet-5-5",
  "background_credential": null
}
```

`background_model`이 미설정 또는 메인 모델과 동일한 경우, 전환은 건너뛴다.

---

## 역할 템플릿과 기본 모델

`animaworks anima set-role`에서 역할을 변경하면 기본 모델도 변경된다:

| 역할 | 기본 모델 | background_model | context_threshold | conversation_history_threshold |
|--------|---------------|-----------------|-------------------|----------------------------------|
| engineer | claude-opus-5-5 | claude-sonnet-5-5 | 0.80 | 0.40 |
| manager | claude-opus-5-5 | claude-sonnet-5-5 | 0.60 | 0.30 |
| writer | claude-sonnet-5-5 | — | 0.70 | 0.30 |
| researcher | claude-sonnet-5-5 | — | 0.50 | 0.30 |
| ops | ollama/glm-4.7 | — | 0.50 | 0.30 |
| general | claude-sonnet-5-5 | — | 0.50 | 0.30 |

Opus 계열 역할(engineer, manager)은 `background_model`로 Sonnet이 자동 설정된다.
Sonnet 이하의 역할은 이미 비용 효율이 좋기 때문에 `background_model`는 미설정.

---

## 자주 묻는 질문

### 모델을 변경했는데 반영되지 않는다

`set-model`는 root API를 통해 root 소유의 `status.json`를 업데이트하고, 실행 중인 Anima의 모델 설정을 reload한다. 종료 중인 Anima는 다음 시작 시 새 설정을 읽는다. Anima 프로세스에서 이 파일을 직접 편집하지 않는다.

### models.json을 편집했는데 반영되지 않음

models.json는 파일의 mtime으로 자동 리로드된다. `anima reload`으로도 반영 가능.

### 컨텍스트 윈도우를 늘리고 싶음

`models.json`의 `context_window`을 변경하거나, `config.json`의 `model_context_windows`으로 오버라이드.

### 어떤 모델을 선택해야 할지 모르겠다

- **고품질・자율 실행 필요** → `claude-opus-5-5`(Mode S)
- **밸런스・비용 중시** → `claude-sonnet-5-5`(Mode S)
- **저비용・대량 처리** → `openai/gpt-4.1-mini`(Mode A)
- **로컬 GPU・비용 $0** → `openai/qwen3.5-35b-a3b`(Mode A, vLLM)**추천**
- **로컬・경량** → `ollama/qwen3:14b`(Mode A)

### Heartbeat / Cron 비용을 줄이고 싶다

`background_model`을 설정한다. 자세한 내용은 위의 "백그라운드 모델(비용 최적화)" 섹션을 참조.
Opus를 메인으로 사용하는 경우, `background_model`에 Sonnet을 설정하는 것만으로 Heartbeat + Inbox 비용을 약 73% 절감할 수 있다.

vLLM에서 `openai/qwen3.5-35b-a3b`를 `background_model`로 설정하면, **백그라운드 처리 비용을 완전히 $0로 만들 수 있다**. Sonnet과 동등한 88% 종합 점수가 확인되었다.
