FROM apache/airflow:2.8.1-python3.11

# Install system dependencies as root (required for Playwright)
USER root
RUN apt-get update && \
    apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Switch to airflow user (non-root) for all Python operations
USER airflow

# Copy and install ScrapAI requirements
COPY requirements.txt /tmp/scrapai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/scrapai-requirements.txt

# Install Playwright browsers as airflow user (non-root)
RUN playwright install chromium
