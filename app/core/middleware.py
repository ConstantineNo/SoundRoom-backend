from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.background import BackgroundTask
from app.core.database import SessionLocal
from app.services.security_service import SecurityService
from app.services.stats_service import StatsService

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        path = request.url.path
        
        # Create a new DB session for security checks
        db = SessionLocal()
        try:
            # 1. Check if IP is banned
            if SecurityService.is_banned(db, ip):
                return Response(content="Access Denied", status_code=403)

            # 2. Check Rate Limit (In-Memory)
            if not SecurityService.check_rate_limit(db, ip):
                SecurityService.ban_ip(db, ip, reason="Rate Limit Exceeded", duration_minutes=60)
                return Response(content="Too Many Requests", status_code=429)

            response = await call_next(request)
            
            # 3. Post-processing for Security (404 Trap)
            if response.status_code == 404:
                if not SecurityService.check_sensitive_path(db, ip, path):
                    # If check returns False, it means they just got banned.
                    pass

            # 4. Record Statistics (Background Task)
            request_info = {
                "ip": ip,
                "path": path,
                "method": request.method,
                "user_agent": request.headers.get("user-agent"),
                "status_code": response.status_code
            }
            
            response.background = BackgroundTask(self.record_stats, request_info)
            
            return response
        finally:
            db.close()

    @staticmethod
    def record_stats(request_info: dict):
        db = SessionLocal()
        try:
            StatsService.record_visit(db, request_info)
        finally:
            db.close()
