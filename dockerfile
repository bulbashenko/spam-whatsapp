FROM python:3.12-slim

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
    libappindicator3-1 \
    libindicator7 \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i google-chrome-stable_current_amd64.deb \
    && apt-get install -y -f \
    && rm google-chrome-stable_current_amd64.deb

RUN LATEST_CHROMEDRIVER_VERSION=$(wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE) \
    && wget https://chromedriver.storage.googleapis.com/$LATEST_CHROMEDRIVER_VERSION/chromedriver_linux64.zip \
    && unzip chromedriver_linux64.zip \
    && mv chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm chromedriver_linux64.zip

ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV PATH=$PATH:/usr/local/bin

WORKDIR /app

COPY ./backend /app

COPY requirements.txt /app/

RUN pip install -r requirements.txt --no-deps

RUN pip install greenlet==3.0.3

ENV PYTHONPATH=/app:$PYTHONPATH

EXPOSE 9000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
