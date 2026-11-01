<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/operations/property-report-discord-delivery.md -->
<!-- i18n: source-sha256=b3aaea8100ef0ae39fab0b7284164f0edc9fb85cc6acd08a0ae9559608866515 generated=2026-10-24 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# Discord Reporting for Real Estate Daily Reports

The targets are Anjo City 1K rentals (`PTY-ANJO-1K-DAILY`) and daily sale/purchase information (`PROP-07`). This procedure covers the notification configuration and recovery records for reports operated in the current local environment.

## Normal Configuration

From October 25, 2026 onward, daily sale/purchase information (`PROP-07`) and each property's investment analysis report to Discord thread `1563692914620637246`.
The sending script and generated reports both use `sale_investment_analysis.SALE_DISCORD_THREAD_ID`.
Anjo City 1K rental reports continue to use the existing destination, `1491411026263146658`.

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

### Investment Analysis for New Sale Properties (Added 2026-10-25)

`daily-sale-info` processes every existing listing difference in `comparison.new_rows` and creates property-specific Markdown files and an index under `E:/OneDriveBiz/Obsidian/_notes/Property/`.
To show these in the "New" view in `31_Property DB.base`, set the tag to `新規` and include `日付`, `作成日時`, `物件番号`, and `書類名`. Fill in `物件` only when the property name has been verified; otherwise leave it blank.
If the property name is unknown, use "location, structure, year built, price" for the note name (the Base `name` field), for example `今池町・RC・1987年・5000万円`. Add a date or other suffix only to resolve a name collision.
Do not filter the analysis targets by whether they passed the initial screening. Follow the existing difference logic for continued listings and reassigned IDs. If there are no new listings, there is nothing to create; if history cannot be compared, mark the new-listing determination as pending in the daily Products report.

The analysis includes listing values and the SHA-256 of the source JSON, the initial assessment, scenario-based estimates for NOI, debt service, cash flow, and DSCR, and items to check for repairs, legal issues, hazards, and exit options. State the assumptions used for vacancy, expenses, and loan terms. The 8% threshold remains the initial gross-yield screening criterion; it does not establish that a purchase is advisable. Keep the decision pending when information is insufficient.

Link the index from the daily Products report and save the individual file and index paths and SHA-256 values in the Hikaru evidence under `investment_analysis`.
When rerunning an existing daily report, fill in any missing analyses without recollecting data or creating duplicate Products entries. Sakura's runtime script, `review_daily_sale_product_report.py`, validates the analysis through `core.reports.property.sale_investment_analysis.validate_evidence_analysis` and includes the analysis count and index path in the normal completion notification text. The script also carries `investment_analysis` into the review result.
The existing review hold release and duplicate-notification prevention remain in effect. No cron time or command changes are needed.

### Sale Property Numbers

Manage persistent numbers in `SalePortals/property-registry.sqlite3` in the `PROP-000001` format. Assign initial numbers from saved listing history. These numbers are separate from the P codes in reports.
Prefer listing URL history for matching. For different URLs, match on address, year and month built, building area, land area, and number of units. Do not include price or yield in the match key, so the same number remains assigned after a price change or across listing sites.
When a listing lacks enough information to match, or matches multiple candidates, hold it under a separate number to avoid incorrect merges. An index-page URL may cover multiple properties, so do not merge based on the URL alone.

Add the property number to each table in the daily Products report and include a number ledger for all listings. Keep the original JSON/CSV as evidence, and output numbered data as `numbered-listings.json` / `.csv` for that day.
Save the file paths and SHA-256 values, listing count, and property count after deduplication under `property_numbering` in the Hikaru evidence.
If multiple new-difference entries share a number, consolidate the analysis to one entry per property and retain the listing sources and price differences in the text. On 2026-10-25, 15 listings were consolidated into 8 properties, and an existing listing for PROP-000023 was analyzed as a user-requested trial.
Keep the trial analysis out of the daily `new_count` and `investment_analysis`; link to it separately from the daily report.

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
