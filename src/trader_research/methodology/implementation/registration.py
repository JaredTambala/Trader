"""Registration, provenance, and safety checks for method implementations."""

from __future__ import annotations

from trader_research.governance.artifacts import QUANTITATIVE_METHODS_OWNER

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import ArtifactReference

import ast
import hashlib
import importlib
import importlib.util
import inspect
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from trader.indicators import Indicator
from trader.signals import Signal

from trader_research.foundation.artifacts import ResearchArtifactStore
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import METHOD_IMPLEMENTATION_MANIFEST
from trader_research.knowledge.approved_cards import ApprovedMethodCardReadError, ApprovedMethodCardReader
from trader_research.methodology.registry import get_method
from trader_research.methodology.implementation.io import file_sha256, local_mutating_error, save_manifest
from trader_research.methodology.implementation.manifest import (
    DEFAULT_ALLOWED_IMPORTS,
    DEFAULT_ENTRYPOINTS,
    FORBIDDEN_CALLS,
    INDICATOR_RUNTIME_CONTRACT,
    MATH_REGISTER_METHOD_IMPLEMENTATION,
    SIGNAL_RUNTIME_CONTRACT,
    MethodImplementationManifest,
    mapping,
)


def register_method_implementation(
    *,
    artifact_root: str | Path,
    method_id: str,
    method_card_ids: Sequence[str],
    method_contract: Mapping[str, Any] | None = None,
    entrypoint: str | None = None,
    source_path: str | Path | None = None,
    class_name: str | None = None,
    constructor_kwargs: Mapping[str, Any] | None = None,
    implementation_kind: str = "maintained",
    dependency_allowlist: Sequence[str] | None = None,
    expected_source_hash: str | None = None,
    approved_card_reader: ApprovedMethodCardReader | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Validate evidence, source safety, runtime contract, and persist a manifest.

    Registration resolves the maintained method contract, derives or validates the
    implementation entrypoint, checks approved method-card evidence, hashes the
    source file, scans imports and forbidden calls, verifies required provenance in
    the module docstring, imports the class, and confirms it subclasses the expected
    Indicator or Signal runtime. Only implementations that pass those deterministic
    checks are written as manifests.
    """
    blockers: list[str] = []
    warnings: list[str] = []
    method_id = method_id.strip()
    entrypoint = (entrypoint or DEFAULT_ENTRYPOINTS.get(method_id) or "").strip()
    method_card_ids = tuple(str(item).strip() for item in method_card_ids if str(item).strip())
    method_contract = _method_contract(method_id, method_contract, method_card_ids, constructor_kwargs)
    constructor_kwargs = _constructor_kwargs(method_id, method_contract, constructor_kwargs)
    dependency_allowlist = tuple(dependency_allowlist or DEFAULT_ALLOWED_IMPORTS)

    entry = get_method(method_id)
    if entry is None:
        blockers.append(f"unsupported method_id: {method_id}")
    runtime_contract = _runtime_contract_for_entry(entry)
    required_runtime_class = _runtime_contract_class(runtime_contract)
    if required_runtime_class is None:
        blockers.append(f"unsupported runtime_contract: {runtime_contract}")
    if isinstance(method_contract, Mapping):
        method_contract = dict(method_contract)
        method_contract.setdefault("runtime_contract", runtime_contract)
    if implementation_kind not in {"maintained", "generated"}:
        blockers.append("implementation_kind must be maintained or generated")
    requires_card_evidence = implementation_kind == "generated" or bool(entry and entry.requires_evidence)
    if requires_card_evidence and not method_card_ids:
        blockers.append("approved method-card refs are required")
    elif method_card_ids:
        if approved_card_reader is None:
            blockers.append("approved method-card reader is required")
        else:
            try:
                approved = approved_card_reader.has_approved_method_card(method_card_ids, method_id=method_id)
            except ApprovedMethodCardReadError as exc:
                return local_mutating_error(
                    MATH_REGISTER_METHOD_IMPLEMENTATION,
                    "approved_method_card_read_error",
                    str(exc),
                )
            if not approved:
                blockers.append("approved method-card evidence does not match the requested method")

    source = Path(source_path).expanduser().resolve() if source_path is not None else _source_path_for_entrypoint(entrypoint)
    if source is None:
        blockers.append(f"could not resolve source path for entrypoint: {entrypoint}")
        source_hash = ""
        source_provenance: Mapping[str, Any] = {}
    elif source.exists() and source.is_file():
        source_hash = file_sha256(source)
        blockers.extend(_static_safety_blockers(source, dependency_allowlist=dependency_allowlist))
        source_provenance, provenance_blockers = _source_provenance(
            source,
            method_id=method_id,
            method_card_ids=method_card_ids,
            entrypoint=entrypoint,
            class_name=class_name,
            runtime_contract=runtime_contract,
            require_method_cards=requires_card_evidence,
        )
        blockers.extend(provenance_blockers)
    else:
        source_hash = ""
        source_provenance = {}
        blockers.append(f"source path does not exist: {source}")
    if expected_source_hash and source_hash and expected_source_hash != source_hash:
        blockers.append("source hash does not match expected_source_hash")

    implementation_class = None
    if not blockers:
        try:
            implementation_class = _load_implementation_class(
                entrypoint=entrypoint,
                source_path=source if implementation_kind == "generated" else None,
                class_name=class_name,
            )
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            blockers.append(str(exc))
    if implementation_class is not None and required_runtime_class is not None and not issubclass(
        implementation_class,
        required_runtime_class,
    ):
        blockers.append(f"entrypoint is not a {runtime_contract} subclass")

    if blockers:
        return error_result(
            command=MATH_REGISTER_METHOD_IMPLEMENTATION,
            code="method_implementation_registration_failed",
            message="method implementation registration failed",
            data={"blockers": blockers, "warnings": warnings},
        )

    resolved_class_name = class_name or entrypoint.split(":")[-1]
    manifest = MethodImplementationManifest(
        implementation_id=stable_research_id(
            "method_impl",
            {
                "method_id": method_id,
                "entrypoint": entrypoint,
                "source_hash": source_hash,
                "method_card_ids": list(method_card_ids),
                "constructor_kwargs": dict(constructor_kwargs),
            },
        ),
        method_id=method_id,
        language="python",
        implementation_kind=implementation_kind,
        entrypoint=entrypoint,
        class_name=resolved_class_name,
        source_path=str(source),
        source_hash=source_hash,
        source_provenance=source_provenance,
        constructor_kwargs=constructor_kwargs,
        method_card_ids=method_card_ids,
        method_contract=method_contract,
        runtime_contract=runtime_contract,
        dependency_allowlist=dependency_allowlist,
    )
    manifest_payload = manifest.to_dict()
    if artifact_store is not None:
        manifest_record = artifact_store.save_artifact(
            agent_owner=QUANTITATIVE_METHODS_OWNER,
            artifact_type=METHOD_IMPLEMENTATION_MANIFEST,
            artifact_id=manifest.implementation_id,
            payload=manifest_payload,
            status=manifest.status,
            source_hash=manifest.source_hash,
            metadata={"method_id": manifest.method_id, "runtime_contract": manifest.runtime_contract},
        )
        manifest_ref = ArtifactReference(
            artifact_type=METHOD_IMPLEMENTATION_MANIFEST,
            uri=manifest_record.uri,
            metadata={"id": manifest.implementation_id},
        ).to_dict()
    else:
        manifest_path = save_manifest(artifact_root, manifest)
        manifest_ref = ArtifactReference(
            artifact_type=METHOD_IMPLEMENTATION_MANIFEST,
            path=manifest_path,
            metadata={"id": manifest.implementation_id},
        ).to_dict()
    return success_result(
        command=MATH_REGISTER_METHOD_IMPLEMENTATION,
        data={"method_implementation_manifest": manifest_payload},
        artifacts={
            "method_implementation_manifest": manifest_ref,
        },
        warnings=warnings,
    )


def _method_contract(
    method_id: str,
    method_contract: Mapping[str, Any] | None,
    method_card_ids: Sequence[str],
    constructor_kwargs: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if method_contract:
        payload = dict(method_contract)
    else:
        payload = {"method_id": method_id, "parameters": _registry_parameters(method_id, constructor_kwargs), "no_lookahead": True}
    refs = payload.get("knowledge_evidence_refs") or [{"method_card_id": method_card_id} for method_card_id in method_card_ids]
    payload["knowledge_evidence_refs"] = list(refs) if not isinstance(refs, Mapping) else [dict(refs)]
    return payload


def _registry_parameters(method_id: str, constructor_kwargs: Mapping[str, Any] | None) -> Mapping[str, Any]:
    kwargs = dict(constructor_kwargs or {})
    if method_id in {"sma", "ema", "rsi"}:
        return {"period": int(kwargs.get("period", 3 if method_id != "rsi" else 5))}
    if method_id == "rolling_volatility":
        return {"window": int(kwargs.get("window", kwargs.get("window_size", 3))), "ddof": int(kwargs.get("ddof", 1))}
    if method_id == "z_score":
        return {"window": int(kwargs.get("window", kwargs.get("window_size", 3)))}
    if method_id == "bollinger_wma_band_rule":
        return {
            "period": int(kwargs.get("period", 3)),
            "stddev_multiplier": float(kwargs.get("stddev_multiplier", 2.0)),
        }
    if method_id == "bollinger_bwma_action_signal":
        return {
            "period": int(kwargs.get("period", 20)),
            "stddev_multiplier": float(kwargs.get("stddev_multiplier", 2.0)),
        }
    return {}


def _constructor_kwargs(
    method_id: str,
    method_contract: Mapping[str, Any],
    constructor_kwargs: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if constructor_kwargs:
        return dict(constructor_kwargs)
    parameters = mapping(method_contract.get("parameters"))
    if method_id in {"sma", "ema", "rsi"}:
        return {"period": int(parameters.get("period", 3 if method_id != "rsi" else 5))}
    if method_id == "rolling_volatility":
        return {"window_size": int(parameters.get("window", 3)), "ddof": int(parameters.get("ddof", 1))}
    if method_id == "z_score":
        return {"window_size": int(parameters.get("window", 3))}
    if method_id == "bollinger_wma_band_rule":
        return {
            "period": int(parameters.get("period", 3)),
            "stddev_multiplier": float(parameters.get("stddev_multiplier", 2.0)),
        }
    if method_id == "bollinger_bwma_action_signal":
        return {
            "period": int(parameters.get("period", 20)),
            "stddev_multiplier": float(parameters.get("stddev_multiplier", 2.0)),
        }
    return {}


def _source_provenance(
    path: Path,
    *,
    method_id: str,
    method_card_ids: Sequence[str],
    entrypoint: str,
    class_name: str | None,
    runtime_contract: str,
    require_method_cards: bool,
) -> tuple[Mapping[str, Any], list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return {}, [f"source syntax error: {exc}"]
    docstring = ast.get_docstring(tree, clean=True) or ""
    normalized = docstring.lower()
    blockers: list[str] = []
    required_terms = {
        "Source reference": "source reference",
        "Implements": "implements",
        "Trader runtime contract": runtime_contract.lower(),
        "warmup behavior": "warmup",
        "no-lookahead boundary": "lookahead",
    }
    for label, term in required_terms.items():
        if term not in normalized:
            blockers.append(f"module docstring missing {label}")
    if method_id.lower() not in normalized:
        blockers.append(f"module docstring missing registry method: {method_id}")
    declared_method_card_ids = sorted(set(re.findall(r"method_card_[A-Za-z0-9_]+", docstring)))
    if require_method_cards and not declared_method_card_ids:
        blockers.append("module docstring missing approved method-card reference")
    if require_method_cards:
        for method_card_id in method_card_ids:
            if method_card_id.lower() not in normalized:
                blockers.append(f"module docstring missing approved method-card ref: {method_card_id}")
    resolved_class_name = class_name or entrypoint.split(":")[-1]
    if resolved_class_name and resolved_class_name.lower() not in normalized:
        blockers.append(f"module docstring missing implementation class: {resolved_class_name}")
    return {
        "module_docstring": docstring,
        "required_method_id": method_id,
        "registered_method_card_ids": list(method_card_ids),
        "declared_method_card_ids": declared_method_card_ids,
        "exact_registered_method_card_ids_required": require_method_cards,
        "required_class_name": resolved_class_name,
        "validated": not blockers,
    }, sorted(set(blockers))


def _static_safety_blockers(path: Path, *, dependency_allowlist: Sequence[str]) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"source syntax error: {exc}"]
    allowed = set(dependency_allowlist)
    blockers: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _import_allowed(alias.name, allowed):
                    blockers.append(f"import is not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not _import_allowed(module, allowed):
                blockers.append(f"import is not allowed: {module}")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            blockers.append("global/nonlocal mutation is not allowed")
        elif isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in FORBIDDEN_CALLS:
                blockers.append(f"call is not allowed: {call_name}")
    return sorted(set(blockers))


def _import_allowed(module: str, allowed: set[str]) -> bool:
    return any(module == item or module.startswith(f"{item}.") for item in allowed)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _runtime_contract_for_entry(entry: Any) -> str:
    runtime_contract = str(getattr(entry, "runtime_contract", "") or "").strip()
    return runtime_contract or INDICATOR_RUNTIME_CONTRACT


def _runtime_contract_class(runtime_contract: str) -> type[Indicator] | type[Signal] | None:
    if runtime_contract == INDICATOR_RUNTIME_CONTRACT:
        return Indicator
    if runtime_contract == SIGNAL_RUNTIME_CONTRACT:
        return Signal
    return None


def _load_implementation_class(*, entrypoint: str, source_path: Path | None = None, class_name: str | None = None) -> type[Any]:
    if source_path is not None and source_path.exists() and class_name:
        module_name = f"_trader_generated_{hashlib.sha256(str(source_path).encode('utf-8')).hexdigest()[:12]}"
        spec = importlib.util.spec_from_file_location(module_name, source_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load source path: {source_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        loaded = getattr(module, class_name)
    else:
        if ":" not in entrypoint:
            raise ValueError("entrypoint must use module:ClassName format")
        module_name, object_name = entrypoint.split(":", 1)
        module = importlib.import_module(module_name)
        loaded = getattr(module, object_name)
    if not isinstance(loaded, type):
        raise TypeError("entrypoint is not a class")
    return loaded


def _source_path_for_entrypoint(entrypoint: str) -> Path | None:
    if ":" not in entrypoint:
        path_text, _, _class_name = entrypoint.rpartition(":")
        path = Path(path_text)
        return path.resolve() if path.exists() else None
    module_name, object_name = entrypoint.split(":", 1)
    try:
        module = importlib.import_module(module_name)
        loaded = getattr(module, object_name)
    except (ImportError, AttributeError):
        return None
    source = inspect.getsourcefile(loaded)
    return Path(source).resolve() if source else None
