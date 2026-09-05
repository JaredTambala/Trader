"""Lazy local MLflow ``python_function`` inference adapter."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from datetime import datetime
import importlib.metadata
import importlib.util
from time import perf_counter
from typing import Any, Mapping, Sequence

from trader.predictions import (
    FeatureBatch,
    FeatureColumn,
    FeatureRow,
    InferenceAdapterProfile,
    ModelIdentity,
    PredictionBatch,
    PredictionObservation,
    PredictionRequest,
    Predictor,
    canonical_json_hash,
)


class MLflowLocalPyfuncAdapter:
    """Resolve an immutable MLflow model version into one local predictor."""

    adapter_version = "1"

    def __init__(self, *, profile_name: str, tracking_uri: str) -> None:
        if not str(profile_name).strip() or not str(tracking_uri).strip():
            raise ValueError("MLflow profile_name and tracking_uri are required")
        self._profile_name = str(profile_name).strip()
        self._tracking_uri = str(tracking_uri).strip()

    def profile(self) -> InferenceAdapterProfile:
        """Return provider metadata without importing optional runtime packages."""
        available = (
            importlib.util.find_spec("mlflow") is not None
            and importlib.util.find_spec("pandas") is not None
        )
        try:
            provider_version = (
                importlib.metadata.version("mlflow") if available else "unavailable"
            )
        except importlib.metadata.PackageNotFoundError:
            provider_version = "unavailable"
            available = False
        configuration_digest = (
            f"sha256:{canonical_json_hash({'tracking_uri': self._tracking_uri})}"
        )
        return InferenceAdapterProfile(
            profile_name=self._profile_name,
            provider="mlflow",
            adapter_version=f"{self.adapter_version}+mlflow-{provider_version}",
            configuration_digest=configuration_digest,
            capabilities=("local_model", "python_function", "pinned_model_version"),
            available=available,
            reason=None if available else "MLflow and pandas are not installed",
        )

    def validate_deployment(
        self, manifest: Mapping[str, object]
    ) -> Mapping[str, object]:
        """Load the pinned model and compare actual outputs with the parity fixture."""
        predictor = self.build_predictor(manifest)
        feature_batch = _parity_feature_batch(manifest)
        output_names = tuple(
            str(item["name"])
            for item in _sequence_of_mappings(manifest["output_contract"])
        )
        policy = _mapping(manifest["inference_policy"], "inference_policy")
        batch = predictor.predict(
            PredictionRequest(
                run_id="deployment_validation",
                cycle_id=str(manifest["deployment_id"]),
                feature_batch=feature_batch,
                requested_outputs=output_names,
                timeout_ms=int(policy["timeout_ms"]),
            )
        )
        fixture = _mapping(manifest["parity_fixture"], "parity_fixture")
        actual = [item.to_dict() for item in batch.observations]
        actual_digest = f"sha256:{canonical_json_hash(actual)}"
        expected_digest = str(fixture["expected_outputs_digest"])
        if batch.status != "success":
            return {
                "status": "blocked",
                "blocker": batch.error or batch.status,
                "latency_ms": batch.latency_ms,
            }
        if actual_digest != expected_digest:
            return {
                "status": "blocked",
                "blocker": "MLflow parity fixture output mismatch",
                "expected_outputs_digest": expected_digest,
                "actual_outputs_digest": actual_digest,
                "latency_ms": batch.latency_ms,
            }
        return {
            "status": "passed",
            "expected_outputs_digest": expected_digest,
            "actual_outputs_digest": actual_digest,
            "latency_ms": batch.latency_ms,
        }

    def build_predictor(self, manifest: Mapping[str, object]) -> Predictor:
        """Load one pinned model; optional imports occur only at this boundary."""
        profile = self.profile()
        if not profile.available:
            raise RuntimeError(
                profile.reason or "MLflow inference adapter is unavailable"
            )
        import mlflow
        import pandas as pd  # type: ignore[import-untyped]

        model_payload = _mapping(
            _mapping(manifest["model_version"], "model_version")["payload"],
            "model_version payload",
        )
        mlflow.set_tracking_uri(self._tracking_uri)
        model = mlflow.pyfunc.load_model(str(model_payload["model_uri"]))
        return MLflowPyfuncPredictor(
            model=model,
            dataframe_factory=pd.DataFrame,
            identity=_model_identity(model_payload, profile),
            output_contract=_sequence_of_mappings(manifest["output_contract"]),
        )


class MLflowPyfuncPredictor:
    """Provider-neutral predictor over one already-loaded pyfunc model."""

    def __init__(
        self,
        *,
        model: object,
        dataframe_factory: Any,
        identity: ModelIdentity,
        output_contract: Sequence[Mapping[str, Any]],
    ) -> None:
        self._model = model
        self._dataframe_factory = dataframe_factory
        self.identity = identity
        self._output_contract = tuple(dict(item) for item in output_contract)

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        """Run local inference and normalize supported pyfunc output shapes."""
        rows = [
            [row.values[column.name] for column in request.feature_batch.schema]
            for row in request.feature_batch.rows
        ]
        frame = self._dataframe_factory(
            rows,
            columns=[column.name for column in request.feature_batch.schema],
        )
        started = perf_counter()
        try:
            raw = self._model.predict(frame)  # type: ignore[attr-defined]
            records = _prediction_records(raw, len(rows), request.requested_outputs)
            observations = _observations(
                records,
                request.feature_batch.symbols,
                self._output_contract,
                request.requested_outputs,
            )
            latency_ms = (perf_counter() - started) * 1000.0
            if latency_ms > request.timeout_ms:
                return _failed_batch(
                    self.identity,
                    request,
                    "timeout",
                    latency_ms,
                    "inference timeout exceeded",
                )
            return PredictionBatch(
                model_identity=self.identity,
                feature_batch_hash=request.feature_batch.input_hash,
                decision_ts=request.feature_batch.decision_ts,
                observations=observations,
                status="success",
                latency_ms=latency_ms,
                coverage={
                    "requested_rows": len(rows),
                    "returned_rows": len(records),
                    "requested_symbols": list(request.feature_batch.symbols),
                },
            )
        except Exception as exc:
            latency_ms = (perf_counter() - started) * 1000.0
            return _failed_batch(self.identity, request, "error", latency_ms, str(exc))


def _parity_feature_batch(manifest: Mapping[str, object]) -> FeatureBatch:
    feature_payload = _mapping(
        _mapping(manifest["feature_set"], "feature_set")["payload"],
        "feature_set payload",
    )
    fixture = _mapping(manifest["parity_fixture"], "parity_fixture")
    schema = tuple(
        FeatureColumn(
            name=str(item["name"]),
            dtype=str(item["dtype"]),
            nullable=bool(item.get("nullable", False)),
        )
        for item in _sequence_of_mappings(feature_payload["schema"])
    )
    rows = tuple(
        FeatureRow(
            symbol=str(item.get("symbol") or "") or None,
            as_of_ts=datetime.fromisoformat(str(item["as_of_ts"])),
            availability_ts=datetime.fromisoformat(str(item["availability_ts"])),
            values=_mapping(item["values"], "parity row values"),
        )
        for item in _sequence_of_mappings(fixture["rows"])
    )
    return FeatureBatch.build(
        feature_set_id=str(feature_payload["feature_set_id"]),
        feature_set_digest=str(feature_payload["feature_set_digest"]),
        decision_ts=datetime.fromisoformat(str(fixture["decision_ts"])),
        schema=schema,
        rows=rows,
    )


def _model_identity(
    model: Mapping[str, Any], profile: InferenceAdapterProfile
) -> ModelIdentity:
    return ModelIdentity(
        registered_model_name=str(model["registered_model_name"]),
        model_version=str(model["model_version"]),
        model_version_id=str(model["model_version_id"]),
        model_digest=str(model["model_digest"]),
        signature_digest=str(model["signature_digest"]),
        source_run_id=str(model["source_run_id"]),
        adapter_profile=profile.profile_name,
        adapter_version=profile.adapter_version,
    )


def _prediction_records(
    raw: object, row_count: int, output_names: Sequence[str]
) -> list[dict[str, object]]:
    records: object
    if hasattr(raw, "to_dict"):
        try:
            records = raw.to_dict(orient="records")
        except TypeError:
            records = raw.to_dict()
    elif hasattr(raw, "tolist"):
        records = raw.tolist()
    else:
        records = raw
    if isinstance(records, MappingABC):
        records = _records_from_columns(records, row_count)
    if not isinstance(records, SequenceABC) or isinstance(records, (str, bytes)):
        records = [records]
    sequence = list(records)
    if sequence and not isinstance(sequence[0], (MappingABC, SequenceABC)):
        if len(output_names) != 1:
            raise ValueError(
                "scalar prediction output requires exactly one requested output"
            )
        sequence = [{output_names[0]: value} for value in sequence]
    normalized: list[dict[str, object]] = []
    for item in sequence:
        if isinstance(item, MappingABC):
            normalized.append({str(key): value for key, value in item.items()})
            continue
        if isinstance(item, SequenceABC) and not isinstance(item, (str, bytes)):
            values = list(item)
            if len(values) != len(output_names):
                raise ValueError(
                    "prediction output width does not match requested outputs"
                )
            normalized.append(dict(zip(output_names, values, strict=True)))
            continue
        raise ValueError("unsupported MLflow prediction output shape")
    if len(normalized) != row_count:
        raise ValueError("prediction output row count does not match feature rows")
    return normalized


def _records_from_columns(
    value: Mapping[object, object], row_count: int
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [dict() for _ in range(row_count)]
    for raw_name, raw_values in value.items():
        name = str(raw_name)
        if isinstance(raw_values, MappingABC):
            values = list(raw_values.values())
        elif isinstance(raw_values, SequenceABC) and not isinstance(
            raw_values, (str, bytes)
        ):
            values = list(raw_values)
        else:
            values = [raw_values]
        if len(values) != row_count:
            raise ValueError(
                "prediction output column length does not match feature rows"
            )
        for index, item in enumerate(values):
            rows[index][name] = item
    return rows


def _observations(
    records: Sequence[Mapping[str, object]],
    symbols: Sequence[str],
    output_contract: Sequence[Mapping[str, Any]],
    requested_outputs: Sequence[str],
) -> tuple[PredictionObservation, ...]:
    contract_by_name = {str(item["name"]): item for item in output_contract}
    observations: list[PredictionObservation] = []
    for index, record in enumerate(records):
        for output_name in requested_outputs:
            if output_name not in record:
                raise ValueError(f"prediction output is missing {output_name}")
            contract = contract_by_name[output_name]
            observations.append(
                PredictionObservation(
                    output_name=output_name,
                    semantics=str(contract["semantics"]),
                    value=record[output_name],
                    horizon=str(contract["horizon"]),
                    symbol=symbols[index] if symbols else None,
                    units=str(contract.get("units") or "") or None,
                )
            )
    return tuple(observations)


def _failed_batch(
    identity: ModelIdentity,
    request: PredictionRequest,
    status: str,
    latency_ms: float,
    error: str,
) -> PredictionBatch:
    return PredictionBatch(
        model_identity=identity,
        feature_batch_hash=request.feature_batch.input_hash,
        decision_ts=request.feature_batch.decision_ts,
        observations=(),
        status=status,
        latency_ms=latency_ms,
        coverage={
            "requested_rows": len(request.feature_batch.rows),
            "returned_rows": 0,
        },
        error=error,
    )


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{label} must be a mapping")
    return {str(key): inner for key, inner in value.items()}


def _sequence_of_mappings(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)):
        raise ValueError("value must be a sequence of mappings")
    return tuple(_mapping(item, "sequence item") for item in value)
