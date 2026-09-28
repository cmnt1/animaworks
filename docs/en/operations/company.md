<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/operations/company.md -->
<!-- i18n: source-sha256=eef72adf793e641fbc9faf0bde9b9e5891bbced2bf077b33fbf3241b6cfa3c10 generated=2026-09-28 engine=luna model=gpt-6-luna translator=2 -->

> Verified commit: 581e20f1

# Company Management

The company feature is a mechanism for organizing Anima, shared assets, and channels by company within a single AnimaWorks runtime. Use only fictional examples for company names and display names.

## Data Placement and Membership

Company-specific data is placed in `companies/<company>/`, and Anima membership is indicated by `company` in each `animas/<name>/status.json`. The company directory contains display information, company knowledge and skills, shared areas, and more. `companies/<company>/animas/` is a view that references member Anima, while the Anima entities themselves reside on the `animas/` side.

The scope of information sharing is divided as follows:

- Individual knowledge and skills are placed in that Anima's area.
- Knowledge, skills, and work files shared with the company are placed in that company's area.
- Only content that can be common across the entire company is placed in the common area.

Direct communication or delegation between Anima in different companies is subject to boundary checks. Reads and writes to other companies' areas are also restricted. Operations that cannot confirm company boundaries are rejected. Anima without a company assignment are not subject to company separation, so if isolation is needed, assign them explicitly to a company.

## CLI

`cli/commands/company_cmd.py` registers each command in `animaworks company`.

```sh
animaworks company create example-company --display-name "Example Company"
animaworks company list
animaworks company assign sample-anima --to example-company
animaworks company assign sample-anima --unassign
```

`create` creates a company area and fills in any missing skeleton. `list` displays the company and membership status. `assign` changes an Anima's membership. `--unassign` removes membership.

To move existing assets into a company area, use `animaworks company adopt <path> --to <company>`. A backup is created before the move, and by default a relative link remains at the previous location. The dry-run capable `split` plans company creation, membership changes, and asset moves together from a manifest, and applies them only when `--execute` is specified. `export` generates a bundle for company migration. For moves, splits, and exports, check the scope before executing, and after completion, verify the backup against the output.

## Channel Company Assignment

`channel_company_defaults` in `config.json` is a mapping table for inferring the company from the channel name for open channels created without a company specified. Channels to which a value is applied become company-scoped, and participation eligibility and posting permissions follow membership boundaries. When modifying an existing channel, check the target channel's company and members.

For boards created from external messaging, the per-integration `default_channel_company` can also be used. See the [configuration reference](../reference/config.md) for all configuration items.

## GitHub Account Assignment

`github_identities` in `config.json` is a mapping table for selecting which account's credentials to use from the GitHub CLI. `anima:<name>` is a per-Anima specification, and the company slug is used as the company-wide default specification, with per-Anima specifications taking priority.

```json
{
  "github_identities": {
    "example-company": "example-github-account",
    "anima:sample-anima": "sample-github-account"
  }
}
```

Confirm that you are logged in to the corresponding GitHub CLI account. Do not duplicate token values into the configuration file; obtain credentials from the account the command needs. If it cannot be resolved, fall back to the normal active GitHub CLI account.

## Operational Checks

Membership changes are reflected using `status.json` as the source of truth. If company shared assets or search indexes are modified, verify the membership and reference scope, and update the shared index as needed. Do not place company-specific information, personal information, or credentials in the common area.
