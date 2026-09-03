from __future__ import annotations

from .base import BaseDataSource, CountryDataRecord, DataSourceError, MissingDataError


class WGIDataSource(BaseDataSource):
    SOURCE_NAME = "World Bank WGI"
    API_URL = "https://api.worldbank.org/v2"
    INDICATOR_MAP = {
        "GOV_WGI_PV.SC": "Political Stability and Absence of Violence/Terrorism (0-100 governance score)",
        "GOV_WGI_GE.SC": "Government Effectiveness (0-100 governance score)",
        "GOV_WGI_RQ.SC": "Regulatory Quality (0-100 governance score)",
        "GOV_WGI_RL.SC": "Rule of Law (0-100 governance score)",
        "GOV_WGI_CC.SC": "Control of Corruption (0-100 governance score)",
        "GOV_WGI_VA.SC": "Voice and Accountability (0-100 governance score)",
        # Legacy/alternate short codes accepted as aliases for backward compatibility.
        "PV.EST": "GOV_WGI_PV.SC",
        "GE.EST": "GOV_WGI_GE.SC",
        "RQ.EST": "GOV_WGI_RQ.SC",
        "RL.EST": "GOV_WGI_RL.SC",
        "CC.EST": "GOV_WGI_CC.SC",
        "VA.EST": "GOV_WGI_VA.SC",
    }

    @classmethod
    def _resolve_code(cls, indicator_id: str) -> str:
        mapped = cls.INDICATOR_MAP.get(indicator_id)
        if mapped and mapped.startswith("GOV_WGI_") and mapped.endswith(".SC"):
            return mapped
        return indicator_id

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        iso3 = (country_iso3 or "").strip().upper()
        if not iso3:
            raise DataSourceError("country_iso3 is required")
        code = self._resolve_code(indicator_id)
        url = f"{self.API_URL}/country/{iso3}/indicator/{code}?format=json&per_page=200"
        payload = self._request_json(url)
        if len(payload) < 2:
            raise MissingDataError(f"No WGI payload for {code}")
        observations = payload[1] or []
        valid = [item for item in observations if item.get("value") is not None and item.get("date")]
        if not valid:
            raise MissingDataError(f"No valid WGI data for {code} in {iso3}")
        latest = valid[0]
        value = latest.get("value")
        observation_date = str(latest.get("date") or "")
        stale = self._is_stale(observation_date, max_age_years=kwargs.get("max_age_years", 3))
        return CountryDataRecord(
            country_iso3=iso3,
            indicator_id=code,
            raw_value=value,
            unit=kwargs.get("unit", "index"),
            observation_date=observation_date,
            source_name=self.SOURCE_NAME,
            source_url=url,
            retrieved_at=self._utc_now(),
            input_method="API",
            confidence="Low" if stale else "High",
            status="available",
            metadata={
                "series": code,
                "indicator_label": self.INDICATOR_MAP.get(code, code),
                "historical_count": len(valid),
                "stale": stale,
            },
        )

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        iso3 = (country_iso3 or "").strip().upper()
        code = self._resolve_code(indicator_id)
        url = f"{self.API_URL}/country/{iso3}/indicator/{code}?format=json&per_page=200"
        payload = self._request_json(url)
        if len(payload) < 2:
            return []
        observations = payload[1] or []
        out = []
        for obs in observations:
            value = obs.get("value")
            date = obs.get("date")
            if value is None or not date:
                continue
            stale = self._is_stale(str(date), max_age_years=kwargs.get("max_age_years", 3))
            out.append(
                CountryDataRecord(
                    country_iso3=iso3,
                    indicator_id=code,
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
        return out
