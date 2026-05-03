FROM python:3.12-slim

WORKDIR /zoey/app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Create required directories
RUN mkdir -p /zoey/pwa /zoey/logs /zoey/backups

EXPOSE 8000

# No --reload flag: hot reload causes uvicorn path crashes in Docker
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
