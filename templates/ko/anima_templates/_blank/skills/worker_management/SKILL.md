---
name: worker-management
description: >-
  AnimaWorks 서버 프로세스의 운영 관리 스킬.
  코드 업데이트 후 핫 리로드(server reload), Anima 프로세스 재시작,
  서버 상태 확인(실행 중 Anima 목록·메모리 사용량)을 실행한다.
  "리로드해줘" "업데이트 반영해줘" "다시 불러와줘" "시스템 상태" "서버 재시작" "프로세스 확인"
---


# 스킬: 시스템 관리

## CLI 명령어 (권장)

`animaworks` CLI에서 개별 Anima 관리를 할 수 있습니다. **API를 직접 호출하는 것보다 CLI를 우선 사용하세요.**

```bash
# 個別Animaのリスタート（設定変更の反映等）
animaworks anima restart <name>

# ステータス確認（全体 or 個別）
animaworks anima status
animaworks anima status <name>

# モデル変更（root APIでstatusを更新 + 起動中ならreload）
animaworks anima set-model <name> <model>

# ロール変更
animaworks anima set-role <name> <role>

# Anima一覧
animaworks anima list

# 無効化 / 有効化
animaworks anima disable <name>
animaworks anima enable <name>

# 削除（--archive でバックアップ可）
animaworks anima delete <name>
```

### 자주 쓰는 사용법

```bash
# config.json変更後に特定Animaだけリスタート
animaworks anima restart aoi

# モデルを変更して起動中プロセスに自動reload
animaworks anima set-model aoi claude-sonnet-5-5
```

## API 참조 (CLI를 사용할 수 없는 경우)

기본 URL: `$ANIMAWORKS_SERVER_URL` (설정되지 않았다면 `http://localhost:18500`)

| 엔드포인트 | 메서드 | 용도 |
|--------------|---------|------|
| `/api/system/status` | GET | 시스템 상태 확인 |
| `/api/system/reload` | POST | **전체 anima 핫 리로드** |
| `/api/animas` | GET | anima 목록 |
| `/api/animas/{name}` | GET | anima 상세 |
| `/api/animas/{name}/restart` | POST | 개별 재시작 |
| `/api/animas/{name}/stop` | POST | 개별 종료 |
| `/api/animas/{name}/start` | POST | 종료된 anima 시작 |
| `/api/animas/{name}/chat` | POST | 메시지 전송 |
| `/api/animas/{name}/trigger` | POST | 하트비트 즉시 실행 |

## 리로드 절차 (프로그램 업데이트 후)

```bash
curl -s -X POST "${ANIMAWORKS_SERVER_URL:-http://localhost:18500}"/api/system/reload | python3 -m json.tool
```

- `added`: 새로 감지된 anima
- `refreshed`: 다시 로드된 anima (파일 변경이 반영됨)
- `removed`: 디스크에서 삭제된 anima
- **서버 재시작은 필요 없음. 이 엔드포인트로 설정·프롬프트 변경이 즉시 반영됨**

## 주의사항

- 워커를 종료해도 anima의 데이터(기억·설정)는 남아 있음
- **자기 자신을 종료하는 작업은 하지 말 것**
- 개별 작업은 CLI → API 순서로 사용할 것
