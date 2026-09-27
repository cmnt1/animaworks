# 엔지니어 전문 가이드라인
## 코딩 원칙

- **최소 변경**: 기존 코드에 대한 변경은 필요 최소한으로. 대규모 리팩터는 명시적 지시가 있을 때만. 범위 외 수정은 별도 작업으로 기록
- **YAGNI**: 미래의 확장을 예측해 코드를 복잡하게 만들지 않음. 추상화는 동일 패턴이 3회 등장한 후 (Rule of Three)
- **보안**: 입력 검증 필수, SQL은 파라미터 바인딩, 시크릿 하드코딩 금지, `pathlib.Path`로 경로 탐색 방지, `shell=True` 회피
## 코드 품질

- `from __future__ import annotations` + `str | None` 형식의 타입 힌트 필수
- `pathlib.Path`로 경로 조작, Google-style docstring, `logging.getLogger(__name__)`
- Pydantic Model / dataclass로 데이터 정의
- 시맨틱 커밋: `feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`
## 테스트·오류 처리

- 코드 변경 후 관련 테스트 확인. 새 함수에는 유닛 테스트 추가
- 구체적인 예외를 캐치 (추상적인 `except:` 금지). 재시도에는 지수 백오프 사용
- `async/await` + `asyncio.Lock()`. CPU 바운드는 `asyncio.to_thread()`

프로젝트 고유 규칙은 저장소의 `.cursorrules` / `CLAUDE.md` 참조