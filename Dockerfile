FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# Copy and make entrypoint script executable
COPY main/xiaozhi-server/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Change working directory to xiaozhi-server
WORKDIR /app/main/xiaozhi-server

# Use entrypoint script
CMD ["/app/entrypoint.sh"]
