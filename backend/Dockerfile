FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# python:3.13-slim has no system timezone database. business_time.py needs
# America/Phoenix from the tzdata package pinned in requirements.txt.
RUN python -c "from zoneinfo import ZoneInfo; ZoneInfo('America/Phoenix')"
COPY . .
EXPOSE 8001
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001} --proxy-headers --forwarded-allow-ips='*'"]
