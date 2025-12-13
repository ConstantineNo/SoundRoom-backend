import geoip2.database
from user_agents import parse
from sqlalchemy.orm import Session
from datetime import date, datetime
from app.core.config import GEOIP_DB_PATH, WHITELIST_IPS
from app.models.statistics import VisitorLog, DailyStats

class StatsService:
    _geoip_reader = None

    @classmethod
    def get_geoip_reader(cls):
        if cls._geoip_reader is None:
            try:
                cls._geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
            except FileNotFoundError:
                # print(f"GeoIP database not found at {GEOIP_DB_PATH}")
                return None
        return cls._geoip_reader

    @classmethod
    def resolve_location(cls, ip: str):
        if ip in ["127.0.0.1", "::1", "localhost"]:
            return "Local", "Local"
            
        reader = cls.get_geoip_reader()
        if not reader:
            return None, None
            
        try:
            response = reader.city(ip)
            country = response.country.names.get('zh-CN', response.country.name)
            city = response.city.names.get('zh-CN', response.city.name)
            return country, city
        except Exception:
            return None, None

    @classmethod
    def parse_device(cls, user_agent_str: str):
        user_agent = parse(user_agent_str)
        
        device_type = "pc"
        if user_agent.is_mobile:
            device_type = "mobile"
        elif user_agent.is_tablet:
            device_type = "tablet"
            
        return {
            "device_type": device_type,
            "os": user_agent.os.family,
            "browser": user_agent.browser.family
        }

    @classmethod
    def record_visit(cls, db: Session, request_info: dict):
        ip = request_info.get("ip")
        if ip in WHITELIST_IPS:
            return

        # 1. Resolve Info
        country, city = cls.resolve_location(ip)
        device_info = cls.parse_device(request_info.get("user_agent", ""))

        # 2. Save Visitor Log
        log = VisitorLog(
            ip_address=ip,
            country=country,
            city=city,
            user_agent=request_info.get("user_agent"),
            device_type=device_info["device_type"],
            os=device_info["os"],
            browser=device_info["browser"],
            request_path=request_info.get("path"),
            request_method=request_info.get("method"),
            status_code=request_info.get("status_code")
        )
        db.add(log)

        # 3. Update Daily Stats
        today = date.today()
        daily_stats = db.query(DailyStats).filter(DailyStats.date == today).first()
        
        if not daily_stats:
            daily_stats = DailyStats(date=today, pv=0, uv=0, top_urls={})
            db.add(daily_stats)
        
        daily_stats.pv += 1
        
        # Check UV (simple check: if this IP hasn't visited today)
        has_visited_today = db.query(VisitorLog).filter(
            VisitorLog.ip_address == ip,
            VisitorLog.created_at >= datetime.combine(today, datetime.min.time())
        ).first()
        
        if not has_visited_today:
            daily_stats.uv += 1

        # Update Top URLs
        current_top = dict(daily_stats.top_urls or {})
        path = request_info.get("path")
        current_top[path] = current_top.get(path, 0) + 1
        daily_stats.top_urls = current_top

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Error recording stats: {e}")
