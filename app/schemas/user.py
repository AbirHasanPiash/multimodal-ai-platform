from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict

# Auth & Input Schemas
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class GoogleLogin(BaseModel):
    token: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Output/Response Schemas

class WalletResponse(BaseModel):
    id: UUID
    credits: int
    
    model_config = ConfigDict(from_attributes=True)

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    wallet: WalletResponse | None = None

    model_config = ConfigDict(from_attributes=True)