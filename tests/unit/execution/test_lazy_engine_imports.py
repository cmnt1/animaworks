from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_isolated(tmp_path: Path, code: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ANIMAWORKS_DATA_DIR"] = str(tmp_path / "data")
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_shared_execution_imports_do_not_load_engines(tmp_path: Path) -> None:
    result = _run_isolated(
        tmp_path,
        """
import sys
import core.execution.base
import core.execution.rate_guard
import core.execution.cli_stream
assert not any(name.startswith('core.execution.engines.') for name in sys.modules)
""",
    )
    assert result.returncode == 0, result.stderr


def test_executor_package_attributes_resolve_lazily(tmp_path: Path) -> None:
    result = _run_isolated(
        tmp_path,
        """
from core.execution import LiteLLMExecutor, GrokCLIExecutor
assert LiteLLMExecutor is not None
assert GrokCLIExecutor is None or isinstance(GrokCLIExecutor, type)
import core.execution
try:
    getattr(core.execution, 'UnknownExecutor')
except AttributeError:
    pass
else:
    raise AssertionError('unknown executor attribute unexpectedly resolved')
""",
    )
    assert result.returncode == 0, result.stderr
