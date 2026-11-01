<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/operations/property-report-discord-delivery.md -->
<!-- i18n: source-sha256=b3aaea8100ef0ae39fab0b7284164f0edc9fb85cc6acd08a0ae9559608866515 generated=2026-11-01 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# Discord Reporting for Real Estate Daily Reports

The targets are Anjo City 1K rentals (`PTY-ANJO-1K-DAILY`) and daily sale/purchase information (`PROP-07`). This procedure covers the notification configuration and recovery records for reports operated in the current local environment.

## Normal Configuration

From 2026-10-25 onward, daily sale/purchase information (PROP-07) and the investment analysis report for each property are reported to
Discord thread `1563692914620637246`.
The send script and generated reports commonly reference `sale_investment_analysis.SALE_DISCORD_THREAD_ID`.
For Anjo City 1K rentals, use the existing reporting destination `1491411026263146658`.

For the following 4 jobs in `C:\Users\cmnt\.animaworks\animas\sakura\cron.md`, do not add `--local-only` during normal operation.

| Job | Schedule | Execution target |
|---|---|---|
| Anjo City 1K Rentals Products review/completion report | `*/15 6-12 * * *` | `sakura/scripts/review_anjo_1k_product_draft.py` |
| Daily sale/purchase information report Products review/completion report | `*/15 6-12 * * *` | `sakura/scripts/review_daily_sale_product_report.py` |
| Anjo City 1K Rentals review backlog recheck | `10,40 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PTY-ANJO-1K-DAILY` |
| Daily sale/purchase information report review backlog recheck | `12,42 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PROP-07` |

The review script is under the Anima runtime, and `run_report_job.py` is under the repository. Keep the existing cron configuration for the Python path to execute.

- Only items explicitly approved with `review_hold: false` are updated as completed or reported as completed. Do not treat pending or approval-unknown items as approved in order to resume notifications.
- `confirmed` is owner-managed. Do not change it when restoring or retrying notifications.
- `--local-only` is for limited work that does not perform external sending. If left in normal cron, Discord reporting stops even after review ends.
- If descriptions such as "external notifications prohibited" from limited work remain in cron or work notes, update those descriptions as well when returning to normal operation.

## Confirmation Order When There Is No Report

### Investment Feasibility Analysis for New Sale/Purchase Properties (Added 2026-10-25)

`daily-sale-info` targets all existing listing diffs `comparison.new_rows`,
and creates property-specific Markdown and a list in `E:/OneDriveBiz/Obsidian/_notes/Property/`.
To display them in the "New" view of `31_Property DB.base`, use the tag `新規`,
and assign `日付`, `作成日時`, `物件番号`, and `書類名`. For `物件`, enter only property names that can be confirmed, and leave it blank if unknown.
For the note name (Base's name field), if the property name is unknown, use "location, structure, building age, price"
(example: `今池町・RC・1987年・5000万円`). Add a date, etc. only when it conflicts with a note of the same name.
Do not narrow targets based on whether they passed the first screening. Continued listings and ID reassignment follow the existing diff determination.
If there are zero new items, state that there is nothing to create; if history comparison is unavailable, state in the daily Products that new determination is pending.

The analysis includes listing values and the SHA-256 of the source JSON, first judgment, trial calculations under different assumptions for NOI, repayment, CF, and DSCR,
and confirmation items for repairs, legal matters, hazards, and exit. Clearly state the assumptions for vacancy rate, expense ratio, and financing conditions in the trial calculations.
8% is the conventional first-screening benchmark for gross yield, and is not a final determination that purchase is possible. If materials are insufficient, defer judgment.

Link from the daily Products to the list, and save the paths and SHA-256 of the individual files and the list in Hikaru evidence `investment_analysis`.
When rerunning existing daily portions, supplement analyses that have not been created, and do not recollect or duplicate Products.
Sakura's runtime script `review_daily_sale_product_report.py`
validates the analysis with `core.reports.property.sale_investment_analysis.validate_evidence_analysis`,
and includes the analysis count and list path from `notification_text` in the normal completion notification.
The same script also carries over `investment_analysis` to the review results.
Review hold release and existing notification duplication prevention continue to apply. No changes to cron times or commands are needed.

### Sale/Purchase Property Numbers

Manage numbers in the `PROP-000001` format persistently in `SalePortals/property-registry.sqlite3`.
For the first time, assign numbers from the saved listing history. These are different from the report's P codes.
Prioritize the history of listing URLs, and match different URLs by agreement of location, building date, building area, land area, and number of units.
Do not include price or yield in the matching key, and maintain the same number even if the price changes or the medium differs.
Listings lacking the information necessary for a match, or listings with multiple candidates, are held as separate numbers to avoid incorrect merging.
List page URLs may contain multiple properties, so do not merge based only on URL.

Add property numbers to each table in the daily Products, and attach a number ledger for all listings.
Keep the original JSON/CSV as preservation evidence, and output numbered data to the same day's `numbered-listings.json` / `.csv`.
Save file paths and SHA-256, the number of listings, and the number of properties after duplicate merging in Hikaru evidence `property_numbering`.
If the same number appears multiple times in new diffs, combine the analysis into one item per property, and leave the listing source and price differences in the body.
On 2026-10-25, 15 listings were merged into 8 properties, and an existing listing for PROP-000023 was trial-analyzed at the user's request.
Do not mix trial analyses into the daily `new_count` or `investment_analysis`; link them separately from the daily body.

### Notification Confirmation

1. Identify the target in Products by `task_code`, `report_date`, and file path. Do not identify it by P code alone. On 2026-10-17, `P-00391` was duplicated between rentals and sale/purchase, and it was not renumbered in this notification recovery.
2. Check `status` and `discord.status` in the review evidence. `done_local` / `deferred` mean completion of local review only, and do not mean it was sent to Discord.
3. If a hold reason remains, close the review by comparing the generation evidence, source data and copy, listing count, and necessary preservation history. Separate consistency of listing information from validation of investment eligibility and prediction model accuracy.
4. Rerun only completed/approved unnotified items by passing the report date to the corresponding review script with `YYYYMMDD`. When notifying, do not add `--local-only`. Recollection or regeneration of data is unnecessary.
5. Compare the message ID in the send response with the actual message on Discord. If the response is unknown, check the actual message, and do not resend before confirming.
6. Rerun the same target and confirm that it becomes `NOOP_ALREADY_REVIEWED` or that there are 0 unnotified items.
7. After changing cron, check the reload time and registration result of `state/cron_registration.json`. If a process restart is necessary, target only Sakura after confirming it is not in use. Do not restart the entire server.

## Recovery Results on 2026-10-18

The `--local-only` left in 4 jobs during the previous recovery was the cause of the notification stoppage. The setting was removed, and normal completion reporting was restored.

- Rentals: resent 7 items from 10/12〜18.
- Sale/purchase: resent 5 items from 10/13・14・16・17・18. 10/15 had already been sent, so it was not resent.
- For sale/purchase on 10/17 and 10/18, independently compared the pending official generation evidence, source/copy JSON, CSV, Markdown, and listing-day history. Confirmed 15 listings and 4 first-screening passes for each, then sent after approval.
- Saved the message IDs for all 12 items, re-fetched the actual Discord messages, and compared them. On rerun, there were 0 approved unnotified items.
- Latest day's message IDs: sale/purchase `1561328465259528206`, rentals `1561328472964599909`.
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
