from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import requests


class DataSourceError(RuntimeError):
    """Raised for connector-level fetch or parsing errors."""


class MissingDataError(DataSourceError):
    """Raised when the connector cannot locate a valid data point."""


@dataclass
class CountryDataRecord:
    country_iso3: str
    indicator_id: str
    raw_value: Any
    unit: str
    observation_date: str
    source_name: str
    source_url: str
    retrieved_at: str
    input_method: str
    confidence: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "country_iso3": self.country_iso3,
            "indicator_id": self.indicator_id,
            "raw_value": self.raw_value,
            "unit": self.unit,
            "observation_date": self.observation_date,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "input_method": self.input_method,
            "confidence": self.confidence,
            "status": self.status,
            "metadata": self.metadata,
        }


class BaseDataSource:
    SOURCE_NAME = "Base Data Source"
    DEFAULT_TIMEOUT = 15

    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        raise NotImplementedError("Subclasses must implement fetch_indicator().")

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        return [self.fetch_indicator(country_iso3, indicator_id, **kwargs)]

    def _request_json(self, url: str, timeout: int | None = None) -> Any:
        try:
            response = requests.get(url, timeout=timeout or self.timeout)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise DataSourceError(f"Timeout while fetching {url}: {exc}") from exc
        except requests.RequestException as exc:
            raise DataSourceError(f"Request failed for {url}: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise DataSourceError(f"Malformed JSON returned from {url}") from exc

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _is_stale(observation_date: str | None, max_age_years: int = 3) -> bool:
        if not observation_date:
            return True
        try:
            year = int(str(observation_date)[:4])
            current_year = datetime.now(timezone.utc).year
            return (current_year - year) > max_age_years
        except (TypeError, ValueError):
            return True


class CountryDataService:
    def __init__(self, sources: Sequence[BaseDataSource] | None = None):
        self.sources = list(sources or [])

    def register(self, source: BaseDataSource) -> None:
        self.sources.append(source)

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        last_error: Exception | None = None
        for source in self.sources:
            try:
                record = source.fetch_indicator(country_iso3, indicator_id, **kwargs)
                if record and record.status == "available":
                    return record
            except (DataSourceError, MissingDataError) as exc:
                last_error = exc
                continue
        if last_error is not None:
            return CountryDataRecord(
                country_iso3=country_iso3,
                indicator_id=indicator_id,
                raw_value=None,
                unit="unknown",
                observation_date="",
                source_name="Manual",
                source_url="",
                retrieved_at=BaseDataSource._utc_now(),
                input_method="manual",
                confidence="Low",
                status="missing",
                metadata={"fallback_error": str(last_error), "reason": "No available automated source"},
            )
        return CountryDataRecord(
            country_iso3=country_iso3,
            indicator_id=indicator_id,
            raw_value=None,
            unit="unknown",
            observation_date="",
            source_name="Manual",
            source_url="",
            retrieved_at=BaseDataSource._utc_now(),
            input_method="manual",
            confidence="Low",
            status="missing",
            metadata={"reason": "No data sources configured"},
        )

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        for source in self.sources:
            try:
                records = source.fetch_historical(country_iso3, indicator_id, **kwargs)
                if records:
                    return records
            except (DataSourceError, MissingDataError):
                continue
        return []
