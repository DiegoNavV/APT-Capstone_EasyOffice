"""
Prueba manual de la generación de documentos.

Crea un trámite FICTICIO con todos los datos, genera su PDF con la plantilla ACTIVA del servicio y deja el resultado en 
/tmp/prueba_documento.pdf (dentro del contenedor). Al terminar borra los datos ficticios, así no queda nada en la base.

Uso (desde Código\\easyoffice-backend):
    docker compose exec backend python scripts/probar_documento.py
    docker compose cp backend:/tmp/prueba_documento.pdf .

Opcional: indicar parte del nombre del servicio (por defecto "contrato"):
    docker compose exec backend python scripts/probar_documento.py autorizacion

Si no hay datos bancarios configurados (BANCO_TEXTO_EASY_OFFICE en el .env), usa un texto de prueba que lo dice claramente. 
NUNCA uses datos reales de personas aquí.
"""
import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DOCUMENTOS_DIR"] = "/tmp/prueba_documentos"
if not os.environ.get("BANCO_TEXTO_EASY_OFFICE", "").strip():
    os.environ["BANCO_TEXTO_EASY_OFFICE"] = "00000000 de BANCO DE PRUEBA, a nombre de su titular EMPRESA DE PRUEBA (TEXTO DE PRUEBA)"
from app import documentos, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.seguridad import ahora_utc  # noqa: E402

# Valores ficticios que identifican lo que crea esta prueba (y que _limpiar borra después).
FOLIO = "ZZZZZ-99-2099"            # cumple el formato de folio de la base (2 a 5 letras)
RUT_FICTICIO = "99999999-9"        # empresa
RUN_REPRESENTANTE = "99999998-8"
RUN_CLIENTE = "99999997-7"


def main() -> int:
    fragmento = (sys.argv[1] if len(sys.argv) > 1 else "contrato").lower()
    db = SessionLocal()
    creados = {"sucursal": None, "cliente": None, "empresa": None, "tramite": None}
    try:
        servicio = next(
            (s for s in db.query(models.ServicioContratado).filter(models.ServicioContratado.activo.is_(True)).all()
             if fragmento in s.nombre.lower()),
            None,
        )
        if servicio is None:
            print(f"No encontré un servicio activo con «{fragmento}» en su nombre.")
            return 1

        # Restos de una prueba anterior que se haya cortado a medias.
        _limpiar(db)

        sucursal = db.query(models.Sucursal).filter(models.Sucursal.activa.is_(True)).first()
        if sucursal is None:
            sucursal = models.Sucursal(
                iniciales="ZZ", nombre="Sucursal de prueba", direccion="Calle de Prueba 123, Oficina 1",
                comuna="Santiago", region="Metropolitana", rol_propiedad="000-000",
            )
            db.add(sucursal)
            creados["sucursal"] = sucursal
        responsable = db.query(models.Usuario).filter(models.Usuario.activo.is_(True)).first()
        if responsable is None:
            print("No hay ningún usuario activo para dejar como responsable. Crea uno con scripts/crear_user.py.")
            return 1
        cliente = models.Cliente(nombre="Cliente de Prueba", rut=RUN_CLIENTE, email="prueba@ejemplo.cl")
        solicitud = models.SolicitudContacto(
            nombre="Cliente de Prueba", rut=RUN_CLIENTE, email="prueba@ejemplo.cl",
            id_servicio=servicio.id_servicio, estado="convertida", fecha_cierre=ahora_utc(),
        )
        representante = models.RepresentanteLegal(
            rut=RUN_REPRESENTANTE, nombre="Persona de Prueba Ficticia",
            domicilio="Avenida Falsa 742", comuna="Santiago", region="Metropolitana",
        )
        empresa = models.Empresa(
            rut_empresa=RUT_FICTICIO, razon_social="Empresa de Prueba SpA", representante=representante,
            giro_principal="Servicios de prueba", email="prueba@ejemplo.cl", celular="912345678",
            fecha_escritura=date(2026, 1, 10), notaria="Notaría de Prueba", datos={},
        )
        db.add_all([cliente, solicitud, empresa])
        db.commit()
        creados.update(cliente=cliente, empresa=empresa)

        tramite = models.Tramite(
            id_cliente=cliente.id_cliente, id_servicio=servicio.id_servicio, id_empresa=empresa.id_empresa,
            id_usuario_responsable=responsable.id_usuario, id_solicitud_origen=solicitud.id_solicitud,
            id_sucursal=sucursal.id_sucursal, folio=FOLIO, codigo_seguimiento="PRUEBA99",
            condiciones={
                "servicios": [
                    {"id_servicio_ofrecido": 0, "nombre": "Domicilio tributario", "descripcion": "*Domicilio tributario", "precio": 59990, "ciclo_pago": "ANUAL"},
                    {"id_servicio_ofrecido": 0, "nombre": "Web mail + dominio", "descripcion": "*Web mail", "precio": 14990, "ciclo_pago": "ANUAL"},
                ],
                "duracion_meses": 12, "fecha_inicio": "2026-10-02", "fecha_vencimiento": "2027-10-01",
            },
        )
        db.add(tramite)
        db.commit()
        creados["tramite"] = tramite

        print(f"Servicio: {servicio.nombre}. Generando con la plantilla activa...")
        try:
            resultado = documentos.generar(db, tramite)
        except documentos.DocumentoNoGenerable as e:
            print(f"No se pudo generar: {e.mensaje}")
            return 1
        shutil.copy(documentos.ruta_del_documento(tramite), "/tmp/prueba_documento.pdf")
        print(f"Listo: plantilla versión {resultado['version_plantilla']}, {resultado['tamano_bytes']} bytes.")
        print("PDF en /tmp/prueba_documento.pdf (dentro del contenedor).")
        return 0
    finally:
        db.rollback()
        _limpiar(db)
        db.close()
        shutil.rmtree("/tmp/prueba_documentos", ignore_errors=True)


def _limpiar(db) -> None:
    """Borra todo lo que crea esta prueba (identificado por el folio y los RUT ficticios). El trámite de
    prueba no tiene historial, así que no choca con el trigger que impide borrar historial_estado."""
    tramite = db.query(models.Tramite).filter(models.Tramite.folio == FOLIO).first()
    if tramite:
        db.delete(tramite)
        db.commit()
    for s in db.query(models.SolicitudContacto).filter(models.SolicitudContacto.rut == RUN_CLIENTE).all():
        db.delete(s)
    empresa = db.query(models.Empresa).filter(models.Empresa.rut_empresa == RUT_FICTICIO).first()
    if empresa:
        db.delete(empresa)
        db.flush()
    for r in db.query(models.RepresentanteLegal).filter(models.RepresentanteLegal.rut == RUN_REPRESENTANTE).all():
        db.delete(r)
    for c in db.query(models.Cliente).filter(models.Cliente.rut == RUN_CLIENTE).all():
        db.delete(c)
    for s in db.query(models.Sucursal).filter(models.Sucursal.iniciales == "ZZ", models.Sucursal.nombre == "Sucursal de prueba").all():
        db.delete(s)
    db.commit()


if __name__ == "__main__":
    sys.exit(main())