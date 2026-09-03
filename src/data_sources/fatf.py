from __future__ import annotations

from typing import Any

from .base import BaseDataSource, CountryDataRecord, MissingDataError


class FATFDataSource(BaseDataSource):
    SOURCE_NAME = "FATF"
    DEFAULT_URL = "https://www.fatf-gafi.org/publications/high-risk-and-other-monitored-jurisdictions/"

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        iso3 = (country_iso3 or "").strip().upper()
        if not iso3:
            raise ValueError("country_iso3 is required")
        if not indicator_id:
            raise ValueError("indicator_id is required")

        source_url = kwargs.get("source_url") or self.DEFAULT_URL
        payload = self._request_json(source_url)
        status = self._extract_status(payload, iso3)
        if status is None:
            raise MissingDataError(f"No FATF status found for {iso3}")

        effective_date = self._extract_effective_date(payload, iso3)
        previous_status = self._extract_previous_status(payload, iso3)
        stale = self._is_stale(str(effective_date), max_age_years=5)
        return CountryDataRecord(
            country_iso3=iso3,
            indicator_id=indicator_id,
            raw_value=status,
            unit="enum",
            observation_date=str(effective_date),
            source_name=self.SOURCE_NAME,
            source_url=source_url,
            retrieved_at=self._utc_now(),
            input_method="API",
            confidence="Low" if stale else "Medium",
            status="available",
            metadata={
                "status": status,
                "previous_status": previous_status,
                "effective_date": effective_date,
                "api_payload": payload,
                "stale": stale,
            },
        )

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        iso3 = (country_iso3 or "").strip().upper()
        source_url = kwargs.get("source_url") or self.DEFAULT_URL
        payload = self._request_json(source_url)
        history = self._extract_history(payload, iso3)
        records: list[CountryDataRecord] = []
        for item in history:
            observation_date = item.get("effective_date") or item.get("date") or ""
            stale = self._is_stale(str(observation_date), max_age_years=5)
            records.append(
                CountryDataRecord(
                    country_iso3=iso3,
                    indicator_id=indicator_id,
                    raw_value=item.get("status") or item.get("value") or "",
                    unit="enum",
                    observation_date=str(observation_date),
                    source_name=self.SOURCE_NAME,
                    source_url=source_url,
                    retrieved_at=self._utc_now(),
                    input_method="API",
                    confidence="Low" if stale else "Medium",
                    status="available",
                    metadata={"historical": True, "status_entry": item},
                )
            )
        return records

    @staticmethod
    def _extract_status(payload: Any, country_iso3: str) -> Any:
        records = FATFDataSource._flatten_records(payload)
        for item in records:
            country_name = str(item.get("country") or item.get("jurisdiction") or item.get("country_name") or "").upper()
            iso = str(item.get("iso3") or item.get("country_iso3") or "").upper()
            if country_name == country_iso3 or iso == country_iso3:
                return item.get("status") or item.get("label") or item.get("current_status")
        return None

    @staticmethod
    def _extract_previous_status(payload: Any, country_iso3: str) -> Any:
        records = FATFDataSource._flatten_records(payload)
        for item in records:
            country_name = str(item.get("country") or item.get("jurisdiction") or item.get("country_name") or "").upper()
            iso = str(item.get("iso3") or item.get("country_iso3") or "").upper()
            if country_name == country_iso3 or iso == country_iso3:
                return item.get("previous_status") or item.get("prior_status") or item.get("last_status")
        return None

    @staticmethod
    def _extract_effective_date(payload: Any, country_iso3: str) -> Any:
        records = FATFDataSource._flatten_records(payload)
        for item in records:
            country_name = str(item.get("country") or item.get("jurisdiction") or item.get("country_name") or "").upper()
            iso = str(item.get("iso3") or item.get("country_iso3") or "").upper()
            if country_name == country_iso3 or iso == country_iso3:
                return item.get("effective_date") or item.get("date") or item.get("latest_update")
        return ""

    @staticmethod
    def _extract_history(payload: Any, country_iso3: str) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        records = FATFDataSource._flatten_records(payload)
        for item in records:
            country_name = str(item.get("country") or item.get("jurisdiction") or item.get("country_name") or "").upper()
            iso = str(item.get("iso3") or item.get("country_iso3") or "").upper()
            if country_name == country_iso3 or iso == country_iso3:
                history.append(item)
        return history

    @staticmethod
    def _flatten_records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            candidates: list[Any] = []
            for key in ("data", "results", "records", "jurisdictions", "items"):
                val = payload.get(key)
                if isinstance(val, list):
                    candidates.extend(val)
            if not candidates:
                for value in payload.values():
                    if isinstance(value, (dict, list)):
                        candidates.extend(FATFDataSource._flatten_records(value))
            return [c for c in candidates if isinstance(c, dict)]
        if isinstance(payload, list):
            flattened: list[dict[str, Any]] = []
            for item in payload:
                if isinstance(item, dict):
                    flattened.append(item)
                elif isinstance(item, list):
                    flattened.extend(FATFDataSource._flatten_records(item))
            return flattened
        return []
