<table align="center" width="100%" style="border: none; border-collapse: collapse;">
  <tr>
    <td width="220" align="left" valign="middle" style="border: none;">
      <img src="https://dwzhu-pku.github.io/PaperBanana/static/images/logo.jpg" alt="PaperBanana Logo" width="180"/>
    </td>
    <td align="left" valign="middle" style="border: none;">
      <h1>Simple PaperBanana</h1>
      <p><strong>A lightweight web frontend for PaperBanana</strong></p>
      <p>
        <a href="https://arxiv.org/abs/2601.23265"><img src="https://img.shields.io/badge/arXiv-2601.23265-b31b1b?logo=arxiv&logoColor=white" alt="arXiv"/></a>
        <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+"/></a>
        <a href="https://ai.google.dev/"><img src="https://img.shields.io/badge/Gemini-Free%20Tier-4285F4?logo=google&logoColor=white" alt="Gemini Free Tier"/></a>
        <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?logo=opensourceinitiative&logoColor=white" alt="License: MIT"/></a>
        <br/>
        <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI"/></a>
        <a href="https://railway.app"><img src="https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway&logoColor=white" alt="Railway"/></a>
      </p>
    </td>
  </tr>
</table>

---

> **What is this?** This repo is a **simple web frontend wrapper** for [PaperBanana](https://arxiv.org/abs/2601.23265), the agentic academic illustration system developed by Google Research. It provides a browser-based UI so anyone can generate publication-ready scientific diagrams without touching the command line. The original PaperBanana model, research, and pipeline architecture were created by Dawei Zhu, Rui Meng, Yale Song, Xiyu Wei, Sujian Li, Tomas Pfister, and Jinsung Yoon at Google.

> This project is **not affiliated with or endorsed by** the original authors or Google Research.
> The underlying implementation is based on the [community open-source version](https://github.com/llmsresearch/paperbanana) of the paper.

---

## What It Does

Simple PaperBanana wraps the full PaperBanana pipeline in a clean web interface:

1. **Paste** your methodology text and figure caption
2. **Click Generate** and watch as the 5-agent pipeline iterates
3. **View all iterations** side by side with critic feedback
4. **Download** any generated diagram as PNG

Under the hood, the pipeline runs 5 specialized agents across two phases:

| Phase | Agent | Role |
|-------|-------|------|
| Planning | **Retriever** | Finds the most relevant reference illustrations |
| Planning | **Planner** | Generates a detailed textual description of the diagram |
| Planning | **Stylist** | Refines the description for visual aesthetics |
| Refinement | **Visualizer** | Renders the description into an image via Gemini |
| Refinement | **Critic** | Evaluates the image and suggests revisions |

The Visualizer-Critic loop repeats for up to 3 iterations, progressively improving the output.

<p align="center">
  <img src="assets/img/hero_image.png" alt="PaperBanana takes paper as input and provides diagram as output" style="max-width: 960px; width: 100%; height: auto;"/>
</p>

---

## Live Demo

Try it now (bring your own free Google Gemini API key):

**[paperbanana.vizuara.ai](https://paperbanana.vizuara.ai)**

Your API key is stored only in your browser's localStorage and is never persisted on the server.

---

## Run Locally

### Prerequisites

- Python 3.10+
- A free [Google Gemini API key](https://makersuite.google.com/app/apikey)

### Setup

```bash
git clone https://github.com/VizuaraAI/simplepaperbanana.git
cd simplepaperbanana

pip install -e ".[web]"

cp .env.example .env
# Edit .env and add: GOOGLE_API_KEY=your-key-here
```

### Run

```bash
python -m uvicorn web.app:app --port 8000
```

Open **http://localhost:8000** in your browser.

---

## Deploy to Railway

This repo is ready to deploy on [Railway](https://railway.app) with zero configuration:

1. Fork this repo
2. Connect it to a new Railway project
3. Railway auto-detects the `Dockerfile` and deploys

The app reads `PORT` from the environment (Railway sets this automatically). No environment variables are required on the server -- users provide their own API keys via the browser UI.

### Files for deployment

| File | Purpose |
|------|---------|
| `Dockerfile` | Python 3.12 slim image, installs deps, runs uvicorn |
| `railway.toml` | Dockerfile builder config, health check at `/api/health` |
| `.dockerignore` | Excludes `.env`, `outputs/`, tests, etc. |

---

## Architecture

```
simplepaperbanana/
├── web/
│   ├── app.py                 # FastAPI backend (~200 lines)
│   │   ├── GET  /             # Serves the single-page frontend
│   │   ├── GET  /api/health   # Health check
│   │   ├── GET  /api/recent   # Lists recent generation runs
│   │   ├── GET  /api/images/  # Serves generated images
│   │   └── POST /api/generate # SSE-streamed generation pipeline
│   └── static/
│       └── index.html         # Single-file frontend (HTML + CSS + JS)
├── paperbanana/               # Core pipeline (from upstream)
│   ├── agents/                # Retriever, Planner, Stylist, Visualizer, Critic
│   ├── core/                  # Pipeline orchestration, config, types
│   └── providers/             # Gemini VLM + image generation
├── Dockerfile                 # Production container
├── railway.toml               # Railway deployment config
└── tests/
    └── test_web_ui.py         # Automated web UI test suite (41 tests)
```

### How streaming works

The frontend sends a `POST /api/generate` request. The backend runs the pipeline as an async task and streams progress via **Server-Sent Events (SSE)**:

- `event: status` -- Phase updates ("Planning diagram...", "Completed iteration 2/3")
- `event: iteration` -- Completed iteration with image URL and critic feedback
- `event: complete` -- Generation finished
- `event: error` -- Something went wrong

Images are served via a dedicated `/api/images/` endpoint (not embedded in SSE) for reliability. If the SSE connection drops (common on cloud platforms), the frontend automatically polls for results.

---

## API Key Security

- API keys are stored **only in the user's browser** (`localStorage`)
- Keys are sent per-request via the `X-Api-Key` HTTP header
- The server never persists or logs API keys
- The server can optionally use a `GOOGLE_API_KEY` environment variable as a fallback (useful for local development)

---

## CLI and Python API

This repo also includes the full PaperBanana CLI and Python API from the [upstream implementation](https://github.com/llmsresearch/paperbanana):

```bash
# Generate a diagram from the command line
paperbanana generate \
  --input method.txt \
  --caption "Overview of our encoder-decoder architecture"

# Generate a statistical plot
paperbanana plot \
  --data results.csv \
  --intent "Bar chart comparing model accuracy"
```

```python
import asyncio
from paperbanana import PaperBananaPipeline, GenerationInput, DiagramType

pipeline = PaperBananaPipeline()
result = asyncio.run(pipeline.generate(
    GenerationInput(
        source_context="Our framework consists of...",
        communicative_intent="Overview of the proposed method.",
        diagram_type=DiagramType.METHODOLOGY,
    )
))
print(f"Output: {result.image_path}")
```

See the [upstream repo](https://github.com/llmsresearch/paperbanana) for full CLI reference, MCP server setup, and configuration options.

---

## Citation

If you use this work, please cite the **original paper**:

```bibtex
@article{zhu2026paperbanana,
  title={PaperBanana: Automating Academic Illustration for AI Scientists},
  author={Zhu, Dawei and Meng, Rui and Song, Yale and Wei, Xiyu
          and Li, Sujian and Pfister, Tomas and Yoon, Jinsung},
  journal={arXiv preprint arXiv:2601.23265},
  year={2026}
}
```

**Original paper**: [arxiv.org/abs/2601.23265](https://arxiv.org/abs/2601.23265)

---

## Disclaimer

This project is a frontend wrapper built on top of an independent open-source reimplementation of the PaperBanana paper. It is not affiliated with, endorsed by, or connected to the original authors, Google Research, or Peking University. The underlying implementation may differ from the original system described in the paper. Use at your own discretion.

## License

MIT
