from uuid import UUID
from decimal import Decimal
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class TransactionBase(BaseModel):
    amount: Decimal
    currency: str
    credits_added: Decimal
    status: str

class TransactionCreate(TransactionBase):
    user_id: UUID
    package_id: Optional[UUID] = None
    stripe_session_id: str

class TransactionResponse(TransactionBase):
    id: UUID
    user_id: UUID
    package_id: Optional[UUID] = None
    stripe_session_id: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)