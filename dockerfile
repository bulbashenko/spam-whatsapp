# Usa la imagen base de Python
FROM python:3.12-slim

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar el código fuente
COPY ./backend /app

# Copiar el archivo de requerimientos
COPY requirements.txt /app/

# Instalar dependencias del sistema y Google Chrome versión 114
RUN apt-get update && \
    apt-get install -y \
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
    --no-install-recommends && \
    # Descargar e instalar Google Chrome versión 114
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    dpkg -i google-chrome-stable_current_amd64.deb && \
    apt-get install -y -f && \
    rm google-chrome-stable_current_amd64.deb && \
    # Descargar e instalar ChromeDriver versión 114
    wget https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm chromedriver_linux64.zip && \
    # Limpiar cache de apt para reducir el tamaño de la imagen
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Instalar las dependencias de Python desde requirements.txt
RUN pip install -r requirements.txt --no-deps

# Instalar greenlet versión específica
RUN pip install greenlet==3.0.3

# Establecer la variable de entorno PYTHONPATH
ENV PYTHONPATH=/app:$PYTHONPATH

# Exponer el puerto 9000
EXPOSE 9000

# Comando para iniciar la aplicación
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
