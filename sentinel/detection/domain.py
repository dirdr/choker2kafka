from datetime import timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from sentinel.stream.domain import TimestampUnit


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Rule(FrozenModel):
    rule_id: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=100)
    fields: tuple[str, ...] = Field(min_length=1, max_length=20)
    parameters: dict[str, Any]


class Contract(FrozenModel):
    contract_id: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1, strict=True)
    topic: str = Field(min_length=1, max_length=249)
    owner: str
    effective_from: AwareDatetime
    rules: tuple[Rule, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_rules(self):
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("Contract rule IDs must be unique")
        return self


class TimestampBounds(FrozenModel):
    unit: TimestampUnit
    max_age_seconds: int = Field(default=60, ge=0, le=86400, strict=True)
    max_future_seconds: int = Field(default=5, ge=0, le=3600, strict=True)


class EventSample(FrozenModel):
    event_id: UUID
    topic: str
    partition: int
    kafka_offset: int
    producer_id: str
    code_version: str
    config_revision: int
    event_time: int
    kafka_timestamp_ms: int | None
    kafka_timestamp_type: str
    ingested_at: AwareDatetime
    payload: dict[str, Any]


class WindowSnapshot(FrozenModel):
    run_id: UUID
    run_started_at: AwareDatetime
    evaluated_at: AwareDatetime
    topic: str
    producer_id: str
    last_received_at: AwareDatetime | None
    events: tuple[EventSample, ...]
    contracts: tuple[Contract, ...]
    overflow: bool = False

    @property
    def recent_start(self):
        return self.evaluated_at - timedelta(seconds=10)

    @property
    def baseline_start(self):
        return self.evaluated_at - timedelta(seconds=70)


class Signal(FrozenModel):
    signal_id: UUID = Field(default_factory=uuid4)
    rule_id: str
    kind: str
    topic: str
    producer_id: str
    run_id: UUID
    affected_fields: tuple[str, ...]
    contract_id: str
    contract_version: int
    window_start: AwareDatetime
    window_end: AwareDatetime
    observed: dict[str, Any]
    expected: dict[str, Any]
    evidence_ids: tuple[str, ...]


class CheckResult(FrozenModel):
    contract_id: str
    contract_version: int
    rule_id: str
    kind: str
    status: Literal[
        "healthy",
        "violated",
        "warming_up",
        "stale",
        "missing_contract",
        "unsupported_rule",
        "invalid_contract",
        "evidence_limit",
    ]
    evaluated_at: AwareDatetime
    recent_samples: int = 0
    baseline_samples: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)
    signal: Signal | None = None


def applicable_contract(
    contracts: tuple[Contract, ...], contract_id: str, at: AwareDatetime
) -> Contract | None:
    candidates = [
        contract
        for contract in contracts
        if contract.contract_id == contract_id and contract.effective_from <= at
    ]
    return max(candidates, key=lambda contract: contract.effective_from, default=None)
