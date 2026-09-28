### 리포지토리 작업 규칙

- canonical checkout의 `main` / `master`는 참조 전용. 구현·검증·commit은 반드시 전용 `git worktree`에서 수행
- worktree는 `{data_dir}/companies/<会社>/shared/worktrees/`(다른 anima와 공유할 수 있는 장소. `node_modules`나 빌드 산출물을 만드는 리포지토리는 반드시 여기) 또는 `/tmp/`에 생성. canonical checkout에 대한 조작은 `git worktree add`와 참조로 한정
- worktree에서의 merge는 canonical checkout이 clean한 것을 확인한 후에 수행. dirty라면 변경하지 않고 보고
- 타인의 변경을 임의로 stash·폐기·덮어쓰지 않음
