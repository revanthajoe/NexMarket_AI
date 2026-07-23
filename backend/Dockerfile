FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 + ML
RUN apt-get update && apt-get install -y \
    gcc g++ libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p assets/posters ml/lstm ml/xgboost_model

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
