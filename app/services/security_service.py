import time
import subprocess
from collections import defaultdict, deque
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.config import (
    WHITELIST_IPS, SENSITIVE_PATHS, 
    RATE_LIMIT_THRESHOLD_PER_SECOND, RATE_LIMIT_THRESHOLD_PER_MINUTE
)
from app.models.statistics import BannedIP

class SecurityService:
    # In-memory storage
    _request_timestamps = defaultdict(deque) # {ip: deque([timestamp, ...])}
    _sensitive_path_hits = defaultdict(int)  # {ip: count}
    _banned_ips_cache = set()
    _last_cache_update = 0

    @classmethod
    def is_banned(cls, db: Session, ip: str) -> bool:
        # Refresh cache every minute
        if time.time() - cls._last_cache_update > 60:
            cls._refresh_banned_cache(db)
        
        return ip in cls._banned_ips_cache

    @classmethod
    def _refresh_banned_cache(cls, db: Session):
        try:
            active_bans = db.query(BannedIP.ip_address).filter(
                BannedIP.is_active == True,
                (BannedIP.expires_at == None) | (BannedIP.expires_at > datetime.utcnow())
            ).all()
            cls._banned_ips_cache = {b.ip_address for b in active_bans}
            cls._last_cache_update = time.time()
        except Exception as e:
            print(f"Error refreshing ban cache: {e}")

    @classmethod
    def check_rate_limit(cls, ip: str) -> bool:
        if ip in WHITELIST_IPS:
            return True

        now = time.time()
        timestamps = cls._request_timestamps[ip]
        
        # Remove timestamps older than 1 minute
        while timestamps and timestamps[0] < now - 60:
            timestamps.popleft()
        
        timestamps.append(now)

        # Check per minute limit
        if len(timestamps) > RATE_LIMIT_THRESHOLD_PER_MINUTE:
            return False
            
        # Check per second limit (last 1 second)
        recent_requests = [t for t in timestamps if t > now - 1]
        if len(recent_requests) > RATE_LIMIT_THRESHOLD_PER_SECOND:
            return False
            
        return True

    @classmethod
    def check_sensitive_path(cls, db: Session, ip: str, path: str) -> bool:
        if ip in WHITELIST_IPS:
            return True
            
        # Check if path ends with any sensitive suffix or contains sensitive keywords
        is_sensitive = any(s in path for s in SENSITIVE_PATHS)
        
        if is_sensitive:
            cls._sensitive_path_hits[ip] += 1
            if cls._sensitive_path_hits[ip] >= 5:
                cls.ban_ip(db, ip, reason=f"Sensitive Path Scan: {path}")
                return False
        
        return True

    @classmethod
    def ban_ip(cls, db: Session, ip: str, reason: str, duration_minutes: int = None):
        if ip in WHITELIST_IPS:
            return

        # 1. Add to Database
        expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes) if duration_minutes else None
        
        try:
            existing_ban = db.query(BannedIP).filter(BannedIP.ip_address == ip).first()
            if existing_ban:
                existing_ban.is_active = True
                existing_ban.reason = reason
                existing_ban.expires_at = expires_at
                existing_ban.banned_at = datetime.utcnow()
            else:
                new_ban = BannedIP(
                    ip_address=ip,
                    reason=reason,
                    expires_at=expires_at
                )
                db.add(new_ban)
            
            db.commit()
            cls._banned_ips_cache.add(ip)
        except Exception as e:
            db.rollback()
            print(f"Error banning IP in DB: {e}")

        # 2. Execute System Command (iptables)
        # Note: This requires root privileges. 
        # If running as non-root, this will fail or needs sudo configuration.
        try:
            subprocess.run(
                ["iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"], 
                check=False # Don't raise exception if it fails (e.g. permission denied)
            )
        except FileNotFoundError:
            pass # iptables not found
