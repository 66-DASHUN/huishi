FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Validate reference media and generated videos before persisting assets.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./

RUN addgroup --system --gid 10001 huishi \
    && adduser --system --uid 10001 --ingroup huishi --home /nonexistent --no-create-home huishi \
    && mkdir -p /var/lib/huishi/uploads /var/log/huishi /var/backups/huishi/postgres \
    && chown -R huishi:huishi /var/lib/huishi /var/log/huishi /var/backups/huishi

USER huishi
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "--timeout", "240", "-b", "0.0.0.0:8000", "wsgi:app"]
