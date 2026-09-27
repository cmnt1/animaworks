<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/security.md -->
<!-- i18n: source-sha256=9efcb666c04a3459cbe0b3f825deff0bd2f4bcf9f165216c31a6af574c8ca609 generated=2026-09-27 engine=local model=deepseek-v4-flash translator=2 -->

> Verified commit: 581e20f1

# Security

AnimaWorks does not trust external input as instructions and enforces permission boundaries along execution paths. The basics are: do not broaden permissions when configuration cannot be read, and use the same decision across multiple execution engines. This chapter describes the main boundaries in the implementation. For the list of configuration items, see the [Configuration Reference](reference/config.md); for authentication categories per API, see the [API Reference](reference/api.md).

## Threat model

The assets to protect are Anima's data and credentials, other Anima and company data, commands executed on the host, and the ability to send to external services. Threat sources include malicious content arriving via web, email, chat, and other channels; instructions that attempt to induce operations beyond permissions; broken configuration; and compromised child processes or external services.

Rather than relying solely on the model's response, the host records the origin of input, applies permission checks to operations, and validates paths and callers. However, this does not prevent arbitrary host compromise. Managing the runtime directory, OS, credentials, and network is also the operator's responsibility.

## Trust boundaries and data provenance

`core/execution/_sanitize.py` resolves trust from provenance. If there is a chain of provenance, the lowest trust in the chain is inherited. Unknown provenance is also classified on the low side, and data with omitted provenance is not considered trusted.

| Trust level | Example provenance | Handling |
|---|---|---|
| `trusted` | System origin, internal data between Anima instances | Include in the prompt with a trust boundary tag. |
| `medium` | Human input, output from integration processing | Treat the content as data and perform permission checks separately. |
| `untrusted` | Web, external platforms, unknown or mixed provenance | Do not execute as instructions; explicitly maintain the trust boundary. |

`wrap_tool_result`, `wrap_external_message`, and `wrap_priming` wrap content in boundary tags and neutralize any notation in the input body that spoofs the same boundary tag. Tool result trust is resolved through a centralized table, and unregistered tools are treated on the low side. The trust of tools used during a session is also tracked, and the lower trust is carried forward to subsequent processing.

## Permission checks

### External tools and operations with side effects

`core/tooling/permissions.py`'s `check_tool_access` handles access to external tools and per-operation permissions through a common decision path. Per-Anima `permissions.json` defines allow and deny rules for commands and external tools, as well as file access scope. Deny takes precedence over allow. Even when `allow_all` is enabled, operations individually restricted by the execution profile require explicit permission. The same decision applies to core, shared, and personal tools.

The `permissions.global.json` applied to all Anima instances defines command deny patterns and input detection patterns. `core/config/global_permissions.py`'s `GlobalPermissionsCache` loads at startup, and if periodic integrity checks detect runtime changes, it reverts to the startup content. It is also protected from file operations intended for Anima.

If problems occur in configuration loading, schema validation, or profile loading, the operation is denied. Do not default to allowing when the decision cannot be confirmed.

### Bash commands

The pure function `evaluate_command` in `core/tooling/command_policy.py` makes centralized command decisions. ToolHandler, the Claude Agent SDK hook, and the Codex hook all call the same policy. The evaluation includes shell injection detection, common deny rules for all Anima instances, recursive search guards (Layer 2.6), per-Anima deny and allowlists, path traversal checks, and prevention of writes to other Anima directories. The recursive search guard rejects operations that scan the entire runtime or large log areas in one pass and encourages targeted searches.

If the common policy cannot be loaded, the caller is also rejected as an error. Decisions must not differ when the execution engine changes.

### Files and company boundaries

`core/config/file_access_policy.py` checks read and write targets resolved to real paths and applies per-Anima allow, read-only, and deny routes. It also inspects the targets of resolved symbolic links and hides protected paths such as runtime control information from model-facing file operations.

If the company affiliation differs, other companies' areas are excluded from access. The company's `shared/` has limited write routes. Operations whose company boundary cannot be confirmed are denied on the safe side. An Anima without a company affiliation does not have the same boundaries as a company-affiliated Anima, so configure an affiliation when company separation is required.

## Skill trust model

Skills distinguish between their registration source and inspection status. Skills outside the runtime are enumerated read-only from the configured host-side external roots. They do not have the same write permissions as skills copied into Anima-managed areas. Skill creation and promotion are separate permission operations and follow trust level, scan results, and explicit human-initiated operation conditions.

## Processes and internal API

Each Anima runs in a separate child process managed by the supervisor. Inter-process requests go through the internal API, which validates per-Anima or per-operator call tokens derived from a secret generated at each server startup. Tokens are generated in-process, and no private key is stored on disk. After validation, it checks whether the requested operation can target the caller itself or only its descendants in the hierarchy.

When authentication configuration is required, `auth_guard` in `server/app.py` checks the session cookie. Exception conditions such as secure localhost connections and the list of paths that do not require authentication are described in the [authentication categories in the API Reference](reference/api.md). Webhooks use per-service signature validation rather than session cookies.

## External sending and receiving

External sending includes checks for destination resolution, operation permission, recipient count, and per-hour and per-day send limits. DM and shared channel send limits share a common budget. On the receiving side, cooldown and cascade detection control inbox startup. Do not put credentials in code or documents, and enable only approved integrations. For details on send rules, see [Messaging](architecture/messaging.md).

## Adversarial threat analysis

| Threat | Defense and limitations |
|---|---|
| Instructions embedded in external messages | Mark provenance as low trust with boundary tags. The model may still misinterpret, so external requests are not treated as permissions. |
| Compound shell commands or broad searches | Split commands into syntactic units and evaluate the same policy across all execution paths. This is not a guarantee of semantically understanding every obfuscated shell expression. |
| Access to other Anima or company data | Validate canonical paths, company affiliation, and caller identity. An Anima without company configuration is not isolated by company boundaries. |
| Broken permission configuration or credentials | Treat failures in JSON loading, permission checks, and internal caller validation as denials. Threats where the host administrator can modify configuration or the execution environment itself require separate management. |

## Defense in depth

The layers are: boundary tags showing input provenance, per-Anima tool permissions, common command evaluation, file path and company affiliation checks, internal API caller validation, HTTP authentication, and send volume limits. Each layer protects a different operation point, so no single layer is designed to provide safety on its own. Operate together with configuration management, execution environment protection, and least privilege for external services.

## Residual risks and operations

- Trust tags do not completely prevent model misinterpretation. For requests contained in externally sourced content, confirm the content's origin before executing.
- `permissions.json` and `permissions.global.json` are permission boundaries. Take a backup before editing, and validate the JSON and schema after changes. If a read error occurs, do not loosen permissions; fix the cause.
- When enabling localhost trust, correctly restrict the reverse proxy's forwarded headers and exposure scope. When exposing the server to the internet, configure authentication and TLS.
- The internal API's log mode is for migration verification and differs from operations that enforce caller validation. Check the production configuration.
- Send limits are a mechanism to reduce the impact of misdirected sends; they do not replace human review of destinations and content or least privilege on the external service side.

## Related documents

- [Configuration Reference](reference/config.md)
- [API Reference](reference/api.md)
- [Messaging](architecture/messaging.md)
- [Anima Files](architecture/anima-files.md)
- [Process Architecture](architecture/process.md)