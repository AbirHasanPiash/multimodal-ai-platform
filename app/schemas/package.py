from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class PackageBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    description: Optional[str] = None
    price: Decimal = Field(..., gt=0, description="Price in USD")
    credits: Decimal = Field(..., gt=0, description="Amount of credits user receives")
    is_active: bool = True
    is_featured: bool = False

class PackageCreate(PackageBase):
    pass

class PackageUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, gt=0)
    credits: Optional[Decimal] = Field(None, gt=0)
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None

class PackageResponse(PackageBase):
    id: UUID
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)