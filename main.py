from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, validator, ValidationError
from typing import Optional, List
from datetime import datetime, timedelta
import string
import random
import validators
import uuid
import httpx
from error_handlers import validation_exception_handler, http_exception_handler, general_exception_handler

app = FastAPI()

app.add_exception_handler(ValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Authentication credentials
AUTH_CREDENTIALS = {
    "email": "harshdeep22154109@akgec.ac.in",
    "name": "harshdeep singh",
    "rollNo": "2200271540038",
    "accessCode": "uuMbyY",
    "clientID": "92a3704f-3908-4df2-94f2-a3f8e5c06175",
    "clientSecret": "dZUCRhgQhxrKxxtu"
}

class AuthResponse(BaseModel):
    token_type: str
    access_token: str
    expires_in: int

class URLCreateRequest(BaseModel):
    url: str
    validity: Optional[int] = 30
    shortcode: Optional[str] = None
    
    @validator('url')
    def validate_url(cls, v):
        if not validators.url(v):
            raise ValueError('Invalid URL format')
        return v
    
    @validator('shortcode')
    def validate_shortcode(cls, v):
        if v is not None:
            if not v.isalnum() or len(v) < 4 or len(v) > 10:
                raise ValueError('Shortcode must be alphanumeric and between 4-10 characters')
        return v

class URLCreateResponse(BaseModel):
    shortLink: str
    expiry: str

class ClickDetail(BaseModel):
    timestamp: str
    referrer: str
    location: str

class URLStatsResponse(BaseModel):
    clickCount: int
    originalUrl: str
    createdAt: str
    expiry: str
    clickDetails: List[ClickDetail]

class URLRecord:
    def __init__(self, original_url: str, shortcode: str, expiry: datetime):
        self.original_url = original_url
        self.shortcode = shortcode
        self.created_at = datetime.utcnow()
        self.expiry = expiry
        self.click_count = 0
        self.click_details = []
    
    def add_click(self, referrer: str, location: str):
        self.click_count += 1
        self.click_details.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "referrer": referrer or "Direct",
            "location": location or "Unknown"
        })
    
    def is_expired(self):
        return datetime.utcnow() > self.expiry

url_storage = {}

def generate_shortcode():
    while True:
        shortcode = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        if shortcode not in url_storage:
            return shortcode

def get_client_location(request: Request):
    return request.headers.get("CF-IPCountry", "Unknown")

from logging_middleware import RequestLoggingMiddleware, get_application_logger, set_logging_auth_token, Log, log_controller, log_service, log_auth

app.add_middleware(RequestLoggingMiddleware)
logger = get_application_logger("url_shortener")

# Global variable to store auth token
current_auth_token = None

async def get_auth_token():
    global current_auth_token
    
    auth_url = "http://20.244.56.144/evaluation-service/auth"
    
    try:
        await log_auth("info", "Requesting authentication token")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(auth_url, json=AUTH_CREDENTIALS)
            
            if response.status_code in [200, 201]:
                auth_data = response.json()
                current_auth_token = auth_data.get("access_token")
                
                # Set the token for logging middleware
                set_logging_auth_token(current_auth_token)
                
                await log_auth("info", "Authentication token obtained successfully")
                return auth_data
            else:
                await log_auth("error", f"Authentication failed: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Authentication failed: {response.text}"
                )
                
    except httpx.TimeoutException:
        await log_auth("error", "Authentication request timed out")
        raise HTTPException(
            status_code=408,
            detail="Authentication request timed out"
        )
    except Exception as e:
        await log_auth("error", f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Authentication error: {str(e)}"
        )

@app.on_event("startup")
async def startup_event():
    try:
        await get_auth_token()
        await log_controller("info", "Application started successfully with authentication")
    except Exception as e:
        await log_controller("error", f"Failed to initialize authentication: {str(e)}")

@app.post("/auth", response_model=AuthResponse)
async def authenticate():
    auth_data = await get_auth_token()
    return AuthResponse(
        token_type=auth_data.get("token_type", "Bearer"),
        access_token=auth_data.get("access_token"),
        expires_in=auth_data.get("expires_in", 1743574344)
    )

@app.post("/shorturls", response_model=URLCreateResponse, status_code=201)
async def create_short_url(request: URLCreateRequest, http_request: Request):
    await log_controller("info", f"Creating short URL for: {request.url}")
    
    if request.shortcode:
        if request.shortcode in url_storage:
            await log_controller("warn", f"Shortcode already exists: {request.shortcode}")
            raise HTTPException(
                status_code=409, 
                detail="Shortcode already exists"
            )
        shortcode = request.shortcode
        await log_controller("info", f"Using custom shortcode: {shortcode}")
    else:
        shortcode = generate_shortcode()
        await log_controller("info", f"Generated shortcode: {shortcode}")
    
    validity_minutes = request.validity if request.validity is not None else 30
    expiry = datetime.utcnow() + timedelta(minutes=validity_minutes)
    
    url_record = URLRecord(request.url, shortcode, expiry)
    url_storage[shortcode] = url_record
    
    await log_service("info", f"URL shortened successfully: {shortcode} -> {request.url}")
    
    base_url = f"{http_request.url.scheme}://{http_request.url.netloc}"
    short_link = f"{base_url}/{shortcode}"
    
    return URLCreateResponse(
        shortLink=short_link,
        expiry=expiry.isoformat() + "Z"
    )

@app.get("/shorturls/{shortcode}", response_model=URLStatsResponse)
async def get_url_stats(shortcode: str):
    await log_controller("info", f"Getting stats for shortcode: {shortcode}")
    
    if shortcode not in url_storage:
        await log_controller("warn", f"Shortcode not found: {shortcode}")
        raise HTTPException(
            status_code=404, 
            detail="Shortcode not found"
        )
    
    record = url_storage[shortcode]
    await log_service("info", f"Retrieved stats for {shortcode}: {record.click_count} clicks")
    
    return URLStatsResponse(
        clickCount=record.click_count,
        originalUrl=record.original_url,
        createdAt=record.created_at.isoformat() + "Z",
        expiry=record.expiry.isoformat() + "Z",
        clickDetails=record.click_details
    )

@app.get("/{shortcode}")
async def redirect_to_url(shortcode: str, request: Request):
    await log_controller("info", f"Redirecting shortcode: {shortcode}")
    
    if shortcode not in url_storage:
        await log_controller("warn", f"Shortcode not found for redirect: {shortcode}")
        raise HTTPException(
            status_code=404, 
            detail="Shortcode not found"
        )
    
    record = url_storage[shortcode]
    
    if record.is_expired():
        await log_controller("warn", f"Expired shortcode accessed: {shortcode}")
        raise HTTPException(
            status_code=410, 
            detail="Short link has expired"
        )
    
    referrer = request.headers.get("referer", "")
    location = get_client_location(request)
    record.add_click(referrer, location)
    
    await log_service("info", f"Successful redirect: {shortcode} -> {record.original_url}")
    
    return RedirectResponse(url=record.original_url, status_code=302)

@app.get("/")
async def health_check():
    await log_controller("info", "Health check requested")
    return {"status": "healthy", "service": "URL Shortener Microservice"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 