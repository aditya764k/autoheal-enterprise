FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# The Docker socket is mounted at runtime via docker-compose volume:
#   volumes:
#     - /var/run/docker.sock:/var/run/docker.sock
CMD ["python", "monitor.py"]
