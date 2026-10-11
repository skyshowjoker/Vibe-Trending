from typing import Literal

from pydantic import BaseModel, Field


class SeriesPlan(BaseModel):
    name: str
    indicator: str
    country: str = "CHN"
    unit: str = ""
    frequency: str = "annual"
    source: str = "worldbank"
    query: str = ""
    urls: list[str] = Field(default_factory=list, max_length=8)
    source_options: dict[str, str] = Field(default_factory=dict)


class Plan(BaseModel):
    title: str
    start_year: int = Field(default=2015, ge=1960, le=2100)
    end_year: int = Field(default=2025, ge=1960, le=2100)
    series: list[SeriesPlan] = Field(min_length=1, max_length=8)
    notes: str = "缺失值保留为空，不插值；仅使用来源返回的数值。"


class Prompt(BaseModel):
    prompt: str = Field(min_length=2, max_length=4000)


class ProjectInput(BaseModel):
    prompt: str = ""
    plan: Plan


class PlanEdit(BaseModel):
    plan: Plan
    base_revision: str
    instruction: str = Field(min_length=2, max_length=4000)


class PointEdit(BaseModel):
    series_id: str
    date: str = Field(pattern=r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
    value: float = Field(allow_inf_nan=False)
    reason: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https?://")


class Schedule(BaseModel):
    enabled: bool = False
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Shanghai"
