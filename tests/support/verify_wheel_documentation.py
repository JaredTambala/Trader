"""Verify that a built Trader wheel contains package-owned documentation."""

from __future__ import annotations

from pathlib import Path
import sys
from zipfile import ZipFile


PACKAGE_NAMES = (
    "trader",
    "trader_standard",
    "trader_research",
    "trader_mcp",
    "trader_agents",
    "trader_mlflow",
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def verify_wheel(wheel_path: Path) -> None:
    """Raise when required package-owned documents are absent from a wheel."""
    with ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())
    expected: set[str] = set()
    for package_name in PACKAGE_NAMES:
        source_package = REPO_ROOT / "src" / package_name
        expected.add(f"{package_name}/README.md")
        expected.update(
            f"{package_name}/docs/{path.name}"
            for path in (source_package / "docs").iterdir()
            if path.is_file() and path.suffix in {".md", ".ipynb"}
        )
    missing = sorted(expected - names)
    if missing:
        raise SystemExit("Wheel is missing package documentation:\n" + "\n".join(missing))


def main(arguments: list[str] | None = None) -> None:
    """Verify the single wheel path supplied on the command line."""
    values = list(sys.argv[1:] if arguments is None else arguments)
    if len(values) != 1:
        raise SystemExit("usage: verify_wheel_documentation.py PATH_TO_WHEEL")
    verify_wheel(Path(values[0]))


if __name__ == "__main__":
    main()
