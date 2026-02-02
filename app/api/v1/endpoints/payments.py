import stripe
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from decimal import Decimal

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User, Wallet
from app.models.package import Package
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionResponse
from typing import List

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter()

# CHECKOUT ENDPOINT
@router.post("/create-checkout-session/{package_id}")
async def create_checkout_session(
    package_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a Stripe Checkout Session.
    Configured for maximum compatibility (RBI Compliant) and security.
    """
    # Fetch Package
    package = await db.get(Package, package_id)
    if not package or not package.is_active:
        raise HTTPException(status_code=404, detail="Package not found or inactive")

    # Create Stripe Session
    try:
        checkout_session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            payment_method_types=["card"],
            
            # Key Compliance Settings
            billing_address_collection='required',
            customer_email=current_user.email,
            
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": package.name,
                        "description": package.description,
                    },
                    "unit_amount": int(package.price * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{settings.FRONTEND_URL}/dashboard/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.FRONTEND_URL}/dashboard/payment/cancel",
            metadata={
                "user_id": str(current_user.id),
                "package_id": str(package.id),
                "credits": str(package.credits),
            },
            client_reference_id=str(current_user.id)
        )
    except Exception as e:
        # Log this error in your actual logs
        raise HTTPException(status_code=400, detail=f"Stripe Error: {str(e)}")

    # Create Pending Transaction Record
    db_transaction = Transaction(
        user_id=current_user.id,
        package_id=package.id,
        stripe_session_id=checkout_session.id,
        amount=package.price,
        currency="usd",
        credits_added=package.credits,
        status="pending"
    )
    db.add(db_transaction)
    await db.commit()

    return {"checkout_url": checkout_session.url}


# WEBHOOK ENDPOINT
@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request, 
    stripe_signature: str = Header(None), 
    db: AsyncSession = Depends(get_db)
):
    payload = await request.body()
    
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_checkout_completed(session, db)

    return {"status": "success"}


async def handle_checkout_completed(session, db: AsyncSession):
    stripe_session_id = session["id"]
    
    # Metadata extraction
    user_id = session.get("metadata", {}).get("user_id")
    credits_str = session.get("metadata", {}).get("credits")

    if not user_id or not credits_str:
        return

    try:
        # Get Transaction
        result = await db.execute(
            select(Transaction).where(Transaction.stripe_session_id == stripe_session_id)
        )
        transaction_record = result.scalar_one_or_none()

        if not transaction_record or transaction_record.status == "completed":
            return

        # Lock Wallet
        result = await db.execute(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        wallet = result.scalar_one_or_none()

        if not wallet:
            wallet = Wallet(user_id=user_id, credits=0)
            db.add(wallet)

        # Update (Atomic)
        wallet.credits += Decimal(credits_str)
        transaction_record.status = "completed"
        transaction_record.completed_at = datetime.now(timezone.utc)

        db.add(wallet)
        db.add(transaction_record)
        await db.commit()
        
    except Exception as e:
        await db.rollback()
        print(f"CRITICAL ERROR in Webhook: {str(e)}")
        raise e
    

# PAYMENT HISTORY ENDPOINT
@router.get("/history", response_model=List[TransactionResponse])
async def read_payment_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
    )
    return result.scalars().all()