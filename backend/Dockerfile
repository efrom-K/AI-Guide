# AI Audio Guide backend — FastAPI + uvicorn, optional local Whisper STT.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp1: OpenMP runtime needed by ctranslate2 (faster-whisper).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies (incl. the optional STT extra). Copying the source the
# package needs first keeps the build self-contained.
COPY pyproject.toml ./
COPY app ./app
COPY sim ./sim
COPY prompts ./prompts
COPY web ./web
# Editable install: keeps the source tree in place so prompts.py resolves
# /app/prompts via __file__ (it would point into site-packages otherwise).
RUN pip install -e ".[stt]"

EXPOSE 8000

# Bind 0.0.0.0 so the phone on the LAN can reach it.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
