from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date
from datetime import datetime, timedelta, timezone
from app.schemas.admin_stats import AdminOverviewStats

from app.core.database import get_db
from app.models import User, Message, GeneratedImage, GeneratedAudio, GeneratedVideo, Chat, Transaction

router = APIRouter()

@router.get("/overview", response_model=AdminOverviewStats)
async def get_admin_overview(db: AsyncSession = Depends(get_db)):
    # Calculate Grand Totals efficiently
    
    # Revenue (Only completed transactions)
    revenue_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.status == "completed")
    
    # Content Counts
    counts_stmt = select(
        func.count(User.id).label("users"),
        func.count(Chat.id).label("chats")
    )
    
    # Costs & Tokens
    ai_metrics_stmt = select(
        func.coalesce(func.sum(Message.tokens), 0).label("tokens"),
        func.coalesce(func.sum(Message.cost), 0).label("msg_cost")
    )

    # Execute totals queries
    revenue = await db.scalar(revenue_stmt)
    user_chat_counts = (await db.execute(counts_stmt)).first()
    ai_metrics = (await db.execute(ai_metrics_stmt)).first()
    
    img_count = await db.scalar(select(func.count(GeneratedImage.id)))
    audio_count = await db.scalar(select(func.count(GeneratedAudio.id)))
    video_count = await db.scalar(select(func.count(GeneratedVideo.id)))
    
    # Calculate Total AI Cost
    img_cost = await db.scalar(select(func.coalesce(func.sum(GeneratedImage.cost), 0)))
    aud_cost = await db.scalar(select(func.coalesce(func.sum(GeneratedAudio.cost), 0)))
    vid_cost = await db.scalar(select(func.coalesce(func.sum(GeneratedVideo.cost), 0)))
    
    total_ai_cost = ai_metrics.msg_cost + img_cost + aud_cost + vid_cost

    # 2. Time-Series Data (Last 30 Days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    # Revenue Trend
    rev_trend_stmt = (
        select(cast(Transaction.created_at, Date).label("day"), func.sum(Transaction.amount))
        .where(Transaction.status == "completed", Transaction.created_at >= thirty_days_ago)
        .group_by("day")
        .order_by("day")
    )
    rev_trend_res = await db.execute(rev_trend_stmt)
    revenue_trend = [{"date": str(r[0]), "value": r[1]} for r in rev_trend_res.all()]

    # User Growth Trend
    user_trend_stmt = (
        select(cast(User.created_at, Date).label("day"), func.count(User.id))
        .where(User.created_at >= thirty_days_ago)
        .group_by("day")
        .order_by("day")
    )
    user_trend_res = await db.execute(user_trend_stmt)
    user_growth_trend = [{"date": str(u[0]), "value": u[1]} for u in user_trend_res.all()]

    return {
        "total_revenue": revenue,
        "total_users": user_chat_counts.users,
        "total_chats": user_chat_counts.chats,
        "total_images_generated": img_count,
        "total_audio_generated": audio_count,
        "total_videos_generated": video_count,
        "total_tokens_consumed": ai_metrics.tokens,
        "total_ai_cost": total_ai_cost,
        "revenue_trend": revenue_trend,
        "user_growth_trend": user_growth_trend
    }