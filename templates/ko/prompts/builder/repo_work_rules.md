### 저장소 작업 규칙

- canonical checkout의 `main` / `master`는 읽기 전용으로 취급합니다. 구현, 검증, commit은 반드시 전용 `git worktree`에서 수행합니다
- 클론, 빌드 산출물, 검증 로그, 임시 스크립트 같은 일회성 작업물은 환경 변수 `ANIMAWORKS_SCRATCH_DIR` 아래에 두고 `state/` 바로 아래에는 작업 디렉터리를 만들지 않습니다. scratch는 작업 종료 시 또는 24시간 동안 사용하지 않으면 자동 삭제됩니다
- 다른 Anima와 공유하는 worktree만 `{data_dir}/companies/<회사>/shared/worktrees/`에 만들고, 작업이 끝나면 `git worktree remove`로 정리합니다. 개인용 worktree는 scratch에 두며, 24시간 동안 사용하지 않은 worktree는 자동 삭제됩니다. canonical checkout 조작은 `git worktree add`와 읽기로 한정합니다
- 패키지 캐시는 설정된 공용 캐시(`UV_CACHE_DIR` 등)를 사용하고 PR마다 별도 캐시 디렉터리를 만들지 않습니다
- worktree에서 merge하기 전에 canonical checkout이 clean인지 확인합니다. dirty이면 변경하지 말고 보고합니다
- 명시적 지시 없이 다른 작업자의 변경을 stash, 폐기 또는 덮어쓰지 않습니다
