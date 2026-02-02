from fastapi import APIRouter, HTTPException, status
from sqlalchemy.future import select
from sqlalchemy.exc import OperationalError, InterfaceError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import secrets
import asyncio
import logging

from app.core.database import async_session_maker
from app.models.user import User, Wallet
from app.schemas.user import UserCreate, Token, UserLogin, GoogleLogin
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


async def execute_with_retry(
    operation,
    max_retries: int = 3,
    base_delay: float = 1.0
):
    """
    Execute a database operation with automatic retry on connection failures.
    Uses exponential backoff between retries.
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await operation()
        except (
            OperationalError,
            InterfaceError,
            TimeoutError,
            asyncio.CancelledError,
            ConnectionRefusedError,
            OSError
        ) as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt)
                logger.warning(
                    f"Database operation failed (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait_time}s: {type(e).__name__}: {str(e)}"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    f"Database operation failed after {max_retries} attempts: "
                    f"{type(e).__name__}: {str(e)}"
                )
    
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database temporarily unavailable. Please try again in a few moments."
    )


async def get_user_by_email(email: str) -> User | None:
    """Get user by email with retry logic."""
    async def operation():
        async with async_session_maker() as db:
            result = await db.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()
    
    return await execute_with_retry(operation)


async def create_user_with_wallet(
    email: str,
    hashed_password: str,
    full_name: str,
    is_active: bool = True
) -> User:
    """Create a new user with wallet using retry logic."""
    async def operation():
        async with async_session_maker() as db:
            # Create User
            new_user = User(
                email=email,
                hashed_password=hashed_password,
                full_name=full_name,
                is_active=is_active
            )
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            
            # Create Wallet
            wallet = Wallet(user_id=new_user.id, credits=10.0)
            db.add(wallet)
            await db.commit()
            
            return new_user
    
    return await execute_with_retry(operation)


# Auth Endpoints

@router.post("/signup", response_model=Token)
async def signup(user_in: UserCreate):
    """
    Register a new user with email and password.
    """
    try:
        # Check if user exists
        existing_user = await get_user_by_email(user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create User with Wallet
        new_user = await create_user_with_wallet(
            email=user_in.email,
            hashed_password=get_password_hash(user_in.password),
            full_name="New User",
            is_active=True
        )

        # Return Token
        access_token = create_access_token(data={"sub": new_user.email})
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during signup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during signup"
        )


@router.post("/login", response_model=Token)
async def login(user_in: UserLogin):
    """
    Login with email and password.
    """
    try:
        # Get user from database
        user = await get_user_by_email(user_in.email)
        
        # Verify credentials
        if not user or not verify_password(user_in.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect email or password"
            )
        
        # Return Token
        access_token = create_access_token(data={"sub": user.email})
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during login"
        )


@router.post("/google", response_model=Token)
async def google_login(login_data: GoogleLogin):
    """
    Login or register using Google OAuth2.
    """
    try:
        # Verify the Token with Google
        try:
            id_info = id_token.verify_oauth2_token(
                login_data.token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
        except ValueError as e:
            logger.warning(f"Invalid Google token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google Token"
            )

        # Extract User Info
        email = id_info.get("email")
        name = id_info.get("name", "Google User")
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google Token: Email missing"
            )

        # Check if User Exists in DB
        user = await get_user_by_email(email)

        if not user:
            # Auto-Register New User
            logger.info(f"Creating new user from Google login: {email}")
            random_password = secrets.token_urlsafe(32)
            hashed_pw = get_password_hash(random_password)
            
            user = await create_user_with_wallet(
                email=email,
                hashed_password=hashed_pw,
                full_name=name,
                is_active=True
            )

        # Create Access Token
        access_token = create_access_token(data={"sub": user.email})
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during Google login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during authentication"
        )


# Health Check Endpoint

@router.get("/health")
async def health_check():
    """
    Check if the auth service and database are healthy.
    """
    try:
        # Try to connect to database
        async def check_db():
            async with async_session_maker() as db:
                await db.execute(select(1))
                return True
        
        db_healthy = await execute_with_retry(check_db, max_retries=1, base_delay=0.5)
        
        return {
            "status": "healthy",
            "database": "connected" if db_healthy else "disconnected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }