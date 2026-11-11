FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shopbot ./shopbot
COPY commerce_api ./commerce_api
COPY alembic.ini ./alembic.ini

CMD ["python", "-m", "shopbot"]
