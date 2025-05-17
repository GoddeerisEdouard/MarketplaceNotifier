FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1
ENV USE_DOCKER_CONFIG=true
ENV PYTHONPATH=/app

WORKDIR /app
# Copy the Python webserver script
COPY ../../src/shared src/shared
COPY ../../src/api src/api
COPY ../../config config

# Install any dependencies (optional)
RUN pip install --no-cache-dir -r src/api/requirements.txt

# Expose port 5000 for the web server
EXPOSE 5000

# Command to run the web server
CMD ["python", "src/api/webserver.py"]
