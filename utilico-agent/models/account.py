from datetime import datetime
from pydantic import BaseModel, ConfigDict


class Address(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    street: str
    city: str
    state: str
    postcode: str


class Account(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account_id: str
    account_type: str
    customer_name: str
    address: Address
    billing_cycle: str
    tariff_code: str
    dri_pool: list[str]
    regulatory_tier: str
    created_at: datetime
    updated_at: datetime
