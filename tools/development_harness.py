"""Local control surface for concurrent, outcome-driven Trader development.

The harness owns local execution state only. Notion remains authoritative for
assignment, priority, dependencies, and delivery status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


DEFAULT_MANIFEST = Path("plans/development_tracks.yaml")
DEFAULT_STATE_DIR = Path(".trader-development/state")


class HarnessError(ValueError):
    """Raised when the development manifest or local state is invalid."""


@dataclass(frozen=True)
class IntentDecision:
    """A human decision the product should make easier."""

    decision_id: str
    statement: str


@dataclass(frozen=True)
class AcceptanceScenario:
    """A concrete situation in which a product decision can be evaluated."""

    scenario_id: str
    decision_id: str
    trigger: str
    desired_outcome: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class IntentReference:
    """A journey or requirement parsed from the canonical intent document."""

    identifier: str
    title: str


@dataclass(frozen=True)
class CurrentStateEvidence:
    """Repository evidence used to detect stale or contradictory product state."""

    path: Path
    max_age_days: int
    reviewed_marker: str
    required_markers: tuple[str, ...]
    forbidden_markers: tuple[str, ...]


@dataclass(frozen=True)
class ProductIntent:
    """Human-reviewed product direction that gives tracks their purpose."""

    mission: str
    current_problem: str
    decisions: tuple[IntentDecision, ...]
    acceptance_scenarios: tuple[AcceptanceScenario, ...]
    principles: tuple[str, ...]
    open_questions: tuple[str, ...]
    review_question: str
    source: Path
    journeys: tuple[IntentReference, ...]
    requirements: tuple[IntentReference, ...]


@dataclass(frozen=True)
class Check:
    """One declared validation command for a development track."""

    name: str
    command: str
    profile: str = "focused"
    requires_database: bool = False


@dataclass(frozen=True)
class WorkspaceFile:
    """A tracked template copied into an isolated worktree without overwriting."""

    source: Path
    target: Path


@dataclass(frozen=True)
class MergePlan:
    """Declared integration strategy for one independently mergeable work item."""

    mode: str
    target: str
    after: tuple[str, ...]


@dataclass(frozen=True)
class Evidence:
    """Evidence obligations a human can inspect before a merge decision."""

    required: tuple[str, ...]
    artifacts: tuple[str, ...]


@dataclass(frozen=True)
class Review:
    """Human review question and decision point for a track."""

    question: str
    decision_point: str


@dataclass(frozen=True)
class Track:
    """A product-facing development stream with executable validation."""

    track_id: str
    capability_id: str
    title: str
    user_outcome: str
    instrumental_purpose: str
    scope: tuple[str, ...]
    branch: str
    depends_on: tuple[str, ...]
    serves: tuple[str, ...]
    scenarios: tuple[str, ...]
    journeys: tuple[str, ...]
    requirements: tuple[str, ...]
    workspace_files: tuple[WorkspaceFile, ...]
    merge: MergePlan
    checks: tuple[Check, ...]
    evidence: Evidence
    review: Review


@dataclass(frozen=True)
class HarnessConfig:
    """Validated repository and track configuration."""

    root: Path
    base_branch: str
    worktrees_dir: Path
    state_dir: Path
    database_env: str
    admin_prefix: str
    product_intent: ProductIntent
    current_state: CurrentStateEvidence | None
    tracks: tuple[Track, ...]


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HarnessError(f"{field} must be a non-empty string")
    return value.strip()


def _strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise HarnessError(f"{field} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HarnessError(f"{field} must be a mapping")
    return value


def _relative_file(value: Any, field: str) -> Path:
    path = Path(_string(value, field))
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HarnessError(f"{field} must be a relative path inside the worktree")
    return path


def _intent_references(source: Path, pattern: str, label: str) -> tuple[IntentReference, ...]:
    """Read uniquely identified intent headings from the canonical source."""
    content = source.read_text(encoding="utf-8")
    references = tuple(
        IntentReference(identifier=identifier, title=title.strip())
        for identifier, title in re.findall(pattern, content, re.MULTILINE)
    )
    identifiers = [reference.identifier for reference in references]
    if not references:
        raise HarnessError(f"{label} source contains no recognised entries: {source}")
    if len(identifiers) != len(set(identifiers)):
        raise HarnessError(f"{label} source contains duplicate identifiers")
    return references


def load_config(manifest: Path, root: Path | None = None) -> HarnessConfig:
    """Load and validate a development track manifest.

    Args:
        manifest: YAML manifest path, relative to the repository root unless absolute.
        root: Optional repository root used for tests and embedding.

    Returns:
        A typed configuration with validated dependencies and checks.

    Raises:
        HarnessError: If the manifest is malformed or contains a dependency cycle.
    """
    repository_root = (root or Path.cwd()).resolve()
    manifest_path = manifest if manifest.is_absolute() else repository_root / manifest
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise HarnessError(f"manifest not found: {manifest_path}") from exc
    document = _mapping(raw, "manifest")
    if document.get("version") != 1:
        raise HarnessError("manifest version must be 1")
    repository = _mapping(document.get("repository"), "repository")
    base_branch = _string(repository.get("base_branch"), "repository.base_branch")
    worktrees_dir = Path(_string(repository.get("worktrees_dir"), "repository.worktrees_dir"))
    state_dir = Path(_string(repository.get("state_dir"), "repository.state_dir"))
    postgres = _mapping(repository.get("postgres", {}), "repository.postgres")
    database_env = _string(postgres.get("database_env", "PG_TEST_DB"), "repository.postgres.database_env")
    admin_prefix = _string(postgres.get("admin_prefix", "PG_ADMIN"), "repository.postgres.admin_prefix")
    raw_intent = _mapping(document.get("product_intent"), "product_intent")
    source_relative = _relative_file(raw_intent.get("source"), "product_intent.source")
    intent_source = repository_root / source_relative
    if not intent_source.is_file():
        raise HarnessError(f"product intent source does not exist: {intent_source}")
    journeys = _intent_references(
        intent_source,
        r"^###\s+(UJ-\d+)\s+—\s+(.+?)\s*$",
        "user journey",
    )
    requirements = _intent_references(
        intent_source,
        r"^###\s+(FR-\d+)\s+—\s+(.+?)\s*$",
        "functional requirement",
    )
    journey_ids = {reference.identifier for reference in journeys}
    requirement_ids = {reference.identifier for reference in requirements}
    raw_decisions = raw_intent.get("decisions")
    if not isinstance(raw_decisions, list) or not raw_decisions:
        raise HarnessError("product_intent.decisions must be a non-empty list")
    decisions: list[IntentDecision] = []
    decision_ids: set[str] = set()
    for index, raw_decision in enumerate(raw_decisions):
        decision = _mapping(raw_decision, f"product_intent.decisions[{index}]")
        decision_id = _string(decision.get("id"), f"product_intent.decisions[{index}].id")
        if decision_id in decision_ids:
            raise HarnessError(f"duplicate product intent decision id: {decision_id}")
        decision_ids.add(decision_id)
        decisions.append(
            IntentDecision(
                decision_id=decision_id,
                statement=_string(
                    decision.get("statement"),
                    f"product_intent.decisions[{index}].statement",
                ),
            )
        )
    raw_scenarios = raw_intent.get("acceptance_scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise HarnessError("product_intent.acceptance_scenarios must be a non-empty list")
    scenarios: list[AcceptanceScenario] = []
    scenario_ids: set[str] = set()
    for index, raw_scenario in enumerate(raw_scenarios):
        scenario = _mapping(raw_scenario, f"product_intent.acceptance_scenarios[{index}]")
        scenario_id = _string(
            scenario.get("id"), f"product_intent.acceptance_scenarios[{index}].id"
        )
        if scenario_id in scenario_ids:
            raise HarnessError(f"duplicate product acceptance scenario id: {scenario_id}")
        scenario_ids.add(scenario_id)
        scenarios.append(
            AcceptanceScenario(
                scenario_id=scenario_id,
                decision_id=_string(
                    scenario.get("decision"),
                    f"product_intent.acceptance_scenarios[{index}].decision",
                ),
                trigger=_string(
                    scenario.get("trigger"),
                    f"product_intent.acceptance_scenarios[{index}].trigger",
                ),
                desired_outcome=_string(
                    scenario.get("desired_outcome"),
                    f"product_intent.acceptance_scenarios[{index}].desired_outcome",
                ),
                evidence=_strings(
                    scenario.get("evidence"),
                    f"product_intent.acceptance_scenarios[{index}].evidence",
                ),
            )
        )
    product_intent = ProductIntent(
        mission=_string(raw_intent.get("mission"), "product_intent.mission"),
        current_problem=_string(
            raw_intent.get("current_problem"), "product_intent.current_problem"
        ),
        decisions=tuple(decisions),
        acceptance_scenarios=tuple(scenarios),
        principles=_strings(raw_intent.get("principles"), "product_intent.principles"),
        open_questions=_strings(
            raw_intent.get("open_questions"), "product_intent.open_questions"
        ),
        review_question=_string(
            raw_intent.get("review_question"), "product_intent.review_question"
        ),
        source=source_relative,
        journeys=journeys,
        requirements=requirements,
    )
    raw_current_state = document.get("current_state")
    current_state: CurrentStateEvidence | None = None
    if raw_current_state is not None:
        state_document = _mapping(raw_current_state, "current_state")
        max_age_days = state_document.get("max_age_days", 14)
        if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days < 0:
            raise HarnessError("current_state.max_age_days must be a non-negative integer")
        current_state = CurrentStateEvidence(
            path=Path(_string(state_document.get("path"), "current_state.path")),
            max_age_days=max_age_days,
            reviewed_marker=_string(
                state_document.get("reviewed_marker", "Last reviewed:"),
                "current_state.reviewed_marker",
            ),
            required_markers=_strings(
                state_document.get("required_markers", []), "current_state.required_markers"
            ),
            forbidden_markers=_strings(
                state_document.get("forbidden_markers", []), "current_state.forbidden_markers"
            ),
        )
    raw_tracks = document.get("tracks")
    if not isinstance(raw_tracks, list) or not raw_tracks:
        raise HarnessError("tracks must be a non-empty list")

    tracks: list[Track] = []
    ids: set[str] = set()
    branches: set[str] = set()
    merge_modes = {"independent", "stacked", "contract-first", "integration"}
    for index, raw_track in enumerate(raw_tracks):
        item = _mapping(raw_track, f"tracks[{index}]")
        track_id = _string(item.get("id"), f"tracks[{index}].id")
        if track_id in ids:
            raise HarnessError(f"duplicate track id: {track_id}")
        ids.add(track_id)
        branch = _string(item.get("branch"), f"{track_id}.branch")
        if branch in branches:
            raise HarnessError(f"duplicate track branch: {branch}")
        branches.add(branch)
        raw_checks = item.get("checks")
        if not isinstance(raw_checks, list) or not raw_checks:
            raise HarnessError(f"tracks[{index}].checks must be a non-empty list")
        checks_list: list[Check] = []
        for raw_check in raw_checks:
            check = _mapping(raw_check, "check")
            checks_list.append(
                Check(
                    name=_string(check.get("name"), f"{track_id}.checks.name"),
                    command=_string(check.get("command"), f"{track_id}.checks.command"),
                    profile=str(check.get("profile", "focused")),
                    requires_database=bool(check.get("requires_database", False)),
                )
            )
        checks = tuple(checks_list)
        raw_workspace_files = item.get("workspace_files", [])
        if not isinstance(raw_workspace_files, list):
            raise HarnessError(f"{track_id}.workspace_files must be a list")
        workspace_files: list[WorkspaceFile] = []
        for file_index, raw_file in enumerate(raw_workspace_files):
            file = _mapping(raw_file, f"{track_id}.workspace_files[{file_index}]")
            workspace_files.append(
                WorkspaceFile(
                    source=_relative_file(
                        file.get("source"), f"{track_id}.workspace_files[{file_index}].source"
                    ),
                    target=_relative_file(
                        file.get("target"), f"{track_id}.workspace_files[{file_index}].target"
                    ),
                )
            )
        if len({file.target for file in workspace_files}) != len(workspace_files):
            raise HarnessError(f"{track_id}.workspace_files has duplicate targets")
        raw_merge = _mapping(item.get("merge", {}), f"{track_id}.merge")
        merge_mode = _string(
            raw_merge.get("mode", "independent"), f"{track_id}.merge.mode"
        )
        if merge_mode not in merge_modes:
            raise HarnessError(
                f"{track_id}.merge.mode must be one of {sorted(merge_modes)}"
            )
        merge = MergePlan(
            mode=merge_mode,
            target=_string(raw_merge.get("target", base_branch), f"{track_id}.merge.target"),
            after=_strings(raw_merge.get("after", []), f"{track_id}.merge.after"),
        )
        raw_evidence = _mapping(item.get("evidence"), f"{track_id}.evidence")
        raw_review = _mapping(item.get("review"), f"{track_id}.review")
        tracks.append(
            Track(
                track_id=track_id,
                capability_id=_string(
                    item.get("capability_id", track_id), f"{track_id}.capability_id"
                ),
                title=_string(item.get("title"), f"{track_id}.title"),
                user_outcome=_string(item.get("user_outcome"), f"{track_id}.user_outcome"),
                instrumental_purpose=_string(
                    item.get("instrumental_purpose"), f"{track_id}.instrumental_purpose"
                ),
                scope=_strings(item.get("scope"), f"{track_id}.scope"),
                branch=branch,
                depends_on=_strings(item.get("depends_on", []), f"{track_id}.depends_on"),
                serves=_strings(item.get("serves"), f"{track_id}.serves"),
                scenarios=_strings(item.get("scenarios"), f"{track_id}.scenarios"),
                journeys=_strings(item.get("journeys"), f"{track_id}.journeys"),
                requirements=_strings(item.get("requirements"), f"{track_id}.requirements"),
                workspace_files=tuple(workspace_files),
                merge=merge,
                checks=checks,
                evidence=Evidence(
                    required=_strings(raw_evidence.get("required"), f"{track_id}.evidence.required"),
                    artifacts=_strings(raw_evidence.get("artifacts", []), f"{track_id}.evidence.artifacts"),
                ),
                review=Review(
                    question=_string(raw_review.get("question"), f"{track_id}.review.question"),
                    decision_point=_string(
                        raw_review.get("decision_point"), f"{track_id}.review.decision_point"
                    ),
                ),
            )
        )
    track_ids = {track.track_id for track in tracks}
    decision_ids = {decision.decision_id for decision in product_intent.decisions}
    scenario_ids = {scenario.scenario_id for scenario in product_intent.acceptance_scenarios}
    scenario_decisions = {
        scenario.scenario_id: scenario.decision_id
        for scenario in product_intent.acceptance_scenarios
    }
    unknown_scenario_decisions = {
        scenario.decision_id
        for scenario in product_intent.acceptance_scenarios
        if scenario.decision_id not in decision_ids
    }
    if unknown_scenario_decisions:
        raise HarnessError(
            "product acceptance scenarios reference unknown decisions: "
            f"{sorted(unknown_scenario_decisions)}"
        )
    referenced_scenarios: set[str] = set()
    for track in tracks:
        missing = set(track.depends_on) - track_ids
        if missing:
            raise HarnessError(f"{track.track_id} depends on unknown tracks: {sorted(missing)}")
        missing_merge_after = set(track.merge.after) - track_ids
        if missing_merge_after:
            raise HarnessError(
                f"{track.track_id} merge plan references unknown tracks: "
                f"{sorted(missing_merge_after)}"
            )
        missing_decisions = set(track.serves) - decision_ids
        if missing_decisions:
            raise HarnessError(
                f"{track.track_id} serves unknown product intent decisions: "
                f"{sorted(missing_decisions)}"
            )
        missing_scenarios = set(track.scenarios) - scenario_ids
        if missing_scenarios:
            raise HarnessError(
                f"{track.track_id} references unknown product acceptance scenarios: "
                f"{sorted(missing_scenarios)}"
            )
        missing_journeys = set(track.journeys) - journey_ids
        if missing_journeys:
            raise HarnessError(
                f"{track.track_id} references unknown product journeys: {sorted(missing_journeys)}"
            )
        missing_requirements = set(track.requirements) - requirement_ids
        if missing_requirements:
            raise HarnessError(
                f"{track.track_id} references unknown functional requirements: "
                f"{sorted(missing_requirements)}"
            )
        scenario_decision_ids = {
            scenario_decisions[scenario_id] for scenario_id in track.scenarios
        }
        if not scenario_decision_ids <= set(track.serves):
            raise HarnessError(
                f"{track.track_id} scenarios must serve decisions declared in serves"
            )
        referenced_scenarios.update(track.scenarios)
    unreferenced_scenarios = scenario_ids - referenced_scenarios
    if unreferenced_scenarios:
        raise HarnessError(
            "product acceptance scenarios are not assigned to a track: "
            f"{sorted(unreferenced_scenarios)}"
        )
    _assert_acyclic(tracks)
    return HarnessConfig(
        root=repository_root,
        base_branch=base_branch,
        worktrees_dir=repository_root / worktrees_dir,
        state_dir=repository_root / state_dir,
        database_env=database_env,
        admin_prefix=admin_prefix,
        product_intent=product_intent,
        current_state=current_state,
        tracks=tuple(tracks),
    )


def _assert_acyclic(tracks: list[Track]) -> None:
    dependencies = {track.track_id: set(track.depends_on) for track in tracks}
    resolved: set[str] = set()
    while dependencies:
        ready = {track_id for track_id, deps in dependencies.items() if not deps - resolved}
        if not ready:
            raise HarnessError("track dependencies contain a cycle")
        resolved.update(ready)
        for track_id in ready:
            dependencies.pop(track_id)


def _git(root: Path, *args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd or root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise HarnessError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _track(config: HarnessConfig, track_id: str) -> Track:
    for track in config.tracks:
        if track.track_id == track_id:
            return track
    raise HarnessError(f"unknown track: {track_id}")


def _worktree(config: HarnessConfig, track: Track) -> Path:
    return config.worktrees_dir / track.track_id


def _state_path(config: HarnessConfig, track: Track) -> Path:
    return config.state_dir / f"{track.track_id}.json"


def _intent_state_path(config: HarnessConfig) -> Path:
    return config.state_dir / "product-intent.json"


def _read_intent_state(config: HarnessConfig) -> dict[str, Any]:
    path = _intent_state_path(config)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"invalid product intent state file: {path}") from exc
    return value if isinstance(value, dict) else {}


def _intent_digest(config: HarnessConfig) -> str:
    """Return the content digest that a human intent review accepted."""
    source = config.root / config.product_intent.source
    return hashlib.sha256(source.read_bytes()).hexdigest()


def record_intent_review(config: HarnessConfig, decision: str, notes: str) -> None:
    """Record the human review of the proposed product intent baseline."""
    if decision not in {"accept", "revisit"}:
        raise HarnessError("intent decision must be accept or revisit")
    state = {
        "decision": decision,
        "notes": notes,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "source_sha256": _intent_digest(config),
    }
    config.state_dir.mkdir(parents=True, exist_ok=True)
    _intent_state_path(config).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def product_intent_status(config: HarnessConfig) -> str:
    """Return the local human-review status for product intent."""
    state = _read_intent_state(config)
    decision = state.get("decision")
    if decision not in {"accept", "revisit"}:
        return "needs-review"
    if state.get("source_sha256") != _intent_digest(config):
        return "needs-review"
    return decision


def current_state_status(config: HarnessConfig) -> dict[str, Any]:
    """Check freshness and lexical consistency of the canonical product-state document."""
    evidence = config.current_state
    if evidence is None:
        return {"status": "not-configured"}
    path = evidence.path if evidence.path.is_absolute() else config.root / evidence.path
    result: dict[str, Any] = {
        "status": "missing",
        "path": str(path),
        "max_age_days": evidence.max_age_days,
        "required_markers": list(evidence.required_markers),
        "forbidden_markers": list(evidence.forbidden_markers),
    }
    if not path.is_file():
        result["error"] = "current-state document does not exist"
        return result
    content = path.read_text(encoding="utf-8")
    missing_markers = [marker for marker in evidence.required_markers if marker not in content]
    forbidden_markers = [marker for marker in evidence.forbidden_markers if marker in content]
    result["missing_markers"] = missing_markers
    result["forbidden_markers_found"] = forbidden_markers
    reviewed_match = re.search(
        rf"{re.escape(evidence.reviewed_marker)}\s*(\d{{4}}-\d{{2}}-\d{{2}})", content
    )
    if reviewed_match:
        reviewed_date = datetime.strptime(reviewed_match.group(1), "%Y-%m-%d").date()
        age_days = (datetime.now(UTC).date() - reviewed_date).days
        result["reviewed_date"] = reviewed_date.isoformat()
        result["age_days"] = age_days
    else:
        age_days = None
        result["error"] = f"review date marker {evidence.reviewed_marker!r} is missing or invalid"
    if forbidden_markers:
        result["status"] = "contradictory"
    elif missing_markers:
        result["status"] = "incomplete"
    elif age_days is None:
        result["status"] = "unreviewed"
    elif age_days < 0:
        result["status"] = "future-dated"
    elif age_days > evidence.max_age_days:
        result["status"] = "stale"
    else:
        result["status"] = "fresh"
    return result


def render_current_state(config: HarnessConfig) -> str:
    """Render the canonical product-state evidence check."""
    status = current_state_status(config)
    lines = ["# Trader current-state evidence", "", f"- Status: **{status['status']}**"]
    if status.get("path"):
        lines.append(f"- Source: `{status['path']}`")
    if status.get("reviewed_date"):
        lines.append(f"- Last reviewed: {status['reviewed_date']} ({status['age_days']} days ago)")
    if status.get("missing_markers"):
        lines.append(f"- Missing required evidence: {'; '.join(status['missing_markers'])}")
    if status.get("forbidden_markers_found"):
        lines.append(
            "- Contradictory evidence found: "
            f"{'; '.join(status['forbidden_markers_found'])}"
        )
    if status.get("error"):
        lines.append(f"- Detail: {status['error']}")
    return "\n".join(lines) + "\n"


def render_intent(config: HarnessConfig) -> str:
    """Render the product intent and the decisions served by each track."""
    intent = config.product_intent
    decision_text = {decision.decision_id: decision.statement for decision in intent.decisions}
    lines = [
        "# Trader product intent",
        "",
        f"- Review status: **{product_intent_status(config)}**",
        f"- Current-state evidence: **{current_state_status(config)['status']}**",
        f"- Intent source: `{intent.source}`",
        f"- Mission: {intent.mission}",
        f"- Current problem: {intent.current_problem}",
        f"- Human review question: {intent.review_question}",
        "",
        "## Decisions Trader should make easier",
    ]
    lines.extend(f"- `{decision_id}`: {statement}" for decision_id, statement in decision_text.items())
    lines.extend(["", "## Product acceptance scenarios"])
    for scenario in intent.acceptance_scenarios:
        lines.extend(
            [
                f"- `{scenario.scenario_id}` serves `{scenario.decision_id}`",
                f"  - Trigger: {scenario.trigger}",
                f"  - Desired outcome: {scenario.desired_outcome}",
                f"  - Evidence: {'; '.join(scenario.evidence)}",
            ]
        )
    lines.extend(["", "## Operating principles"])
    lines.extend(f"- {principle}" for principle in intent.principles)
    lines.extend(["", "## Open questions"])
    lines.extend(f"- {question}" for question in intent.open_questions)
    lines.extend(["", "## Candidate user journeys"])
    lines.extend(f"- `{reference.identifier}`: {reference.title}" for reference in intent.journeys)
    lines.extend(["", "## Candidate functional requirements"])
    lines.extend(f"- `{reference.identifier}`: {reference.title}" for reference in intent.requirements)
    lines.extend(["", "## Tracks serving those decisions"])
    for track in config.tracks:
        served = "; ".join(decision_text[decision_id] for decision_id in track.serves)
        scenarios = "; ".join(track.scenarios)
        lines.append(
            f"- `{track.track_id}` — {served} (journeys: {', '.join(track.journeys)}; "
            f"requirements: {', '.join(track.requirements)}; scenarios: {scenarios})"
        )
    return "\n".join(lines) + "\n"


def derive_test_database(base_database: str, track_id: str) -> str:
    """Derive a safe per-track Postgres database name.

    Args:
        base_database: Guarded base database ending in ``_test`` or ``_testing``.
        track_id: Registered track identifier used as the namespace component.

    Returns:
        A PostgreSQL identifier no longer than 63 characters and ending in ``_test``.

    Raises:
        HarnessError: If the base database is not a guarded test database.
    """
    normalized = base_database.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*_(?:test|testing)", normalized):
        raise HarnessError(f"{base_database!r} must end in _test or _testing")
    stem = re.sub(r"_(?:test|testing)$", "", normalized)
    slug = re.sub(r"[^a-z0-9]+", "_", track_id.lower()).strip("_") or "track"
    candidate = f"{stem}_{slug}_test"
    if len(candidate) <= 63:
        return candidate
    digest = hashlib.sha256(track_id.encode("utf-8")).hexdigest()[:8]
    return f"{candidate[:54]}_{digest}"[:63]


def _database_state(config: HarnessConfig, track: Track) -> dict[str, Any]:
    state = _read_state(config, track)
    environment = state.get("test_environment")
    return environment if isinstance(environment, dict) else {}


def test_environment(config: HarnessConfig, track_id: str) -> dict[str, str]:
    """Return the environment that identifies a track's isolated test database."""
    track = _track(config, track_id)
    environment = _database_state(config, track)
    database = str(environment.get("database", "")).strip()
    if not database:
        base_database = os.environ.get(config.database_env, "").strip()
        if not base_database:
            raise HarnessError(
                f"set {config.database_env} before provisioning {track.track_id}"
            )
        database = derive_test_database(base_database, track.track_id)
    environment_values = {
        "TRADER_DEV_TRACK_ID": track.track_id,
        "TRADER_TEST_DATABASE": database,
        config.database_env: database,
    }
    for related_database in ("PG_OPTUNA_TEST_DB", "PG_CHECKPOINT_TEST_DB"):
        if os.environ.get(related_database, "").strip():
            environment_values[related_database] = database
    slug = re.sub(r"[^a-z0-9]+", "_", track.track_id.lower()).strip("_") or "track"
    if os.environ.get("TRADER_OPTUNA_SCHEMA", "").strip():
        environment_values["TRADER_OPTUNA_SCHEMA"] = f"trader_optuna_{slug}"
    if os.environ.get("TRADER_CHECKPOINT_SCHEMA", "").strip():
        environment_values["TRADER_CHECKPOINT_SCHEMA"] = f"trader_checkpoint_{slug}"
    return environment_values


def provision_test_database(config: HarnessConfig, track_id: str, *, reset: bool) -> dict[str, str]:
    """Create one disposable database owned by the configured test role.

    The derived name must contain the registered track identifier and end in
    ``_test``. Reset can therefore affect only this worktree's database.
    """
    track = _track(config, track_id)
    base_database = os.environ.get(config.database_env, "").strip()
    if not base_database:
        raise HarnessError(f"set {config.database_env} before provisioning {track.track_id}")
    database = derive_test_database(base_database, track.track_id)
    prefix = config.admin_prefix
    admin_values = {
        key: os.environ.get(f"{prefix}_{key}", "").strip()
        for key in ("HOST", "PORT", "DB", "USER", "PASSWORD")
    }
    missing = [name for name, value in admin_values.items() if not value]
    if missing:
        raise HarnessError(f"missing {prefix} settings: {', '.join(missing)}")
    test_user = os.environ.get("PG_TEST_USER", "").strip()
    if not test_user:
        raise HarnessError("PG_TEST_USER is required to own the isolated database")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", test_user):
        raise HarnessError("PG_TEST_USER must be a simple Postgres identifier")
    if admin_values["DB"].lower() == database:
        raise HarnessError(f"{prefix}_DB must not equal the derived test database {database!r}")
    try:
        admin_port = int(admin_values["PORT"])
    except ValueError as exc:
        raise HarnessError(f"{prefix}_PORT must be an integer") from exc
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:  # pragma: no cover - project dependency is present
        raise HarnessError("psycopg is required to provision a test database") from exc
    with psycopg.connect(
        host=admin_values["HOST"],
        port=admin_port,
        dbname=admin_values["DB"],
        user=admin_values["USER"],
        password=admin_values["PASSWORD"],
        autocommit=True,
    ) as connection:
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", [database]).fetchone()
        if exists and reset:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                [database],
            )
            connection.execute(sql.SQL("DROP DATABASE {} ").format(sql.Identifier(database)))
            exists = None
        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
                    sql.Identifier(database), sql.Identifier(test_user)
                )
            )
        connection.execute(sql.SQL("ALTER DATABASE {} SET timezone TO 'UTC'").format(sql.Identifier(database)))
        for role_environment in ("PG_OPTUNA_TEST_USER", "PG_CHECKPOINT_TEST_USER"):
            role = os.environ.get(role_environment, "").strip()
            if role:
                connection.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(database), sql.Identifier(role)
                    )
                )
    state = _read_state(config, track)
    state["test_environment"] = {
        "mode": "database",
        "database": database,
        "provisioned_at": datetime.now(UTC).isoformat(),
    }
    config.state_dir.mkdir(parents=True, exist_ok=True)
    _state_path(config, track).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return test_environment(config, track_id)


def _read_state(config: HarnessConfig, track: Track) -> dict[str, Any]:
    path = _state_path(config, track)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"invalid state file: {path}") from exc
    return value if isinstance(value, dict) else {}


def prepare_track(config: HarnessConfig, track_id: str) -> list[str]:
    """Copy declared tracked templates into a worktree without replacing local files."""
    track = _track(config, track_id)
    path = _worktree(config, track)
    if not path.is_dir():
        raise HarnessError(f"start the track before preparing it: {path}")
    worktree_root = path.resolve()
    created: list[str] = []
    for workspace_file in track.workspace_files:
        source = path / workspace_file.source
        target = path / workspace_file.target
        if not source.resolve().is_relative_to(worktree_root) or source.is_symlink():
            raise HarnessError(f"workspace template escapes the worktree: {source}")
        if not target.parent.resolve().is_relative_to(worktree_root) or target.is_symlink():
            raise HarnessError(f"workspace file target escapes the worktree: {target}")
        if not source.is_file():
            raise HarnessError(f"workspace template is missing: {source}")
        _git(config.root, "ls-files", "--error-unmatch", "--", str(workspace_file.source), cwd=path)
        if target.exists():
            if not target.is_file():
                raise HarnessError(f"workspace file target is not a file: {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        created.append(str(workspace_file.target))
    return created


def start_track(config: HarnessConfig, track_id: str) -> Path:
    """Create an isolated worktree and branch for a registered track."""
    track = _track(config, track_id)
    path = _worktree(config, track)
    if path.exists():
        raise HarnessError(f"worktree already exists: {path}")
    config.worktrees_dir.mkdir(parents=True, exist_ok=True)
    _git(config.root, "worktree", "add", "-b", track.branch, str(path), config.base_branch)
    prepare_track(config, track_id)
    return path


def run_checks(config: HarnessConfig, track_id: str, profile: str) -> dict[str, Any]:
    """Run one track's declared checks and persist commit-bound results."""
    track = _track(config, track_id)
    path = _worktree(config, track)
    if not path.is_dir():
        raise HarnessError(f"start the track before checking it: {path}")
    missing_files = [
        str(workspace_file.target)
        for workspace_file in track.workspace_files
        if not (path / workspace_file.target).is_file()
    ]
    if missing_files:
        raise HarnessError(
            f"prepare {track_id} before running checks; missing workspace files: {missing_files}"
        )
    selected = [check for check in track.checks if check.profile == profile]
    if not selected:
        raise HarnessError(f"{track_id} has no checks for profile {profile!r}")
    commit = _git(config.root, "rev-parse", "HEAD", cwd=path)
    results: list[dict[str, Any]] = []
    isolated_environment = test_environment(config, track_id) if any(
        check.requires_database for check in selected
    ) else {}
    if isolated_environment and not _database_state(config, track):
        raise HarnessError(
            f"provision the isolated database before running {track_id} profile {profile!r}: "
            f"uv run python tools/development_harness.py provision-db {track_id}"
        )
    for check in selected:
        command_environment = os.environ.copy()
        if check.requires_database:
            command_environment.update(isolated_environment)
        completed = subprocess.run(
            ["bash", "-eu", "-o", "pipefail", "-c", check.command],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
            env=command_environment,
        )
        results.append(
            {
                "name": check.name,
                "command": check.command,
                "profile": check.profile,
                "requires_database": check.requires_database,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )
    state = _read_state(config, track)
    state.update(
        {
            "track_id": track.track_id,
            "checked_at": datetime.now(UTC).isoformat(),
            "commit": commit,
            "profile": profile,
            "checks": results,
        }
    )
    config.state_dir.mkdir(parents=True, exist_ok=True)
    _state_path(config, track).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def record_review(config: HarnessConfig, track_id: str, decision: str, notes: str) -> None:
    """Record the human decision that controls a track's next action."""
    if decision not in {"continue", "merge", "pause", "redirect"}:
        raise HarnessError("decision must be continue, merge, pause, or redirect")
    track = _track(config, track_id)
    state = _read_state(config, track)
    state["human_review"] = {
        "decision": decision,
        "notes": notes,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    config.state_dir.mkdir(parents=True, exist_ok=True)
    _state_path(config, track).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def track_status(config: HarnessConfig, track: Track) -> dict[str, Any]:
    """Return local execution and evidence status for one track."""
    path = _worktree(config, track)
    state = _read_state(config, track)
    if not path.is_dir():
        phase = "planned"
    else:
        current_commit = _git(config.root, "rev-parse", "HEAD", cwd=path)
        checked = state.get("commit") == current_commit
        passed = bool(state.get("checks")) and all(item.get("returncode") == 0 for item in state["checks"])
        review = state.get("human_review", {}).get("decision")
        intent_accepted = product_intent_status(config) == "accept"
        current_state_ok = current_state_status(config)["status"] in {"fresh", "not-configured"}
        phase = (
            "ready-to-merge"
            if checked and passed and review == "merge" and intent_accepted and current_state_ok
            else "needs-review"
        )
        if state.get("checks") and not passed:
            phase = "blocked-by-check"
        elif not checked:
            phase = "needs-check"
        elif review == "pause":
            phase = "paused"
        elif review == "redirect":
            phase = "redirected"
    return {
        "id": track.track_id,
        "capability_id": track.capability_id,
        "title": track.title,
        "phase": phase,
        "worktree": str(path),
        "branch": track.branch,
        "user_outcome": track.user_outcome,
        "instrumental_purpose": track.instrumental_purpose,
        "review_question": track.review.question,
        "review_decision_point": track.review.decision_point,
        "serves": list(track.serves),
        "scenarios": list(track.scenarios),
        "journeys": list(track.journeys),
        "requirements": list(track.requirements),
        "workspace_files": [str(item.target) for item in track.workspace_files],
        "merge": {
            "mode": track.merge.mode,
            "target": track.merge.target,
            "after": list(track.merge.after),
        },
        "product_intent_status": product_intent_status(config),
        "current_state_status": current_state_status(config)["status"],
        "evidence": list(track.evidence.required),
        "artifacts": list(track.evidence.artifacts),
        "test_database": _database_state(config, track),
        "state": state,
    }


def render_report(config: HarnessConfig) -> str:
    """Render a concise report for human review across all tracks."""
    lines = [
        "# Trader development report",
        "",
        f"Product intent review: **{product_intent_status(config)}**",
        f"Current-state evidence: **{current_state_status(config)['status']}**",
        f"Intent source: `{config.product_intent.source}`",
        f"Mission: {config.product_intent.mission}",
        f"Review question: {config.product_intent.review_question}",
        "",
    ]
    decision_text = {
        decision.decision_id: decision.statement
        for decision in config.product_intent.decisions
    }
    scenario_text = {
        scenario.scenario_id: scenario.desired_outcome
        for scenario in config.product_intent.acceptance_scenarios
    }
    for track in config.tracks:
        status = track_status(config, track)
        served = "; ".join(decision_text[decision_id] for decision_id in track.serves)
        scenarios = "; ".join(
            f"{scenario_id}: {scenario_text[scenario_id]}" for scenario_id in track.scenarios
        )
        lines.extend(
            [
                f"## {track.title} (`{track.track_id}`)",
                f"- Phase: **{status['phase']}**; capability `{track.capability_id}`; branch `{track.branch}`; worktree `{status['worktree']}`",
                f"- Merge strategy: `{track.merge.mode}` into `{track.merge.target}` after `{', '.join(track.merge.after) or 'none'}`",
                f"- User outcome: {track.user_outcome}",
                f"- Why this work matters: {track.instrumental_purpose}",
                f"- Product decisions served: {served}",
                f"- Acceptance scenarios: {scenarios}",
                f"- Intent journeys: {', '.join(track.journeys)}",
                f"- Functional requirements: {', '.join(track.requirements)}",
                f"- Evidence to inspect: {'; '.join(track.evidence.required)}",
                f"- Human review: {track.review.question} ({track.review.decision_point})",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("current-state")
    subparsers.add_parser("intent")
    start = subparsers.add_parser("start")
    start.add_argument("track")
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("track")
    check = subparsers.add_parser("check")
    check.add_argument("track")
    check.add_argument("--profile", default="focused")
    provision = subparsers.add_parser("provision-db")
    provision.add_argument("track")
    provision.add_argument("--reset", action="store_true")
    environment = subparsers.add_parser("test-env")
    environment.add_argument("track")
    review = subparsers.add_parser("review")
    review.add_argument("track")
    review.add_argument("decision", choices=("continue", "merge", "pause", "redirect"))
    review.add_argument("--notes", default="")
    intent_review = subparsers.add_parser("review-intent")
    intent_review.add_argument("decision", choices=("accept", "revisit"))
    intent_review.add_argument("--notes", default="")
    status = subparsers.add_parser("status")
    status.add_argument("--json", action="store_true")
    report = subparsers.add_parser("report")
    report.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the development harness CLI."""
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.manifest)
        if args.command == "validate":
            print(f"valid: {len(config.tracks)} tracks")
        elif args.command == "current-state":
            state = current_state_status(config)
            print(render_current_state(config), end="")
            return 0 if state["status"] in {"fresh", "not-configured"} else 1
        elif args.command == "intent":
            print(render_intent(config), end="")
        elif args.command == "start":
            print(start_track(config, args.track))
        elif args.command == "prepare":
            print(json.dumps({"created": prepare_track(config, args.track)}, indent=2))
        elif args.command == "check":
            state = run_checks(config, args.track, args.profile)
            print(json.dumps(state, indent=2))
            return 0 if all(item["returncode"] == 0 for item in state["checks"]) else 1
        elif args.command == "provision-db":
            print(json.dumps(provision_test_database(config, args.track, reset=args.reset), indent=2))
        elif args.command == "test-env":
            print(json.dumps(test_environment(config, args.track), indent=2))
        elif args.command == "review":
            record_review(config, args.track, args.decision, args.notes)
            print(f"recorded {args.decision} for {args.track}")
        elif args.command == "review-intent":
            record_intent_review(config, args.decision, args.notes)
            print(f"recorded product intent decision: {args.decision}")
        elif args.command == "status":
            values = [track_status(config, track) for track in config.tracks]
            print(json.dumps(values, indent=2) if args.json else "\n".join(f"{v['id']}: {v['phase']}" for v in values))
        elif args.command == "report":
            values = [track_status(config, track) for track in config.tracks]
            print(json.dumps(values, indent=2) if args.json else render_report(config), end="")
        return 0
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
