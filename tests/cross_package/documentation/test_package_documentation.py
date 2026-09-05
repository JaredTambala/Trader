"""Contracts for package-owned documentation and executable examples.

Subject: The distribution-wide package documentation, example, link, and packaging contract.
Level: Cross-package documentation and subprocess integration contract.
Collaborators: Real Markdown, doctest, config loading, shell subprocesses, notebooks, and package metadata.
Guarantees: Shipped learning material is indexed, resolvable, declared, executable, and package-owned.
Non-goals: External-provider availability, prose style scoring, or notebook kernel execution.
"""

from __future__ import annotations

import doctest
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
from urllib.parse import unquote

import nbformat
import pytest

from trader import build_config, load_yaml_config


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_NAMES = (
    "trader",
    "trader_standard",
    "trader_research",
    "trader_mcp",
    "trader_agents",
    "trader_mlflow",
)
REQUIRED_PACKAGE_DOCS = ("architecture.md", "tutorial.md", "usage.md")
EXPECTED_NOTEBOOKS = {
    "trader": ("backtesting_tutorial.ipynb",),
    "trader_standard": ("strategy_composition_tutorial.ipynb",),
    "trader_research": ("research_evidence_tutorial.ipynb",),
    "trader_mcp": (),
    "trader_agents": (),
    "trader_mlflow": ("mlflow_prediction_tutorial.ipynb",),
}
EXECUTABLE_LANGUAGES = frozenset({"bash", "pycon", "python", "sh", "shell"})
CONFIG_LANGUAGES = frozenset({"yaml", "yml"})
FENCE_PATTERN = re.compile(r"^```([^\s`]*)\s*$")
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
VERIFIER_PATTERN = re.compile(r"^<!-- verified: (.+) -->$")


def test_every_package_owns_required_learning_documents() -> None:
    """Require the shared package documentation contract and selected notebooks."""
    for package_name in PACKAGE_NAMES:
        package_root = REPO_ROOT / "src" / package_name
        readme_path = package_root / "README.md"
        assert readme_path.is_file(), package_name
        readme = readme_path.read_text(encoding="utf-8")
        for filename in REQUIRED_PACKAGE_DOCS:
            path = package_root / "docs" / filename
            assert path.is_file(), path.relative_to(REPO_ROOT)
            assert f"docs/{filename}" in readme, (package_name, filename)


def test_package_readmes_index_every_owned_document() -> None:
    """Make every shipped package document discoverable from its package README."""
    for package_name in PACKAGE_NAMES:
        package_root = REPO_ROOT / "src" / package_name
        readme = (package_root / "README.md").read_text(encoding="utf-8")
        for path in sorted((package_root / "docs").iterdir()):
            if path.is_file() and path.suffix in {".md", ".ipynb"}:
                assert f"docs/{path.name}" in readme, (
                    package_name,
                    path.name,
                )
        for filename in EXPECTED_NOTEBOOKS[package_name]:
            path = package_root / "docs" / filename
            assert path.is_file(), path.relative_to(REPO_ROOT)
            assert f"docs/{filename}" in readme, (package_name, filename)


def test_active_markdown_links_and_anchors_resolve() -> None:
    """Resolve every local link in current root and package documentation."""
    failures: list[str] = []
    for source_path in _active_markdown_docs():
        content = source_path.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(content):
            target = raw_target.strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_text, _, anchor = target.partition("#")
            target_path = source_path if not path_text else source_path.parent / unquote(path_text)
            if not target_path.exists():
                failures.append(
                    f"{source_path.relative_to(REPO_ROOT)} -> {raw_target} (missing path)"
                )
                continue
            if anchor and target_path.suffix.lower() == ".md":
                anchors = _markdown_anchors(target_path)
                if unquote(anchor).lower() not in anchors:
                    failures.append(
                        f"{source_path.relative_to(REPO_ROOT)} -> {raw_target} (missing anchor)"
                    )
    assert not failures, "\n".join(failures)


def test_executable_fences_are_declared() -> None:
    """Reject executable fences without an explicit, resolvable verifier."""
    failures: list[str] = []
    for path in _executable_documentation():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, language, _body, verifier in _executable_fences(lines):
            if verifier is None:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} {language} fence has no verifier"
                )
                continue
            if verifier == "doctest":
                if language != "pycon":
                    failures.append(
                        f"{path.relative_to(REPO_ROOT)}:{line_number} doctest must use pycon"
                    )
                continue
            if language in {"python", "pycon"}:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} Python example must use "
                    "doctest-compatible pycon form"
                )
            if language in {"bash", "sh", "shell"} and not verifier.startswith(
                ("offline-shell ", "integration:")
            ):
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} shell verifier must declare "
                    "offline-shell or an integration requirement"
                )
            test_targets = re.findall(r"tests/[A-Za-z0-9_./-]+\.py", verifier)
            if not test_targets:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} verifier names no test"
                )
                continue
            for target in test_targets:
                if not (REPO_ROOT / target).is_file():
                    failures.append(
                        f"{path.relative_to(REPO_ROOT)}:{line_number} missing verifier {target}"
                    )
    assert not failures, "\n".join(failures)


def test_doctest_examples_execute() -> None:
    """Execute every doctest-compatible package Markdown example against installed code."""
    failures: list[str] = []
    parser = doctest.DocTestParser()
    for path in _package_markdown_docs():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, language, body, verifier in _executable_fences(lines):
            if language != "pycon" or verifier != "doctest":
                continue
            runner = doctest.DocTestRunner(
                optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE
            )
            test = parser.get_doctest(
                body,
                {},
                f"{path.stem}:{line_number}",
                str(path),
                line_number,
            )
            runner.run(test)
            summary = runner.summarize(verbose=False)
            if summary.failed:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: "
                    f"{summary.failed}/{summary.attempted} doctests failed"
                )
    assert not failures, "\n".join(failures)


def test_configuration_snippets_use_the_real_config_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load and normalize every declared YAML example with production code."""
    environment = {
        "PG_HOST": "127.0.0.1",
        "PG_PORT": "5432",
        "PG_DB": "trader_docs",
        "PG_USER": "trader_docs",
        "PG_PASSWORD": "documentation-only",
        "ALPACA_API_KEY": "documentation-only",
        "ALPACA_SECRET_KEY": "documentation-only",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    failures: list[str] = []
    snippet_number = 0
    for path in _active_markdown_docs():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, _language, body, verifier in _executable_fences(
            lines,
            languages=CONFIG_LANGUAGES,
        ):
            if verifier != "config":
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} YAML fence must declare config verification"
                )
                continue
            snippet_number += 1
            config_path = tmp_path / f"snippet-{snippet_number}.yaml"
            config_path.write_text(body, encoding="utf-8")
            try:
                build_config(load_yaml_config(config_path))
            except (TypeError, ValueError) as exc:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} invalid config: {exc}"
                )
    assert snippet_number > 0
    assert not failures, "\n".join(failures)


def test_declared_shell_examples() -> None:
    """Syntax-check declared shell blocks and execute offline blocks in isolation."""
    failures: list[str] = []
    executable = shutil.which("trader-agent")
    for path in _executable_documentation():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, language, body, verifier in _executable_fences(lines):
            if language not in {"bash", "sh", "shell"} or verifier is None:
                continue
            syntax = subprocess.run(
                ["bash", "-n"],
                input=body,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if syntax.returncode:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} invalid shell: {syntax.stderr.strip()}"
                )
                continue
            if not verifier.startswith("offline-shell "):
                continue
            if executable is None:
                failures.append("trader-agent entrypoint is not installed")
                continue
            with tempfile.TemporaryDirectory(prefix="trader-doc-shell-") as directory:
                completed = subprocess.run(
                    ["bash", "-eu", "-o", "pipefail", "-c", body],
                    cwd=directory,
                    text=True,
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            if completed.returncode:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number} offline shell failed: "
                    f"{completed.stderr.strip()}"
                )
    assert not failures, "\n".join(failures)


def test_notebooks_are_valid_and_output_free() -> None:
    """Require deterministic notebook structure before execution tests run."""
    for package_name, filenames in EXPECTED_NOTEBOOKS.items():
        for filename in filenames:
            path = REPO_ROOT / "src" / package_name / "docs" / filename
            notebook = nbformat.read(path, as_version=4)
            nbformat.validate(notebook)
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    assert cell.execution_count is None, path.relative_to(REPO_ROOT)
                    assert not cell.outputs, path.relative_to(REPO_ROOT)
                    assert "input(" not in cell.source, path.relative_to(REPO_ROOT)


def test_package_data_declares_every_document_family() -> None:
    """Require explicit wheel data rules for each package documentation tree."""
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = project["tool"]["setuptools"]["package-data"]
    for package_name in PACKAGE_NAMES:
        patterns = set(package_data[package_name])
        assert {"README.md", "docs/*.md", "docs/*.ipynb"} <= patterns


def test_retired_central_documentation_paths_are_absent() -> None:
    """Prevent links or files from recreating displaced package documentation."""
    assert not (REPO_ROOT / "docs" / "core").exists()
    assert not (REPO_ROOT / "docs" / "research_agents").exists()
    assert not (REPO_ROOT / "README_ENV.md").exists()

    stale = ("docs/core", "docs/research_agents", "README_ENV.md")
    paths = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "AGENTS.md",
        *(REPO_ROOT / "plans").glob("*.md"),
        *(REPO_ROOT / "plans" / "agent_designs").glob("*.md"),
        *_active_markdown_docs(),
    ]
    failures: list[str] = []
    for path in paths:
        content = path.read_text(encoding="utf-8")
        for value in stale:
            if value in content:
                failures.append(f"{path.relative_to(REPO_ROOT)} contains {value}")
    assert not failures, "\n".join(failures)


def test_architecture_is_not_named_with_implementation_codes() -> None:
    """Keep delivery checkpoint identifiers out of active architecture names."""
    pattern = re.compile(r"\b(?:ORCH|AGENT|IMP)-(?:GOV|DATA|DESIGN|QUANT|ML|HYP|\d+)[A-Z0-9-]*\b")
    paths = [
        REPO_ROOT / "docs" / "system_architecture.md",
        *(REPO_ROOT / "src" / package / "docs" / "architecture.md" for package in PACKAGE_NAMES),
    ]
    for path in paths:
        assert pattern.search(path.read_text(encoding="utf-8")) is None, path.relative_to(REPO_ROOT)


def _active_markdown_docs() -> tuple[Path, ...]:
    """Return current root and package docs, excluding contributor history."""
    root_docs = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "README.md",
        REPO_ROOT / "docs" / "environment.md",
        REPO_ROOT / "docs" / "product_state.md",
        REPO_ROOT / "docs" / "system_architecture.md",
        REPO_ROOT / "docs" / "test_architecture.md",
        *(REPO_ROOT / "docs" / "workflows").glob("*.md"),
    )
    return tuple(sorted({*root_docs, *_package_markdown_docs()}))


def _executable_documentation() -> tuple[Path, ...]:
    """Return active user-facing Markdown subject to executable-fence policy."""
    return _active_markdown_docs()


def _package_markdown_docs() -> tuple[Path, ...]:
    """Return every package README and focused Markdown document."""
    paths: list[Path] = []
    for package_name in PACKAGE_NAMES:
        package_root = REPO_ROOT / "src" / package_name
        paths.append(package_root / "README.md")
        paths.extend((package_root / "docs").glob("*.md"))
    return tuple(sorted(paths))


def _executable_fences(
    lines: list[str],
    *,
    languages: frozenset[str] = EXECUTABLE_LANGUAGES,
) -> list[tuple[int, str, str, str | None]]:
    """Extract selected code fences and their immediate verifier declaration."""
    fences: list[tuple[int, str, str, str | None]] = []
    index = 0
    while index < len(lines):
        match = FENCE_PATTERN.match(lines[index])
        if match is None or match.group(1).lower() not in languages:
            index += 1
            continue
        language = match.group(1).lower()
        end = index + 1
        while end < len(lines) and lines[end] != "```":
            end += 1
        assert end < len(lines), f"unterminated fence at line {index + 1}"
        verifier_match = VERIFIER_PATTERN.match(lines[index - 1]) if index else None
        verifier = verifier_match.group(1) if verifier_match else None
        fences.append((index + 1, language, "\n".join(lines[index + 1 : end]), verifier))
        index = end + 1
    return fences


def _markdown_anchors(path: Path) -> set[str]:
    """Return GitHub-style heading anchors from one Markdown document."""
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*$", line)
        if match is None:
            continue
        text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", match.group(1))
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"[`*_~]", "", text).strip().lower()
        anchor = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE).replace(" ", "-")
        count = counts.get(anchor, 0)
        counts[anchor] = count + 1
        anchors.add(anchor if count == 0 else f"{anchor}-{count}")
    return anchors
