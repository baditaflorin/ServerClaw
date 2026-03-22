FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8081

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 8081 --workers ${UVICORN_WORKERS:-1}"]
