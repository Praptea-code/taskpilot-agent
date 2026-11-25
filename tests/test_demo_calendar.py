import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_demo_calendar_runs_with_canned_responses(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'demo.db'}"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/demo_calendar.py",
            "--fake",
            "--goal",
            "Prepare the quarterly report by tomorrow",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Scheduled actions:" in result.stdout
    assert "Draft the outline" in result.stdout
    assert "external ref:" in result.stdout
