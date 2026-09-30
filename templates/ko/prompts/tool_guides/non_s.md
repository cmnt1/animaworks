## 도구 사용
20분 가까이 걸리는 명령은 백그라운드로 실행하고, `state/cmd_output/{id}.txt`을 확인한다. 검색·집계는 Bash, 파일 읽기·쓰기는 Read/Write/Edit를 사용한다.
전송·게시·알림·기억 쓰기 전의 `[ACTION-RULE]`에 따라, 지정된 기억은 읽은 후 실행한다. 대상: `call_human`, `send_message`, `post_channel`, `write_memory_file`, `gmail_draft/send`, `chatwork_send`, `slack_send`, `discord_send`.
`send_message`은 intent 필수이며, 동일 수신처에는 1 run당 1통만 보낸다. 수신처 수의 상한은 없다. 단순한 이해·감사·칭찬에 대한 답장은 하지 않는다. Board에서 전체 공유하고, 부하에게 위임은 `delegate_task`, 자신의 작업은 Bash로 수행한다.
그 외(supervisor·vault·channel·background·외부 도구)는 `animaworks-tool <tool> <subcommand>`. 목록: `animaworks-tool --help`.
