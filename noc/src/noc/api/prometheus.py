from datetime import datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from noc.detection.alerts import PrometheusUnavailable

NEVER_SCRAPED_YEAR = 1


class ScrapeTarget(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    labels: dict[str, str]
    health: str
    last_scrape: datetime | None = Field(default=None, alias="lastScrape")
    last_error: str = Field(default="", alias="lastError")

    @field_validator("last_scrape", mode="after")
    @classmethod
    def never_scraped_is_none(cls, value: datetime | None) -> datetime | None:
        if value is None or value.year == NEVER_SCRAPED_YEAR:
            return None
        return value


class TargetsData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    active_targets: list[ScrapeTarget] = Field(alias="activeTargets")


class TargetsResponse(BaseModel):
    status: Literal["success"]
    data: TargetsData


class InstantSample(BaseModel):
    metric: dict[str, str]
    value: tuple[float, str]


class VectorData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    result_type: str = Field(alias="resultType")
    result: list[InstantSample]


class VectorResponse(BaseModel):
    status: Literal["success"]
    data: VectorData


class Sample(BaseModel):
    labels: dict[str, str]
    value: float


class PrometheusReader:
    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def targets(self) -> list[ScrapeTarget]:
        parsed = await self._fetch("/api/v1/targets", {"state": "active"}, TargetsResponse)
        return parsed.data.active_targets

    async def vector(self, promql: str) -> list[Sample]:
        parsed = await self._fetch("/api/v1/query", {"query": promql}, VectorResponse)
        return [
            Sample(labels=item.metric, value=float(item.value[1])) for item in parsed.data.result
        ]

    async def _fetch[ModelT: BaseModel](
        self, path: str, params: dict[str, str], model: type[ModelT]
    ) -> ModelT:
        try:
            response = await self._http.get(self._base_url + path, params=params)
            response.raise_for_status()
            return model.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise PrometheusUnavailable(str(exc)) from exc
