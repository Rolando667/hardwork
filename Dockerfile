FROM python:3.11-slim

WORKDIR /app

# deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app
COPY backend ./backend
COPY grid_bot_calculator.html ./grid_bot_calculator.html

# non-root
RUN useradd -m bot && chown -R bot:bot /app
USER bot

EXPOSE 8000

# The container reads configuration from environment variables / a mounted .env.
# Default is dry_run (places nothing). Bind to 0.0.0.0 inside the container.
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
