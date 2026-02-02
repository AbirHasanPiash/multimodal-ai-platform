from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

class StatTrend(BaseModel):
    date: str
    value: Decimal

class AdminOverviewStats(BaseModel):
    # Top Level Totals
    total_revenue: Decimal
    total_users: int
    total_chats: int
    
    # Multimodal Breakdown
    total_images_generated: int
    total_audio_generated: int
    total_videos_generated: int
    
    # Economics
    total_tokens_consumed: int
    total_ai_cost: Decimal
    
    # Chart Data
    revenue_trend: List[StatTrend]
    user_growth_trend: List[StatTrend]

    class Config:
        from_attributes = True