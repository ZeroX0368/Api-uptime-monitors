
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import time
from pydantic import BaseModel
import os

app = FastAPI(title="Uptime Monitor API", version="1.0.0")

# API Key configuration
VALID_API_KEY = os.environ.get("API_KEY", "dabibanban")


def verify_api_key(apikey: str = Query(..., description="API key required for authentication")):
    """Verify the provided API key"""
    if apikey != VALID_API_KEY:
        raise HTTPException(
            status_code=401, 
            detail="Invalid or expired api key."
        )
    return apikey

# In-memory storage for monitors (in production, use a database)
monitors: Dict[str, Dict] = {}

class MonitorResponse(BaseModel):
    url: str
    status: str
    response_time: Optional[float]
    status_code: Optional[int]
    last_checked: str
    uptime_percentage: float

async def check_url_status(url: str) -> Dict:
    """Check the status of a URL"""
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            return {
                "status": "up" if response.status_code < 400 else "down",
                "status_code": response.status_code,
                "response_time": round(response_time, 2),
                "last_checked": datetime.now().isoformat(),
                "error": None
            }
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return {
            "status": "down",
            "status_code": None,
            "response_time": round(response_time, 2),
            "last_checked": datetime.now().isoformat(),
            "error": str(e)
        }

def calculate_uptime_percentage(monitor_data: Dict) -> float:
    """Calculate uptime percentage based on check history"""
    if not monitor_data.get("checks"):
        return 0.0
    
    total_checks = len(monitor_data["checks"])
    up_checks = sum(1 for check in monitor_data["checks"] if check["status"] == "up")
    
    return round((up_checks / total_checks) * 100, 2) if total_checks > 0 else 0.0

@app.get("/")
async def root():
    return {"message": "Uptime Monitor API", "version": "1.0.0", "example": "ví dụ"}

@app.get("/api/all")
async def list_all_endpoints():
    """List all available API endpoints"""
    endpoints = [
        {
            "path": "/",
            "method": "GET",
            "description": "API root - returns basic info about the API"
        },
        {
            "path": "/api/all",
            "method": "GET", 
            "description": "List all available API endpoints"
        },
        {
            "path": "/api/uptime/monitors",
            "method": "GET",
            "description": "Get all monitors or check a specific URL (use ?url= parameter)"
        },
        {
            "path": "/api/uptime/monitors/add",
            "method": "GET",
            "description": "Add a new URL to monitor (use ?url= parameter)"
        },
        {
            "path": "/api/uptime/monitors/add",
            "method": "POST",
            "description": "Add a new URL to monitor via POST request"
        },
        {
            "path": "/api/uptime/monitors/remove",
            "method": "DELETE",
            "description": "Remove a URL from monitoring (use ?url= parameter)"
        },
        {
            "path": "/api/uptime/monitors/history",
            "method": "GET",
            "description": "Get check history for a specific monitor (use ?url= parameter)"
        },
        {
            "path": "/api/uptime/stats",
            "method": "GET",
            "description": "Get overall statistics including up/down URLs"
        }
    ]
    
    return {
        "total_endpoints": len(endpoints),
        "endpoints": endpoints
    }

@app.get("/api/uptime/monitors")
async def get_monitors(url: Optional[str] = None, apikey: str = Depends(verify_api_key)):
    """Get all monitors or check a specific URL"""
    
    if url:
        # Check specific URL
        if url.startswith(("http://", "https://")):
            check_result = await check_url_status(url)
            
            # Store or update monitor data
            if url not in monitors:
                monitors[url] = {
                    "url": url,
                    "created_at": datetime.now().isoformat(),
                    "checks": []
                }
            
            # Add check to history (keep last 100 checks)
            monitors[url]["checks"].append(check_result)
            if len(monitors[url]["checks"]) > 100:
                monitors[url]["checks"] = monitors[url]["checks"][-100:]
            
            uptime_percentage = calculate_uptime_percentage(monitors[url])
            
            return MonitorResponse(
                url=url,
                status=check_result["status"],
                response_time=check_result["response_time"],
                status_code=check_result["status_code"],
                last_checked=check_result["last_checked"],
                uptime_percentage=uptime_percentage
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")
    
    # Return all monitors
    result = []
    for monitor_url, monitor_data in monitors.items():
        latest_check = monitor_data["checks"][-1] if monitor_data["checks"] else None
        if latest_check:
            result.append(MonitorResponse(
                url=monitor_url,
                status=latest_check["status"],
                response_time=latest_check["response_time"],
                status_code=latest_check["status_code"],
                last_checked=latest_check["last_checked"],
                uptime_percentage=calculate_uptime_percentage(monitor_data)
            ))
    
    return {"monitors": result, "total": len(result)}

async def add_monitor_logic(url: str):
    """Shared logic for adding monitors"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")
    
    if url in monitors:
        raise HTTPException(status_code=400, detail="URL is already being monitored")
    
    # Initial check
    check_result = await check_url_status(url)
    
    monitors[url] = {
        "url": url,
        "created_at": datetime.now().isoformat(),
        "checks": [check_result]
    }
    
    # Generate a simple ID based on timestamp
    monitor_id = str(int(time.time() * 1000))
    monitors[url]["id"] = monitor_id
    
    return {
        "id": monitor_id,
        "url": url,
        "uptime": 100.0,
        "totalChecks": 1,
        "avgResponseTime": check_result["response_time"],
        "lastCheck": {
            "timestamp": check_result["last_checked"],
            "status": check_result["status"],
            "responseTime": check_result["response_time"]
        },
        "isActive": True,
        "message": f"Monitor added for {url}"
    }

@app.get("/api/uptime/monitors/add")
async def add_monitor_get(url: str, apikey: str = Depends(verify_api_key)):
    """Add a new URL to monitor via GET request"""
    return await add_monitor_logic(url)

@app.post("/api/uptime/monitors/add")
async def add_monitor_post(url: str, background_tasks: BackgroundTasks, apikey: str = Depends(verify_api_key)):
    """Add a new URL to monitor via POST request"""
    return await add_monitor_logic(url)

@app.delete("/api/uptime/monitors/remove")
async def remove_monitor(url: str, apikey: str = Depends(verify_api_key)):
    """Remove a URL from monitoring"""
    if url not in monitors:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    del monitors[url]
    return {"message": f"Monitor removed for {url}"}

@app.get("/api/uptime/monitors/remove")
async def remove_monitor_get(url: str, apikey: str = Depends(verify_api_key)):
    """Remove a URL from monitoring via GET request"""
    if url not in monitors:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    del monitors[url]
    return {"message": f"Monitor removed for {url}"}

@app.get("/api/uptime/monitors/history")
async def get_monitor_history(url: str, limit: int = 50, apikey: str = Depends(verify_api_key)):
    """Get check history for a specific monitor"""
    if url not in monitors:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    checks = monitors[url]["checks"][-limit:]
    return {
        "url": url,
        "checks": checks,
        "total_checks": len(monitors[url]["checks"]),
        "uptime_percentage": calculate_uptime_percentage(monitors[url])
    }

@app.get("/api/uptime/stats")
async def get_stats():
    """Get overall statistics"""
    total_monitors = len(monitors)
    up_monitors = 0
    down_monitors = 0
    down_urls = []
    up_urls = []
    
    for url, monitor_data in monitors.items():
        if monitor_data["checks"]:
            latest_check = monitor_data["checks"][-1]
            latest_status = latest_check["status"]
            
            if latest_status == "up":
                up_monitors += 1
                up_urls.append({
                    "url": url,
                    "status": latest_status,
                    "response_time": latest_check["response_time"],
                    "last_checked": latest_check["last_checked"]
                })
            else:
                down_monitors += 1
                down_urls.append({
                    "url": url,
                    "status": latest_status,
                    "response_time": latest_check["response_time"],
                    "last_checked": latest_check["last_checked"],
                    "error": latest_check.get("error")
                })
    
    return {
        "total_monitors": total_monitors,
        "up_monitors": up_monitors,
        "down_monitors": down_monitors,
        "overall_uptime": round((up_monitors / total_monitors * 100), 2) if total_monitors > 0 else 0,
        "up_urls": up_urls,
        "down_urls": down_urls
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
