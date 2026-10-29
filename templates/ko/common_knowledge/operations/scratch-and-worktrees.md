# 작업물 보관 위치(scratch·공유 worktree·캐시)

임시 작업물과 보관할 항목의 위치.

## 위치

| 용도 | 위치 |
|---|---|
| 나만 사용하는 worktree·clone·빌드·검증 로그·임시 스크립트 | `$ANIMAWORKS_SCRATCH_DIR` |
| 다른 Anima에게 리뷰·검증을 넘겨주는 worktree | `{data_dir}/companies/<company>/shared/worktrees/` |
| 나중에 다시 읽을 절차·스크립트 | 내 `procedures/` |
| 나중에 다시 확인할 증거(보고서·스크린샷·집계) | `shared/evidence/` 또는 PR 댓글 |
| `state/` | 상시 상태 파일(`current_state.md`·`background_tasks/` 등)만 |

`$ANIMAWORKS_SCRATCH_DIR`은 실행할 때마다 자동으로 준비된다. 작업 실행 중에는 `animas/<self>/scratch/task-<task_id>/`, 그 외(chat·heartbeat·inbox·cron)에는 `animas/<self>/scratch/<type>/`을 가리킨다.

```bash
WT="$ANIMAWORKS_SCRATCH_DIR/myrepo"
git -C /path/to/canonical worktree add --detach "$WT" origin/main
TMP="$(mktemp -d -p "$ANIMAWORKS_SCRATCH_DIR")"
```

## 자동 삭제

- 작업용 scratch는 작업이 완료되거나 취소되면 사라진다. 그 안에 만든 worktree의 등록도 상위 리포지토리에서 해제된다.
- scratch는 24시간 동안 사용하지 않으면 사라진다.
- `shared/worktrees/`은 24시간 동안 사용하지 않으면 미커밋 변경 사항이 있어도 사라진다(사용 중인 것은 남는다).
- 뒷정리는 자동으로 이루어지므로 작업을 마칠 때 삭제 명령을 실행할 필요는 없다. 남기고 싶은 것은 위 표의 ‘나중에 다시 읽기’ 행에 있는 위치로 옮긴다.

## 패키지 캐시

`UV_CACHE_DIR`·`PIP_CACHE_DIR`·`npm_config_cache`·`npm_config_store_dir`（pnpm）·`GRADLE_USER_HOME`·`NUGET_PACKAGES`·`COMPOSER_CACHE_DIR`은 공용 `{data_dir}/cache/<type>`을 가리키도록 자동으로 설정되어 있다. 그대로 사용한다.
