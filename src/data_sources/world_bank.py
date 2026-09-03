from __future__ import annotations

from typing import Any

from .base import BaseDataSource, CountryDataRecord, DataSourceError, MissingDataError


class WorldBankDataSource(BaseDataSource):
    SOURCE_NAME = "World Bank API"
    API_URL = "https://api.worldbank.org/v2"

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        iso3 = (country_iso3 or "").strip().upper()
        if not iso3:
            raise DataSourceError("country_iso3 is required")
        if not indicator_id:
            raise DataSourceError("indicator_id is required")

        url = f"{self.API_URL}/country/{iso3}/indicator/{indicator_id}?format=json&per_page=200"
        payload = self._request_json(url)
        if len(payload) < 2:
            raise MissingDataError(f"No World Bank payload for {indicator_id}")

        observations = payload[1] or []
        if not observations:
            raise MissingDataError(f"No observations for {indicator_id} in {iso3}")

        valid = [item for item in observations if item.get("value") is not None and item.get("date")]
        if not valid:
            raise MissingDataError(f"No valid observations for {indicator_id} in {iso3}")

        latest = valid[0]
        value = latest.get("value")
        observation_date = str(latest.get("date") or "")
        stale = self._is_stale(observation_date, max_age_years=kwargs.get("max_age_years", 3))
        confidence = "Low" if stale else "High"
        source_url = url
        return CountryDataRecord(
            country_iso3=iso3,
            indicator_id=indicator_id,
            raw_value=value,
            unit=kwargs.get("unit", "index"),
            observation_date=observation_date,
            source_name=self.SOURCE_NAME,
            source_url=source_url,
            retrieved_at=self._utc_now(),
            input_method="API",
            confidence=confidence,
            status="available",
            metadata={
                "series": indicator_id,
                "historical_count": len(valid),
                "stale": stale,
            },
        )

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        iso3 = (country_iso3 or "").strip().upper()
        url = f"{self.API_URL}/country/{iso3}/indicator/{indicator_id}?format=json&per_page=200"
        payload = self._request_json(url)
        if len(payload) < 2:
            return []
        observations = payload[1] or []
        items = []
        for obs in observations:
            value = obs.get("value")
            date = obs.get("date")
            if value is None or not date:
                continue
            stale = self._is_stale(str(date), max_age_years=kwargs.get("max_age_years", 3))
            items.append(
                CountryDataRecord(
                    country_iso3=iso3,
                    indicator_id=indicator_id,
                    raw_value=value,
                    unit=kwargs.get("unit", "index"),
                    observation_date=str(date),
                    source_name=self.SOURCE_NAME,
                    source_url=url,
                    retrieved_at=self._utc_now(),
                    input_method="API",
                    confidence="Low" if stale else "High",
                    status="available",
                    metadata={"historical": True, "stale": stale},
                )
            )
        return items
