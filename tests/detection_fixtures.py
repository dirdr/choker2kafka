from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sentinel.detection.domain import Contract, EventSample, Rule, WindowSnapshot

NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)


def contract(
    unit="milliseconds", version=1, effective_from=None, kind="timestamp_bounds"
):
    return Contract(
        contract_id="orders.checkout",
        version=version,
        topic="orders",
        owner="checkout-team",
        effective_from=effective_from or NOW - timedelta(days=1),
        rules=(
            Rule(
                rule_id="event-time-semantics",
                kind=kind,
                fields=("event_time",),
                parameters={
                    "unit": unit,
                    "max_age_seconds": 60,
                    "max_future_seconds": 5,
                },
            ),
        ),
    )


def sample(ingested_at, unit="milliseconds", revision=1, lag_seconds=0):
    units = {"milliseconds": 1000, "seconds": 1, "microseconds": 1_000_000}[unit]
    value = int((ingested_at.timestamp() - lag_seconds) * units)
    return EventSample(
        event_id=uuid4(),
        topic="orders",
        partition=0,
        kafka_offset=0,
        producer_id="checkout",
        code_version="test",
        config_revision=revision,
        event_time=value,
        kafka_timestamp_ms=int(ingested_at.timestamp() * 1000),
        kafka_timestamp_type="create_time",
        ingested_at=ingested_at,
        payload={"event_time": value},
    )


def snapshot(recent_unit="milliseconds", recent_count=100, baseline_count=100):
    baseline = [
        sample(NOW - timedelta(seconds=69) + timedelta(milliseconds=index * 100))
        for index in range(baseline_count)
    ]
    recent = [
        sample(
            NOW - timedelta(seconds=9) + timedelta(milliseconds=index * 80),
            recent_unit,
            2,
        )
        for index in range(recent_count)
    ]
    return WindowSnapshot(
        run_id=uuid4(),
        run_started_at=NOW - timedelta(minutes=5),
        evaluated_at=NOW,
        topic="orders",
        producer_id="checkout",
        last_received_at=NOW - timedelta(seconds=1),
        events=tuple(baseline + recent),
        contracts=(contract(),),
    )
