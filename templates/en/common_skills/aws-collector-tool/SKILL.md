---
name: aws-collector-tool
description: >-
  AWS infrastructure information collection tool. Retrieves ECS status, CloudWatch logs, and metrics.
  Use when: Use when: checking ECS operation, investigating error logs in CloudWatch, retrieving metrics, or monitoring AWS resources is needed.
tags: [infrastructure, aws, monitoring, external]
---
Understood. Please provide the Japanese content you’d like me to translate, and I’ll follow all the specified instructions.# AWS Collector Tool

An external tool that collects AWS ECS status, CloudWatch logs, and metrics.## How to Call

**Bash**: Run with `animaworks-tool aws_collector <サブコマンド> [引数]`## Action List### ecs_status — ECS Service Status Check
```bash
animaworks-tool aws_collector ecs-status [--cluster NAME] [--service NAME]
```
### error_logs — Retrieve Error Logs
```bash
animaworks-tool aws_collector error-logs --log-group NAME [--hours 1] [--patterns "ERROR"]
```
### metrics — Metric Collection
```bash
animaworks-tool aws_collector metrics --cluster NAME --service NAME [--metric CPUUtilization]
```
## CLI Usage

```bash
animaworks-tool aws_collector ecs-status [--cluster NAME] [--service NAME]
animaworks-tool aws_collector error-logs --log-group NAME [--hours 1] [--patterns "ERROR"]
animaworks-tool aws_collector metrics --cluster NAME --service NAME [--metric CPUUtilization]
```
## Notes

- AWS authentication information (environment variables or credentials) must be configured
- The region can be specified with --region