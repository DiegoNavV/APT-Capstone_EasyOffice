"""Demostración del flujo completo de firma, de punta a punta.

Genera un contrato de ejemplo, lo envía a la API, registra la aceptación del
cliente, descarga el PDF firmado y lo verifica por su hash.

Uso (con los contenedores levantados):
    docker compose exec api python scripts/demo_firma.py
    docker compose cp api:/tmp/demo-contrato-firmado.pdf .
"""
import hashlib
import io
import json
import os
import sys
import time

import httpx

BASE = os.getenv("DEMO_API_URL", "http://127.0.0.1:8000/api/v1")
API_KEY = os.getenv("DEMO_API_KEY", (os.getenv("API_KEYS", "fk_test_dev-inseguro-cambiar").split(",")[0]).strip())
SALIDA = os.getenv("DEMO_SALIDA", "/tmp/demo-contrato-firmado.pdf")


def contrato_de_ejemplo(codigo: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    lineas = [
        ("Helvetica-Bold", 14, "CONTRATO DE PRESTACIÓN DE SERVICIOS (EJEMPLO)"),
        ("Helvetica", 10, f"Folio: {codigo}"),
        ("Helvetica", 10, ""),
        ("Helvetica", 10, "Entre EASY OFFICE SpA y EMPRESA DEMO SpA, representada por Juan Pérez,"),
        ("Helvetica", 10, "se acuerda la prestación de servicios de domicilio tributario."),
        ("Helvetica", 10, "Documento generado solo para pruebas. Datos ficticios."),
    ]
    y = 780
    for fuente, tam, texto in lineas:
        c.setFont(fuente, tam)
        c.drawString(60, y, texto)
        y -= 22
    c.showPage()
    c.save()
    return buffer.getvalue()


def paso(n: int, texto: str) -> None:
    print(f"\n[{n}] {texto}")


def main() -> int:
    # Folio del trámite (nunca el código de seguimiento del cliente).
    codigo = f"LF-{int(time.time()) % 10000:04d}-2026"
    headers = {"X-API-Key": API_KEY}

    paso(1, "Estado de la API")
    r = httpx.get(f"{BASE}/health/ready", timeout=10)
    print("   ", r.status_code, r.json())

    paso(2, f"Enviar contrato folio {codigo} a firmar")
    pdf = contrato_de_ejemplo(codigo)
    datos = {
        "title": "Contrato de servicio (demo)",
        "external_ref": codigo,
        "signers": [{
            "name": "Juan Pérez", "rut": "12.345.678-5",
            "represents_name": "Empresa Demo SpA", "represents_rut": "76.543.210-3",
        }],
    }
    r = httpx.post(
        f"{BASE}/documents",
        files={"file": (f"{codigo}.pdf", pdf, "application/pdf")},
        data={"data": json.dumps(datos)},
        headers={**headers, "Idempotency-Key": f"doc-{codigo}"},
        timeout=30,
    )
    if r.status_code != 201:
        print("    ERROR", r.status_code, r.text)
        return 1
    doc = r.json()
    print(f"    id={doc['id']}  status={doc['status']}")
    print(f"    SHA-256 original: {doc['original_sha256']}")

    paso(3, "El cliente acepta en el sitio web (firma electrónica simple)")
    r = httpx.post(
        f"{BASE}/documents/{doc['id']}/client-signature",
        json={"ip": "200.1.2.3", "user_agent": "Mozilla/5.0 (demo)", "consent": True},
        headers={**headers, "Idempotency-Key": f"firma-{codigo}"},
        timeout=60,
    )
    if r.status_code != 200:
        print("    ERROR", r.status_code, r.text)
        return 1
    doc = r.json()
    print(f"    status={doc['status']}  sello={doc['signature_type']}")
    for s in doc["signers"]:
        print(f"    - {s['name']} ({s['kind']}): {s['status']}")

    paso(4, "Descargar el PDF firmado")
    r = httpx.get(f"{BASE}/documents/{doc['id']}/download", headers=headers, timeout=30)
    with open(SALIDA, "wb") as f:
        f.write(r.content)
    calculado = hashlib.sha256(r.content).hexdigest()
    print(f"    Guardado en {SALIDA} ({len(r.content)} bytes)")
    print(f"    SHA-256 firmado: {calculado}  (coincide: {calculado == doc['signed_sha256']})")

    paso(5, "Verificación pública por hash (sin API key)")
    r = httpx.get(f"{BASE}/verify/{calculado}", timeout=10)
    print("   ", r.json())

    paso(6, "Bitácora de auditoría")
    r = httpx.get(f"{BASE}/documents/{doc['id']}/evidence", headers=headers, timeout=10)
    ev = r.json()
    print(f"    Cadena íntegra: {ev['chain_valid']}")
    for e in ev["events"]:
        print(f"    - {e['event_type']}  hash={e['hash'][:16]}…")

    print("\nListo. Para copiar el PDF a tu carpeta: docker compose cp api:" + SALIDA + " .")
    return 0


if __name__ == "__main__":
    sys.exit(main())
