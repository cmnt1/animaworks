# Episode Extraction from Activity Log

{anima_name}, organize your activity records into a structured timeline.

## Target period: {time_range}

## Existing Episode Content

{existing_episode}

## Activity Log

{activity_chunk}

---

## Output Format

Use the following Markdown format. Separate sections by time period using `## HH:MM-HH:MM Title` headers, with bullet points for events.

```
## HH:MM-HH:MM Section Title

- HH:MM Event summary
  - Details, results, related information
- HH:MM Next event
```

## 규칙

1. **시간대별로 그룹화**: 관련 활동을 30분~2시간 정도의 시간대로 묶는다
2. **글머리 기호 목록으로 간결하게 작성**: 나중에 참고할 수 있는 사실만 남기고, 이메일 본문이나 도구 출력을 옮겨 적지 않는다. 도구 실행은 ‘무엇을 했는지·성공 여부·결론’만 기록한다
3. **불필요한 반복 제거**: 동일한 `current_state.md` 덤프나 중복된 REFLECTION은 한 번만 남긴다
4. **도구 실행 결과**: 무엇을 했는지·성공/실패 여부·결론만 기록하고, 출력 내용은 옮겨 적지 않는다. 정기 점검에서 변화가 없던 항목은 한 줄로 정리한다
5. **통신 내용**: 송수신 메시지의 요점을 기록한다(누가 누구에게 무엇에 관해 보냈는지)
6. **추측을 덧붙이지 않는다**: 행동 기록에 있는 사실만 기록한다. 추론이나 해석은 하지 않는다
7. **기존 내용은 중복 제거에 활용**: 기존 에피소드 내용이 있는 경우, 중복되는 정보는 타임라인에 반영하고 같은 사실을 두 번 기록하지 않는다
8. **마크다운의 `##` 헤더만 사용**: `#`나 `###`은 사용하지 않는다
