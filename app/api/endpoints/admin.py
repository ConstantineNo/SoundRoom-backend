from typing import List, Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_admin
from app.models.statistics import VisitorLog, DailyStats, BannedIP
from app.models.user import User
from app.schemas import statistics as schemas
from app.services.security_service import SecurityService

router = APIRouter()

@router.get("/dashboard/summary", response_model=schemas.DashboardSummary)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Get dashboard summary statistics.
    """
    today = date.today()
    
    # Get today's stats
    daily_stat = db.query(DailyStats).filter(DailyStats.date == today).first()
    today_pv = daily_stat.pv if daily_stat else 0
    today_uv = daily_stat.uv if daily_stat else 0
    
    # Get total users
    total_users = db.query(func.count(User.id)).scalar()
    
    # Get active bans
    active_bans = db.query(func.count(BannedIP.id)).filter(
        BannedIP.is_active == True,
        (BannedIP.expires_at == None) | (BannedIP.expires_at > datetime.utcnow())
    ).scalar()
    
    return {
        "today_pv": today_pv,
        "today_uv": today_uv,
        "total_users": total_users,
        "active_bans": active_bans
    }

@router.get("/logs/visitors", response_model=List[schemas.VisitorLog])
def get_visitor_logs(
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Get recent visitor logs.
    """
    skip = (page - 1) * size
    logs = db.query(VisitorLog).order_by(VisitorLog.created_at.desc()).offset(skip).limit(size).all()
    return logs

@router.get("/stats/daily", response_model=List[schemas.DailyStats])
def get_daily_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Get daily statistics history.
    """
    query = db.query(DailyStats).order_by(DailyStats.date.desc())
    
    if start_date:
        query = query.filter(DailyStats.date >= start_date)
    if end_date:
        query = query.filter(DailyStats.date <= end_date)
        
    return query.limit(limit).all()

@router.get("/security/bans", response_model=List[schemas.BannedIP])
def get_banned_ips(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    List all banned IPs.
    """
    return db.query(BannedIP).order_by(BannedIP.banned_at.desc()).all()

@router.post("/security/bans", response_model=schemas.BannedIP)
def ban_ip(
    ban_data: schemas.BannedIPCreate,
    duration_minutes: Optional[int] = Query(None, description="Duration in minutes. Leave empty for permanent."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Manually ban an IP address.
    """
    SecurityService.ban_ip(
        db=db, 
        ip=ban_data.ip_address, 
        reason=ban_data.reason, 
        duration_minutes=duration_minutes
    )
    
    # Fetch the created ban record
    ban_record = db.query(BannedIP).filter(BannedIP.ip_address == ban_data.ip_address).first()
    if not ban_record:
        raise HTTPException(status_code=400, detail="Failed to ban IP")
        
    return ban_record

@router.delete("/security/bans/{ip_address}")
def unban_ip(
    ip_address: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Unban an IP address.
    """
    ban_record = db.query(BannedIP).filter(BannedIP.ip_address == ip_address).first()
    if not ban_record:
        raise HTTPException(status_code=404, detail="IP not found in ban list")
    
    ban_record.is_active = False
    ban_record.expires_at = datetime.utcnow() # Expire immediately
    db.commit()
    
    # Note: Removing from iptables is harder because we need to find the rule number or use -D with exact match.
    # For now, we just update the DB. The SecurityService cache will update automatically.
    # If strict iptables sync is needed, we would need a shell command here too.
    
    return {"message": f"IP {ip_address} unbanned successfully"}
