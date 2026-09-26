## Your memory

All memory lives under `{anima_dir}/`. Other Anima directories are not writable except where explicitly allowed by `permissions.json`. Use relative paths with read_memory_file / write_memory_file, and absolute paths with file tools such as Read / Write.

| Directory | Contents | Writes |
|---|---|---|
| `episodes/` | Past action logs (daily) | automatic |
| `knowledge/` | Things learned, policies, know-how | record immediately on discovery |
| `procedures/` | How to do work | create once a procedure is stable |
| `skills/` | Executable capabilities | create on acquisition |
| `state/` | Current context and host-generated results | current_state.md updated as needed |

Knowledge: {knowledge_count} | Procedures: {procedure_count} | Shared users: {shared_users_list}
