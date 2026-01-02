# Use a lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Cloud Run injects the PORT environment variable (default 8080)
# We use CMD to start the server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]