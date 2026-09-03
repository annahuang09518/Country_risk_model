from __future__ import annotations

from typing import Any

from .base import BaseDataSource, CountryDataRecord, MissingDataError


class UCDPDataSource(BaseDataSource):
    SOURCE_NAME = "UCDP"
    API_BASE = "https://ucdpapi.pcr.uu.se/api"

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        iso3 = (country_iso3 or "").strip().upper()
        if not iso3:
            raise ValueError("country_iso3 is required")
        if not indicator_id:
            raise ValueError("indicator_id is required")

        url = self._build_url(iso3, indicator_id, **kwargs)
        payload = self._request_json(url)
        rows = self._extract_rows(payload)
        if not rows:
            raise MissingDataError(f"No UCDP data found for {indicator_id} in {iso3}")

        latest = rows[0]
        raw_value = self._extract_value(latest, indicator_id)
        if raw_value is None:
            raw_value = self._summarize_rows(rows)

        observation_date = self._extract_observation_date(latest)
        stale = self._is_stale(observation_date, max_age_years=kwargs.get("max_age_years", 5))
        return CountryDataRecord(
            country_iso3=iso3,
            indicator_id=indicator_id,
            raw_value=raw_value,
            unit=kwargs.get("unit", "count_or_index"),
            observation_date=str(observation_date),
            source_name=self.SOURCE_NAME,
            source_url=url,
            retrieved_at=self._utc_now(),
            input_method="API",
            confidence="Low" if stale else "Medium",
            status="available",
            metadata={
                "series": indicator_id,
                "historical_count": len(rows),
                "stale": stale,
                "raw_rows": rows[:3],
            },
        )

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        iso3 = (country_iso3 or "").strip().upper()
        url = self._build_url(iso3, indicator_id, **kwargs, historical=True)
        payload = self._request_json(url)
        rows = self._extract_rows(payload)
        if not rows:
            return []
        records: list[CountryDataRecord] = []
        for row in rows:
            value = self._extract_value(row, indicator_id)
            if value is None:
                continue
            observation_date = self._extract_observation_date(row)
            stale = self._is_stale(str(observation_date), max_age_years=kwargs.get("max_age_years", 5))
            records.append(
                CountryDataRecord(
                    country_iso3=iso3,
                    indicator_id=indicator_id,
                    raw_value=value,
                    unit=kwargs.get("unit", "count_or_index"),
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
        return records

    @staticmethod
    def _build_url(country_iso3: str, indicator_id: str, **kwargs) -> str:
        historical = kwargs.get("historical")
        if historical:
            return f"{UCDPDataSource.API_BASE}/gedevents/24.1?country={country_iso3}&page=1&pagesize=50"
        return f"{UCDPDataSource.API_BASE}/gedevents/24.1?country={country_iso3}&page=1&pagesize=50"

    @staticmethod
    def _extract_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ("data", "results", "records", "events"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            for nested in payload.values():
                rows = UCDPDataSource._extract_rows(nested)
                if rows:
                    return rows
        elif isinstance(payload, list):
            return payload
        return []

    @staticmethod
    def _extract_value(row: dict[str, Any], indicator_id: str) -> Any:
        lookup = {
            "conflict_existence": ["conflict_exists", "conflict_existence", "active_conflict", "has_conflict"],
            "battle_deaths": ["battle_deaths", "battle_related_deaths", "deaths_battle", "battlerelateddeaths"],
            "civilian_deaths": ["civilian_deaths", "deaths_civilians", "civiliandeaths"],
            "event_count": ["event_count", "events", "conflict_events", "count"],
            "conflict_intensity": ["intensity", "conflict_intensity", "severity"],
        }
        needles = lookup.get(indicator_id, [indicator_id])
        for needle in needles:
            if needle in row and row[needle] is not None:
                return row[needle]
        for key, value in row.items():
            if isinstance(value, (int, float)) and key.lower().endswith("deaths"):
                return value
        return None

    @staticmethod
    def _summarize_rows(rows: list[dict[str, Any]]) -> float:
        values = []
        for row in rows:
            for key in ("battle_deaths", "battle_related_deaths", "civilian_deaths", "deaths_civilians", "event_count", "events", "intensity"):
                if key in row and row[key] is not None:
                    values.append(float(row[key]))
        if not values:
            return 0
        return sum(values)

    @staticmethod
    def _extract_observation_date(row: dict[str, Any]) -> str:
        for key in ("year", "date", "event_date", "start_date", "year_start"):
            value = row.get(key)
            if value is not None:
                return str(value)
        return ""
