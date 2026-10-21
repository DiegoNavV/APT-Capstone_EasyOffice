FROM python:3.12-slim

# LibreOffice (solo el procesador de textos) para convertir los Word a PDF. fonts-liberation trae "Liberation Serif", que ocupa 
# el mismo espacio que Times New Roman; asi el PDF mantiene el mismo largo y saltos de pagina que el contrato en Word.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-liberation \
        fonts-dejavu-core \
        fontconfig \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]