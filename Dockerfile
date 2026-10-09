FROM python:3.14.8-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
RUN groupadd --gid 10001 bot && useradd --uid 10001 --gid bot --no-create-home bot \
    && mkdir /app/data && chown bot:bot /app/data
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
USER 10001:10001
CMD ["sh", "-c", "alembic upgrade head && exec python -m app"]
