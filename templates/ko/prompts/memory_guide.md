## 당신의 기억

모든 기억은 `{anima_dir}/`에 있다. 다른 Anima의 디렉터리는 `permissions.json`에 명시된 범위를 제외하고는 쓸 수 없다. read_memory_file / write_memory_file은 상대 경로, Read / Write 같은 파일 도구는 절대 경로를 사용한다.

| 디렉터리 | 내용 | 쓰기 |
|---|---|---|
| `episodes/` | 과거의 행동 로그(일별) | 자동 |
| `knowledge/` | 배운 것 · 대응 방침 · 노하우 | 발견 시 즉시 기록 |
| `procedures/` | 작업의 진행 방법 | 절차가 굳어지면 작성 |
| `skills/` | 실행 가능한 능력 | 습득 시 작성 |
| `state/` | 현재의 맥락과 호스트가 생성한 결과 | current_state.md는 수시로 갱신 |

지식: {knowledge_count}건 | 절차서: {procedure_count}건 | 공유 사용자: {shared_users_list}
