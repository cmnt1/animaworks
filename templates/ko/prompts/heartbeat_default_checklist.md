- `status: ok`의 `Current Pre-Observed Heartbeat Snapshot`을 확인 근거로 사용한다. 없으면 `heartbeat_observe_snapshot`를 호출한다
- current_state.md의 진행 중 작업과 list_tasks의 STALE / 24시간 초과 대기 작업을 확인하고 근거를 제시한다
- 자신이 멤버인 모든 채널(general과 소속 부서, ops는 멤버인 경우)을 read_channel로 확인하고, 자신에게 온 멘션 여부를 말한다. 칭찬·승인만 있는 게시물은 하지 않는다
- 필요한 외부 도구에 접근할 수 있는지, 진행 중 작업에 블로커가 없는지 확인한다
- 파일 부재·권한 부족·전제 미충족·지침 불명 등의 블로커는 의뢰자에게 즉시 보고한다. 30분을 초과하는 중대한 블로커는 call_human도 보낸다
- 위 사항이 모두 해소되었다고 확인된 응답에만 HEARTBEAT_OK를 포함한다

보드 게시 판단은 `common_knowledge/communication/broadcasting-guide.md`을 따른다.
