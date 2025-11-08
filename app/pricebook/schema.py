from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Service(BaseModel):
    name: str
    unit: str
    base_rate: float
    regional_multiplier: dict[str, float]
    complexity_mods: list[dict[str, float]] = []
    min_fee: float = 0.0
    lead_time: int = 14


class Material(BaseModel):
    sku: str
    cost: float
    waste_factor: float = 0.0


class Adder(BaseModel):
    condition: str
    type: Literal["fixed", "multiplier"]
    value: float


class Discount(BaseModel):
    condition: str
    percent: float


class Tax(BaseModel):
    region: str
    percent: float


class PriceBook(BaseModel):
    services: list[Service]
    materials: list[Material]
    adders: list[Adder] = []
    discounts: list[Discount] = []
    taxes: list[Tax] = []
