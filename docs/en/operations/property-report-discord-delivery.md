<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/operations/property-report-discord-delivery.md -->
<!-- i18n: source-sha256=9da26e5e5a929acf085ea2b5c75f563fc8fd28ee92c9be5af3d0e6012f6c5886 generated=2026-10-21 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# Discord Reporting for Real Estate Daily Reports

The targets are Anjo City 1K rentals (`PTY-ANJO-1K-DAILY`) and daily sale/purchase information (`PROP-07`). This procedure covers the notification configuration and recovery records for reports operated in the current local environment.

## Normal Configuration

The following four jobs in `C:\Users\cmnt\.animaworks\animas\sakura\cron.md` do not have `--local-only` attached during normal operation.

| Job | Schedule | Execution Target |
|---|---|---|
| Anjo City 1K Rentals Products Review/Completion Report | `*/15 6-12 * * *` | `sakura/scripts/review_anjo_1k_product_draft.py` |
| Daily Sale/Purchase Information Report Products Review/Completion Report | `*/15 6-12 * * *` | `sakura/scripts/review_daily_sale_product_report.py` |
| Anjo City 1K Rentals Review Backlog Recheck | `10,40 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PTY-ANJO-1K-DAILY` |
| Daily Sale/Purchase Information Report Review Backlog Recheck | `12,42 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PROP-07` |

The review script is under the Anima runtime, and `run_report_job.py` is under the repository. The Python path to execute maintains the existing cron configuration.

- Only items explicitly approved with `review_hold: false` are updated as completed or reported as complete. Do not treat pending or approval-unknown items as approved in order to resume notifications.
- `confirmed` is owner-managed. Do not change it when restoring or retrying notifications.
- `--local-only` is for limited work that does not perform external sending. If left in the normal cron, Discord reporting stops even after the review is finished.
- If the explanation "external notifications prohibited" from limited work remains in cron or work notes, update the explanation as well when returning to normal operation.

## Confirmation Order When There Is No Report

1. Identify the target in Products by `task_code`, `report_date`, and file path. Do not identify it by P code alone. On 2026-10-17, `P-00391` was duplicated between rentals and sale/purchase, and it was not renumbered in this notification recovery.
2. Check `status` and `discord.status` in the review evidence. `done_local` / `deferred` only indicate completion of a local review and do not mean it has been sent to Discord.
3. If a pending reason remains, close the review by cross-checking the generated evidence, source data and copy, listing count, and necessary saved history. Separate listing information consistency from investment suitability and predictive model accuracy validation.
4. Re-execute only the completed and approved but unnotified items by passing the report date to the corresponding review script via `YYYYMMDD`. When notifying, do not attach `--local-only`. Re-collection or regeneration of data is unnecessary.
5. Cross-check the message ID in the send response with the actual message on Discord. If the response is unknown, check the actual message and do not resend before confirming.
6. Re-execute the same target and confirm that it becomes `NOOP_ALREADY_REVIEWED` or zero unnotified items.
7. After changing cron, check the reload time and registration result of `state/cron_registration.json`. If a process restart is necessary, target only Sakura that has been confirmed not to be in operation. Do not restart the entire server.

## Recovery Results on 2026-10-18

The `--local-only` left in the four jobs during the previous recovery was the cause of the notification stoppage. The setting was removed and returned to normal completion reporting.

- Rentals: Supplementary sent 7 items from 10/12〜18.
- Sale/Purchase: Supplementary sent 5 items from 10/13・14・16・17・18. 10/15 had already been sent, so it was not resent.
- For sale/purchase 10/17 and 10/18, independently cross-checked the pending official generation evidence, source/copy JSON, CSV, Markdown, and listing-day history. Confirmed 15 listings each and 4 primary passes, then sent after approval.
- Saved the message IDs for all 12 items, re-fetched the actual Discord messages, and cross-checked them. There were 0 approved but unnotified items at re-execution.
- Message IDs for the latest day: sale/purchase `1561328465259528206`, rentals `1561328472964599909`.
- Notification destination thread: `1491411026263146658`. After Sakura restart, confirmed 6 jobs registered and 0 rejections at the 19:43:03 JST configuration reload.

Local evidence, backups, and Discord retrieval results before and after sending were saved in the following locations. These and the actual cron and Products are outside Git management, and committing only this document does not change the actual environment configuration.

```text
E:\OneDriveBiz\Obsidian\_data\Property\Products\2026\10\18\discord-recovery\
  audit.json
  send-receipts.json
  verified-message-ids.json
  completion.json
  discord-before.json
  discord-after.json
  backups\
```
