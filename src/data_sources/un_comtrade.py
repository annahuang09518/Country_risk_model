from __future__ import annotations

from math import fsum
from typing import Any

from .base import BaseDataSource, CountryDataRecord, MissingDataError


class UNComtradeDataSource(BaseDataSource):
    SOURCE_NAME = "UN Comtrade"
    API_BASE = "https://comtradeapi.un.org/data/v1/get"

    def fetch_indicator(self, country_iso3: str, indicator_id: str, **kwargs) -> CountryDataRecord:
        iso3 = (country_iso3 or "").strip().upper()
        if not iso3:
            raise ValueError("country_iso3 is required")

        payload = self._request_json(self._build_url(iso3, indicator_id, **kwargs))
        rows = self._extract_rows(payload)
        if not rows:
            raise MissingDataError(f"No UN Comtrade data found for {indicator_id} in {iso3}")

        raw_value = self._compute_indicator_value(rows, indicator_id)
        if raw_value is None:
            raise MissingDataError(f"Unable to calculate {indicator_id} from UN Comtrade payload")

        observation_date = rows[0].get("period") or rows[0].get("year") or ""
        stale = self._is_stale(str(observation_date), max_age_years=3)
        return CountryDataRecord(
            country_iso3=iso3,
            indicator_id=indicator_id,
            raw_value=raw_value,
            unit=kwargs.get("unit", "share"),
            observation_date=str(observation_date),
            source_name=self.SOURCE_NAME,
            source_url=self._build_url(iso3, indicator_id, **kwargs),
            retrieved_at=self._utc_now(),
            input_method="API",
            confidence="Low" if stale else "Medium",
            status="available",
            metadata={
                "series": indicator_id,
                "raw_rows": rows[:5],
                "stale": stale,
                "hh_i_mode": "0_1" if kwargs.get("share_scale") == "0_1" else "0_100",
            },
        )

    def fetch_historical(self, country_iso3: str, indicator_id: str, **kwargs) -> list[CountryDataRecord]:
        iso3 = (country_iso3 or "").strip().upper()
        payload = self._request_json(self._build_url(iso3, indicator_id, **kwargs, historical=True))
        rows = self._extract_rows(payload)
        out: list[CountryDataRecord] = []
        for row in rows:
            period = row.get("period") or row.get("year") or ""
            value = self._compute_indicator_value([row], indicator_id)
            if value is None:
                continue
            stale = self._is_stale(str(period), max_age_years=3)
            out.append(
                CountryDataRecord(
                    country_iso3=iso3,
                    indicator_id=indicator_id,
                    raw_value=value,
                    unit=kwargs.get("unit", "share"),
                    observation_date=str(period),
                    source_name=self.SOURCE_NAME,
                    source_url=self._build_url(iso3, indicator_id, **kwargs, historical=True),
                    retrieved_at=self._utc_now(),
                    input_method="API",
                    confidence="Low" if stale else "Medium",
                    status="available",
                    metadata={"historical": True, "stale": stale},
                )
            )
        return out

    @staticmethod
    def _build_url(country_iso3: str, indicator_id: str, **kwargs) -> str:
        historical = kwargs.get("historical")
        reporter = kwargs.get("reporter") or country_iso3
        partner = kwargs.get("partner") or "all"
        flow = kwargs.get("flow") or "all"
        if historical:
            return f"{UNComtradeDataSource.API_BASE}/C/A/HS?reporter={reporter}&partner={partner}&tradeflow={flow}&period=2020,2021,2022,2023,2024&fmt=json"
        return f"{UNComtradeDataSource.API_BASE}/C/A/HS?reporter={reporter}&partner={partner}&tradeflow={flow}&period=2024&fmt=json"

    @staticmethod
    def _extract_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ("data", "results", "records"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            for nested in payload.values():
                rows = UNComtradeDataSource._extract_rows(nested)
                if rows:
                    return rows
        elif isinstance(payload, list):
            return payload
        return []

    @staticmethod
    def _compute_indicator_value(rows: list[dict[str, Any]], indicator_id: str) -> Any:
        shares = []
        for row in rows:
            if isinstance(row, dict):
                value = row.get("NetWeight") or row.get("TradeValue") or row.get("qty") or row.get("value")
                if value is not None:
                    shares.append(float(value))
        if not shares:
            return None
        if indicator_id in {"trade_hhi", "HHI", "concentration_hhi"}:
            total = fsum(shares)
            if total <= 0:
                return 0.0
            return sum((s / total) ** 2 for s in shares)
        if indicator_id in {"top_1_partner_share", "top1", "top_1"}:
            total = fsum(shares)
            if total <= 0:
                return 0.0
            return max(shares) / total
        if indicator_id in {"top_3_partner_share", "top3", "top_3"}:
            total = fsum(shares)
            if total <= 0:
                return 0.0
            ordered = sorted(shares, reverse=True)
            return sum(ordered[:3]) / total
        if indicator_id in {"top_5_partner_share", "top5", "top_5"}:
            total = fsum(shares)
            if total <= 0:
                return 0.0
            ordered = sorted(shares, reverse=True)
            return sum(ordered[:5]) / total
        return shares[0] if len(shares) == 1 else fsum(shares)
