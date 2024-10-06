FROM python:3.9-slim

WORKDIR /app
ENV PYTHONPATH="${PYTHONPATH}:/app"
ENV USE_DOCKER_CONFIG=true

# Copy the Python webserver script
COPY . .

# Install any dependencies (optional)
RUN pip install --no-cache-dir -r /app/api/src/api/requirements.txt || true

# Expose port 5000 for the web server
EXPOSE 5000

# Command to run the web server
CMD ["python", "/app/api/src/api/webserver.py"]
