from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Refund(StrictModel):
    transaction_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    amount_cents: int = Field(gt=0, le=1000000)
    currency: Literal["USD"] = "USD"
    idempotency_key: str = Field(min_length=8, max_length=100)


class Receipt(StrictModel):
    transaction_id: str = Field(max_length=80)
    amount_cents: int = Field(ge=0, le=1000000)
    currency: str = Field(max_length=3)
    readable: bool


class Evidence(StrictModel):
    transaction_id: str = Field(max_length=80)
    extraction: Receipt
