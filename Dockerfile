FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get update && apt-get install -y chromium-driver chromium && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"] 