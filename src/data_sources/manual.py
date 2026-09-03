from __future__ import annotations

from typing import Any

from .base import BaseDataSource, CountryDataRecord, DataSourceError


class ManualInputSource(BaseDataSource):
    SOURCE_NAME = "Manual Analyst Input"

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        if not country_iso3:
            raise DataSourceError("country_iso3 is required")
        if not indicator_id:
            raise DataSourceError("indicator_id is required")

        raw_value = kwargs.get("raw_value")
        unit = kwargs.get("unit", "manual")
        observation_date = kwargs.get("observation_date") or ""
        return CountryDataRecord(
            country_iso3=country_iso3,
            indicator_id=indicator_id,
            raw_value=raw_value,
            unit=unit,
            observation_date=str(observation_date),
            source_name=self.SOURCE_NAME,
            source_url="",
            retrieved_at=self._utc_now(),
            input_method="manual",
            confidence=kwargs.get("confidence", "Low"),
            status="available" if raw_value is not None else "missing",
            metadata={"manual": True, "analyst_notes": kwargs.get("analyst_notes", "")},
        )
