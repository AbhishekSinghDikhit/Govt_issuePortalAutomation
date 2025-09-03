#!/bin/bash
# Install Playwright dependencies (Chromium + system libs)
playwright install --with-deps chromium

# Run FastAPI app
exec uvicorn main:app --host 0.0.0.0 --port $PORT