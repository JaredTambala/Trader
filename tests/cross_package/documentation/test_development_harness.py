"""Contract tests for the repository's local development harness.

Subject: Cross-track development manifest validation and human-facing reporting.
Level: In-process contract with a temporary Git worktree integration check.
Collaborators: Real YAML parser, harness module, and Git executable; no Notion or external model.
Guarantees: Track outcomes, dependencies, checks, worktree creation, local evidence state, and review decisions remain explicit.
Non-goals: Merging branches, changing Notion, product runtime behavior, or proving any track's domain capability.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "tools" / "development_harness.py"
SPEC = importlib.util.spec_from_file_location("development_harness", MODULE_PATH)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
sys.modules["development_harness"] = harness
SPEC.loader.exec_module(harness)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)


MINIMAL_INTENT = """product_intent:
  source: intent.md
  mission: mission
  current_problem: problem
  decisions:
    - id: decision
      statement: decision statement
  acceptance_scenarios:
    - id: scenario
      decision: decision
      trigger: trigger
      desired_outcome: desired outcome
      evidence: [evidence]
  principles: [principle]
  open_questions: [question]
  review_question: review question
"""

MINIMAL_INTENT_SOURCE = """# Test intent

### UJ-01 — Test journey

### FR-01 — Test requirement
"""


def _write_intent_source(root: Path) -> None:
    (root / "intent.md").write_text(MINIMAL_INTENT_SOURCE, encoding="utf-8")


@pytest.fixture(autouse=True)
def _temporary_intent_source(tmp_path: Path) -> None:
    _write_intent_source(tmp_path)


def test_manifest_exposes_outcomes_dependencies_checks_and_review() -> None:
    """A valid manifest exposes enough context to choose and review a track."""
    config = harness.load_config(ROOT / "plans/development_tracks.yaml", ROOT)

    assert len(config.tracks) == 6
    assert {track.track_id for track in config.tracks} >= {
        "mcp-capabilities",
        "agent-identities",
        "console-experience",
        "data-sources",
        "backtest-reality",
        "strategy-research",
    }
    for track in config.tracks:
        assert track.user_outcome
        assert track.instrumental_purpose
        assert track.serves
        assert track.scenarios
        assert track.journeys
        assert track.requirements
        assert track.checks
        assert track.review.question
    assert config.product_intent.mission
    assert config.product_intent.source == Path("docs/product_intent.md")
    assert {journey.identifier for journey in config.product_intent.journeys} >= {
        "UJ-01",
        "UJ-06",
    }
    assert {requirement.identifier for requirement in config.product_intent.requirements} >= {
        "FR-01",
        "FR-14",
    }
    assert {decision.decision_id for decision in config.product_intent.decisions}
    assert {scenario.scenario_id for scenario in config.product_intent.acceptance_scenarios}
    assert {track.capability_id for track in config.tracks} >= {
        "mcp",
        "agentic-qualification",
        "console",
    }
    assert config.tracks[0].merge.mode == "independent"


def test_multiple_work_items_can_share_a_capability_with_merge_order(tmp_path: Path) -> None:
    """Capability grouping does not collapse independently mergeable worktrees."""
    manifest = tmp_path / "tracks.yaml"
    manifest.write_text(
        """version: 1
repository:
  base_branch: main
  worktrees_dir: .worktrees
  state_dir: .state
"""
        + MINIMAL_INTENT
        + """tracks:
  - id: contract
    capability_id: mcp
    title: Contract
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/contract
    depends_on: []
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    merge: {mode: contract-first, target: main}
    checks: [{name: check, command: 'true'}]
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
  - id: qualification
    capability_id: mcp
    title: Qualification
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/qualification
    depends_on: []
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    merge: {mode: stacked, target: main, after: [contract]}
    checks: [{name: check, command: 'true'}]
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
""",
        encoding="utf-8",
    )

    config = harness.load_config(manifest, tmp_path)

    assert [track.capability_id for track in config.tracks] == ["mcp", "mcp"]
    assert config.tracks[1].merge.after == ("contract",)


def test_product_intent_render_and_review_gate(tmp_path: Path) -> None:
    """Product decisions render clearly and require explicit human acceptance."""
    manifest = tmp_path / "tracks.yaml"
    manifest.write_text(
        """version: 1
repository:
  base_branch: main
  worktrees_dir: .worktrees
  state_dir: .state
"""
        + MINIMAL_INTENT
        + """tracks:
  - id: example
    title: Example
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/example
    depends_on: []
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    checks: [{name: check, command: 'true'}]
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
""",
        encoding="utf-8",
    )
    config = harness.load_config(manifest, tmp_path)

    rendered = harness.render_intent(config)

    assert "mission" in rendered
    assert "decision statement" in rendered
    assert "desired outcome" in rendered
    assert harness.product_intent_status(config) == "needs-review"
    harness.record_intent_review(config, "accept", "reviewed for the example")
    assert harness.product_intent_status(config) == "accept"
    (tmp_path / "intent.md").write_text(MINIMAL_INTENT_SOURCE + "\nrevision\n", encoding="utf-8")
    assert harness.product_intent_status(config) == "needs-review"


def test_current_state_evidence_detects_stale_and_contradictory_sources(tmp_path: Path) -> None:
    """Current-state review blocks stale or contradictory canonical evidence."""
    current_state = tmp_path / "current_state.md"
    current_state.write_text(
        f"# Current\nLast reviewed: {datetime.now(UTC).date().isoformat()}\nrequired\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "tracks.yaml"
    manifest.write_text(
        """version: 1
repository:
  base_branch: main
  worktrees_dir: .worktrees
  state_dir: .state
current_state:
  path: current_state.md
  max_age_days: 14
  required_markers: [required]
  forbidden_markers: [contradiction]
"""
        + MINIMAL_INTENT
        + """tracks:
  - id: example
    title: Example
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/example
    depends_on: []
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    checks: [{name: check, command: 'true'}]
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
""",
        encoding="utf-8",
    )
    config = harness.load_config(manifest, tmp_path)

    assert harness.current_state_status(config)["status"] == "fresh"

    current_state.write_text(
        f"# Current\nLast reviewed: {(datetime.now(UTC).date() - timedelta(days=15)).isoformat()}\nrequired\n",
        encoding="utf-8",
    )
    assert harness.current_state_status(config)["status"] == "stale"

    current_state.write_text(
        f"# Current\nLast reviewed: {datetime.now(UTC).date().isoformat()}\nrequired\ncontradiction\n",
        encoding="utf-8",
    )
    assert harness.current_state_status(config)["status"] == "contradictory"


def test_database_identity_is_unique_and_guarded() -> None:
    """Each track receives a guarded database name without touching production names."""
    assert harness.derive_test_database("trader_test", "mcp-capabilities") == (
        "trader_mcp_capabilities_test"
    )
    assert len(harness.derive_test_database("trader_test", "x" * 100)) <= 63
    with pytest.raises(harness.HarnessError, match="_test or _testing"):
        harness.derive_test_database("trader", "mcp-capabilities")


def test_manifest_rejects_dependency_cycles(tmp_path: Path) -> None:
    """A cyclic track graph fails before any worktree can be created."""
    manifest = tmp_path / "tracks.yaml"
    manifest.write_text(
        """version: 1
repository:
  base_branch: main
  worktrees_dir: .worktrees
  state_dir: .state
"""
        + MINIMAL_INTENT
        + """
tracks:
  - id: a
    title: A
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/a
    depends_on: [b]
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    checks: [{name: check, command: 'true'}]
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
  - id: b
    title: B
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/b
    depends_on: [a]
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    checks: [{name: check, command: 'true'}]
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
""",
        encoding="utf-8",
    )

    with pytest.raises(harness.HarnessError, match="cycle"):
        harness.load_config(manifest, tmp_path)


def test_start_and_review_bind_local_state_to_track(tmp_path: Path) -> None:
    """Starting a track creates an isolated branch and review persists locally."""
    repository = tmp_path / "repo"
    repository.mkdir()
    _write_intent_source(repository)
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test")
    (repository / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "seed")
    manifest = repository / "tracks.yaml"
    manifest.write_text(
        """version: 1
repository:
  base_branch: main
  worktrees_dir: .worktrees
  state_dir: .state
"""
        + MINIMAL_INTENT
        + """
tracks:
  - id: example
    title: Example
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/example
    depends_on: []
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    checks: [{name: check, command: 'true'}]
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
""",
        encoding="utf-8",
    )
    config = harness.load_config(manifest, repository)

    worktree = harness.start_track(config, "example")
    harness.record_review(config, "example", "continue", "keep the slice narrow")
    status = harness.track_status(config, config.tracks[0])

    assert worktree.exists()
    assert status["phase"] == "needs-check"
    assert status["state"]["human_review"]["decision"] == "continue"

    harness.run_checks(config, "example", "focused")
    harness.record_review(config, "example", "merge", "the focused check passed")
    assert harness.track_status(config, config.tracks[0])["phase"] == "needs-review"
    harness.record_intent_review(config, "accept", "the baseline is understood")
    assert harness.track_status(config, config.tracks[0])["phase"] == "ready-to-merge"


def test_prepare_copies_tracked_template_without_overwriting_local_file(tmp_path: Path) -> None:
    """Worktree preparation makes ignored local setup reproducible and preserves edits."""
    repository = tmp_path / "repo"
    repository.mkdir()
    _write_intent_source(repository)
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test")
    (repository / "env.template").write_text("TEMPLATE=value\n", encoding="utf-8")
    (repository / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repository, "add", "README.md", "env.template")
    _git(repository, "commit", "-m", "seed")
    manifest = repository / "tracks.yaml"
    manifest.write_text(
        """version: 1
repository:
  base_branch: main
  worktrees_dir: .worktrees
  state_dir: .state
"""
        + MINIMAL_INTENT
        + """tracks:
  - id: example
    title: Example
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/example
    depends_on: []
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    workspace_files:
      - source: env.template
        target: local.env
    checks: [{name: check, command: 'true'}]
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
""",
        encoding="utf-8",
    )
    config = harness.load_config(manifest, repository)
    worktree = harness.start_track(config, "example")

    assert (worktree / "local.env").read_text(encoding="utf-8") == "TEMPLATE=value\n"
    assert harness.prepare_track(config, "example") == []
    (worktree / "local.env").write_text("LOCAL=override\n", encoding="utf-8")
    assert harness.prepare_track(config, "example") == []
    assert (worktree / "local.env").read_text(encoding="utf-8") == "LOCAL=override\n"


def test_postgres_profile_injects_the_provisioned_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A database check receives only its track-specific Postgres identity."""
    repository = tmp_path / "repo"
    repository.mkdir()
    _write_intent_source(repository)
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test")
    (repository / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "seed")
    manifest = repository / "tracks.yaml"
    manifest.write_text(
        """version: 1
repository:
  base_branch: main
  worktrees_dir: .worktrees
  state_dir: .state
"""
        + MINIMAL_INTENT
        + """
tracks:
  - id: example
    title: Example
    user_outcome: outcome
    instrumental_purpose: purpose
    scope: [scope]
    branch: dev/example
    depends_on: []
    serves: [decision]
    scenarios: [scenario]
    journeys: [UJ-01]
    requirements: [FR-01]
    checks:
      - name: database identity
        profile: postgres
        requires_database: true
        command: test "$PG_TEST_DB" = "trader_example_test"
    evidence: {required: [evidence]}
    review: {question: question, decision_point: point}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("PG_TEST_DB", "trader_test")
    config = harness.load_config(manifest, repository)
    harness.start_track(config, "example")
    config.state_dir.mkdir(parents=True)
    (config.state_dir / "example.json").write_text(
        json.dumps({"test_environment": {"mode": "database", "database": "trader_example_test"}}),
        encoding="utf-8",
    )

    state = harness.run_checks(config, "example", "postgres")

    assert state["checks"][0]["returncode"] == 0
