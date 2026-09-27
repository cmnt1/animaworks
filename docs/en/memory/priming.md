<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/memory/priming.md -->
<!-- i18n: source-sha256=0081dfa1257d883fc97eee25f5116efbb8b51b9c5d27c1879fdc6512ae266bd3 generated=2026-09-27 engine=local model=deepseek-v4-flash translator=2 -->

> Confirmed commit: 193a5e72
# Automatic Recall (Priming)

Automatic recall is the process of retrieving relevant memory cues from the execution path that received input and adding them to the LLM context. The configuration is defined in `core/memory/priming/engine.py` at `PrimingEngine`, and the default profile is defined in `core/config/schemas.py` at `PrimingConfig`.
## Profiles and Channels

The default value of `PrimingConfig.profile` is `compact`. If `priming_profile` is specified as `compact` or `full` in `status.json` for each Anima, it can override that Anima's configuration. The channel overview is as follows.

| Channel | What is retrieved | `compact` | `full` |
|---|---|---:|---:|
| A | Sender profile | ○ | ○ |
| B | Recent activity in the activity log | — | ○ |
| C0 | Pointers to resident candidates and important knowledge | ○ | ○ |
| C | Search for related knowledge | Conditional | ○ |
| E | Incomplete tasks | ○ | ○ |
| F | Past episodes | — | ○ |
| G | Not an independent channel. Graph-derived candidates accompanying episode search | — | ○ (within F's search) |
| Auxiliary | Recent sent content, unsent notifications to humans | ○ | ○ |

In `compact`, channels A, E, C0, and auxiliary information are collected in parallel. The C search is performed when `channel` is `chat` or `task`, or when `intent` is `question`, `request`, or `delegation`. Reading recent activity (B), searching episodes (F), and graph candidates equivalent to G that may be used within that search are not part of the retrieval targets for `compact`. G is not an independent Priming channel.
## C0 and `always_prime`

When `always_prime: true` is set in a knowledge file, it is treated as a resident candidate for automatic recall on the RAG index. `compact` calls C0 with `resident_only=True` and selects up to 3 normal knowledge pointers from these explicit opt-in candidates. The current `compact` path does not check for matches with the input query and selects resident candidates in order of update date and time. Candidates treated as ACTION-RULE may be injected in the body. Being `[IMPORTANT]` alone is not a reason to inject unrelated knowledge as resident content. `full` searches not only resident candidates but also important knowledge related to the query.
## Search Policy

The search policy is defined in `core/memory/retrieval/unified_search.py` at `TRIGGER_POLICIES`. In the search for `scope="all"`, the scope, number of candidates, and whether reranking is applied vary depending on the trigger. C and F specify individual scopes, so while using those scopes, the candidate count and rerank policy for each trigger are applied.

| trigger | Main search scope | rerank |
|---|---|---:|
| `chat` | facts, episodes, knowledge, procedures, activity log | Enabled |
| `inbox` | facts, episodes, activity log | Enabled |
| `heartbeat` | episodes, activity log | Disabled |
| `task` | facts, procedures, knowledge | Enabled |
| `cron` | facts, episodes, knowledge, activity log | Enabled |
| `tool` | Scope for tool search | Enabled |

For individual search stages and the scope of `search_memory`, see [Intentional Recall and Search](retrieval.md).
## Limits and Timeouts

The default value of `priming.max_tokens` is 2,000, and it is used as the upper limit for recall results passed to the profile. It is not a mechanism for dynamically allocating this value according to message type. Unsent human notifications are handled under a separate contract and are not excluded to satisfy the normal recall budget.

The default value of `priming.channel_timeout_seconds` is 60 seconds. An upper limit is set for each channel, and only the timed-out channel is treated as empty while other retrieval results continue. For all configuration items, see the [Configuration Reference](../reference/config.md).