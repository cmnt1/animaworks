---
name: aws-collector-tool
description: >-
  AWS 인프라 정보 수집 도구. ECS 상태, CloudWatch 로그, 메트릭스를 가져옵니다.
  Use when: ECS 가동 확인, CloudWatch에서 오류 로그 조사, 메트릭스 수집, AWS 리소스 모니터링이 필요할 때.
tags: [infrastructure, aws, monitoring, external]
---


# AWS Collector 도구

AWS ECS 상태, CloudWatch 로그, 메트릭스를 수집하는 외부 도구.

## 호출 방법

**Bash**: `animaworks-tool aws_collector <サブコマンド> [引数]` 로 실행

## 액션 목록

### ecs_status — ECS 서비스 상태 확인
```bash
animaworks-tool aws_collector ecs-status [--cluster NAME] [--service NAME]
```

### error_logs — 오류 로그 가져오기
```bash
animaworks-tool aws_collector error-logs --log-group NAME [--hours 1] [--patterns "ERROR"]
```

### metrics — 메트릭스 가져오기
```bash
animaworks-tool aws_collector metrics --cluster NAME --service NAME [--metric CPUUtilization]
```

## CLI 사용법

```bash
animaworks-tool aws_collector ecs-status [--cluster NAME] [--service NAME]
animaworks-tool aws_collector error-logs --log-group NAME [--hours 1] [--patterns "ERROR"]
animaworks-tool aws_collector metrics --cluster NAME --service NAME [--metric CPUUtilization]
```

## 주의사항

- AWS 인증 정보(환경 변수 또는 credentials) 설정 필요
- --region 으로 리전 지정 가능
