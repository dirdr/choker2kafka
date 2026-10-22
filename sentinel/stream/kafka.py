from datetime import UTC, datetime

from confluent_kafka import (
    Consumer,
    KafkaError,
    KafkaException,
    Producer,
    TopicPartition,
)
from confluent_kafka.admin import AdminClient, NewTopic

from sentinel.connections import kafka_configuration
from sentinel.stream.domain import OrderEvent, StreamRecord


class KafkaStream:
    def __init__(self, topic: str, group_id: str):
        self.topic = topic
        self.group_id = group_id
        self.producer = None
        self.consumer = None

    def open(self) -> None:
        configuration = kafka_configuration()
        admin = AdminClient(configuration)
        metadata = admin.list_topics(timeout=5)
        if self.topic not in metadata.topics:
            future = admin.create_topics(
                [NewTopic(self.topic, num_partitions=1, replication_factor=-1)],
                request_timeout=5,
                operation_timeout=5,
            )[self.topic]
            try:
                future.result(timeout=10)
            except KafkaException as error:
                if error.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                    raise
        elif metadata.topics[self.topic].error:
            raise KafkaException(metadata.topics[self.topic].error)
        self.producer = Producer(
            {
                **configuration,
                "enable.idempotence": True,
                "delivery.timeout.ms": 10000,
                "request.timeout.ms": 5000,
            }
        )
        self.consumer = Consumer(
            {
                **configuration,
                "group.id": self.group_id,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
                "allow.auto.create.topics": False,
            }
        )
        self.consumer.subscribe([self.topic])

    def publish(self, events: list[OrderEvent]) -> None:
        errors = []

        def delivered(error, message):
            if error is not None:
                errors.append(error)

        for event in events:
            self.producer.produce(
                self.topic,
                key=event.producer_id,
                value=event.model_dump_json().encode(),
                on_delivery=delivered,
            )
        pending = self.producer.flush(timeout=10)
        if errors:
            raise KafkaException(errors[0])
        if pending:
            raise TimeoutError("Kafka delivery deadline exceeded")

    def receive(self) -> list[StreamRecord]:
        records = []
        for message in self.consumer.consume(num_messages=100, timeout=0.2):
            if error := message.error():
                if error.code() == KafkaError._PARTITION_EOF:
                    continue
                raise KafkaException(error)
            timestamp_type, timestamp_ms = message.timestamp()
            records.append(
                StreamRecord(
                    topic=message.topic(),
                    partition=message.partition(),
                    offset=message.offset(),
                    kafka_timestamp_ms=timestamp_ms if timestamp_ms >= 0 else None,
                    kafka_timestamp_type={
                        0: "unavailable",
                        1: "create_time",
                        2: "log_append_time",
                    }.get(timestamp_type, "unavailable"),
                    payload=message.value(),
                    ingested_at=datetime.now(UTC),
                )
            )
        return records

    def acknowledge(self, records: list[StreamRecord]) -> None:
        offsets = {}
        for record in records:
            key = (record.topic, record.partition)
            offsets[key] = max(offsets.get(key, 0), record.offset + 1)
        if not offsets:
            return
        committed = self.consumer.commit(
            offsets=[
                TopicPartition(topic, partition, offset)
                for (topic, partition), offset in offsets.items()
            ],
            asynchronous=False,
        )
        for partition in committed:
            if partition.error:
                raise KafkaException(partition.error)

    def close(self) -> None:
        try:
            if self.consumer is not None:
                self.consumer.close()
        finally:
            self.consumer = None
            if self.producer is not None:
                self.producer.purge()
                self.producer.poll(0)
                self.producer = None
