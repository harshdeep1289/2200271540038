import logging
import time
import json
import uuid
import httpx
import asyncio
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Configure basic logging as fallback
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class LoggingService:
    def __init__(self):
        self.api_url = "http://20.244.56.144/evaluation-service/logs"
        self.auth_token = None
        self.client = httpx.AsyncClient(timeout=30.0)
    
    def set_auth_token(self, token: str):
        self.auth_token = token
    
    async def log_to_api(self, stack: str, level: str, package: str, message: str) -> bool:
        try:
            if not self.auth_token:
                logging.warning("No auth token available for logging API")
                return False
            
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "stack": stack.lower(),
                "level": level.lower(),
                "package": package.lower(),
                "message": message
            }
            
            response = await self.client.post(
                self.api_url,
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                return True
            else:
                logging.error(f"Failed to send log to API: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Error sending log to API: {str(e)}")
            return False
    
    async def close(self):
        await self.client.aclose()

# Global logging service instance
_logging_service = LoggingService()

def set_logging_auth_token(token: str):
    _logging_service.set_auth_token(token)

async def Log(stack: str, level: str, package: str, message: str):

    # Validate inputs
    valid_stacks = ["backend", "frontend"]
    valid_levels = ["debug", "info", "warn", "error", "fatal"]
    valid_backend_packages = [
        "cache", "controller", "cron_job", "db", "domain", 
        "handler", "repository", "route", "service"
    ]
    valid_frontend_packages = ["api"]
    valid_common_packages = ["auth", "config", "middleware", "utils"]
    
    if stack.lower() not in valid_stacks:
        logging.error(f"Invalid stack: {stack}. Must be one of {valid_stacks}")
        return
    
    if level.lower() not in valid_levels:
        logging.error(f"Invalid level: {level}. Must be one of {valid_levels}")
        return
    
    # Validate package based on stack
    all_valid_packages = valid_backend_packages + valid_frontend_packages + valid_common_packages
    if package.lower() not in all_valid_packages:
        logging.error(f"Invalid package: {package}. Must be one of {all_valid_packages}")
        return
    
    # Send to external API
    success = await _logging_service.log_to_api(stack, level, package, message)
    
    # Also log locally as fallback
    local_logger = logging.getLogger("url_shortener")
    log_entry = f"[{stack.upper()}:{package.upper()}] {message}"
    
    if level.lower() == "debug":
        local_logger.debug(log_entry)
    elif level.lower() == "info":
        local_logger.info(log_entry)
    elif level.lower() == "warn":
        local_logger.warning(log_entry)
    elif level.lower() == "error":
        local_logger.error(log_entry)
    elif level.lower() == "fatal":
        local_logger.critical(log_entry)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    
    def __init__(self, app, logger_name: str = "url_shortener"):
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        await Log(
            stack="backend",
            level="info",
            package="middleware",
            message=f"Request started: {request.method} {request.url.path} [ID: {request_id}]"
        )
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            await Log(
                stack="backend",
                level="info",
                package="middleware",
                message=f"Request completed: {request.method} {request.url.path} - Status: {response.status_code} - Time: {round(process_time, 4)}s [ID: {request_id}]"
            )
            
            response.headers["X-Request-ID"] = request_id
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            
            await Log(
                stack="backend",
                level="error",
                package="middleware",
                message=f"Request failed: {request.method} {request.url.path} - Error: {str(e)} - Time: {round(process_time, 4)}s [ID: {request_id}]"
            )
            
            raise

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

# Helper functions for different log contexts
async def log_controller(level: str, message: str):
    await Log("backend", level, "controller", message)

async def log_service(level: str, message: str):
    await Log("backend", level, "service", message)

async def log_db(level: str, message: str):
    await Log("backend", level, "db", message)

async def log_handler(level: str, message: str):
    await Log("backend", level, "handler", message)

async def log_auth(level: str, message: str):
    await Log("backend", level, "auth", message) 