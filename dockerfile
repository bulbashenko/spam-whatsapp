# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Install required system dependencies for Chrome and ChromeDriver
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    libx11-dev \
    libxss1 \
    libappindicator3-1 \
    libgdk-pixbuf2.0-0 \
    libnss3 \
    libasound2 \
    fonts-liberation \
    libgbm1 \
    libvulkan1 \
    xdg-utils \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i google-chrome-stable_current_amd64.deb \
    && apt-get install -y -f \
    && rm google-chrome-stable_current_amd64.deb

# Install ChromeDriver (make sure the version matches the Chrome version)
RUN LATEST_CHROMEDRIVER_VERSION=$(wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE) \
    && wget https://chromedriver.storage.googleapis.com/$LATEST_CHROMEDRIVER_VERSION/chromedriver_linux64.zip \
    && unzip chromedriver_linux64.zip \
    && mv chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm chromedriver_linux64.zip

# Set environment variables for Chrome and ChromeDriver
ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV PATH=$PATH:/usr/local/bin

# Set the working directory
WORKDIR /app

# Copy the backend code into the container
COPY ./backend /app

# Copy the requirements.txt file and install Python dependencies
COPY requirements.txt /app/

RUN pip install -r requirements.txt --no-deps

# Install additional Python dependencies
RUN pip install greenlet==3.0.3

# Set Python path to include the app
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose the FastAPI application port
EXPOSE 9000

# Command to run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
