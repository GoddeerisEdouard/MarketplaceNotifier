# Dockerfile.redis_pubsub
FROM python:3.9-slim

WORKDIR /app
ENV PYTHONPATH="${PYTHONPATH}:/app"

# Copy the Redis Pub/Sub script
COPY . .

# Install any dependencies (optional)
RUN pip install --no-cache-dir -r requirements.txt || true

# Command to run the Redis Pub/Sub script
CMD ["python", "main.py"]
