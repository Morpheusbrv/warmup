FROM python:3.10-slim

# Instalar dependências de sistema para RIP, PDF e bibliotecas gráficas
RUN apt-get update && apt-get install -y \
    ghostscript \
    mupdf-tools \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
