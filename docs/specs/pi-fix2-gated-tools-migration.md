# pi-fix2: Gated side-effect tools — migration guide

## Summary

Dangerous write/send actions are now **gated** (require an explicit
`external_tools.allow` entry). This matches existing `gmail_send` /
`slack_send` / `discord_channel_post` behavior.

| Tool | Action | Allow key | Notes |
|------|--------|-----------|--------|
| chatwork | `send` | `chatwork_send` | Newly gated |
| discord | `send` | `discord_send` | Newly gated (`channel_post` already gated) |
| github | `create-issue` | `github_create-issue` | Newly gated |
| github | `create-pr` | `github_create-pr` | Newly gated |
| machine | `run` | `machine_run` | Newly gated; **do not grant** if tool is denied |

`allow_all: true` does **not** auto-permit gated actions. Explicit allow is required.

Semantics live in `core/tooling/permissions.py` (`is_action_gated` /
`get_permitted_tools`) and are unchanged by this migration — only
`EXECUTION_PROFILE` flags and per-Anima/template allow lists change.

## Before you apply

1. Deploy / pull the pi-fix2 code change (gated flags in tool modules).
2. Scan current usage (optional, for audit):

```bash
python scripts/scan_gated_tool_usage.py \
  --out docs/records/$(date +%Y%m%d)_gated-tool-usage-scan.md
```

3. Dry-run the allow migration:

```bash
python scripts/migrate_pi_fix2_gated_allows.py
# or explicit data dir:
python scripts/migrate_pi_fix2_gated_allows.py --data-dir ~/.animaworks
```

Confirm the planned `WOULD ADD` lines match production needs.

## Apply (production)

```bash
python scripts/migrate_pi_fix2_gated_allows.py --apply
```

- Idempotent: re-running does not duplicate allows.
- Never grants `machine_run` (live animas keep `"deny": ["machine"]`).
- Only touches `~/.animaworks/animas/*/permissions.json` under `--data-dir`.

Restart or reload Animas if your deployment caches permissions in-process.

## Default allow map (2026-08-01)

| Allow key | Animas |
|-----------|--------|
| `chatwork_send` | aoi, kotoha, mei, mio, nagi, natsume, rin, ritsu, sakura, sora |
| `discord_send` | aoi, mei, mio, nagi, natsume, rin, ritsu, sakura, sora |
| `github_create-issue` | aoi, ayame, kotoha, mei, mio, natsume, rin, ritsu, sakura, sora, sumire |
| `github_create-pr` | same as create-issue |
| `machine_run` | *(none)* |

To grant an extra anima later, append the key to that anima's
`permissions.json` → `external_tools.allow` (or extend `DEFAULT_ALLOWS` in
the migration script and re-run with `--apply`).

## Role templates

`templates/{en,ja}/roles/*/permissions.json` and `_blank`:

- All roles that already had `discord_channel_post` also get `discord_send`.
- `engineer` also gets `github_create-issue` and `github_create-pr`.
- `chatwork_send` / `machine_run` are **not** in templates (same pattern as
  `gmail_send` / `slack_send`: grant only where operationally needed).

Korean (`ko`) role templates keep empty allow lists unchanged.

## Rollback

Remove the newly added keys from each anima's `external_tools.allow`, or
revert the tool module `gated: True` flags. Prefer removing allows only if
the code gate must stay.

## Related

- Issue: pi-fix2 (prompt-injection audit follow-up)
- Scan helper: `scripts/scan_gated_tool_usage.py`
- Migration: `scripts/migrate_pi_fix2_gated_allows.py`
