"""Provider-neutral canonical market-data snapshot contract."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_MIC_RE = re.compile(r"^[A-Z0-9]{4}$")
_CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PARIS = ZoneInfo("Europe/Paris")


class MarketSnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class InstrumentCandidate(MarketSnapshotModel):
    provider_instrument_id: str | None
    provider_symbol: str | None
    ticker: str | None = None
    mic: str | None = None
    currency: str | None = None
    issuer: str | None = None


class InstrumentMapping(MarketSnapshotModel):
    instrument_id: str
    isin: str
    provider: str
    status: Literal["resolved", "ambiguous", "not_found", "invalid"]
    provider_instrument_id: str | None = None
    provider_symbol: str | None = None
    ticker: str | None = None
    mic: str | None = None
    exchange: str | None = None
    currency: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    mapping_source: str
    mapping_confidence: float | None = None
    retrieved_at: datetime
    issuer: str | None = None
    candidates: list[InstrumentCandidate] = Field(default_factory=list)

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_mapping_state(self) -> InstrumentMapping:
        if self.status != "invalid" and not _valid_isin(self.isin):
            raise ValueError("isin is not a valid ISO 6166 identifier")
        if self.status == "resolved":
            if not self.provider_symbol or not self.mic:
                raise ValueError("resolved mappings require provider_symbol and mic")
            if self.candidates:
                raise ValueError("resolved mappings cannot contain unresolved candidates")
        elif self.status == "ambiguous":
            if len(self.candidates) < 2:
                raise ValueError("ambiguous mappings require at least two candidates")
            if any((self.provider_symbol, self.ticker, self.provider_instrument_id)):
                raise ValueError("ambiguous mappings cannot select a candidate")
        elif any((self.provider_symbol, self.ticker, self.provider_instrument_id, self.candidates)):
            raise ValueError("unresolved mappings cannot select a candidate")
        if self.mapping_confidence is not None and not 0 <= self.mapping_confidence <= 1:
            raise ValueError("mapping_confidence must be in [0, 1]")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")
        if self.mic is not None and not _MIC_RE.fullmatch(self.mic):
            raise ValueError("mic must be a four-character MIC")
        if self.currency is not None and not _CURRENCY_RE.fullmatch(self.currency):
            raise ValueError("currency must be a three-character ISO code")
        return self


class MarketDailyObservation(MarketSnapshotModel):
    instrument_id: str
    isin: str
    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adjusted_close: float | None
    volume: float | None
    currency: str | None
    mic: str
    provider: str
    provider_symbol: str
    retrieved_at: datetime
    available_at: datetime
    snapshot_checksum: str
    adjustment_basis: str | None = None
    adjusted_close_available_at: datetime | None = None
    adjusted_close_point_in_time_safe: bool = False

    @field_validator("isin")
    @classmethod
    def validate_market_isin(cls, value: str) -> str:
        if not _valid_isin(value):
            raise ValueError("isin is not a valid ISO 6166 identifier")
        return value

    @field_validator("retrieved_at", "available_at", "adjusted_close_available_at")
    @classmethod
    def validate_aware_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_market_row(self) -> MarketDailyObservation:
        if self.available_at != _available_at(self.session_date):
            raise ValueError("raw market available_at must be D+1 midnight Europe/Paris")
        if self.adjusted_close_point_in_time_safe and self.adjusted_close_available_at is None:
            raise ValueError("point-in-time adjusted close requires adjusted_close_available_at")
        if not _CHECKSUM_RE.fullmatch(self.snapshot_checksum):
            raise ValueError("snapshot_checksum must be a sha256 checksum")
        if not _MIC_RE.fullmatch(self.mic):
            raise ValueError("mic must be a four-character MIC")
        if self.currency is not None and not _CURRENCY_RE.fullmatch(self.currency):
            raise ValueError("currency must be a three-character ISO code")
        for value in (self.open, self.high, self.low, self.close, self.adjusted_close, self.volume):
            if value is not None and not math.isfinite(value):
                raise ValueError("market numeric fields must be finite or null")
        return self


class CorporateActionObservation(MarketSnapshotModel):
    instrument_id: str
    isin: str
    event_date: date
    event_type: Literal[
        "split", "reverse_split", "dividend", "symbol_change", "isin_change", "delisting", "other"
    ]
    split_ratio: float | None = None
    cash_dividend: float | None = None
    currency: str | None = None
    ex_date: date | None = None
    record_date: date | None = None
    payment_date: date | None = None
    source_symbol: str | None = None
    provider: str
    retrieved_at: datetime
    available_at: datetime
    snapshot_checksum: str

    @field_validator("isin")
    @classmethod
    def validate_action_isin(cls, value: str) -> str:
        if not _valid_isin(value):
            raise ValueError("isin is not a valid ISO 6166 identifier")
        return value


class RawSnapshotReference(MarketSnapshotModel):
    artifact_id: str
    checksum: str
    content_type: str
    source_url: str
    provider_symbol: str
    retrieved_at: datetime
    size_bytes: int = Field(ge=0)
    capture_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("checksum")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        if not _CHECKSUM_RE.fullmatch(value):
            raise ValueError("checksum must be sha256 hex")
        return value

    @field_validator("source_url")
    @classmethod
    def strip_url_credentials(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("source_url must be HTTPS and must not contain query or fragment")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def validate_raw_retrieved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value


class MarketDataSnapshot(MarketSnapshotModel):
    schema_version: Literal["market-data/1.0"]
    snapshot_id: str
    provider: str
    universe_id: str
    retrieved_at: datetime
    raw_snapshots: list[RawSnapshotReference]
    instruments: list[InstrumentMapping]
    market_daily: list[MarketDailyObservation]
    corporate_actions: list[CorporateActionObservation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def validate_snapshot_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_provider_consistency(self) -> MarketDataSnapshot:
        if any(row.provider != self.provider for row in self.market_daily):
            raise ValueError("market rows must match snapshot provider")
        if any(action.provider != self.provider for action in self.corporate_actions):
            raise ValueError("corporate actions must match snapshot provider")
        checksums = {item.checksum for item in self.raw_snapshots}
        if any(row.snapshot_checksum not in checksums for row in self.market_daily):
            raise ValueError("each market row must reference a raw snapshot checksum")
        if any(action.snapshot_checksum not in checksums for action in self.corporate_actions):
            raise ValueError("each corporate action must reference a raw snapshot checksum")
        return self


def _valid_isin(value: str) -> bool:
    if not _ISIN_RE.fullmatch(value):
        return False
    expanded = "".join(str(int(char, 36)) if char.isalpha() else char for char in value)
    total = 0
    for index, char in enumerate(reversed(expanded)):
        digit = int(char)
        if index % 2:
            digit *= 2
            digit = digit // 10 + digit % 10
        total += digit
    return total % 10 == 0


def _available_at(session_date: date) -> datetime:
    return datetime.combine(session_date + timedelta(days=1), time.min, tzinfo=_PARIS)
