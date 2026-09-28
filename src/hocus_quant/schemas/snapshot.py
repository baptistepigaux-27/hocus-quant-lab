"""Gremlin snapshot envelope validation."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GremlinSnapshot(BaseModel):
    """Generic acquisition envelope; payload remains source-owned and uninterpreted."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    retrieved_at: datetime
    source_url: str
    content_type: str
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    payload: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: str | None = None
    records: list[dict[str, Any]] | None = None

    @field_validator("retrieved_at")
    @classmethod
    def retrieved_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")
        return value

    @model_validator(mode="after")
    def checksum_must_match_payload(self) -> GremlinSnapshot:
        actual = "sha256:" + hashlib.sha256(self.payload.encode("utf-8")).hexdigest()
        if self.checksum != actual:
            raise ValueError("checksum does not match UTF-8 payload")
        return self
