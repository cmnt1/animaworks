# How the Organization Structure Works

In AnimaWorks, the organization structure is built using each Anima's `status.json` (or `identity.md`) as the Single Source of Truth (SSoT).
`core/org/org_sync.py` synchronizes the **supervisor** on disk to `config.json`, which is then used during prompt construction.
This document explains how the organization structure is defined, interpreted, and displayed.

## Data Sources and Priority Order

### supervisor (Supervisor)

The reporting hierarchy is defined in each Anima's `supervisor`. Read priority:

1. **status.json** — `"supervisor"` key (recommended)
2. **identity.md** — Rows in the table format `| 上司 | name |` (Japanese only. The `read_anima_supervisor` of `core/config/models.py` is parsed)

If `supervisor` is unset, empty, "なし", "(なし)", "（なし）", "-", or "---", the Anima is at the top level (highest rank).
The root-owned CLI/API operation `animaworks config set animas.<name>.supervisor <supervisor>` updates both status and config. Direct edits to only `config.json` are **synchronized from disk** by org_sync and may be overwritten.

### speciality (Specialty)

The specialty area is resolved from `_scan_all_animas()` of `core/prompt/builder.py` in the following priority order:

1. **status.json** — `"speciality"` key (free text)
2. **config.json** — `animas.<name>.speciality` (fallback when status.json has no `speciality` key)
3. **status.json** — `"role"` key (final fallback when the above cannot resolve. Role names: engineer, researcher, manager, writer, ops, general)

**Note:** org_sync does **not synchronize speciality**. Speciality is resolved each time from disk and config during prompt construction.
An Anima created via `animaworks anima create --from-md` will have `role` in `status.json` but not `speciality`.
If you want a custom display (e.g., "開発リード"), use `animaworks config set animas.<name>.speciality "開発リード"`; it updates the root-owned status/config values together.

## config.json Synchronization via org_sync

The `sync_org_structure()` of `core/org/org_sync.py` performs the following:

1. Reads `status.json` / `identity.md` from each Anima directory (only those where `identity.md` exists) and extracts the supervisor (`read_anima_supervisor`)
2. Detects circular references (Animas with circular references are excluded from synchronization)
3. Updates the `animas.<name>.supervisor` of `config.json` to match the values on disk (**supervisor only**)
4. Removes config entries for Animas that no longer exist on disk (prune)

**Items synchronized:** supervisor only. Speciality is not updated by org_sync.

**Execution timing:**

- At server startup (after the Anima process of `animaworks start` starts)
- When an Anima is added via reconciliation (`on_anima_added` callback)

## Hierarchy Definition via supervisor

- `supervisor: null` or unset → that Anima is at the top level (highest rank)
- `supervisor: "alice"` → alice is the supervisor

Example root-owned status values (for illustration only; set them with the root config CLI/API):

```json
{
  "enabled": true,
  "supervisor": null,
  "speciality": "経営戦略・全体統括"
}
```

```json
{
  "enabled": true,
  "supervisor": "alice",
  "speciality": "開発リード"
}
```

With this configuration, the following hierarchy is built:

```
alice（経営戦略・全体統括）
├── bob（開発リード）
│   └── dave（バックエンド開発）
└── carol（デザイン・UX）
```

Important constraints:
- The name specified as supervisor must be a known Anima name (English name)
- Circular references (alice → bob → alice) are detected and excluded from synchronization
- An Anima can have only one supervisor

## Organization Context Construction Process

The `_build_org_context()` of `core/prompt/builder.py` calculates the following information from the directory scan and the merge result of config.json:

1. **Supervisor**: The value of your own supervisor. If unset, "You are at the top"
2. **Subordinates**: All Animas whose supervisor is your name
3. **Peers**: Animas that share the same supervisor as you (excluding yourself)

The result is injected into the system prompt as "Your position in the organization":

```
## あなたの組織上の位置

あなたの専門: 開発リード

上司: alice (経営戦略・全体統括)
部下: dave (バックエンド開発)
同僚（同じ上司を持つメンバー）: carol (デザイン・UX)
```

## How to Read Your Position

From the "Your position in the organization" section of the system prompt, you can check the following:

| Item | Meaning | Impact on Behavior |
|------|---------|-------------------|
| Your specialty | The value of speciality | You are responsible for questions and decisions in this area |
| Supervisor | The Anima you report to | The destination for progress reports and issue escalation |
| Subordinates | Animas under your command | Delegation targets for tasks and progress confirmation |
| Peers | Colleagues sharing the same supervisor | People you can directly coordinate with on related work |

### Points to Check

- If your supervisor is "(なし — あなたがトップです)", you are at the top of the organization and bear overall responsibility
- If your subordinates are "(なし)", you are a task executor and should do the work yourself
- If you have peers, you can directly coordinate with them on related work

## Behavior When the Organization Changes

Changes to the organization structure are reflected in the following steps:

1. Change organization fields through the root-owned setting interface, e.g. `animaworks config set animas.<name>.supervisor <supervisor>` or `animaworks config set animas.<name>.speciality <speciality>`.
2. The CLI/API updates both `status.json` and `config.json`; `org_sync` keeps the hierarchy synchronized. The next reconciliation/prompt uses the updated value.
3. **Speciality** is read during prompt construction, so it applies to the next chat/heartbeat without restarting the Anima.

Notes:
- Do not edit `status.json` or `config.json` directly from an Anima process. Root and the offline CLI are the only writers.
- After an organization change, you SHOULD notify the affected Animas via message

## Example Organization Structure Patterns

Below are examples of organization fields. Set them through the root-owned config CLI/API; org_sync keeps `supervisor` synchronized, and `speciality` is resolved during prompt construction.

### Pattern 1: Flat Organization

Everyone is at the top level. No reporting hierarchy.

Root-owned status values (for illustration):
```json
{ "supervisor": null, "speciality": "企画" }
{ "supervisor": null, "speciality": "開発" }
{ "supervisor": null, "speciality": "デザイン" }
```

```
alice（企画）
bob（開発）
carol（デザイン）
```

Characteristics:
- Everyone can interact directly on equal footing
- Suitable for small teams or when each person has independent work
- Everyone's peers are "(なし)" (because they do not share the same supervisor)

### Pattern 2: Hierarchical Organization

There is a clear reporting hierarchy. This is the most common pattern.

Set each hierarchy field through the root config CLI/API, for example `animaworks config set animas.dave.supervisor bob`:

```
alice（CEO・全体統括）
├── bob（開発部長）
│   ├── dave（バックエンド）
│   └── eve（フロントエンド）
└── carol（営業部長）
    └── frank（顧客対応）
```

Characteristics:
- bob and carol are peers (same supervisor = alice)
- dave and eve are peers (same supervisor = bob)
- Contact from dave to frank follows the path bob → alice → carol → frank (cross-department rule)

### Pattern 3: Specialist + Manager Type

A small number of managers oversee a larger number of specialists.

```
manager（プロジェクト管理）
├── dev1（API開発）
├── dev2（DB設計）
├── dev3（インフラ）
└── qa（品質保証）
```

Characteristics:
- All members are peers. Direct coordination is easy
- The manager handles overall task allocation and progress management
- Suitable for startups and project teams

## Using speciality

`speciality` is root-owned free text stored in `status.json` (and mirrored in config for org sync). Set it with `animaworks config set animas.<name>.speciality <value>`. When unset, `role` (role name) is displayed as a fallback.

- Displayed next to each Anima's name in the organization context (e.g., `bob (開発リード)` or `bob (engineer)`)
- Serves as a clue for other Animas to decide who to consult or delegate tasks to
- If unset, it is displayed as "(未設定)"

**Behavior when creating an Anima (`core/anima/factory.py`):**
- When created via `animaworks anima create --from-md PATH [--role ROLE] [--supervisor NAME] [--name NAME]`, `supervisor` and `role` are written to `status.json`
- **supervisor**: If the `--supervisor` option is specified, it takes priority. If not specified, it is parsed from the basic information table of the character sheet (`| 上司 | name |`)
- **speciality**: Not included in the basic information table of the character sheet, and `_create_status_json` also does not write speciality, so it is not automatically set at creation
- If a custom specialty display is needed, set it with `animaworks config set animas.<name>.speciality "開発リード"` after creation; do not edit the settings files directly
- The same applies when created via `create_from_template` / `create_blank`: speciality is not automatically set in status.json (if the template contains status.json, its content is copied)

How to write an effective speciality:
- Be specific and short: `バックエンド開発` `顧客サポート` `データ分析`
- Avoid being too vague: `いろいろ` → `企画・調整・進行管理`
- If you have multiple specialties, separate them with a middle dot: `UI設計・フロントエンド開発`
