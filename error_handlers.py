from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from typing import Union
import traceback

async def validation_exception_handler(request: Request, exc: ValidationError):
    errors = []
    for error in exc.errors():
        field = ".".join(str(x) for x in error["loc"])
        message = error["msg"]
        errors.append(f"{field}: {message}")
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "message": "Invalid input data",
            "details": errors
        }
    )

async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": get_error_type(exc.status_code),
            "message": exc.detail
        }
    )

async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred"
        }
    )

def get_error_type(status_code: int) -> str:
    error_types = {
        400: "Bad Request",
        404: "Not Found", 
        409: "Conflict",
        410: "Gone",
        422: "Validation Error",
        500: "Internal Server Error"
    }
    return error_types.get(status_code, "Unknown Error") 