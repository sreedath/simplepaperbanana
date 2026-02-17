FROM python:3.12-slim

WORKDIR /app

# Install system deps for Pillow / matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libjpeg62-turbo-dev zlib1g-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY paperbanana/ paperbanana/
COPY web/ web/
COPY prompts/ prompts/
COPY data/ data/
COPY configs/ configs/
COPY mcp_server/ mcp_server/

# Install package with web extras
RUN pip install --no-cache-dir ".[web]"

# Create outputs directory
RUN mkdir -p outputs

# Railway sets PORT env var
ENV PORT=8000

EXPOSE 8000

CMD ["python", "-m", "web.app"]
