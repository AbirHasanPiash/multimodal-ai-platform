from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Wallet
from app.schemas.user import UserResponse, UserUpdateProfile

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def read_user_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user profile + Wallet Credits
    """
    # Explicitly load the wallet to ensure it is returned in the response
    await db.refresh(current_user, attribute_names=["wallet"])
    return current_user

@router.post("/topup")
async def dev_top_up_credits(
    amount: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    TEMPORARY: Add fake credits for testing.
    1 Amount = 1 Credit
    """
    if amount > 10000:
        raise HTTPException(status_code=400, detail="Max 10,000 credits allowed.")
        
    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = result.scalar_one_or_none()
    
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet.credits += amount
    
    await db.commit()
    await db.refresh(wallet)
    return {"message": "Credits updated", "new_credits": wallet.credits}


@router.patch("/me", response_model=UserResponse)
async def update_user_me(
    payload: UserUpdateProfile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update own profile (Currently only supports updating full_name).
    """
    # Update fields if they are provided in the payload
    if payload.full_name is not None:
        current_user.full_name = payload.full_name

    await db.commit()

    # Refresh user to ensure updated_at is accurate
    await db.refresh(current_user, attribute_names=["wallet"])

    return current_user