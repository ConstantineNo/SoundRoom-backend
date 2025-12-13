from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, Dict, Any

class VisitorLogBase(BaseModel):
    ip_address: str
    country: Optional[str] = None
    city: Optional[str] = None
    user_agent: Optional[str] = None
    device_type: Optional[str] = None
    os: Optional[str] = None
    browser: Optional[str] = None
    request_path: str
    request_method: str
    status_code: int

class VisitorLogCreate(VisitorLogBase):
    pass

class VisitorLog(VisitorLogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class DailyStatsBase(BaseModel):
    date: date
    pv: int
    uv: int
    top_urls: Dict[str, int]

class DailyStats(DailyStatsBase):
    id: int

    class Config:
        from_attributes = True

class BannedIPBase(BaseModel):
    ip_address: str
    reason: str
    expires_at: Optional[datetime] = None
    is_active: bool = True

class BannedIPCreate(BannedIPBase):
    pass

class BannedIP(BannedIPBase):
    id: int
    banned_at: datetime

    class Config:
        from_attributes = True

class DashboardSummary(BaseModel):
    today_pv: int
    today_uv: int
    total_users: int
    active_bans: int

class WhitelistIPBase(BaseModel):
    ip_address: str
    description: Optional[str] = None

class WhitelistIPCreate(WhitelistIPBase):
    pass

class WhitelistIP(WhitelistIPBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
