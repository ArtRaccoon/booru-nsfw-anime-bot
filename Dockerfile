FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data
CMD ["python", "-m", "app.bot"]
