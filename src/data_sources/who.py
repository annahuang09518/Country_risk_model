from __future__ import annotations

from typing import Any

from .base import BaseDataSource, CountryDataRecord, MissingDataError


class WHODataSource(BaseDataSource):
    SOURCE_NAME = "WHO"
    API_BASE = "https://ghoapi.azureedge.net/api"

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        iso3 = (country_iso3 or "").strip().upper()
        if not iso3:
            raise ValueError("country_iso3 is required")
        if not indicator_id:
            raise ValueError("indicator_id is required")

        url = self._build_url(iso3, indicator_id)
        payload = self._request_json(url)
        rows = self._extract_rows(payload)
        if not rows:
            raise MissingDataError(f"No WHO data found for {indicator_id} in {iso3}")

        latest = rows[0]
        value = self._extract_value(latest)
        if value is None:
            raise MissingDataError(f"WHO payload for {indicator_id} did not include a numeric value")

        observation_date = self._extract_observation_date(latest)
        stale = self._is_stale(str(observation_date), max_age_years=3)
        return CountryDataRecord(
            country_iso3=iso3,
            indicator_id=indicator_id,
            raw_value=value,
            unit=kwargs.get("unit", "count_or_rate"),
            observation_date=str(observation_date),
            source_name=self.SOURCE_NAME,
            source_url=url,
            retrieved_at=self._utc_now(),
            input_method="API",
            confidence="Low" if stale else "Medium",
            status="available",
            metadata={
                "series": indicator_id,
                "stale": stale,
                "raw_rows": rows[:3],
            },
        )

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        iso3 = (country_iso3 or "").strip().upper()
        url = self._build_url(iso3, indicator_id)
        payload = self._request_json(url)
        rows = self._extract_rows(payload)
        out: list[CountryDataRecord] = []
        for row in rows:
            value = self._extract_value(row)
            if value is None:
                continue
            observation_date = self._extract_observation_date(row)
            stale = self._is_stale(str(observation_date), max_age_years=3)
            out.append(
                CountryDataRecord(
                    country_iso3=iso3,
                    indicator_id=indicator_id,
                    raw_value=value,
                    unit=kwargs.get("unit", "count_or_rate"),
                    observation_date=str(observation_date),
                    source_name=self.SOURCE_NAME,
                    source_url=url,
                    retrieved_at=self._utc_now(),
                    input_method="API",
                    confidence="Low" if stale else "Medium",
                    status="available",
                    metadata={"historical": True, "stale": stale},
                )
            )
        return out

    @staticmethod
    def _build_url(country_iso3: str, indicator_id: str) -> str:
        return f"{WHODataSource.API_BASE}/{indicator_id}?format=json&filter=COUNTRY:{country_iso3}"

    @staticmethod
    def _extract_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ("value", "data", "records", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            for nested in payload.values():
                rows = WHODataSource._extract_rows(nested)
                if rows:
                    return rows
        elif isinstance(payload, list):
            return payload
        return []

    @staticmethod
    def _extract_value(row: dict[str, Any]) -> Any:
        for key in ("value", "NumericValue", "numericValue", "count", "cases"):
            if key in row and row[key] is not None:
                return row[key]
        return None

    @staticmethod
    def _extract_observation_date(row: dict[str, Any]) -> str:
        for key in ("date", "Date", "year", "Year", "period"):
            value = row.get(key)
            if value is not None:
                return str(value)
        return ""
