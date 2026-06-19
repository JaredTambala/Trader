from __future__ import annotations

from pathlib import Path

from trader_research.math_tools import (
    math_generate_python_method,
    math_list_method_contracts,
    math_register_method_implementation,
    math_run_indicator_fixtures,
    math_run_signal_fixtures,
    math_validate_method_contract,
)
from trader_research.knowledge.domain import MethodCard
from trader_research.knowledge.store import JsonKnowledgeStore
from trader_research.math_domain import MethodRegistryEntry, ParameterSpec
from trader.signals import Signal
from trader_standard.signals import BollingerBwmaActionSignal


METHODS = {
    "sma": ("method_card_sma_seed_v1", {"period": 3}),
    "ema": ("method_card_ema_seed_v1", {"period": 3}),
    "rsi": ("method_card_rsi_seed_v1", {"period": 5}),
    "rolling_volatility": ("method_card_rolling_volatility_seed_v1", {"window": 3, "ddof": 1}),
    "z_score": ("method_card_z_score_seed_v1", {"window": 3}),
}


def test_register_and_validate_initial_indicator_implementations(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"

    for method_id, (method_card_id, parameters) in METHODS.items():
        registered = math_register_method_implementation(
            artifact_root=artifact_root,
            method_id=method_id,
            method_card_ids=[method_card_id],
            method_contract=_contract(method_id, parameters, method_card_id),
        )

        assert registered.ok is True, registered.to_dict()
        manifest = registered.data["method_implementation_manifest"]
        assert manifest["method_id"] == method_id
        assert manifest["status"] == "registered"
        assert manifest["source_hash"]
        assert manifest["source_provenance"]["validated"] is True
        assert method_card_id in manifest["source_provenance"]["module_docstring"]

        validated = math_run_indicator_fixtures(
            artifact_root=artifact_root,
            implementation_manifest=manifest,
        )

        assert validated.ok is True, validated.to_dict()
        report = validated.data["indicator_validation_report"]
        assert report["status"] == "passed"
        assert report["fixture_count"] >= 1
        assert validated.data["method_implementation_manifest"]["status"] == "validated"


def test_register_and_validate_bollinger_from_persisted_method_card(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    method_card_id = "method_card_bollinger_wma_band_rule_algorithmic_trading_v1"
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_card(
        MethodCard(
            method_card_id=method_card_id,
            method_id="bollinger_wma_band_rule",
            title="Bollinger WMA band rule",
            family="indicator",
            status="approved",
            assumptions=(
                "input observations are ordered",
                "period and multiplier are fixed before evaluation",
            ),
            inputs=("price series",),
            outputs=("middle band", "upper band", "lower band", "bandwidth"),
            failure_modes=("insufficient warmup observations", "zero center band for bandwidth"),
            approved_by="test",
            approval_note="Approved for fixture validation test.",
        )
    )

    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="bollinger_wma_band_rule",
        method_card_ids=[method_card_id],
        method_contract=_contract(
            "bollinger_wma_band_rule",
            {"period": 3, "stddev_multiplier": 2.0},
            method_card_id,
        ),
        knowledge_store=store,
    )

    assert registered.ok is True, registered.to_dict()
    manifest = registered.data["method_implementation_manifest"]
    assert manifest["method_id"] == "bollinger_wma_band_rule"
    assert manifest["source_provenance"]["validated"] is True
    assert method_card_id in manifest["source_provenance"]["module_docstring"]

    validated = math_run_indicator_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=manifest,
        knowledge_store=store,
    )

    assert validated.ok is True, validated.to_dict()
    report = validated.data["indicator_validation_report"]
    assert report["status"] == "passed"
    assert report["fixture_results"][0]["actual"][2]["middle"] == 2.0
    assert validated.data["method_implementation_manifest"]["status"] == "validated"


def test_math_tools_use_persisted_method_contracts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_contract(
        MethodRegistryEntry(
            method_id="db_only_indicator",
            family="indicator",
            status="approved",
            purpose="Validate that method contracts are loaded from the knowledge store.",
            parameters=(ParameterSpec("period", "int", min_value=2, max_value=20),),
            inputs=("price series",),
            outputs=("derived series",),
            assumptions=("observations are ordered",),
            failure_modes=("insufficient warmup observations",),
            artifact_outputs=("indicator_validation_report.json",),
            warmup="period - 1 observations",
            nan_policy="propagate",
            no_lookahead=True,
        )
    )

    listed = math_list_method_contracts(knowledge_store=store)
    valid = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={"method_id": "db_only_indicator", "parameters": {"period": 5}, "no_lookahead": True},
        knowledge_store=store,
    )
    missing = math_validate_method_contract(
        artifact_root=artifact_root,
        method_contract={"method_id": "db_only_indicator", "parameters": {"period": 1}, "no_lookahead": True},
        knowledge_store=store,
    )

    assert listed.ok is True
    assert [method["method_id"] for method in listed.data["methods"]] == ["db_only_indicator"]
    assert valid.ok is True, valid.to_dict()
    assert valid.data["method"]["method_id"] == "db_only_indicator"
    assert missing.ok is False
    assert missing.data["method_validation_report"]["blockers"] == ["parameter period is below minimum 2.0"]


def test_register_and_validate_bollinger_action_signal_from_persisted_method_card(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    method_card_id = "method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_card(
        MethodCard(
            method_card_id=method_card_id,
            method_id="bollinger_bwma_action_signal",
            title="Bollinger BWMA action signal",
            family="signal",
            status="approved",
            assumptions=(
                "input bars are ordered latest first",
                "period and multiplier are fixed before evaluation",
            ),
            inputs=("latest-first OHLCV bar window",),
            outputs=("scalar action signal: +1 buy, -1 sell, 0 no action",),
            failure_modes=("insufficient warmup observations", "non-finite input values"),
            approved_by="test",
            approval_note="Approved for signal fixture validation test.",
        )
    )
    store.save_method_contract(_signal_contract_entry(method_card_id))

    signal = BollingerBwmaActionSignal(period=20, stddev_multiplier=2.0)
    assert isinstance(signal, Signal)

    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="bollinger_bwma_action_signal",
        method_card_ids=[method_card_id],
        method_contract=_contract(
            "bollinger_bwma_action_signal",
            {"period": 20, "stddev_multiplier": 2.0},
            method_card_id,
        ),
        knowledge_store=store,
    )

    assert registered.ok is True, registered.to_dict()
    manifest = registered.data["method_implementation_manifest"]
    assert manifest["runtime_contract"] == "trader.signals.Signal"
    assert manifest["method_id"] == "bollinger_bwma_action_signal"
    assert manifest["source_provenance"]["validated"] is True
    assert method_card_id in manifest["source_provenance"]["module_docstring"]

    validated = math_run_signal_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=manifest,
        knowledge_store=store,
    )

    assert validated.ok is True, validated.to_dict()
    report = validated.data["signal_implementation_validation_report"]
    assert report["status"] == "passed"
    assert [result["actual"] for result in report["fixture_results"]] == [1.0, -1.0, 0.0]
    assert validated.data["method_implementation_manifest"]["status"] == "validated"


def test_signal_fixtures_fail_on_insufficient_bars(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    method_card_id = "method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_card(
        MethodCard(
            method_card_id=method_card_id,
            method_id="bollinger_bwma_action_signal",
            title="Bollinger BWMA action signal",
            family="signal",
            status="approved",
            assumptions=("input bars are ordered latest first",),
            inputs=("latest-first OHLCV bar window",),
            outputs=("scalar action signal",),
            failure_modes=("insufficient warmup observations",),
            approved_by="test",
            approval_note="Approved for signal fixture validation test.",
        )
    )
    store.save_method_contract(_signal_contract_entry(method_card_id))
    registered = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="bollinger_bwma_action_signal",
        method_card_ids=[method_card_id],
        method_contract=_contract(
            "bollinger_bwma_action_signal",
            {"period": 20, "stddev_multiplier": 2.0},
            method_card_id,
        ),
        knowledge_store=store,
    )

    result = math_run_signal_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=registered.data["method_implementation_manifest"],
        fixtures=[
            {
                "fixture_id": "bollinger_bwma_insufficient_bars",
                "closes": [10.0] * 19,
                "expected": 0.0,
            }
        ],
        knowledge_store=store,
    )

    assert result.ok is False
    assert result.data["signal_implementation_validation_report"]["status"] == "failed"
    assert result.data["signal_implementation_validation_report"]["fixture_results"][0]["status"] == "failed"


def test_register_rejects_runtime_contract_mismatch(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    signal_card_id = "method_card_bollinger_bwma_action_signal_algorithmic_trading_v1"
    indicator_card_id = "method_card_sma_seed_v1"
    store = JsonKnowledgeStore(artifact_root)
    store.save_method_card(
        MethodCard(
            method_card_id=signal_card_id,
            method_id="bollinger_bwma_action_signal",
            title="Bollinger BWMA action signal",
            family="signal",
            status="approved",
            assumptions=("input bars are ordered latest first",),
            inputs=("bars",),
            outputs=("signal",),
            failure_modes=("warmup",),
        )
    )
    store.save_method_contract(_signal_contract_entry(signal_card_id))

    indicator_for_signal = _write_temp_source(
        tmp_path / "indicator_for_signal.py",
        '''"""Citation-backed Bollinger/BWMA action signal implementation.

Source reference:
- Approved method card: ``method_card_bollinger_bwma_action_signal_algorithmic_trading_v1``.
- Registry method: ``bollinger_bwma_action_signal``.

Implements:
- Entrypoint ``IndicatorForSignal``.
- Trader runtime contract ``trader.signals.Signal``.
- Warmup behavior and output ordering are declared for registration tests.
- No-lookahead boundary: every output uses only the supplied window.
"""

from trader.indicators import Indicator


class IndicatorForSignal(Indicator):
    @property
    def name(self):
        return "indicator_for_signal"

    @property
    def window(self):
        return 2

    def compute_series(self, bars):
        return [0.0]
''',
    )
    signal_for_indicator = _write_temp_source(
        tmp_path / "signal_for_indicator.py",
        '''"""Citation-backed simple moving average implementation.

Source reference:
- Approved method card: ``method_card_sma_seed_v1``.
- Registry method: ``sma``.

Implements:
- Entrypoint ``SignalForIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Warmup behavior and output ordering are declared for registration tests.
- No-lookahead boundary: every output uses only the supplied window.
"""

from trader.signals import Signal


class SignalForIndicator(Signal):
    @property
    def name(self):
        return "signal_for_indicator"

    @property
    def window(self):
        return 2

    def compute(self, bars):
        return 0.0
''',
    )

    signal_result = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="bollinger_bwma_action_signal",
        method_card_ids=[signal_card_id],
        method_contract=_contract("bollinger_bwma_action_signal", {"period": 20, "stddev_multiplier": 2.0}, signal_card_id),
        entrypoint=f"{indicator_for_signal}:IndicatorForSignal",
        source_path=str(indicator_for_signal),
        class_name="IndicatorForSignal",
        implementation_kind="generated",
        knowledge_store=store,
    )
    indicator_result = math_register_method_implementation(
        artifact_root=artifact_root,
        method_id="sma",
        method_card_ids=[indicator_card_id],
        method_contract=_contract("sma", {"period": 3}, indicator_card_id),
        entrypoint=f"{signal_for_indicator}:SignalForIndicator",
        source_path=str(signal_for_indicator),
        class_name="SignalForIndicator",
        implementation_kind="generated",
    )

    assert signal_result.ok is False
    assert "entrypoint is not a trader.signals.Signal subclass" in signal_result.data["blockers"]
    assert indicator_result.ok is False
    assert "entrypoint is not a trader.indicators.Indicator subclass" in indicator_result.data["blockers"]


def test_register_rejects_non_indicator_entrypoint(tmp_path: Path) -> None:
    source_path = tmp_path / "plain.py"
    source_path.write_text(
        '''"""Citation-backed simple moving average implementation.

Source reference:
- Approved method card: ``method_card_sma_seed_v1``.
- Registry method: ``sma``.

Implements:
- Entrypoint ``PlainImplementation``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Warmup behavior and output ordering are declared for registration tests.
- No lookahead: every output uses only the trailing window.
"""


class PlainImplementation:
    pass
''',
        encoding="utf-8",
    )

    result = math_register_method_implementation(
        artifact_root=tmp_path / "artifacts",
        method_id="sma",
        method_card_ids=["method_card_sma_seed_v1"],
        method_contract=_contract("sma", {"period": 3}, "method_card_sma_seed_v1"),
        entrypoint=f"{source_path}:PlainImplementation",
        source_path=str(source_path),
        class_name="PlainImplementation",
        implementation_kind="generated",
    )

    assert result.ok is False
    assert "entrypoint is not a trader.indicators.Indicator subclass" in result.data["blockers"]


def test_register_rejects_missing_provenance_docstring(tmp_path: Path) -> None:
    source_path = tmp_path / "undocumented.py"
    source_path.write_text(
        "from trader.indicators import Indicator\n\nclass UndocumentedIndicator(Indicator):\n    pass\n",
        encoding="utf-8",
    )

    result = math_register_method_implementation(
        artifact_root=tmp_path / "artifacts",
        method_id="sma",
        method_card_ids=["method_card_sma_seed_v1"],
        method_contract=_contract("sma", {"period": 3}, "method_card_sma_seed_v1"),
        entrypoint=f"{source_path}:UndocumentedIndicator",
        source_path=str(source_path),
        class_name="UndocumentedIndicator",
        implementation_kind="generated",
    )

    assert result.ok is False
    assert "module docstring missing Source reference" in result.data["blockers"]
    assert "module docstring missing approved method-card ref: method_card_sma_seed_v1" in result.data["blockers"]


def test_register_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    result = math_register_method_implementation(
        artifact_root=tmp_path / "artifacts",
        method_id="sma",
        method_card_ids=["method_card_sma_seed_v1"],
        method_contract=_contract("sma", {"period": 3}, "method_card_sma_seed_v1"),
        expected_source_hash="not-the-real-hash",
    )

    assert result.ok is False
    assert "source hash does not match expected_source_hash" in result.data["blockers"]


def test_register_rejects_unknown_method_card(tmp_path: Path) -> None:
    result = math_register_method_implementation(
        artifact_root=tmp_path / "artifacts",
        method_id="sma",
        method_card_ids=["method_card_missing"],
        method_contract=_contract("sma", {"period": 3}, "method_card_missing"),
    )

    assert result.ok is False
    assert "approved method-card evidence does not match the requested method" in result.data["blockers"]


def test_generated_python_method_is_quarantined_and_validated(tmp_path: Path) -> None:
    result = math_generate_python_method(
        artifact_root=tmp_path / "artifacts",
        method_id="sma",
        method_card_ids=["method_card_sma_seed_v1"],
        method_contract=_contract("sma", {"period": 3}, "method_card_sma_seed_v1"),
        llm_payload={
            "class_name": "GeneratedSmaIndicator",
            "source_code": GENERATED_SMA_SOURCE,
        },
    )

    assert result.ok is True, result.to_dict()
    source_path = Path(result.data["generated_source_path"])
    assert "method_implementations/quarantine" in source_path.as_posix()
    assert "/src/" not in source_path.as_posix()
    assert result.data["status"] == "validated"
    manifest = result.data["registration"]["method_implementation_manifest"]
    assert manifest["source_provenance"]["validated"] is True
    assert result.data["fixture_validation"]["indicator_validation_report"]["status"] == "passed"


def test_generated_python_method_rejects_unsafe_source(tmp_path: Path) -> None:
    result = math_generate_python_method(
        artifact_root=tmp_path / "artifacts",
        method_id="sma",
        method_card_ids=["method_card_sma_seed_v1"],
        method_contract=_contract("sma", {"period": 3}, "method_card_sma_seed_v1"),
        llm_payload={
            "class_name": "BadIndicator",
            "source_code": "import os\nfrom trader.indicators import Indicator\nclass BadIndicator(Indicator):\n    pass\n",
        },
    )

    assert result.ok is False
    assert result.errors[0]["code"] == "generated_method_safety_failed"
    source_path = Path(result.data["generated_source_path"])
    assert "method_implementations/quarantine" in source_path.as_posix()
    assert "/src/" not in source_path.as_posix()


def _contract(method_id: str, parameters: dict[str, object], method_card_id: str) -> dict[str, object]:
    return {
        "method_id": method_id,
        "parameters": parameters,
        "no_lookahead": True,
        "knowledge_evidence_refs": [{"method_card_id": method_card_id}],
    }


def _signal_contract_entry(method_card_id: str) -> MethodRegistryEntry:
    return MethodRegistryEntry(
        method_id="bollinger_bwma_action_signal",
        family="signal",
        status="approved",
        purpose="Emit a scalar Bollinger/BWMA band action signal from a fixed trailing price window.",
        parameters=(
            ParameterSpec("period", "int", min_value=2, max_value=500, default=20),
            ParameterSpec("stddev_multiplier", "float", min_value=0, max_value=10, default=2.0),
        ),
        inputs=("latest-first OHLCV bar window",),
        outputs=("scalar action signal: +1 buy, -1 sell, 0 no action",),
        assumptions=("input bars are ordered latest first",),
        failure_modes=("insufficient warmup observations",),
        artifact_outputs=("method_implementation_manifest.json", "signal_implementation_validation_report.json"),
        warmup="period observations",
        nan_policy="reject",
        no_lookahead=True,
        requires_evidence=True,
        approved_method_card_ids=(method_card_id,),
        runtime_contract="trader.signals.Signal",
    )


def _write_temp_source(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


GENERATED_SMA_SOURCE = '''"""Citation-backed simple moving average implementation.

Source reference:
- Approved method card: ``method_card_sma_seed_v1``.
- Registry method: ``sma``.

Implements:
- Entrypoint ``GeneratedSmaIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- For each completed trailing window of ``period`` close values, return the arithmetic mean.
- Outputs omit warmup observations and are latest-first.
- No lookahead: every output uses only close values inside its trailing window.
"""

from trader.indicators import Indicator


class GeneratedSmaIndicator(Indicator):
    def __init__(self, period: int = 3) -> None:
        self.period = int(period)

    @property
    def name(self) -> str:
        return "sma"

    @property
    def window(self) -> int:
        return self.period

    def compute_series(self, bars):
        closes = [float(bar.close) for bar in bars]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for SMA computation")
        values = []
        for idx in range(0, len(closes) - self.window + 1):
            values.append(sum(closes[idx : idx + self.window]) / self.window)
        return values
'''
