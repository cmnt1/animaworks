# Tool Usage Guide

### 백그라운드 명령 출력
장시간 명령 출력은 `state/cmd_output/`에 저장됩니다. `Read(path="state/cmd_output/{id}.txt")`로 중간 출력을 확인할 수 있습니다.
약 20분가량 걸릴 수 있는 명령 (예: 무거운 테스트)은 백그라운드로 실행하고, 몇 분마다 상태나 출력의 끝을 확인하며 진행 상황을 추적하세요.
