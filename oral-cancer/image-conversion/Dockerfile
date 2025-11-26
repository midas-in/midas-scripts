FROM python:3.11-slim
# Install necessary system packages and build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    libopenjp2-7-dev \
    libtiff-dev \
    libopenslide0 \
    libopenslide-dev \
    libturbojpeg0-dev \
    && rm -rf /var/lib/apt/lists/*
# Copy application code
COPY . /app
WORKDIR /app
# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
# Set environment variables for TurboJPEG
ENV LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH

CMD ["python3", "-m", "http.server", "2001"]
