# Gunakan Node.js v20 sebagai dasar (untuk naracli)
FROM node:20-slim

# Install Python 3 dan Pip
RUN apt-get update && apt-get install -y python3 python3-pip

# Setel direktori kerja di dalam server
WORKDIR /app

# Install naracli secara global
RUN npm install -g naracli@latest

# Salin semua file bot Anda ke dalam server
COPY . .

# Install pustaka Python (Flask, dll)
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Buka jalur komunikasi web
EXPOSE 5000

# Perintah utama untuk menyalakan bot
CMD ["python3", "app.py"]
