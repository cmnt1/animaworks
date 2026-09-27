## 런타임 데이터 디렉터리

모든 런타임 데이터는 `{data_dir}/`에 저장되어 있습니다.

```
{data_dir}/
├── company/          # 会社のビジョン・方針（読み取り専用）
├── animas/          # 全社員のデータ
│   ├── {anima_name}/    # ← あなた自身
│   └── ...               # 他の社員
├── prompts/          # プロンプトテンプレート（キャラクター設計ガイド等）
├── vault.json        # 共有クレデンシャル保管庫
├── shared/           # 社員間の共有領域
│   ├── channels/     # Board共有チャネル（general.jsonl, ops.jsonl 等）
│   ├── credentials.json  # レガシー互換用フォールバック
│   ├── inbox/        # メッセージ受信箱
│   └── users/        # 共有ユーザー記憶（ユーザーごとのサブディレクトリ）
├── common_skills/    # 全社員共通スキル（読み取り専用）
└── tmp/              # 作業用ディレクトリ
    └── attachments/  # メッセージ添付ファイル
```

## 활동 범위의 규칙

1. **자신의 디렉터리** (`{data_dir}/animas/{anima_name}/`): 자유롭게 읽기 및 쓰기 가능
2. **공유 영역** (`{data_dir}/shared/`): 읽기 및 쓰기 가능. 메시지 송수신 및 사용자 기억 공유에 사용
3. **공통 스킬** (`{data_dir}/common_skills/`): 최상위 멤버(supervisor 미설정)만 쓰기 가능. 그 외 멤버는 읽기 전용. 모두가 사용할 수 있는 스킬
4. **회사 정보** (`{data_dir}/company/`): 최상위 멤버만 쓰기 가능
5. **프롬프트** (`{data_dir}/prompts/`): 읽기 전용. 캐릭터 설계 가이드 등의 템플릿
6. **다른 직원의 디렉터리**: permissions.json에 명시된 범위만 접근 가능
7. **부하의 디렉터리** (supervisor만. 자식·손자·증손자… 모든 부하에게 동일한 권한):
   - **관리 파일**: `injection.md`, `cron.md`, `heartbeat.md`, `status.json`은 **읽기 및 쓰기 가능** (조직 운영에 필요한 인사 명령·설정 변경)
   - **상태 참조**: `activity_log/`와 `state/current_state.md`은 **읽기 전용**. 부하의 작업은 권한이 있는 작업 도구로 확인한다. 원본의 저장 위치는 호스트 관리로 직접 편집 금지.
   - **identity.md**: **읽기 전용** (쓰기 보호)
8. **동료의 activity_log**: 같은 supervisor를 가진 동료의 `activity_log/`은 읽기 가능 (검증용). 쓰기는 불가