from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.models.user import User, Wallet
from app.schemas.user import UserCreate, Token, UserLogin
from app.core.security import get_password_hash, verify_password, create_access_token
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from app.core.config import settings
from app.schemas.user import GoogleLogin
import secrets

router = APIRouter()

@router.post("/signup", response_model=Token)
async def signup(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    # 1. Check if user exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2. Create User
    new_user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name="New User"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # 3. Create Empty Wallet for User
    wallet = Wallet(user_id=new_user.id, credits=0)
    db.add(wallet)
    await db.commit()

    # 4. Return Token
    access_token = create_access_token(data={"sub": new_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
        
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/google", response_model=Token)
async def google_login(login_data: GoogleLogin, db: AsyncSession = Depends(get_db)):
    try:
        # 1. Verify the Token with Google
        # This checks the signature and expiration automatically
        id_info = id_token.verify_oauth2_token(
            login_data.token, 
            google_requests.Request(), 
            settings.GOOGLE_CLIENT_ID
        )

        # 2. Extract User Info
        email = id_info.get("email")
        name = id_info.get("name")
        
        if not email:
            raise HTTPException(status_code=400, detail="Invalid Google Token: Email missing")

    except ValueError:
        # Token is invalid (expired or fake)
        raise HTTPException(status_code=400, detail="Invalid Google Token")

    # 3. Check if User Exists in DB
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # 4. Auto-Register New User
        # We generate a random password because they will login via Google
        random_password = secrets.token_urlsafe(32)
        hashed_pw = get_password_hash(random_password)
        
        new_user = User(
            email=email,
            hashed_password=hashed_pw,
            full_name=name,
            is_active=True
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # Create Wallet for new user
        wallet = Wallet(user_id=new_user.id, credits=0)
        db.add(wallet)
        await db.commit()
        
        user = new_user

    # 5. Create Access Token
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}