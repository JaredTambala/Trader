from __future__ import annotations

from pathlib import Path
import re

from trader_mcp.constants import REGISTERED_TOOL_NAMES
from trader_research.agents import AGENT_DEFINITIONS


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = REPO_ROOT / "docs" / "research_agents"
CURRENT_DOCS = (
    "README.md",
    "architecture.md",
    "agents.md",
    "mcp_tools.md",
    "workflows.md",
    "operations.md",
    "tool_contracts.md",
)
STALE_CURRENT_CLAIMS = (
    "backtest tools are not registered yet",
    "No backtest tool is exposed",
    "Planned:",
)


def test_research_agent_readme_links_canonical_docs_and_history() -> None:
    readme = (DOC_ROOT / "README.md").read_text(encoding="utf-8")

    for filename in CURRENT_DOCS:
        assert (DOC_ROOT / filename).exists()
        if filename != "README.md":
            assert f"({filename})" in readme
    assert "(history/)" in readme
    assert (DOC_ROOT / "history").is_dir()


def test_registered_mcp_tools_are_documented_once_in_canonical_catalog() -> None:
    catalog = (DOC_ROOT / "mcp_tools.md").read_text(encoding="utf-8")

    for tool_name in REGISTERED_TOOL_NAMES:
        assert catalog.count(f"`{tool_name}`") == 1, tool_name


def test_agent_identities_are_documented_in_canonical_agent_doc() -> None:
    agents_doc = (DOC_ROOT / "agents.md").read_text(encoding="utf-8")

    for definition in AGENT_DEFINITIONS:
        assert definition.display_name in agents_doc


def test_current_research_agent_docs_do_not_carry_stale_tool_claims() -> None:
    for path in _current_markdown_docs():
        content = path.read_text(encoding="utf-8")
        for stale_claim in STALE_CURRENT_CLAIMS:
            assert stale_claim not in content, f"{stale_claim!r} found in {path.relative_to(REPO_ROOT)}"


def test_rich_methodology_operator_guide_covers_required_workflows() -> None:
    workflows = (DOC_ROOT / "workflows.md").read_text(encoding="utf-8")
    operations = (DOC_ROOT / "operations.md").read_text(encoding="utf-8")
    contracts = (DOC_ROOT / "tool_contracts.md").read_text(encoding="utf-8")
    combined = "\n".join((workflows, operations, contracts)).lower()

    required_phrases = (
        "registration and ingestion are deliberately separate",
        "full-document ingestion",
        "field-level source/chunk refs",
        "draft cards are still review artifacts",
        "source suitability matters",
        "pairs trading or cointegration",
        "options straddle",
        "technical indicator",
        "commodity sentiment indicator",
        "data agent scope",
    )

    for phrase in required_phrases:
        assert phrase in combined


def test_canonical_readme_links_resolve() -> None:
    readme_path = DOC_ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")

    for target in re.findall(r"\]\(([^)]+)\)", readme):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (readme_path.parent / target).exists(), target


def _current_markdown_docs() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in DOC_ROOT.glob("*.md")
            if "history" not in path.relative_to(DOC_ROOT).parts
        )
    )
