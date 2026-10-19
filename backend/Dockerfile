FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1 && pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m app
COPY . .
USER app
EXPOSE 8000
CMD ["python", "-m", "app.serve"]
