# Dockerfile.redis_pubsub
FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1
ENV USE_DOCKER_CONFIG=true
ENV PYTHONPATH=/app
WORKDIR /app

# Copy the Redis Pub/Sub script
COPY ../../src/shared src/shared
COPY ../../src/marketplace_notifier src/marketplace_notifier
COPY ../../config config


# Install any dependencies (optional)
RUN pip install --no-cache-dir -r src/marketplace_notifier/requirements.txt

# Command to run the Redis Pub/Sub script
CMD ["python", "src/marketplace_notifier/main.py"]
