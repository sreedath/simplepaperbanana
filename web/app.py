"""PaperBanana Web UI — FastAPI backend with SSE streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("paperbanana.web")

app = FastAPI(title="PaperBanana Web UI")

STATIC_DIR = Path(__file__).parent / "static"
logger.info("STATIC_DIR=%s exists=%s", STATIC_DIR, STATIC_DIR.exists())
logger.info("index.html exists=%s", (STATIC_DIR / "index.html").exists())
OUTPUT_DIR = Path("outputs")

# In-memory mapping of web run_id -> pipeline run_id (for image serving)
_run_dirs: dict[str, Path] = {}


class GenerateRequest(BaseModel):
    source_context: str
    communicative_intent: str
    diagram_type: str = "methodology"
    iterations: int = 3


@app.on_event("startup")
async def startup():
    logger.info("App starting, PORT=%s", os.environ.get("PORT", "not set"))


@app.get("/")
async def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(f"<h1>index.html not found at {index_path}</h1>", status_code=500)
    html = index_path.read_text()
    return HTMLResponse(html)


@app.get("/api/health")
async def health():
    return {"ok": True}


def _resolve_api_key(header_key: str | None) -> str | None:
    """Resolve API key: prefer per-request header, fall back to server env."""
    if header_key:
        return header_key
    return os.environ.get("GOOGLE_API_KEY")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/generate")
async def generate(req: GenerateRequest, x_api_key: str | None = Header(None)):
    api_key = _resolve_api_key(x_api_key)
    if not api_key:
        return JSONResponse(
            {"error": "No API key provided. Please enter your Google Gemini API key."},
            status_code=401,
        )

    async def stream():
        run_id = uuid.uuid4().hex[:12]
        queue: asyncio.Queue = asyncio.Queue()

        async def on_iteration(record):
            await queue.put(record)

        yield _sse("status", {"message": "Initializing pipeline..."})

        try:
            from paperbanana.core.config import Settings
            from paperbanana.core.pipeline import PaperBananaPipeline
            from paperbanana.core.types import DiagramType, GenerationInput

            # Set key in env for this request so providers can pick it up
            os.environ["GOOGLE_API_KEY"] = api_key

            settings = Settings(refinement_iterations=req.iterations)
            pipeline = PaperBananaPipeline(
                settings=settings,
                on_iteration=on_iteration,
                force_all_iterations=True,
            )

            _run_dirs[run_id] = pipeline._run_dir

            gen_input = GenerationInput(
                source_context=req.source_context,
                communicative_intent=req.communicative_intent,
                diagram_type=DiagramType(req.diagram_type),
            )

            # Run pipeline in background task so we can stream iterations
            task = asyncio.create_task(pipeline.generate(gen_input))

            yield _sse("status", {"message": "Planning diagram (this may take a minute)..."})

            while not task.done() or not queue.empty():
                try:
                    record = await asyncio.wait_for(queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    if task.done():
                        break
                    yield ": keepalive\n\n"
                    continue

                yield _sse("status", {
                    "message": f"Completed iteration {record.iteration}/{req.iterations}"
                })

                image_name = Path(record.image_path).name
                image_url = f"/api/images/{run_id}/{image_name}"

                critique_data = None
                if record.critique:
                    critique_data = {
                        "suggestions": record.critique.critic_suggestions,
                        "needs_revision": record.critique.needs_revision,
                        "summary": record.critique.summary,
                    }

                yield _sse("iteration", {
                    "iteration": record.iteration,
                    "image_url": image_url,
                    "description": record.description[:500],
                    "critique": critique_data,
                })

            result = await task

            final_name = Path(result.image_path).name
            final_url = f"/api/images/{run_id}/{final_name}"

            yield _sse("complete", {
                "message": "Generation complete!",
                "final_image_url": final_url,
                "run_id": run_id,
                "total_iterations": len(result.iterations),
            })

        except Exception as e:
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/images/{run_id}/{filename}")
async def serve_image(run_id: str, filename: str):
    run_dir = _run_dirs.get(run_id)
    if not run_dir:
        if OUTPUT_DIR.exists():
            for d in OUTPUT_DIR.iterdir():
                candidate = d / filename
                if candidate.exists():
                    return FileResponse(candidate)
        return JSONResponse({"error": "not found"}, status_code=404)

    for path in [run_dir / filename, *run_dir.glob(f"*/{filename}")]:
        if path.exists():
            return FileResponse(path)

    return JSONResponse({"error": "not found"}, status_code=404)


def main():
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
