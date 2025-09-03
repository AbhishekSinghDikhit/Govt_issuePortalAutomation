#!/bin/bash
# Install Playwright dependencies (Chromium)
playwright install chromium

# Run FastAPI app
exec uvicorn main:app --host 0.0.0.0 --port $PORT