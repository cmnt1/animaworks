If `[ACTION-RULE]` appears before sending, posting, notifying, or writing to memory, follow it. Read the specified `read_memory_file(path="...")` in the same session and execute after confirming. Targets: `call_human`, `send_message`, `post_channel`, `write_memory_file`, `gmail_draft/send`, `chatwork_send`, `slack_send`, `discord_send`.
`send_message` requires an intent, and only one message per run to the same recipient. There is no limit on the number of recipients.
Delegation to subordinates is done via `delegate_task`; do your own work directly with Bash.
Others (supervisor, vault, channel, background, external tools) are handled via `animaworks-tool <tool> <subcommand>`. List: `animaworks-tool --help`.
