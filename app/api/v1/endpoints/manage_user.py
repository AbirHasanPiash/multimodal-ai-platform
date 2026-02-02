from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import joinedload
from app.core.database import get_db
from app.models import User, Wallet
from app.schemas.manage_user import UserAdminResponse, UserListResponse, UserUpdateAdmin

router = APIRouter()

@router.get("", response_model=UserListResponse)
async def list_users_admin(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_superuser: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * size
    
    query = select(User).options(joinedload(User.wallet)).order_by(User.created_at.desc())
    count_query = select(func.count(User.id))

    # Search Logic
    if search:
        search_filter = or_(
            User.email.ilike(f"%{search}%"),
            User.full_name.ilike(f"%{search}%")
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Status Filter
    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    # Role Filter
    if is_superuser is not None:
        query = query.where(User.is_superuser == is_superuser)
        count_query = count_query.where(User.is_superuser == is_superuser)

    total_count = await db.scalar(count_query)
    result = await db.execute(query.offset(offset).limit(size))
    users = result.unique().scalars().all()

    return {
        "users": users,
        "total_count": total_count,
        "page": page,
        "size": size
    }


@router.patch("/{user_id}", response_model=UserAdminResponse)
async def update_user_admin(
    user_id: UUID,
    obj_in: UserUpdateAdmin,
    db: AsyncSession = Depends(get_db)
):
    """Atomically update user details and wallet credits."""
    user = await db.get(User, user_id, options=[joinedload(User.wallet)])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update User Fields
    update_data = obj_in.model_dump(exclude_unset=True)
    
    if "credits" in update_data:
        new_credits = update_data.pop("credits")
        if user.wallet:
            user.wallet.credits = new_credits
        else:
            # Create wallet if it somehow doesn't exist
            new_wallet = Wallet(user_id=user.id, credits=new_credits)
            db.add(new_wallet)

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_admin(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a user (Cascade deletes chats/media/transactions)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await db.delete(user)
    await db.commit()
    return None