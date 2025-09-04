# Python 3.9 slim image untuk Railway
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install depedensi sistem untuk OpenCV dan MediaPipe
RUN apt-get update && apt-get install -y \
    python3-pip \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgstreamer1.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install depedensi Python
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# Copy kode aplikasi ke dalam kontainer
COPY . .

# Buat direktori yang diperlukan
RUN mkdir -p static/uploads static/detected static/reports static/recordings templates

# Environment variables untuk Railway
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1

# Railway akan mengatur port otomatis
CMD ["python", "app.py"]
