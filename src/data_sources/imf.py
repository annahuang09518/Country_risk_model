from __future__ import annotations

from typing import Any

from .base import BaseDataSource, CountryDataRecord, DataSourceError, MissingDataError


class IMFDataSource(BaseDataSource):
    SOURCE_NAME = "IMF DataMapper"
    API_URL = "https://www.imf.org/external/datamapper/api/v1"

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        iso3 = (country_iso3 or "").strip().upper()
        if not iso3:
            raise DataSourceError("country_iso3 is required")
        if not indicator_id:
            raise DataSourceError("indicator_id is required")

        url = f"{self.API_URL}/{indicator_id}/{iso3}"
        payload = self._request_json(url)
        country_series = self._extract_country_series(payload, indicator_id, iso3)
        if not country_series:
            raise MissingDataError(f"No IMF value found for {indicator_id} in {iso3}")

        valid_years = {
            year: value for year, value in country_series.items()
            if isinstance(value, (int, float))
        }
        if not valid_years:
            raise MissingDataError(f"No IMF numeric value found for {indicator_id} in {iso3}")
        latest_year = max(valid_years, key=lambda y: int(y))
        value = valid_years[latest_year]

        source_url = url
        observation_date = kwargs.get("observation_date") or latest_year
        stale = self._is_stale(str(observation_date), max_age_years=kwargs.get("max_age_years", 3))
        return CountryDataRecord(
            country_iso3=iso3,
            indicator_id=indicator_id,
            raw_value=value,
            unit=kwargs.get("unit", "percent"),
            observation_date=str(observation_date),
            source_name=self.SOURCE_NAME,
            source_url=source_url,
            retrieved_at=self._utc_now(),
            input_method="API",
            confidence="Low" if stale else "High",
            status="available",
            metadata={
                "series": indicator_id,
                "stale": stale,
            },
        )

    @staticmethod
    def _extract_value(payload: Any, indicator_id: str) -> Any:
        return None

    def _extract_country_series(self, payload: Any, indicator_id: str, iso3: str) -> dict:
        """Navigate the IMF DataMapper {"values": {series: {country: {year: value}}}} shape."""
        if isinstance(payload, dict):
            values = payload.get("values")
            if isinstance(values, dict):
                series = values.get(indicator_id)
                if isinstance(series, dict):
                    country_series = series.get(iso3)
                    if isinstance(country_series, dict):
                        return country_series
        return {}

    @staticmethod
    def _infer_latest_year(payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ("date", "Date", "year", "Year"):
                if key in payload:
                    return str(payload[key])
            for value in payload.values():
                inferred = IMFDataSource._infer_latest_year(value)
                if inferred:
                    return str(inferred)
        elif isinstance(payload, list):
            for item in payload:
                inferred = IMFDataSource._infer_latest_year(item)
                if inferred:
                    return str(inferred)
        return ""

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        iso3 = (country_iso3 or "").strip().upper()
        url = f"{self.API_URL}/{indicator_id}/{iso3}"
        payload = self._request_json(url)
        country_series = self._extract_country_series(payload, indicator_id, iso3)
        records = []
        for year, value in sorted(country_series.items(), key=lambda kv: int(kv[0]), reverse=True):
            if not isinstance(value, (int, float)):
                continue
            stale = self._is_stale(str(year), max_age_years=kwargs.get("max_age_years", 3))
            records.append(
                CountryDataRecord(
                    country_iso3=iso3,
                    indicator_id=indicator_id,
                    raw_value=value,
                    unit=kwargs.get("unit", "percent"),
                    observation_date=str(year),
                    source_name=self.SOURCE_NAME,
                    source_url=url,
                    retrieved_at=self._utc_now(),
                    input_method="API",
                    confidence="Low" if stale else "High",
                    status="available",
                    metadata={"historical": True, "stale": stale},
                )
            )
        return records
