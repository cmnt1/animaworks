# 엔지니어 전문 가이드라인

## 코딩 원칙

### 최소 변경 원칙
- 기존 코드에 대한 변경은 필요한 최소 범위로 제한합니다
- 대규모 리팩터링은 명시적으로 지시받은 경우에만 실시합니다
- "겸사겸사 수정"은 금지입니다. 범위 밖의 수정은 별도 작업으로 기록하세요

### 오버엔지니어링 회피
- YAGNI(You Aren't Gonna Need It)를 철저히 준수합니다
- 미래의 확장을 "예측"하여 코드를 복잡하게 만들지 마세요
- 추상화는 같은 패턴이 3번 나타난 후에 검토합니다(Rule of Three)
- 단순한 구현으로 요구사항을 충족할 수 있다면 그것이 최선입니다

### 보안 (OWASP Top 10 인식)
- 사용자 입력은 항상 유효성 검사를 수행합니다
- SQL 쿼리에는 파라미터 바인딩을 사용합니다(문자열 결합 금지)
- 시크릿(API 키, 패스워드)을 코드에 하드코딩하지 마세요
- 파일 경로 조합에는 `pathlib.Path`를 사용하여 path traversal을 방지합니다
- 서브프로세스 호출 시 `shell=True`를 피하고 인자 리스트를 사용합니다

```python
# BAD
subprocess.run(f"ls {user_input}", shell=True)

# GOOD
subprocess.run(["ls", user_input], shell=False)
```

## 도구 사용 규칙

### 파일 작업은 전용 도구 우선
- 파일 읽기: `Read` 사용 (`cat`, `head`, `tail` 대신)
- 파일 편집: `Edit` 사용 (`sed`, `awk` 대신)
- 파일 쓰기: `Write` 사용 (`echo >`, `cat <<EOF` 대신)
- 파일 검색: `Glob` 사용 (`find`, `ls` 대신)
- 내용 검색: `Grep` 사용 (`grep`, `rg` 대신)
- `Bash`는 Git 작업, 패키지 관리, 빌드, 테스트 실행 등 전용 도구로 대체할 수 없는 경우에 사용합니다

### 파일 작업 모범 사례
- 기존 파일 편집을 우선하고, 불필요한 파일 생성을 피하세요
- 새 파일을 만들기 전에 기존에 적합한 파일이 없는지 확인하세요
- 문서 파일(*.md, README)은 명시적으로 지시받은 경우에만 생성합니다

## 코드 품질 기준

### 타입 힌트 필수
```python
from __future__ import annotations

def process_item(name: str, count: int = 0) -> dict[str, int]:
    ...
```

- `str | None` 형식을 사용합니다(`Optional[str]` 대신)
- 함수의 매개변수와 반환값에는 반드시 타입 힌트를 붙이세요
- 복잡한 타입은 `TypeAlias`로 이름을 부여합니다

### 경로 작업
```python
from pathlib import Path

# BAD
import os
path = os.path.join(base_dir, "subdir", "file.txt")

# GOOD
path = Path(base_dir) / "subdir" / "file.txt"
```

### docstring (Google 스타일)
```python
def calculate_score(items: list[Item], weight: float = 1.0) -> float:
    """스코어를 계산합니다.

    Args:
        items: 평가 대상 아이템 리스트.
        weight: 스코어 가중 계수.

    Returns:
        계산된 스코어 값.

    Raises:
        ValueError: items가 비어 있는 경우.
    """
```

### 로깅
```python
import logging
logger = logging.getLogger(__name__)

# print()가 아닌 logger를 사용합니다
logger.info("Processing %d items", len(items))
```

### 데이터 모델
- 데이터 구조 정의에는 Pydantic Model 또는 dataclass를 사용합니다
- 딕셔너리 직접 조작보다 구조화된 모델을 우선합니다

## 커밋 규약

시맨틱 커밋 형식을 사용합니다:
- `feat:` — 새 기능 추가
- `fix:` — 버그 수정
- `refactor:` — 리팩터링(기능 변경 없음)
- `docs:` — 문서만 변경
- `test:` — 테스트 추가 또는 수정
- `chore:` — 빌드 설정, 의존성 등 기타

```
feat: OAuth2 플로우를 통한 사용자 인증 추가
fix: 세션 타임아웃 시 메모리 누수 수정
refactor: 데이터베이스 연결 풀을 싱글턴으로 통합
```

## 테스트 가이드라인

- 코드를 변경한 후 관련 테스트가 통과하는지 확인하세요
- 새로운 함수와 메서드에는 유닛 테스트를 작성하세요
- 테스트는 `tests/` 디렉터리에 대상 모듈과 같은 구조로 배치합니다
- 테스트 실행: `pytest`를 사용하여 변경과 관련된 테스트를 지정하여 실행합니다

```bash
# 특정 테스트 파일 실행
pytest tests/test_target_module.py -v

# 변경과 관련된 테스트만 실행
pytest tests/test_target_module.py::TestClassName::test_method -v
```

## 에러 처리

- 빈 `except:`나 `except Exception:`을 피하고, 구체적인 예외를 캐치하세요
- 에러 메시지에는 문제 식별에 필요한 정보를 포함하세요
- 재시도 로직에는 지수 백오프를 사용합니다

```python
# BAD
try:
    result = api_call()
except:
    pass

# GOOD
try:
    result = api_call()
except ConnectionError as e:
    logger.warning("API 연결 실패 (attempt %d/%d): %s", attempt, max_retries, e)
    raise
```

## 비동기 처리

- `async/await`를 사용하고, 블로킹 호출을 피하세요
- 공유 상태에는 `asyncio.Lock()`을 사용합니다
- 장시간 CPU 바운드 작업은 `asyncio.to_thread()`로 오프로드합니다
