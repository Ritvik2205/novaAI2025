from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.guardrails.topic_gate import reset_topic_gate_cache
from app.routers import rag

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

configure_logging()
settings = get_settings()
reset_topic_gate_cache()

app = FastAPI(title=settings.app_name)
app.include_router(rag.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("Frontend build not found. Run `npm run build` inside frontend/.", status_code=503)
    return FileResponse(index_file)


@app.get("/health")
async def healthcheck() -> dict:
    return {"status": "ok"}
