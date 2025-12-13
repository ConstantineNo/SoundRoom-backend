from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, JSON
from datetime import datetime
from app.core.database import Base

class VisitorLog(Base):
    __tablename__ = "visitor_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), index=True)  # IPv6 support
    country = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    
    # Device Info
    user_agent = Column(String(500))
    device_type = Column(String(20))  # 'mobile', 'pc', 'tablet'
    os = Column(String(50))           # 'Windows', 'iOS'
    browser = Column(String(50))      # 'Chrome', 'Safari'
    
    # Request Info
    request_path = Column(String(255))
    request_method = Column(String(10))
    status_code = Column(Integer)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class DailyStats(Base):
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True)
    pv = Column(Integer, default=0)
    uv = Column(Integer, default=0)
    top_urls = Column(JSON, default=dict) # {"/api/v1/scores": 150, ...}

class BannedIP(Base):
    __tablename__ = "banned_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), unique=True, index=True)
    reason = Column(String(255))  # 例如: "Rate Limit", "Sensitive Path: .env"
    banned_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # Null = 永久封禁
    is_active = Column(Boolean, default=True)  # 手动解封可设为 False
