FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# sed: si el repo se clonó en Windows con finales de línea CRLF, el script
# fallaría con "no such file or directory". Se normaliza a LF.
RUN sed -i 's/\r$//' scripts/entrypoint.sh \
    && chmod +x scripts/entrypoint.sh \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser /app

# La API no corre como root dentro del contenedor.
USER appuser

EXPOSE 8000
CMD ["./scripts/entrypoint.sh"]
