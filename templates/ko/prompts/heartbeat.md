하트비트입니다. 담당의 정기 확인을 수행해 주세요.

## 확인 사항
{checklist}

미처리 요청·이상·마감일이 있는 업무에 필요한 대응을 선택한다.
- 실제 작업은 `submit_tasks`, 위임은 `delegate_task`. 기존 작업에 대한 추가 정보는 기존 ID에 연결하고, 같은 내용의 작업을 새로 만들지 않는다. 인간에 대한 연락·승인은 `send_message` / `call_human`에서 판단·대응이 필요한 상대에게 직접 보내고, 같은 내용을 모든 계층에 전달하지 않는다.
- 받은 지침은 대응·위임·명시한 대기 이유 중 하나를 남긴다.
- `animaworks-tool task board`에서 자신의 대장을 정리한다. 닫을지는 주인이 현재 상황에서 판단하며, 작업 본문의 「취소 없음」「pending 유지」 등의 과거 지정보다 우선한다. 스스로 진행할 수 없는 대기는 대기 이유와 해제 조건을 적어 `task cancel ID --reason 理由`(보류 대장이 있으면 그곳에 1행), 전제가 바뀌었거나 당분간 착수할 수 없는 것은 닫고 이후 확인은 하나의 집계 작업으로 모으며, 결론까지 끝난 것은 `task done ID --note 結果`. 위임한 쪽은 `--all`에서 보고, 진행되지 않는 위임은 `task claim ID` → `task cancel`로 닫는다.
- 미완료 실행 알림은 기완료된 조작·성과를 확인한 후 계속을 판단하고, 계속은 `submit_tasks`의 tasks에 `{{"task_id":"既存ID","resume":true}}`(원래 입력은 저장됨). 불필요하면 `update_task(status="cancelled", summary="理由")`.

복구 목적의 순회·일괄 재투입은 불필요. 필요한 업무 절차·승인 조건은 참조한다. 대응 사항이 없으면 HEARTBEAT_OK만 반환한다.

## 관측과 연락 확인

Current Pre-Observed Heartbeat Snapshot이 제시된 경우, 고정 스코프의 관측 결과로서 먼저 확인한다. 같은 범위를 재스캔하지 않고, 외부 확인이 필요한 경우에만 추가로 조사한다. 연락은 `communication/message-quality-protocol.md`, 위임은 `operations/task-delegation-guide.md`에 따른다.
