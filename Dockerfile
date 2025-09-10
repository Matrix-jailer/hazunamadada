# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Expose the port
EXPOSE 10000

# Start command
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]
