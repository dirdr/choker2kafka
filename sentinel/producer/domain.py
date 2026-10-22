import base64
import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from sentinel.stream.domain import TimestampUnit

CONFIG_PATH = "producer/config.json"


class ProducerFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    producer_id: str = Field(pattern=r"^checkout$")
    event_time_unit: TimestampUnit

    def contents(self) -> bytes:
        return (json.dumps(self.model_dump(mode="json"), indent=2) + "\n").encode()


@dataclass(frozen=True)
class SourceFile:
    configuration: ProducerFile
    file_sha: str
    commit_sha: str | None
    repository: str | None
    branch: str | None

    @classmethod
    def local(cls, content: bytes):
        return cls(
            ProducerFile.model_validate_json(content),
            hashlib.sha256(content).hexdigest(),
            None,
            None,
            None,
        )

    @classmethod
    def github(cls, response: dict, commit: str, repository: str, branch: str):
        if (
            response.get("type") != "file"
            or response.get("path") != CONFIG_PATH
            or response.get("size", 0) > 10000
        ):
            raise ValueError("Unsupported producer source")
        content = base64.b64decode(response["content"], validate=False)
        return cls(
            ProducerFile.model_validate_json(content),
            response["sha"],
            commit,
            repository,
            branch,
        )
