# Memory Consolidation Task (Weekly)

{anima_name}, it is time to organize your memory for the past week.

## Current knowledge files ({total_knowledge_count} total)

{knowledge_files_list}

## Merge candidates (similar file pairs — advisory only)

{merge_candidates}

※ The pairs above are **mechanical suggestions** based on vector similarity, not merge instructions.
In a narrow domain, files about different subjects (e.g. customer A vs customer B) can score highly similar. Decide whether to merge by **reading the contents yourself**, following the criteria in Step 1.

## Critical constraints
- **You MUST perform this work yourself directly**. Do NOT use `delegate_task`, `submit_tasks`, or `send_message`. Complete all work using only memory operation tools

## Workflow

**Rule for all steps**: Per-entity knowledge files (per-customer, per-project, per-person — e.g. `customer-context-*`) must **survive as separate detailed files** through merging, compression, and conceptual integration. Even when extracting principles into concept or SSOT files, never delete or summarize away the original details.

### Step 0: Self-compact injection.md (run every time — MUST)

Use `read_memory_file(path="injection.md")` to inspect the current content.

Keep `injection.md` under a **2,000 character target** as a constitution plus pointer index:

- **Keep resident**: role definition, non-negotiable rules, safety, approval, confidentiality, and duplicate-action prevention that must apply on every turn
- **Move out**: procedural details to `procedures/`; learned knowledge, examples, and operational notes to `knowledge/`
- **Replace**: detailed prose with `read_memory_file(path="...")` pointers
- **Preserve**: do not remove the core rules for external sending, confidential information, approval, and duplicate send/draft prevention

If it exceeds 2,000 characters, do not create a proposal file. Rewrite it directly during this consolidation with `write_memory_file(path="injection.md", mode="overwrite")`.
Even when it is already within 2,000 characters, check whether detailed prose has accumulated and shorten it with the same policy when needed.

{hygiene_section}

### Step 1: Review duplicate files (merge at your own judgment)

Review each merge-candidate pair and the file list above, and merge **only true duplicates**.
Merge candidates are advisory; there is no obligation to merge every pair.

Decision criteria:
- **Merge**: genuine duplicates or fragments of the same topic (old/new versions of the same procedure, restatements of the same fact)
- **Do NOT merge**: files about different entities (per-customer, per-project, per-person, per-system context files). Keep them as **separate files** even when similarity is high
- **When in doubt, do not merge**. Preserving information granularity and searchability takes priority

For pairs you decide to merge:
1. Use `read_memory_file` to review both contents
2. Combine the information **without losing details** and write to one file with `write_memory_file` (do not discard specifics through summarization)
3. Archive the redundant one with `archive_memory_file` (state the merge target and your reasoning in the reason)
4. If `[IMPORTANT]` tag exists, preserve it in the merged file

- Do not defer pairs you decided to merge. Complete them now

### Step 2: Conceptual integration of [IMPORTANT] knowledge

Consolidate `[IMPORTANT]`-tagged knowledge/ files older than 30 days.

1. Use `search_memory` to find knowledge/ with `[IMPORTANT]`; review those 30+ days old
2. Group by related themes and extract abstract principles
3. Create `concept-{theme}.md` (include `[IMPORTANT]` at the top)
4. Remove `[IMPORTANT]` tag from original files (keep the files themselves)

Skip isolated `[IMPORTANT]` entries or those less than 30 days old.

### Step 3: Procedure knowledge organization

Review files in procedures/:
- Outdated procedures → update or archive
- Similar procedures → merge

### Step 4: Compress old episodes

If episodes/ has files older than 30 days:
- Compress entries without `[IMPORTANT]` tag to key points only

### Step 5: Resolve knowledge contradictions

Check for contradictory knowledge files; keep the accurate one and archive the outdated one.

After completion, output a summary (include number of pairs merged and files archived).
