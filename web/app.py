"""PaperBanana Web UI — FastAPI backend with SSE streaming."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
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
    return HTMLResponse(index_path.read_text())


@app.get("/favicon.png")
async def favicon():
    return FileResponse(STATIC_DIR / "favicon.png", media_type="image/png")


@app.get("/api/health")
async def health():
    return {"ok": True}


def _resolve_api_key(header_key: str | None) -> str | None:
    if header_key:
        return header_key
    return os.environ.get("GOOGLE_API_KEY")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _image_to_data_url(image_path: str) -> str | None:
    """Read an image file and return a base64 data URL."""
    p = Path(image_path)
    if not p.exists():
        logger.warning("Image not found: %s", image_path)
        return None
    ext = p.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
    content_type = mime.get(ext, "image/png")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{content_type};base64,{b64}"


@app.post("/api/generate")
async def generate(req: GenerateRequest, x_api_key: str | None = Header(None)):
    api_key = _resolve_api_key(x_api_key)
    if not api_key:
        return JSONResponse(
            {"error": "No API key provided. Please enter your Google Gemini API key."},
            status_code=401,
        )

    async def stream():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_iteration(record):
            await queue.put(record)

        yield _sse("status", {"message": "Initializing pipeline..."})

        try:
            from paperbanana.core.config import Settings
            from paperbanana.core.pipeline import PaperBananaPipeline
            from paperbanana.core.types import DiagramType, GenerationInput

            os.environ["GOOGLE_API_KEY"] = api_key

            settings = Settings(refinement_iterations=req.iterations)
            pipeline = PaperBananaPipeline(
                settings=settings,
                on_iteration=on_iteration,
                force_all_iterations=True,
            )

            gen_input = GenerationInput(
                source_context=req.source_context,
                communicative_intent=req.communicative_intent,
                diagram_type=DiagramType(req.diagram_type),
            )

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

                # Encode image as base64 data URL — no separate request needed
                image_data_url = _image_to_data_url(record.image_path)

                critique_data = None
                if record.critique:
                    critique_data = {
                        "suggestions": record.critique.critic_suggestions,
                        "needs_revision": record.critique.needs_revision,
                        "summary": record.critique.summary,
                    }

                yield _sse("iteration", {
                    "iteration": record.iteration,
                    "image_data": image_data_url,
                    "description": record.description[:500],
                    "critique": critique_data,
                })

            result = await task

            # Final image as data URL too
            final_data_url = _image_to_data_url(result.image_path)

            yield _sse("complete", {
                "message": "Generation complete!",
                "final_image_data": final_data_url,
                "total_iterations": len(result.iterations),
            })

        except Exception as e:
            logger.exception("Generation failed")
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def main():
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
