# Python 3.10 tabanlı bir imaj kullanıyoruz
FROM python:3.10-slim

# Ortam değişkenleri
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Gerekli sistem paketlerini yükle
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Çalışma dizini
WORKDIR /app

# Gerekli dosyaları kopyala
COPY . /app/

# Bağımlılıkları yükle
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Uygulamanın dışa açılacağı port
EXPOSE 8181

# Uygulama başlat
CMD ["python", "server.py"]
