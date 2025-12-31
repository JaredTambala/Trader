import os
import subprocess
import sys

from trader.cycle import run_cycle


def test_run_cycle_returns_success(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "events.duckdb")
    result = run_cycle()
    assert result.status == "success"
    assert result.run_id
    assert (tmp_path / "events.duckdb").exists()


def test_module_entrypoint_runs(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(["src", env.get("PYTHONPATH", "")]).strip(
        os.pathsep
    )
    env["DB_PATH"] = str(tmp_path / "events.duckdb")
    completed = subprocess.run(
        [sys.executable, "-m", "trader.cycle"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
