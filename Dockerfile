FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5050

CMD ["sh", "-c", "gunicorn --worker-class gthread --threads ${WEB_THREADS:-20} --bind 0.0.0.0:${PORT:-5050} backend.main:app"]
