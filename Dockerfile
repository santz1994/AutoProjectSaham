FROM python:3.11-slim

WORKDIR /app

# install minimal build deps then remove cache
COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get remove -y gcc \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.main"]
