<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/operations/property-report-discord-delivery.md -->
<!-- i18n: source-sha256=b3aaea8100ef0ae39fab0b7284164f0edc9fb85cc6acd08a0ae9559608866515 generated=2026-11-01 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# 부동산 일일 리포트의 Discord 보고

대상은 안조시 1K 임대(`PTY-ANJO-1K-DAILY`)와 데일리 매매 정보(`PROP-07`)이다. 이 절차는 현재 로컬 환경에서 운영하는 리포트의 알림 설정과 복구 기록을 다룬다.

## 일반 설정

2026-10-25 이후, 데일리 매매 정보(PROP-07)와 각 물건의 투자 분석 리포트는
Discord 스레드 `1563692914620637246`에 보고한다.
전송 스크립트와 생성 리포트는 `sale_investment_analysis.SALE_DISCORD_THREAD_ID`을 공통 참조한다.
안조시 1K 임대의 보고 대상은 기존의 `1491411026263146658`를 사용한다.

`C:\Users\cmnt\.animaworks\animas\sakura\cron.md`의 다음 4개 작업은 일반 운영에서 `--local-only`를 붙이지 않는다.

| 작업 | 스케줄 | 실행 대상 |
|---|---|---|
| 안조시 1K 임대 Products 리뷰・완료 보고 | `*/15 6-12 * * *` | `sakura/scripts/review_anjo_1k_product_draft.py` |
| 데일리 매매 정보 리포트 Products 리뷰・완료 보고 | `*/15 6-12 * * *` | `sakura/scripts/review_daily_sale_product_report.py` |
| 안조시 1K 임대 리뷰 적체 재확인 | `10,40 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PTY-ANJO-1K-DAILY` |
| 데일리 매매 정보 리포트 리뷰 적체 재확인 | `12,42 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PROP-07` |

리뷰용 스크립트는 Anima의 런타임 하위에, `run_report_job.py`은 리포지토리 하위에 있다. 실행하는 Python 경로는 기존 cron 설정을 유지한다.

- `review_hold: false`를 명시하여 승인한 것만 완료 업데이트・완성 보고한다. 보류 중・승인 불명인 것을 알림 재개를 위해 승인 취급하지 않는다.
- `confirmed`는 오너 관리. 알림 복구・재시도에서는 변경하지 않는다.
- `--local-only`은 외부 전송을 하지 않는 한정 작업용. 일반 cron에 남겨 두면 리뷰가 끝나도 Discord 보고가 멈춘다.
- 한정 작업 시의 "외부 알림 금지"라는 설명이 cron이나 작업 메모에 남아 있는 경우, 일반 운영 복귀에 맞춰 설명도 업데이트한다.

## 보고가 없는 경우의 확인 순서

### 신규 매매 물건의 투자 가능성 분석(2026-10-25 추가)

`daily-sale-info`은 기존 게재 차이 `comparison.new_rows` 전건을 대상으로,
`E:/OneDriveBiz/Obsidian/_notes/Property/`에 물건별 Markdown과 목록을 작성한다.
`31_Property DB.base`의 "신규" 뷰에서 표시하기 위해 태그는 `新規`로 하고,
`日付`・`作成日時`・`物件番号`・`書類名`을 부여한다. `物件`는 확인할 수 있었던 물건명만 기입하고, 불명이면 공란으로 둔다.
노트명(Base의 name란)은 물건명이 불명이면 "소재지・구조・준공연도・가격"
(예: `今池町・RC・1987年・5000万円`)으로 한다. 동명 노트와 충돌할 때만 날짜 등을 붙인다.
1차 통과 여부로 대상을 좁히지 않는다. 계속 게재・ID 교체는 기존 차이 판정에 따른다.
신규 제로는 작성 대상 없음, 이력 비교 불가는 신규 판정 보류로 일일 Products에 명시한다.

분석에는 게재값과 출처 JSON의 SHA-256, 1차 판단, NOI・상환・CF・DSCR의 가정별 시산,
수선・법무・해저드・출구의 확인 사항을 포함한다. 시산의 공실률・경비율・융자 조건은 가정을 명기한다.
8%는 기존의 표면 수익률 1차 기준이며, 구매 가능의 확정 판단이 아니다. 자료 부족은 판단 보류.

일일 Products에서 목록에 링크하고, Hikaru 증적의 `investment_analysis`에 개별 파일과 목록의 경로・SHA-256을 저장한다.
기존 일일분 재실행에서는 미작성 분석을 보완하고, 재수집이나 Products의 중복 작성은 하지 않는다.
Sakura의 런타임 스크립트 `review_daily_sale_product_report.py`는
`core.reports.property.sale_investment_analysis.validate_evidence_analysis`에서 분석을 검증하고,
`notification_text`의 분석 건수・목록 경로를 일반 완료 알림에 포함한다.
같은 스크립트는 리뷰 결과에도 `investment_analysis`를 승계한다.
리뷰 보류 해제와 기존 알림 중복 방지는 계속 적용한다. cron 시각・명령은 변경 불필요.

### 매매 물건 번호

`SalePortals/property-registry.sqlite3`에서 `PROP-000001` 형식의 번호를 영구 관리한다.
최초에는 저장된 게재 이력에서 채번한다. 리포트의 P 코드와는 다른 번호이다.
게재 URL의 이력을 우선하고, 다른 URL은 소재지・준공연월・건물 면적・토지 면적・호수의 일치로 대조한다.
가격・수익률은 대조 키에 포함하지 않고, 가격 변경이나 매체 차이에도 같은 번호를 유지한다.
일치에 필요한 정보가 부족한 게재나 복수 후보가 있는 게재는 별도 번호로 보류하고, 오통합을 피한다.
목록 페이지 URL은 복수 물건을 포함할 수 있으므로, URL만으로는 통합하지 않는다.

일일 Products의 각 표에 물건 번호를 부가하고, 전 게재의 번호 대장을 붙인다.
원본 JSON/CSV는 저장 증적으로 보존하고, 번호 부여 데이터는 같은 날의 `numbered-listings.json` / `.csv`에 출력한다.
Hikaru 증적의 `property_numbering`에 파일 경로와 SHA-256, 게재 수와 중복 통합 후의 물건 수를 저장한다.
신규 차이에 같은 번호가 여러 개 있는 경우, 분석은 물건별로 1건으로 묶고 게재 출처와 가격 차이를 본문에 남긴다.
2026-10-25는 15건 게재를 8개 물건으로 통합하고, PROP-000023의 기존 게재를 사용자 요청으로 시험 분석했다.
시험 분석은 일일 `new_count`나 `investment_analysis`에 혼입시키지 않고, 일일 본문에서 별도로 링크한다.

### 알림 확인

1. Products의 `task_code`・`report_date`・파일 경로로 대상을 특정한다. P 코드만으로는 특정하지 않는다. 2026-10-17에는 임대와 매매에서 `P-00391`가 중복되어 있었고, 이번 알림 복구에서는 번호를 고치지 않았다.
2. 리뷰 증적의 `status`과 `discord.status`를 확인한다. `done_local` / `deferred`은 로컬 리뷰만 완료된 것이며, Discord 전송 완료를 의미하지 않는다.
3. 보류 사유가 남아 있는 경우, 생성 증적・원본 데이터와 복사본・게재 건수・필요한 저장 이력을 대조하여 리뷰를 닫는다. 게재 정보의 정합성과 투자 적격성・예측 모델의 정밀도 검증을 분리한다.
4. 완료・승인된 미알림분만, 대응하는 리뷰용 스크립트에 보고일을 `YYYYMMDD`로 전달하여 재실행한다. 알림할 때는 `--local-only`을 붙이지 않는다. 데이터 재수집이나 재생성은 불필요.
5. 전송 응답의 message ID와 Discord상의 실제 메시지를 대조한다. 응답 불명인 경우에는 실제 메시지를 조사하고, 확인 전에 재전송하지 않는다.
6. 같은 대상을 재실행하여 `NOOP_ALREADY_REVIEWED` 또는 미알림 0건이 되는 것을 확인한다.
7. cron 변경 후에는 `state/cron_registration.json`의 재읽기 시각과 등록 결과를 확인한다. 프로세스 재시작이 필요하면, 작업 중이 아님이 확인된 Sakura만을 대상으로 한다. 서버 전체를 재시작하지 않는다.

## 2026-10-18의 복구 결과

지난번 복구에서 4개 작업에 남긴 `--local-only`이 알림 중지의 원인이었다. 설정을 해제하고, 일반 완료 보고로 되돌렸다.

- 임대: 10/12〜18의 7건을 추가 전송.
- 매매: 10/13・14・16・17・18의 5건을 추가 전송. 10/15은 이미 전송 완료였으므로 재전송하지 않았다.
- 매매 10/17・18은 보류 중이던 정식 생성 증적・원본/복사 JSON・CSV・Markdown・게재 일수 이력을 독립 대조. 각 15건 게재・1차 통과 4건을 확인하여 승인 후 전송했다.
- 12건 모두의 message ID를 저장하고, Discord의 실제 메시지를 재취득하여 대조. 재실행 시의 승인 완료 미알림은 0건.
- 최신일의 message ID: 매매 `1561328465259528206`, 임대 `1561328472964599909`.
- 알림 대상 스레드: `1491411026263146658`. Sakura 재시작 후, 19:43:03 JST의 설정 재읽기에서 6개 작업 등록・거부 0건을 확인.

로컬 증적・백업・전송 전후의 Discord 취득 결과는 다음 위치에 저장했다. 이것들과 실제 cron・Products는 Git 관리 외이며, 이 문서의 커밋만으로는 실환경 설정은 변경되지 않는다.

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
