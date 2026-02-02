from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal

class UserWalletSchema(BaseModel):
    credits: Decimal
    updated_at: datetime

class UserAdminResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    created_at: datetime
    wallet: Optional[UserWalletSchema]

    class Config:
        from_attributes = True

class UserUpdateAdmin(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    credits: Optional[Decimal] = Field(None, ge=0)

class UserListResponse(BaseModel):
    users: List[UserAdminResponse]
    total_count: int
    page: int
    size: int