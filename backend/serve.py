from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import uvicorn
from typing import Optional
from datetime import datetime
import httpx
import logging

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Skillsync - Engineering Talent Analyzer")

# Ensure templates and static directories exist
os.makedirs("frontend", exist_ok=True)
os.makedirs("frontend/static", exist_ok=True)

templates = Jinja2Templates(directory="frontend")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Jinja2 filters

def format_datetime(timestamp):
    if isinstance(timestamp, (int, float)):
        if timestamp > 1000000000000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    return timestamp

templates.env.filters['datetime'] = format_datetime

def format_time(hours: Optional[float]) -> str:
    if hours is None:
        return "N/A"
    try:
        total_seconds = int(hours * 3600)
        days, remainder = divmod(total_seconds, 86400)
        hrs, remainder = divmod(remainder, 3600)
        mins, _ = divmod(remainder, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hrs > 0:
            parts.append(f"{hrs}h")
        if mins > 0 and days == 0:
            parts.append(f"{mins}m")
        return " ".join(parts) if parts else "< 1m"
    except (ValueError, TypeError):
        return "N/A"

templates.env.globals['format_time'] = format_time
templates.env.filters['format_time'] = format_time

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, error: Optional[str] = None):
    """Render the home page with the chat interface."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "error": error}
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render a blank dashboard page (can be filled by chat or prompt)."""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )

@app.post("/process-prompt", response_class=HTMLResponse)
async def process_prompt_endpoint(
    request: Request,
    prompt_input: str = Form(...),
    model: str = Form("fast")
):
    """Process prompt and return dashboard HTML."""
    try:
        logger.info("Prompt: " + prompt_input)
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                "http://localhost:8080/process",
                json={"prompt": prompt_input, "model": model},
                timeout=120
            )
            response.raise_for_status()
            result = response.text
            # Clean up escaped characters
            result = result.replace("\\n", "\n")\
                        .replace("\\t", "\t")\
                        .replace("\\r", "\r")\
                        .replace("\\\"", '"')\
                        .replace("\\'", "'")\
                        .replace("\\\\", "\\")
            if result.startswith("\""):
                result = result[1:-1]
            logger.info(result)

        # Render the dashboard HTML
        dashboard_template = templates.env.from_string(result)
        dashboard_html = dashboard_template.render(request=request)
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "dashboard_html": dashboard_html
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "error": f"Error processing prompt: {str(e)}"
            }
        )

@app.get("/health")
async def health():
    from fastapi.responses import Response
    return Response(content="Health is good!", status_code=418)

@app.get("/prompt", response_class=HTMLResponse)
async def prompt(request: Request):
    return templates.TemplateResponse("prompt.html", {"request": request})

if __name__ == "__main__":
    uvicorn.run("serve:app", host="0.0.0.0", port=8000, reload=True) 