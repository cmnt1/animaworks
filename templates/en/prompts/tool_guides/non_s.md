## Tool Usage
Commands that take nearly 20 minutes should be run in the background, then check `state/cmd_output/{id}.txt`. Use Bash for search and aggregation, and Read/Write/Edit for file reading and writing.

Before sending, posting, notifying, or writing to memory, follow `[ACTION-RULE]` and read the specified memory before executing. Targets: `call_human`, `send_message`, `post_channel`, `write_memory_file`, `gmail_draft/send`, `chatwork_send`, `slack_send`, `discord_send`.

`send_message` requires an intent, and only one message per run to the same recipient. There is no limit on the number of recipients. Do not reply to mere acknowledgments, thanks, or praise. Share broadly on the Board, delegate to subordinates via `delegate_task`, and do your own work with Bash.

For others (supervisor, vault, channel, background, external tools), see `animaworks-tool <tool> <subcommand>`. List: `animaworks-tool --help`.
