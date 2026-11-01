# 지견 승격 리뷰 — Obsidian `_inbox/` 판정 흐름

각 Anima가 `procedures/` `knowledge/` 에 축적한 지견 중, `promote_knowledge.py`(주간 cron)가
Obsidian `_ai_rules/_inbox/<Project>/` 에 스테이징한다. 본 문서는 그 staging을
**정본(`_ai_rules/projects/<Project>/runbooks/`)으로 승격시킬지·폐기할지**를 판정하기 위한
공통 프레임워크.

> 설계 취지: Obsidian `_ai_rules/` 은 "스톡 / canonical", Anima의 per-anima 기억은 "플로".
> Anima가 직접 Obsidian 정본에 기록하는 것은 금지. `_inbox/` 을 한 단계 끼워 넣음으로써 정본의 품질을 유지한다.

## 관계자와 책임 분담

| 구분 | 대상 inbox | 판정자 | 보조 |
|---|---|---|---|
| 전사·조직 횡단 | `_inbox/General/` | **오너(인간)** | sakura가 리뷰 관점을 정리하여 call_human |
| 부문 고유 | `_inbox/<部門>/` | **부문 GL** | sakura가 delegate_task로 의뢰, GL이 판정 |
| 부문 횡단 노하우 | `_inbox/<部門>/` 의 일부 | **부문 GL → sakura → 오너** | GL이 "General 후보" 플래그하여 상신 |

부문 GL(project_manager):

- Affiliate → kanna
- Finance → ayane
- Property → hikaru
- Administration → sora(※ `_ai_rules/projects/Administration/` 은 미정비, 당분간 General 취급)

## 채택 기준(승격 판정)

다음을 **모두 충족하는** 것만 runbooks에 승격시킨다:

1. **재이용성**: 동종의 상황이 장래 다시 일어날 수 있다(1회 한정 상황 메모는 불채택)
2. **재현 가능성**: 구체적인 커맨드·설정값·판단 포인트가 적혀 있다
3. **비중복**: 기존 runbooks / common_knowledge와 내용이 중복되지 않는다
4. **정확성**: 낡은 정보·잘못된 추측을 포함하지 않는다
5. **입도 적절**: 너무 세밀(1커맨드 메모)하지도 너무 거칠(챕터 레벨)하지도 않다

## 불채택해야 할 패턴

- 날짜 고유의 스냅샷(`weekly-consolidation-2026w20.md` 같은 주간 회고)
- 일회성 장애 대응으로 재발하지 않는 것
- 기존 문서와 내용이 거의 같아 부가 가치가 없는 것
- Anima 자신의 감상·깨달음만으로 절차화되지 않은 것
- 해당 Anima의 per-anima knowledge/ 에 두면 충분한 것

## 판정 흐름

```
_inbox/<Project>/<file>.md を開く
   ↓
採用基準1-5をすべて満たすか？
   ├─ Yes → 「採用」
   │         ├─ frontmatter `status: pending_review` を削除
   │         ├─ frontmatter `promoted_at` `source_*` は残す（出自トレース）
   │         ├─ ファイル名から `YYYY-MM-DD-<anima>-` プレフィックスを除去
   │         └─ `_ai_rules/projects/<Project>/runbooks/` に移動
   │
   ├─ 部門横断（General候補） → 「上申」
   │         └─ そのまま `_inbox/General/` に移動し、sakura に報告
   │
   └─ No → 「不採用」
             └─ `_inbox/` から削除（source側の `promoted_to_inbox` スタンプは残るので再昇格されない）
```

## 부문 GL 에 대한 delegate_task 템플릿(sakura용)

```
to: <gl_name>
intent: delegation
content:
  Obsidian の `E:/OneDriveBiz/Obsidian/_ai_rules/_inbox/<Project>/` 配下に、今週Animaから昇格された
  知見が staging されています。`common_knowledge/operations/knowledge-promotion-review.md` の
  「採用基準」と「判定フロー」に従って各ファイルを判定し、以下を行ってください。

  完了条件:
  - 採用したファイル: `_ai_rules/projects/<Project>/runbooks/` に移動済み（frontmatter整形・ファイル名整形済み）
  - 不採用ファイル: `_inbox/<Project>/` から削除済み
  - General候補としてsakuraへ上申するファイル: `_inbox/General/` に移動し、報告に列挙
  - 報告に含めるもの: 採用件数 / 不採用件数 / 上申件数 / 各ファイル名と一行理由

  期限: <YYYY-MM-DD HH:MM>
```

## 정형 규칙(채택 시)

frontmatter 예:

```yaml
---
# 残す（出自トレース用）
project: Affiliate
promoted_at: 2026-05-18T12:34:56+09:00
role: runbook
scope: project
source_anima: kanna
source_confidence: 1.0
source_kind: procedures
source_path: C:/Users/cmnt/.animaworks/animas/kanna/procedures/xxx.md
updated: 2026-05-18

# 削除する
status: pending_review
```

파일명:

- before: `2026-05-18-kanna-sql-server-334-trigger-output-fix.md`
- after:  `sql-server-334-trigger-output-fix.md`

> 주의: Obsidian view(`AI Rules DB.base`)가 `status: pending_review` 로 `_inbox/` 를 필터링하고 있는
> 경우가 있으므로, status를 삭제하지 않는 한 정본 취급이 되지 않는다.

## 관련

- 승격 스크립트: `E:/OneDriveBiz/Tools/General/animaworks/scripts/promote_knowledge.py`
- 설정: `scripts/promote_knowledge.json`
- 운영 문서: `scripts/promote_knowledge.md`
- SoT 원칙: `E:/OneDriveBiz/Obsidian/_ai_rules/_index.md`
