전송·게시·알림·기억 쓰기 전에 `[ACTION-RULE]`이 나오면 따른다. 지정된 `read_memory_file(path="...")`은 같은 세션에서 읽고, 확인 후에 실행한다. 대상: `call_human`, `send_message`, `post_channel`, `write_memory_file`, `gmail_draft/send`, `chatwork_send`, `slack_send`, `discord_send`.
`send_message`은 1회 실행당 최대 2개 수신처·각 1통, intent 필수.
부하에게 위임은 `delegate_task`, 자신의 작업은 Bash로 직접 수행한다.
그 외(supervisor·vault·channel·background·외부 도구)는 `animaworks-tool <tool> <subcommand>`. 목록: `animaworks-tool --help`.