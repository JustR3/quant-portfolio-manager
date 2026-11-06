"""The documented `exit-eval` command exists and its help runs (README / CLAUDE.md example)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_exit_eval_help_runs():
    out = subprocess.run(
        [sys.executable, "main.py", "exit-eval", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    assert "--export" in out.stdout


def test_readme_documents_exit_eval_and_its_builders():
    readme = (ROOT / "README.md").read_text()
    assert "uv run ./main.py exit-eval" in readme
    for tool in ("tools/download_sector_etfs.py", "tools/build_8k_earnings_cache.py"):
        assert tool in readme and (ROOT / tool).exists()
