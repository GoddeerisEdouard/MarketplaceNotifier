# Use the official Redis image from Docker Hub
FROM redis:latest

# Expose the default Redis port
EXPOSE 6379

# Run the Redis server
CMD ["redis-server"]
