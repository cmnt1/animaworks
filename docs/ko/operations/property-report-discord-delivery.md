<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/operations/property-report-discord-delivery.md -->
<!-- i18n: source-sha256=b3aaea8100ef0ae39fab0b7284164f0edc9fb85cc6acd08a0ae9559608866515 generated=2026-10-24 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# 부동산 일일 리포트의 Discord 보고

대상은 안조시 1K 임대(`PTY-ANJO-1K-DAILY`)와 데일리 매매 정보(`PROP-07`)입니다. 이 절차는 현재 로컬 환경에서 운영하는 리포트의 알림 설정과 복구 기록을 다룹니다.

## 일반 설정

2026년 10월 25일부터 데일리 매매 정보(`PROP-07`)와 각 매물의 투자 분석 리포트는 Discord 스레드 `1563692914620637246`에 보고합니다.
전송 스크립트와 생성된 리포트는 `sale_investment_analysis.SALE_DISCORD_THREAD_ID`를 함께 참조합니다.
안조시 1K 임대 보고 대상은 기존 `1491411026263146658`을 계속 사용합니다.

`C:\Users\cmnt\.animaworks\animas\sakura\cron.md`의 다음 4개 작업은 일반 운영에서 `--local-only`을 붙이지 않습니다.

| 작업 | 스케줄 | 실행 대상 |
|---|---|---|
| 안조시 1K 임대 Products 리뷰·완료 보고 | `*/15 6-12 * * *` | `sakura/scripts/review_anjo_1k_product_draft.py` |
| 데일리 매매 정보 리포트 Products 리뷰·완료 보고 | `*/15 6-12 * * *` | `sakura/scripts/review_daily_sale_product_report.py` |
| 안조시 1K 임대 리뷰 적체 재확인 | `10,40 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PTY-ANJO-1K-DAILY` |
| 데일리 매매 정보 리포트 리뷰 적체 재확인 | `12,42 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PROP-07` |

리뷰용 스크립트는 Anima의 런타임 하위에, `run_report_job.py`은 리포지토리 하위에 있습니다. 실행하는 Python 경로는 기존 cron 설정을 유지합니다.

- `review_hold: false`을 명시하여 승인한 것만 완료 업데이트·완성 보고합니다. 보류 중·승인 불명인 것을 알림 재개를 위해 승인으로 취급하지 않습니다.
- `confirmed`는 오너 관리입니다. 알림 복구·재시도에서는 변경하지 않습니다.
- `--local-only`은 외부 전송을 하지 않는 한정 작업용입니다. 일반 cron에 남기면 리뷰가 끝나도 Discord 보고가 멈춥니다.
- 한정 작업 시의 "외부 알림 금지"라는 설명이 cron이나 작업 메모에 남아 있는 경우, 일반 운영 복귀에 맞춰 설명도 업데이트합니다.

### 신규 매매 매물의 투자 분석 (2026-10-25 추가)

`daily-sale-info`는 기존 매물 차이인 `comparison.new_rows` 전체를 대상으로 `E:/OneDriveBiz/Obsidian/_notes/Property/`에 매물별 Markdown 파일과 목록을 만듭니다.
`31_Property DB.base`의 "신규" 뷰에서 표시되도록 태그는 `新規`로 하고 `日付`·`作成日時`·`物件番号`·`書類名`을 설정합니다. `物件`에는 확인된 매물명만 입력하고, 알 수 없으면 비워 둡니다.
매물명을 모르는 경우 노트 이름(Base의 name 필드)은 "소재지·구조·준공연도·가격"으로 합니다. 예: `今池町・RC・1987年・5000万円`. 동일 이름 노트와 충돌할 때만 날짜 등을 덧붙입니다.
1차 통과 여부로 분석 대상을 제한하지 않습니다. 계속 게재되거나 ID가 재부여된 경우에는 기존 차이 판정 규칙을 따릅니다. 신규 매물이 없으면 생성 대상이 없으며, 이력 비교를 할 수 없으면 신규 판정을 보류로 표시해 일일 Products에 명시합니다.

분석에는 게재 값과 출처 JSON의 SHA-256, 1차 판단, 가정별 NOI·상환액·현금흐름(CF)·DSCR 추정, 수리·법률·재해 위험·매각 출구 확인 항목을 포함합니다. 공실률·경비율·대출 조건 가정을 명시합니다. 8%는 기존의 표면 수익률 1차 기준이며 매입 가능 여부를 확정하는 판단은 아닙니다. 자료가 부족하면 판단을 보류합니다.

일일 Products에서 목록으로 링크하고 Hikaru 증거의 `investment_analysis`에 개별 파일과 목록의 경로 및 SHA-256을 저장합니다.
기존 일일분을 다시 실행할 때는 누락된 분석을 보완하고, 데이터를 다시 수집하거나 Products를 중복 생성하지 않습니다. Sakura 런타임 스크립트 `review_daily_sale_product_report.py`는 `core.reports.property.sale_investment_analysis.validate_evidence_analysis`로 분석을 검증하고, 일반 완료 알림 문구에 분석 건수와 목록 경로를 포함합니다. 리뷰 결과에도 `investment_analysis`를 이어 전달합니다.
기존 리뷰 보류 해제와 중복 알림 방지는 계속 적용합니다. cron 시각과 명령은 변경할 필요가 없습니다.

### 매매 매물 번호

`SalePortals/property-registry.sqlite3`에서 `PROP-000001` 형식의 번호를 영구 관리합니다. 최초 번호는 저장된 게재 이력에서 부여합니다. 리포트의 P 코드와는 별도 번호입니다.
게재 URL 이력을 우선하며, URL이 다르면 소재지·준공 연월·건물 면적·토지 면적·세대 수가 일치하는지 확인합니다. 가격과 수익률은 매칭 키에 포함하지 않아 가격 변경이나 매체가 달라도 같은 번호를 유지합니다.
매칭에 필요한 정보가 부족하거나 여러 후보가 있는 게재는 잘못 합치지 않도록 별도 번호로 보류합니다. 목록 페이지 URL에는 여러 매물이 포함될 수 있으므로 URL만으로 통합하지 않습니다.

일일 Products의 각 표에 매물 번호를 추가하고 전체 게재 번호 대장을 첨부합니다. 원본 JSON/CSV는 보존 증거로 유지하고, 번호가 붙은 데이터는 해당 일자의 `numbered-listings.json` / `.csv`로 출력합니다.
Hikaru 증거의 `property_numbering`에 파일 경로와 SHA-256, 게재 건수, 중복 통합 후 매물 수를 저장합니다.
신규 차이에 같은 번호가 여러 번 있으면 분석은 매물별 1건으로 통합하고, 본문에 게재처와 가격 차이를 남깁니다. 2026-10-25에는 게재 15건을 매물 8개로 통합했고, 사용자가 요청한 시험 분석으로 기존 매물 PROP-000023을 분석했습니다.
시험 분석은 일일 `new_count`나 `investment_analysis`에 포함하지 않고 일일 본문에서 별도로 링크합니다.

## 보고가 없을 때의 확인 순서

1. Products의 `task_code`·`report_date`·파일 경로로 대상을 특정합니다. P 코드만으로는 특정하지 않습니다. 2026-10-17에는 임대와 매매에서 `P-00391`가 중복되어 있었고, 이번 알림 복구에서는 번호를 바꾸지 않았습니다.
2. 리뷰 증적의 `status`과 `discord.status`를 확인합니다. `done_local` / `deferred`은 로컬 리뷰만의 완료이며, Discord 전송 완료를 의미하지 않습니다.
3. 보류 사유가 남아 있는 경우에는 생성 증적·원본 데이터와 복사본·게재 건수·필요한 저장 이력을 대조하여 리뷰를 닫습니다. 게재 정보의 정합성과 투자 적격성·예측 모델의 정확도 검증을 분리합니다.
4. 완료·승인된 미알림 분만, 대응하는 리뷰용 스크립트에 보고일을 `YYYYMMDD`로 전달하여 재실행합니다. 알림할 때는 `--local-only`을 붙이지 않습니다. 데이터 재수집이나 재생성은 불필요합니다.
5. 전송 응답의 message ID와 Discord상의 실제 메시지를 대조합니다. 응답 불명인 경우에는 실제 메시지를 조사하고, 확인 전에 재전송하지 않습니다.
6. 같은 대상을 재실행하여 `NOOP_ALREADY_REVIEWED` 또는 미알림 0건이 되는 것을 확인합니다.
7. cron 변경 후에는 `state/cron_registration.json`의 재로드 시각과 등록 결과를 확인합니다. 프로세스 재시작이 필요하면, 작업 중이 아님을 확인한 Sakura만을 대상으로 합니다. 서버 전체를 재시작하지 않습니다.

## 2026-10-18의 복구 결과

이전 복구에서 4개 작업에 남긴 `--local-only`이 알림 중단의 원인이었습니다. 설정을 해제하고 일반 완성 보고로 되돌렸습니다.

- 임대: 10/12〜18의 7건을 보충 전송.
- 매매: 10/13・14・16・17・18의 5건을 보충 전송. 10/15은 이미 전송 완료였으므로 재전송하지 않았습니다.
- 매매 10/17·18은 보류 중이던 정식 생성 증적·원본/복사 JSON·CSV·Markdown·게재 일수 이력을 독립 대조. 각 15건 게재·1차 통과 4건을 확인하여 승인 후 전송했습니다.
- 12건 모두의 message ID를 저장하고, Discord의 실제 메시지를 재취득하여 대조. 재실행 시 승인된 미알림은 0건.
- 최신일의 message ID: 매매 `1561328465259528206`, 임대 `1561328472964599909`.
- 알림 대상 스레드: `1491411026263146658`. Sakura 재시작 후, 19:43:03 JST의 설정 재로드에서 6개 작업 등록·거부 0건을 확인.

로컬 증적·백업·전송 전후의 Discord 취득 결과는 다음 위치에 저장했습니다. 이들과 실제 cron·Products는 Git 관리 외이며, 이 문서의 커밋만으로는 실환경의 설정이 변경되지 않습니다.

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
