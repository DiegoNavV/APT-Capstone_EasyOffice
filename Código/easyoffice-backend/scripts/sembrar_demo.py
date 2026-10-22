"""Siembra datos de DEMO (ficticios) para poder navegar el panel con información real:
solicitudes, trámites en distintos estados, un par de empresas y dos cuentas con las
que iniciar sesión. Nunca se corre solo -- es manual, para desarrollo/demo.

Uso (con los contenedores levantados):
    docker compose exec backend python scripts/sembrar_demo.py

Se puede correr más de una vez: busca por correo/RUT antes de crear, así que no
duplica las cuentas de demo (los trámites y solicitudes sí se agregan de nuevo
cada vez que se corre -- es intencional, para ir sumando volumen).
"""
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crud, models, schemas  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.seguridad import hash_password  # noqa: E402

PASSWORD_DEMO = "DemoEasyOffice123!"

NOMBRES = [
    "Javiera", "Matías", "Francisca", "Benjamín", "Catalina", "Sebastián", "Antonia", "Tomás",
    "Valentina", "Joaquín", "Camila", "Diego", "Fernanda", "Vicente", "Martina", "Ignacio",
    "Josefa", "Felipe", "Constanza", "Agustín",
]
APELLIDOS = [
    "González", "Muñoz", "Rojas", "Díaz", "Pérez", "Soto", "Contreras", "Silva",
    "Martínez", "Sepúlveda", "Morales", "Araya", "Fuentes", "Torres", "Reyes", "Flores",
]
EMPRESAS = [
    "Panadería El Buen Pan", "Estudio Jurídico Andes", "Taller Mecánico Rengo", "Clínica Veterinaria Austral",
    "Diseño Studio Nómade", "Comercializadora del Sur", "Ferretería La Esquina", "Consultora Horizonte",
]


def _rut(cuerpo: int) -> str:
    """RUT con dígito verificador real (módulo 11), para que la demo se vea auténtica."""
    suma, mult = 0, 2
    for d in reversed(str(cuerpo)):
        suma += int(d) * mult
        mult = mult + 1 if mult < 7 else 2
    resto = 11 - (suma % 11)
    dv = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    return f"{cuerpo}-{dv}"


def _persona(n: int) -> dict:
    nombre = f"{random.choice(NOMBRES)} {random.choice(APELLIDOS)}"
    return {
        "nombre": nombre,
        # Aleatorio (no determinístico por n): así cada corrida genera gente
        # distinta en vez de siempre los mismos 18 RUT.
        "rut": _rut(random.randint(10_000_000, 24_999_999)),
        "email": f"{nombre.lower().replace(' ', '.')}{n}.{random.randint(100, 999)}@correo-demo.cl",
        "telefono": f"+569{random.randint(10_000_000, 99_999_999)}",
    }


def _rut_empresa_nuevo(db) -> str:
    """rut_empresa es UNIQUE y, a diferencia de cliente (que crud.py reutiliza
    por RUT si ya existe), acá no hay reuso -- si se repite, la segunda corrida
    del script revienta. Se verifica contra la base antes de usarlo."""
    for _ in range(50):
        candidato = _rut(random.randint(76_000_000, 79_999_999))
        if not db.query(models.Empresa).filter_by(rut_empresa=candidato).first():
            return candidato
    raise RuntimeError("No se pudo generar un RUT de empresa único para la demo.")


def _usuario_demo(db, nombre: str, email: str, rol: str) -> models.Usuario:
    u = db.query(models.Usuario).filter_by(email=email).first()
    if u:
        return u
    r = db.query(models.Rol).filter_by(nombre=rol).first()
    u = models.Usuario(nombre=nombre, email=email, password_hash=hash_password(PASSWORD_DEMO), rol=r, activo=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def main() -> None:
    db = SessionLocal()

    servicios = db.query(models.ServicioContratado).filter_by(activo=True).all()
    sucursales = db.query(models.Sucursal).filter_by(activa=True).all()
    servicios_ofrecidos = db.query(models.ServicioOfrecido).filter_by(activo=True).all()
    if not servicios:
        print("No hay servicio_contratado activo -- corre primero db/init/02_seed.sql.")
        raise SystemExit(1)

    agente = _usuario_demo(db, "Rocío Agente Demo", "agente.demo@easyoffice.cl", "agente")
    admin = _usuario_demo(db, "Marco Admin Demo", "admin.demo@easyoffice.cl", "administrador")
    responsables = [agente, admin]

    # ---- Solicitudes: unas quedan pendientes, el resto se convierte a trámite ----
    N_PENDIENTES = 5
    N_CONVERTIDAS = 13
    creadas, convertidas = 0, 0

    for n in range(N_PENDIENTES):
        p = _persona(n)
        crud.crear_solicitud(db, schemas.SolicitudContactoCreate(
            nombre=p["nombre"], rut=p["rut"], email=p["email"], telefono=p["telefono"],
            servicio_id=random.choice(servicios).id_servicio,
            mensaje="Quiero formalizar mi emprendimiento.",
        ))
        creadas += 1

    ESTADOS_SIMULADOS = ["generado", "en_revision", "procesando_firma", "firmado", "entregado"]

    for n in range(N_PENDIENTES, N_PENDIENTES + N_CONVERTIDAS):
        p = _persona(n)
        servicio = random.choice(servicios)
        solicitud = crud.crear_solicitud(db, schemas.SolicitudContactoCreate(
            nombre=p["nombre"], rut=p["rut"], email=p["email"], telefono=p["telefono"],
            servicio_id=servicio.id_servicio,
            mensaje="Contrata aquí -- demo.",
        ))
        creadas += 1

        responsable = random.choice(responsables)
        sucursal = random.choice(sucursales) if sucursales and random.random() < 0.4 else None
        condiciones = None
        if sucursal and servicios_ofrecidos:
            elegido = random.choice(servicios_ofrecidos)
            condiciones = schemas.CondicionesIn(
                servicios=[schemas.ServicioCondicionIn(
                    id_servicio_ofrecido=elegido.id_servicio_ofrecido,
                    precio=elegido.precio_referencia or 50_000,
                    ciclo_pago=elegido.ciclo_pago_defecto or "ANUAL",
                )],
                duracion_meses=12,
                fecha_inicio=date.today(),
            )

        try:
            tramite = crud.convertir_solicitud_a_tramite(
                db, solicitud, responsable.id_usuario, sucursal=sucursal, condiciones=condiciones,
            )
        except crud.ConflictoDeFolio:
            tramite = crud.convertir_solicitud_a_tramite(db, solicitud, responsable.id_usuario)
        convertidas += 1

        # Simula avance de estado + fechas repartidas en los últimos 20 días, para
        # que los KPIs y Reportes muestren una distribución real, no todo "hoy".
        estado_final = random.choice(ESTADOS_SIMULADOS)
        idx_final = ESTADOS_SIMULADOS.index(estado_final)
        hace = timedelta(days=random.randint(0, 20))
        fecha_base = datetime.now(timezone.utc).replace(tzinfo=None) - hace

        tramite.estado_actual = estado_final
        tramite.fecha_creacion = fecha_base
        tramite.fecha_actualizacion = fecha_base + timedelta(hours=idx_final * 6)
        # convertir_solicitud_a_tramite ya dejó un historial_estado "generado" --
        # si el estado simulado es ese mismo, no se repite (el trigger
        # trg_historial_estado_no_duplicado lo rechaza, y con razón).
        if estado_final != "generado":
            db.add(models.HistorialEstado(
                id_tramite=tramite.id_tramite, estado=estado_final,
                comentario="Estado simulado por scripts/sembrar_demo.py.",
                id_usuario=responsable.id_usuario, fecha=tramite.fecha_actualizacion,
            ))

        # 1 de cada 3 ya tiene su empresa vinculada (como si el cliente ya hubiera
        # enviado sus datos con el código de seguimiento).
        if n % 3 == 0:
            nombre_empresa = random.choice(EMPRESAS)
            empresa = models.Empresa(
                rut_empresa=_rut_empresa_nuevo(db),
                razon_social=nombre_empresa,
                datos={"giro": "Servicios", "direccion": "Demo 123, Santiago"},
            )
            db.add(empresa)
            db.flush()
            tramite.id_empresa = empresa.id_empresa

        db.commit()

    print(f"Listo: {creadas} solicitudes creadas ({N_PENDIENTES} pendientes), {convertidas} convertidas a trámite.")
    print("Cuentas para entrar al panel (http://localhost:5174):")
    print(f"  Agente admin:  {admin.email} / {PASSWORD_DEMO}")
    print(f"  Agente normal: {agente.email} / {PASSWORD_DEMO}")


if __name__ == "__main__":
    main()
