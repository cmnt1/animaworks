---
name: worker-management
description: >-
  AnimaWorks 서버 프로세스의 운영 관리 스킬.
  코드 업데이트 후 핫 리로드(server reload), Anima 프로세스 재시작,
  서버 상태 확인(실행 중인 Anima 목록, 메모리 사용량)을 수행합니다.
  "리로드", "업데이트 반영", "새로고침", "시스템 상태", "서버 재시작", "프로세스 확인"
---

# 스킬: 시스템 관리

## CLI 명령어 (권장)

`animaworks` CLI로 개별 Anima 관리가 가능합니다. **API 직접 호출보다 CLI를 우선하세요.**

```bash
# 개별 Anima 재시작 (설정 변경 반영 등)
animaworks anima restart <name>

# 상태 확인 (전체 또는 개별)
animaworks anima status
animaworks anima status <name>

# 모델 변경 (status.json 업데이트 + 자동 재시작)
animaworks anima set-model <name> <model>

# 역할 변경
animaworks anima set-role <name> <role>

# Anima 목록
animaworks anima list

# 비활성화 / 활성화
animaworks anima disable <name>
animaworks anima enable <name>

# 삭제 (--archive로 백업 가능)
animaworks anima delete <name>
```

### 일반적인 사용법

```bash
# config.json 변경 후 특정 Anima만 재시작
animaworks anima restart aoi

# 모델 변경 및 자동 재시작
animaworks anima set-model aoi claude-sonnet-4-6
```

## API 레퍼런스 (CLI를 사용할 수 없는 경우)

베이스 URL: `http://localhost:18500`

| 엔드포인트 | 메서드 | 용도 |
|--------------|---------|------|
| `/api/system/status` | GET | 시스템 상태 확인 |
| `/api/system/reload` | POST | **전체 anima 핫 리로드** |
| `/api/animas` | GET | anima 목록 |
| `/api/animas/{name}` | GET | anima 상세 |
| `/api/animas/{name}/restart` | POST | 개별 재시작 |
| `/api/animas/{name}/stop` | POST | 개별 정지 |
| `/api/animas/{name}/start` | POST | 정지된 anima 시작 |
| `/api/animas/{name}/chat` | POST | 메시지 전송 |
| `/api/animas/{name}/trigger` | POST | heartbeat 즉시 실행 |

## 리로드 절차 (프로그램 업데이트 후)

```bash
curl -s -X POST http://localhost:18500/api/system/reload | python3 -m json.tool
```

- `added`: 새로 감지된 anima
- `refreshed`: 재로드된 anima (파일 변경 사항이 반영됩니다)
- `removed`: 디스크에서 삭제된 anima
- **서버 재시작이 필요 없습니다. 이 엔드포인트로 설정 및 프롬프트 변경이 즉시 반영됩니다**

## 주의사항

- 워커를 정지해도 anima 데이터(기억, 설정)는 유지됩니다
- **자기 자신을 정지하는 작업은 수행하지 마세요**
- 개별 작업은 CLI → API 순서로 우선하여 사용합니다
