# Terrain Boards generator — the Python pipeline + web editor, for Coolify.
FROM python:3.12-slim

# fonts for label rendering (Helvetica fallback -> DejaVu); curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir numpy scipy pillow matplotlib

COPY scripts/ ./scripts/
COPY data/ ./data/
COPY web/ ./web/

ENV HOST=0.0.0.0 PORT=8765 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
EXPOSE 8765

# data/ holds region configs + generated terrain/previews; mount a volume here
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS -o /dev/null http://localhost:8765/health || exit 1

CMD ["python3", "scripts/path_editor.py"]
