from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class UserRole(str, Enum):
    csr = "csr"
    dri = "dri"
    analyst_manager = "analyst_manager"


class User(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str
    name: str
    role: UserRole
    email: str
    active: bool
    assigned_escalations: list[str]
    created_at: datetime
