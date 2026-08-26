FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies required by OpenCV and PaddleOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python dependencies
COPY requirements.txt .

# Install standard CPU paddlepaddle and python packages
RUN pip install --no-cache-dir paddlepaddle==2.6.2 -i https://pypi.tuna.tsinghua.edu.cn/simple || pip install --no-cache-dir paddlepaddle==2.6.2
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source files
COPY . .

# Expose the API Gateway port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0

# Start all microservices via master runner
CMD ["python", "run_services.py"]
