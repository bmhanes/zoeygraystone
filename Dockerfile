FROM python:3.12-slim

WORKDIR /zoey/app

RUN apt-get update && apt-get install -y \
    gcc \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY zoeycore/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY zoeycore/main.py .
COPY zoeycore/auth.py .
COPY pwa /zoey/pwa

RUN mkdir -p /zoey/logs /zoey/backups

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
