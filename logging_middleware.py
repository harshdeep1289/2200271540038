import logging
import time
import json
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    
    def __init__(self, app, logger_name: str = "url_shortener"):
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        request_data = self._log_request_basic(request, request_id)
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            response_data = self._log_response_basic(response, process_time)
            
            log_data = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "processing_time_seconds": round(process_time, 4)
            }
            
            self.logger.info(f"Request completed: {json.dumps(log_data)}")
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            error_data = {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "processing_time_seconds": round(process_time, 4),
                "error": str(e)
            }
            
            self.logger.error(f"Request failed: {json.dumps(error_data)}")
            raise
    
    def _log_request_basic(self, request: Request, request_id: str) -> dict:
        return {
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown")
        }
    
    def _log_response_basic(self, response: Response, process_time: float) -> dict:
        return {
            "status_code": response.status_code,
            "processing_time_seconds": round(process_time, 4)
        }

def get_application_logger(name: str = "url_shortener") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger 