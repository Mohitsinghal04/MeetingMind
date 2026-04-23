# ============================================================
# MeetingMind — Multi-stage Dockerfile
# Stage 1 : Node 20  → builds React UI → /app/static/
# Stage 2 : Python 3.11 → runs FastAPI + serves static files
# ============================================================

# ── Stage 1: React build ──────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --prefer-offline

COPY frontend/ .
# vite.config.js sets outDir: '../static'  →  output lands at /app/static/
RUN npm run build


# ── Stage 2: Python runtime ───────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps (psycopg2-binary needs libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy meetingmind package into /app/agents/meetingmind/
# (server.py adds /app/agents to sys.path so `import meetingmind` works)
COPY . /app/agents/meetingmind/

# Copy React build from stage 1
COPY --from=frontend-builder /app/static /app/static

EXPOSE 8080
ENV PORT=8080

CMD ["python", "/app/agents/meetingmind/server.py"]
