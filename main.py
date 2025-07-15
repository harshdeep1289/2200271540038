from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, validator, ValidationError
from typing import Optional, List
from datetime import datetime, timedelta
import string
import random
import validators
import uuid
from error_handlers import validation_exception_handler, http_exception_handler, general_exception_handler

app = FastAPI()

app.add_exception_handler(ValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

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

from logging_middleware import RequestLoggingMiddleware, get_application_logger

app.add_middleware(RequestLoggingMiddleware)
logger = get_application_logger("url_shortener")

@app.post("/shorturls", response_model=URLCreateResponse, status_code=201)
async def create_short_url(request: URLCreateRequest, http_request: Request):
    if request.shortcode:
        if request.shortcode in url_storage:
            raise HTTPException(
                status_code=409, 
                detail="Shortcode already exists"
            )
        shortcode = request.shortcode
    else:
        shortcode = generate_shortcode()
    
    validity_minutes = request.validity if request.validity is not None else 30
    expiry = datetime.utcnow() + timedelta(minutes=validity_minutes)
    
    url_record = URLRecord(request.url, shortcode, expiry)
    url_storage[shortcode] = url_record
    
    base_url = f"{http_request.url.scheme}://{http_request.url.netloc}"
    short_link = f"{base_url}/{shortcode}"
    
    return URLCreateResponse(
        shortLink=short_link,
        expiry=expiry.isoformat() + "Z"
    )

@app.get("/shorturls/{shortcode}", response_model=URLStatsResponse)
async def get_url_stats(shortcode: str):
    if shortcode not in url_storage:
        raise HTTPException(
            status_code=404, 
            detail="Shortcode not found"
        )
    
    record = url_storage[shortcode]
    
    return URLStatsResponse(
        clickCount=record.click_count,
        originalUrl=record.original_url,
        createdAt=record.created_at.isoformat() + "Z",
        expiry=record.expiry.isoformat() + "Z",
        clickDetails=record.click_details
    )

@app.get("/{shortcode}")
async def redirect_to_url(shortcode: str, request: Request):
    if shortcode not in url_storage:
        raise HTTPException(
            status_code=404, 
            detail="Shortcode not found"
        )
    
    record = url_storage[shortcode]
    
    if record.is_expired():
        raise HTTPException(
            status_code=410, 
            detail="Short link has expired"
        )
    
    referrer = request.headers.get("referer", "")
    location = get_client_location(request)
    record.add_click(referrer, location)
    
    return RedirectResponse(url=record.original_url, status_code=302)

@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "URL Shortener Microservice"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 