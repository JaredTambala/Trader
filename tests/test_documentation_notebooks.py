"""Execution tests for selected package-owned tutorial notebooks."""

from __future__ import annotations

from pathlib import Path
import shutil

from nbclient import NotebookClient
import nbformat
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = (
    REPO_ROOT / "src" / "trader" / "docs" / "backtesting_tutorial.ipynb",
    REPO_ROOT
    / "src"
    / "trader_standard"
    / "docs"
    / "strategy_composition_tutorial.ipynb",
    REPO_ROOT
    / "src"
    / "trader_research"
    / "docs"
    / "research_evidence_tutorial.ipynb",
    REPO_ROOT
    / "src"
    / "trader_mlflow"
    / "docs"
    / "mlflow_prediction_tutorial.ipynb",
)


@pytest.mark.parametrize("source_path", NOTEBOOKS, ids=lambda path: path.stem)
def test_notebook_executes_from_temporary_copy(
    source_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execute one deterministic notebook without changing the shipped copy."""
    copied_path = tmp_path / source_path.name
    shutil.copy2(source_path, copied_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT / "src"))
    notebook = nbformat.read(copied_path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=30,
        kernel_name="python3",
        resources={"metadata": {"path": str(tmp_path)}},
    )

    executed = client.execute(cwd=str(tmp_path))

    for cell in executed.cells:
        if cell.cell_type == "code":
            assert not any(output.output_type == "error" for output in cell.outputs)
