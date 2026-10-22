"""Lógica de negocio del módulo: crear solicitud, convertirla a trámite
(generando el código de 8 caracteres) y consultar un trámite por código.
"""
import secrets
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, joinedload

from app import campos_servicio, condiciones as reglas_condiciones, enmascarado, models, schemas
from app.utils import normalizar_rut

ESTADOS_DOCUMENTO_DISPONIBLE = {"firmado", "entregado"}

# Agrupación de estados para los KPIs del panel de trámites.
ESTADOS_PENDIENTES_DATOS = ("generado",)
ESTADOS_EN_PROCESO = ("procesando_firma", "en_revision")


def servicio_existe(db: Session, id_servicio: int) -> bool:
    return db.get(models.ServicioContratado, id_servicio) is not None


def crear_solicitud(db: Session, datos: schemas.SolicitudContactoCreate) -> models.SolicitudContacto:
    solicitud = models.SolicitudContacto(
        nombre=datos.nombre,
        rut=datos.rut,
        email=datos.email,
        telefono=datos.telefono,
        id_servicio=datos.servicio_id,
        mensaje=datos.mensaje,
        estado="pendiente",
    )
    db.add(solicitud)
    db.commit()
    db.refresh(solicitud)
    return solicitud


def obtener_solicitud(db: Session, id_solicitud: int) -> models.SolicitudContacto | None:
    return db.get(models.SolicitudContacto, id_solicitud)


def listar_solicitudes(
    db: Session,
    estado: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[schemas.SolicitudListadoOut]:
    """
    Solicitudes de contacto, las más recientes primero. Para cada una ya convertida incluye el código de seguimiento de su trámite.
    """
    consulta = db.query(models.SolicitudContacto)
    if estado:
        consulta = consulta.filter(models.SolicitudContacto.estado == estado)
    # id_solicitud como desempate: fecha_creacion tiene resolución de segundos.
    solicitudes = (
        consulta.order_by(
            models.SolicitudContacto.fecha_creacion.desc(),
            models.SolicitudContacto.id_solicitud.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Una sola consulta extra para todos los códigos (evita N+1).
    ids_tramite = [s.id_tramite_generado for s in solicitudes if s.id_tramite_generado]
    codigos: dict[int, str] = {}
    folios: dict[int, str | None] = {}
    if ids_tramite:
        filas = (
            db.query(models.Tramite.id_tramite, models.Tramite.codigo_seguimiento, models.Tramite.folio)
            .filter(models.Tramite.id_tramite.in_(ids_tramite))
            .all()
        )
        codigos = {fila.id_tramite: fila.codigo_seguimiento for fila in filas}
        folios = {fila.id_tramite: fila.folio for fila in filas}

    return [
        schemas.SolicitudListadoOut(
            id_solicitud=s.id_solicitud,
            nombre=s.nombre,
            rut=s.rut,
            email=s.email,
            telefono=s.telefono,
            mensaje=s.mensaje,
            estado=s.estado,
            id_servicio=s.id_servicio,
            nombre_servicio=s.servicio.nombre if s.servicio else None,
            id_tramite_generado=s.id_tramite_generado,
            codigo_seguimiento=codigos.get(s.id_tramite_generado),
            folio=folios.get(s.id_tramite_generado),
            fecha_creacion=s.fecha_creacion,
        )
        for s in solicitudes
    ]


def contar_novedades(db: Session, desde_id: int | None = None) -> schemas.NovedadesSolicitudesOut:
    """Para el aviso "N solicitudes nuevas" del panel (consulta periódica).
    No devuelve datos de las solicitudes, solo números: el id más alto que existe
    y cuántas hay con id mayor a `desde_id`. Sin `desde_id` (primera consulta
    del panel) solo se informa el id más alto, que el panel guarda como punto
    de partida. Cuenta sobre toda la tabla, sin depender del filtro ni de la
    página que el agente esté viendo."""
    ultimo_id = db.query(func.max(models.SolicitudContacto.id_solicitud)).scalar() or 0
    nuevas = 0
    if desde_id is not None:
        nuevas = (
            db.query(func.count(models.SolicitudContacto.id_solicitud))
            .filter(models.SolicitudContacto.id_solicitud > desde_id)
            .scalar()
        )
    return schemas.NovedadesSolicitudesOut(nuevas=nuevas, ultimo_id=ultimo_id)


# Alfabeto del código de seguimiento: 31 caracteres, sin 0/O/1/I/L para que no se confundan al dictarlos por teléfono o 
# copiarlos desde un mensaje.
ALFABETO_CODIGO = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
LARGO_CODIGO = 8


def _generar_codigo() -> str:
    """Un código aleatorio (sin verificar unicidad). Usa `secrets` porque el
    código es la única credencial del cliente para ver su trámite."""
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))

def _generar_codigo_unico(db: Session) -> str:
    for _ in range(20):
        codigo = _generar_codigo()
        existe = db.query(models.Tramite).filter_by(codigo_seguimiento=codigo).first()
        if not existe:
            return codigo
    # Extremadamente improbable con 31^8 combinaciones, pero no lo dejamos colgado.
    raise RuntimeError("No se pudo generar un código de seguimiento único. Intenta nuevamente.")

class ConflictoDeFolio(Exception):
    """Dos conversiones calcularon el mismo folio a la vez. No se guardó nada;
    basta con reintentar."""


def _armar_condiciones(
    db: Session, datos: schemas.CondicionesIn
) -> dict:
    """Valida contra el catálogo y arma el JSON que se guarda en el trámite.
    Nombre y descripción se copian del catálogo: si Easy Office lo cambia después,
    los contratos ya hechos no cambian."""
    servicios = []
    for item in datos.servicios:
        servicio = db.get(models.ServicioOfrecido, item.id_servicio_ofrecido)
        if not servicio or not servicio.activo:
            raise ValueError(f"El servicio {item.id_servicio_ofrecido} no existe o no está activo en el catálogo.")
        servicios.append({
            "id_servicio_ofrecido": servicio.id_servicio_ofrecido,
            "nombre": servicio.nombre,
            "descripcion": servicio.descripcion,
            "precio": item.precio,
            "ciclo_pago": item.ciclo_pago,
        })

    calculado = reglas_condiciones.calcular_vencimiento(datos.fecha_inicio, datos.duracion_meses)
    vencimiento = datos.fecha_vencimiento or calculado
    return {
        "servicios": servicios,
        "duracion_meses": datos.duracion_meses,
        "fecha_inicio": datos.fecha_inicio.isoformat(),
        "fecha_vencimiento": vencimiento.isoformat(),
        # True si el agente corrigió a mano la fecha que proponía el sistema.
        "vencimiento_manual": vencimiento != calculado,
    }


def convertir_solicitud_a_tramite(
    db: Session,
    solicitud: models.SolicitudContacto,
    id_usuario_responsable: int,
    empresa: models.Empresa | None = None,
    sucursal: models.Sucursal | None = None,
    condiciones: schemas.CondicionesIn | None = None,
) -> models.Tramite:
    """Confirma el pago manual de una solicitud y la convierte en un trámite real, generando su código de seguimiento. Acción exclusiva 
    de un agente/admin: el responsable es siempre quien la ejecuta (lo valida get_usuario_actual en el router, por eso aquí no se 
    vuelve a comprobar que exista).

    `empresa` es opcional: si el agente la indica, el trámite queda vinculado a ella y reutilizará sus datos ya guardados. El router 
    es quien comprueba que exista; aquí solo se vincula.

    `sucursal` (que el router ya comprobó) asigna además el folio automático. `condiciones` (precios, ciclos, duración y fechas) se
    valida contra el catálogo y se guarda en el trámite; exige sucursal.

    Lanza ValueError (datos inválidos), ConflictoDeFolio (reintentar) o RuntimeError (sin código único)."""

    if solicitud.estado == "convertido":
        raise ValueError("Esta solicitud ya fue convertida en un trámite.")
    if not solicitud.id_servicio:
        raise ValueError("La solicitud no tiene un servicio definido; no se puede convertir.")
    if condiciones is not None and sucursal is None:
        raise ValueError("Para fijar las condiciones del contrato hay que indicar la sucursal.")

    # Se valida antes de tocar la base: si algo falla, no queda nada a medias.
    condiciones_json = _armar_condiciones(db, condiciones) if condiciones is not None else None

    # El cliente no tiene cuenta; se busca o se crea por RUT (ya normalizado por
    # el schema al crear la solicitud) para no duplicarlo si ya había hecho una
    # solicitud antes.
    cliente = None
    if solicitud.rut:
        cliente = db.query(models.Cliente).filter_by(rut=solicitud.rut).first()
    if not cliente:
        cliente = models.Cliente(
            nombre=solicitud.nombre,
            rut=solicitud.rut,
            email=solicitud.email,
            telefono=solicitud.telefono,
        )
        db.add(cliente)
        db.flush()  # para obtener id_cliente sin cerrar la transacción

    folio = None
    if sucursal is not None:
        folio = reglas_condiciones.siguiente_folio(db, sucursal, date.today().year)

    try:
        tramite = models.Tramite(
            id_cliente=cliente.id_cliente,
            id_servicio=solicitud.id_servicio,
            id_usuario_responsable=id_usuario_responsable,
            id_solicitud_origen=solicitud.id_solicitud,
            id_empresa=empresa.id_empresa if empresa else None,
            id_sucursal=sucursal.id_sucursal if sucursal else None,
            folio=folio,
            condiciones=condiciones_json,
            codigo_seguimiento=_generar_codigo_unico(db),
            estado_actual="generado",
        )
        db.add(tramite)
        db.flush()

        comentario = "Trámite generado al confirmar el pago de la solicitud de contacto."
        if empresa:
            comentario += f" Vinculado a la empresa {empresa.razon_social} ({empresa.rut_empresa})."
        if sucursal:
            comentario += f" Sucursal {sucursal.nombre}, folio {folio}."
        db.add(models.HistorialEstado(
            id_tramite=tramite.id_tramite,
            estado="generado",
            comentario=comentario,
            id_usuario=id_usuario_responsable,
        ))

        solicitud.estado = "convertido"
        solicitud.id_tramite_generado = tramite.id_tramite

        db.commit()
    except IntegrityError:
        # Lo único que puede chocar aquí es el folio (el código ya se verificó):
        # otro agente tomó ese número en el mismo instante.
        db.rollback()
        raise ConflictoDeFolio("Otro agente generó un folio al mismo tiempo. Intenta nuevamente.")
    db.refresh(tramite)
    return tramite


# ---------------------------------------------------------------------------
# Empresas: búsqueda y sugerencias para vincular al convertir (solo agentes)
# ---------------------------------------------------------------------------

def obtener_empresa(db: Session, id_empresa: int) -> models.Empresa | None:
    return db.get(models.Empresa, id_empresa)


def buscar_empresas(db: Session, texto: str, limite: int = 10) -> list[models.Empresa]:
    """Coincidencia parcial por razón social o RUT de la empresa. Pensada para
    el buscador del agente: devuelve pocas filas y sin el JSON `datos`
    (el schema de salida lo excluye)."""
    texto = texto.strip()
    if not texto:
        return []
    patron = f"%{_escapar_like(texto)}%"
    patron_rut = f"%{_escapar_like(normalizar_rut(texto) or texto)}%"
    return (
        db.query(models.Empresa)
        .filter(or_(
            models.Empresa.razon_social.ilike(patron, escape="\\"),
            models.Empresa.rut_empresa.ilike(patron_rut, escape="\\"),
        ))
        .order_by(models.Empresa.razon_social, models.Empresa.id_empresa)
        .limit(limite)
        .all()
    )


def empresas_sugeridas(db: Session, solicitud: models.SolicitudContacto) -> list[models.Empresa]:
    """Empresas ya vinculadas a trámites anteriores del MISMO solicitante (se identifica por RUT, igual que al convertir). Sin RUT 
    o sin historial no hay sugerencias: el agente usa el buscador o deja el trámite sin empresa."""
    if not solicitud.rut:
        return []
    cliente = db.query(models.Cliente).filter_by(rut=solicitud.rut).first()
    if not cliente:
        return []
    return (
        db.query(models.Empresa)
        .join(models.Tramite, models.Tramite.id_empresa == models.Empresa.id_empresa)
        .filter(models.Tramite.id_cliente == cliente.id_cliente)
        .distinct()
        .order_by(models.Empresa.razon_social, models.Empresa.id_empresa)
        .all()
    )


def obtener_tramite_por_codigo(db: Session, codigo: str) -> models.Tramite | None:
    return (
        db.query(models.Tramite)
        .filter(models.Tramite.codigo_seguimiento == codigo.strip().upper())
        .first()
    )


class EnvioDatosRechazado(Exception):
    """El envío no se puede aceptar (no por errores de campos). El mensaje es
    el que ve el cliente, por eso es genérico a propósito."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class DatosYaEnviados(EnvioDatosRechazado):
    def __init__(self):
        super().__init__("Ya recibimos tus datos. Con tu código puedes revisar el estado de tu trámite.")


class FormularioNoDisponible(EnvioDatosRechazado):
    def __init__(self):
        super().__init__("Este trámite ya no admite el envío de datos.")


class RutNoDisponible(EnvioDatosRechazado):
    # Mismo mensaje exista o no la empresa, para no revelar qué RUT están registrados.
    def __init__(self):
        super().__init__("No pudimos registrar ese RUT. Contacta a tu agente indicando tu código.")


MENSAJE_CAMPO_REGISTRADO = (
    "Este dato ya está registrado y no se puede modificar desde aquí. "
    "Si necesitas cambiarlo, contacta a tu agente."
)

def revisar_campos_cliente(definicion, empresa, campos: dict) -> tuple[tuple, dict[str, str], dict[str, str]]:
    """
    Revisa los campos que escribió el cliente. Devuelve (pendientes, limpios, errores).

    Solo se aceptan los que la empresa aún no tiene: uno ya registrado se rechaza nombrándolo (nunca se sobrescribe). 
    Lo comparten el envío definitivo y la vista previa del borrador, para que ambos apliquen exactamente las mismas reglas.
    """
    registrados = {c.clave for c in definicion if valor_guardado(empresa, c)}
    pendientes = tuple(c for c in definicion if c.clave not in registrados)
    valores = dict(campos)
    errores: dict[str, str] = {}
    for clave in sorted(registrados & set(valores)):
        errores[clave] = MENSAJE_CAMPO_REGISTRADO
        del valores[clave]

    limpios: dict[str, str] = {}
    try:
        limpios = campos_servicio.validar_campos(pendientes, valores)
    except campos_servicio.ErrorCampos as exc:
        errores.update(exc.errores)
    return pendientes, limpios, errores


def registrar_envio_datos(
    db: Session, tramite: models.Tramite, envio: schemas.EnvioDatosIn
) -> models.Tramite:
    """Guarda los datos que el cliente envía con su código. Ocurre UNA sola vez.

    Reglas (todas se comprueban en el servidor):
      - solo si el trámite espera datos y aún no recibió un envío;
      - exige el consentimiento y la confirmación de que no podrá editar;
      - solo se aceptan los campos que faltan: uno ya registrado se rechaza nombrándolo (nunca se sobrescribe);
      - sin empresa vinculada se crea una nueva y se vincula; si ese RUT ya existe se rechaza con un mensaje genérico 
      (el vínculo con una empresa existente lo hace un agente);
      - con empresa vinculada solo se completan los campos vacíos;
      - todo se guarda en una sola transacción y el trámite pasa a `procesando_firma` (o `en_revision` si el servicio requiere revisión)."""
    if tramite.datos_empresa is not None:
        raise DatosYaEnviados()
    definicion = campos_servicio.campos_para_servicio(tramite.servicio.nombre)
    if definicion is None or tramite.estado_actual != ESTADO_ESPERANDO_DATOS:
        raise FormularioNoDisponible()

    empresa = tramite.empresa
    errores: dict[str, str] = {}

    if not envio.consentimiento_aceptado:
        errores["consentimiento_aceptado"] = "Debes aceptar el tratamiento de tus datos para continuar."
    if not envio.acepta_no_editar:
        errores["acepta_no_editar"] = "Debes confirmar que no podrás editar tus datos después de enviarlos."

    pendientes, limpios, errores_campos = revisar_campos_cliente(definicion, empresa, envio.campos)
    errores.update(errores_campos)

    if errores:
        raise campos_servicio.ErrorCampos(errores)

    columnas, datos = campos_servicio.separar_para_guardar(pendientes, limpios)

    try:
        if empresa is None:
            rut = columnas.get("rut_empresa")
            razon = columnas.get("razon_social")
            if not rut or not razon:
                # La definición del servicio no pide lo mínimo para crear la empresa.
                raise FormularioNoDisponible()
            if db.query(models.Empresa).filter_by(rut_empresa=rut).first():
                raise RutNoDisponible()
            empresa = models.Empresa(rut_empresa=rut, razon_social=razon, datos=datos)
            db.add(empresa)
            db.flush()
            tramite.id_empresa = empresa.id_empresa
        elif datos:
            # Se asigna un diccionario nuevo: SQLAlchemy no detecta cambios dentro del JSON.
            empresa.datos = {**(empresa.datos or {}), **datos}

        db.add(models.DatosEmpresaTramite(
            id_tramite=tramite.id_tramite,
            solicitante_es_representante=envio.solicitante_es_representante,
            consentimiento_aceptado=True,
        ))

        nuevo_estado = "en_revision" if tramite.servicio.requiere_revision_humana else "procesando_firma"
        tramite.estado_actual = nuevo_estado
        db.add(models.HistorialEstado(
            id_tramite=tramite.id_tramite,
            estado=nuevo_estado,
            comentario=(
                "El cliente envió sus datos. Queda en revisión."
                if nuevo_estado == "en_revision"
                else "El cliente envió sus datos. Queda en proceso de firma."
            ),
        ))
        db.commit()
    except EnvioDatosRechazado:
        db.rollback()
        raise
    except IntegrityError:
        # Dos envíos casi simultáneos, o el mismo RUT creado justo antes por otro.
        db.rollback()
        if db.query(models.DatosEmpresaTramite).filter_by(id_tramite=tramite.id_tramite).first():
            raise DatosYaEnviados() from None
        raise RutNoDisponible() from None

    db.refresh(tramite)
    return tramite


def documento_disponible(tramite: models.Tramite) -> bool:
    return tramite.estado_actual in ESTADOS_DOCUMENTO_DISPONIBLE


# ---------------------------------------------------------------------------
# Formulario del cliente (público, se accede con el código del trámite)
# ---------------------------------------------------------------------------

ESTADO_ESPERANDO_DATOS = "generado"


def valor_guardado(empresa: models.Empresa | None, campo: campos_servicio.Campo):
    """Lo que la empresa vinculada ya tiene para este campo (None si no hay)."""
    if empresa is None:
        return None
    if campo.en_columna:
        return getattr(empresa, campo.clave, None)
    return (empresa.datos or {}).get(campo.clave)


def obtener_formulario(tramite: models.Tramite) -> schemas.FormularioOut:
    """Qué debe completar el cliente en este trámite.

    Pide solo los campos del servicio contratado. Los que la empresa vinculada ya tiene se marcan como registrados y se 
    devuelven ENMASCARADOS; nunca se devuelven completos (ver app/enmascarado.py). Si el cliente ya envió sus datos, solo se informa 
    el estado, sin ningún dato."""
    enviados = tramite.datos_empresa is not None
    definicion = campos_servicio.campos_para_servicio(tramite.servicio.nombre)
    disponible = (
        not enviados
        and definicion is not None
        and tramite.estado_actual == ESTADO_ESPERANDO_DATOS
    )

    campos: list[schemas.CampoFormularioOut] = []
    if disponible:
        for campo in definicion:
            guardado = valor_guardado(tramite.empresa, campo)
            registrado = bool(guardado)
            campos.append(schemas.CampoFormularioOut(
                clave=campo.clave,
                etiqueta=campo.etiqueta,
                tipo=campo.tipo,
                ayuda=campo.ayuda,
                max_largo=campo.max_largo,
                registrado=registrado,
                valor_enmascarado=enmascarado.enmascarar(campo, guardado) if registrado else None,
            ))

    return schemas.FormularioOut(
        codigo_seguimiento=tramite.codigo_seguimiento,
        nombre_servicio=tramite.servicio.nombre,
        estado_actual=tramite.estado_actual,
        datos_enviados=enviados,
        formulario_disponible=disponible,
        campos=campos,
    )


# ---------------------------------------------------------------------------
# Listado de trámites del panel (agentes y administradores)
# ---------------------------------------------------------------------------

def _datos_cliente_listado(tramite: models.Tramite) -> schemas.ClienteListadoOut:
    """ÚNICO lugar que decide qué "cliente" se muestra en el listado.

    Hoy: los datos de contacto de quien pidió el trámite, con `datos_pendientes=True` porque la empresa aún no completa sus datos.
    Cuando exista el formulario posterior al código, aquí se devolverán la razón social y el RUT de la empresa (y `datos_pendientes=False`). 
    El filtro de búsqueda (`_filtro_busqueda`) debe actualizarse junto con esta función."""
    cliente = tramite.cliente
    return schemas.ClienteListadoOut(
        nombre=cliente.nombre,
        rut=cliente.rut,
        datos_pendientes=True,
    )


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filtro_busqueda(texto: str):
    """Coincidencia parcial por nombre o RUT del cliente, o por código del
    trámite. El RUT se compara tal como se guarda (sin puntos, DV en mayúscula)."""
    patron = f"%{_escapar_like(texto.strip())}%"
    patron_rut = f"%{_escapar_like(normalizar_rut(texto) or texto.strip())}%"
    return or_(
        models.Cliente.nombre.ilike(patron, escape="\\"),
        models.Cliente.rut.ilike(patron_rut, escape="\\"),
        models.Tramite.codigo_seguimiento.ilike(patron, escape="\\"),
    )


def listar_tramites(
    db: Session,
    servicio_id: int | None = None,
    estado: str | None = None,
    agente_id: int | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> schemas.TramitesPaginaOut:
    """Trámites con filtros opcionales, los más recientemente actualizados
    primero. `total` cuenta todos los que cumplen los filtros (para paginar)."""
    base = db.query(models.Tramite).join(models.Tramite.cliente)
    if servicio_id is not None:
        base = base.filter(models.Tramite.id_servicio == servicio_id)
    if estado:
        base = base.filter(models.Tramite.estado_actual == estado)
    if agente_id is not None:
        base = base.filter(models.Tramite.id_usuario_responsable == agente_id)
    if q and q.strip():
        base = base.filter(_filtro_busqueda(q))

    total = base.count()
    tramites = (
        base.options(
            contains_eager(models.Tramite.cliente),
            joinedload(models.Tramite.servicio),
            joinedload(models.Tramite.usuario_responsable),
        )
        # id_tramite como desempate: la fecha tiene resolución de segundos.
        .order_by(models.Tramite.fecha_actualizacion.desc(), models.Tramite.id_tramite.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return schemas.TramitesPaginaOut(
        total=total,
        items=[
            schemas.TramiteListadoOut(
                id_tramite=t.id_tramite,
                codigo_seguimiento=t.codigo_seguimiento,
                cliente=_datos_cliente_listado(t),
                id_servicio=t.id_servicio,
                nombre_servicio=t.servicio.nombre,
                estado_actual=t.estado_actual,
                id_usuario_responsable=t.id_usuario_responsable,
                nombre_agente=t.usuario_responsable.nombre if t.usuario_responsable else None,
                fecha_actualizacion=t.fecha_actualizacion,
                tiene_documento=bool(t.ruta_documento_generado),
                folio=t.folio,
            )
            for t in tramites
        ],
    )


def _contar_tramites_en(db: Session, estados: tuple[str, ...]) -> int:
    return (
        db.query(func.count(models.Tramite.id_tramite))
        .filter(models.Tramite.estado_actual.in_(estados))
        .scalar()
    )


def resumen_tramites(db: Session) -> schemas.TramitesResumenOut:
    """KPIs del panel y opciones de los filtros (servicios y agentes activos)."""
    # "Firmados" = trámites que pasaron a ese estado en las últimas 24 horas,
    # según el historial. Las fechas de la base son UTC (sin zona), igual que
    # `desde`. Se evita "hoy" calendario para no depender de la zona horaria.
    desde = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    firmados_24h = (
        db.query(func.count(func.distinct(models.HistorialEstado.id_tramite)))
        .filter(
            models.HistorialEstado.estado == "firmado",
            models.HistorialEstado.fecha >= desde,
        )
        .scalar()
    )

    servicios = (
        db.query(models.ServicioContratado)
        .filter(models.ServicioContratado.activo.is_(True))
        .order_by(models.ServicioContratado.id_servicio)
        .all()
    )
    agentes = (
        db.query(models.Usuario)
        .filter(models.Usuario.activo.is_(True))
        .order_by(models.Usuario.nombre, models.Usuario.id_usuario)
        .all()
    )

    return schemas.TramitesResumenOut(
        kpis=schemas.TramitesKpisOut(
            pendientes_datos=_contar_tramites_en(db, ESTADOS_PENDIENTES_DATOS),
            en_proceso=_contar_tramites_en(db, ESTADOS_EN_PROCESO),
            firmados_24h=firmados_24h,
            entregados=_contar_tramites_en(db, ("entregado",)),
        ),
        servicios=[
            schemas.OpcionServicioOut(id_servicio=s.id_servicio, nombre=s.nombre)
            for s in servicios
        ],
        agentes=[
            schemas.OpcionAgenteOut(id_usuario=u.id_usuario, nombre=u.nombre)
            for u in agentes
        ],
    )


def reporte_tramites(db: Session) -> schemas.ReporteTramitesOut:
    """Conteos agregados para la vista de Reportes (exclusiva de administradores,
    el router es quien verifica el permiso). Si todavía no hay trámites, devuelve
    los desgloses vacíos -- el panel es quien decide mostrar el aviso de "sin
    suficiente información"."""
    total = db.query(func.count(models.Tramite.id_tramite)).scalar() or 0
    if not total:
        return schemas.ReporteTramitesOut(puede_ver=True, total=0)

    por_estado = (
        db.query(models.Tramite.estado_actual, func.count(models.Tramite.id_tramite))
        .group_by(models.Tramite.estado_actual)
        .order_by(func.count(models.Tramite.id_tramite).desc())
        .all()
    )
    por_servicio = (
        db.query(models.ServicioContratado.nombre, func.count(models.Tramite.id_tramite))
        .join(models.Tramite, models.Tramite.id_servicio == models.ServicioContratado.id_servicio)
        .group_by(models.ServicioContratado.nombre)
        .order_by(func.count(models.Tramite.id_tramite).desc())
        .all()
    )
    por_agente = (
        db.query(models.Usuario.nombre, func.count(models.Tramite.id_tramite))
        .join(models.Tramite, models.Tramite.id_usuario_responsable == models.Usuario.id_usuario)
        .group_by(models.Usuario.nombre)
        .order_by(func.count(models.Tramite.id_tramite).desc())
        .all()
    )

    return schemas.ReporteTramitesOut(
        puede_ver=True,
        total=total,
        por_estado=[schemas.ReporteConteoOut(etiqueta=e, cantidad=c) for e, c in por_estado],
        por_servicio=[schemas.ReporteConteoOut(etiqueta=s, cantidad=c) for s, c in por_servicio],
        por_agente=[schemas.ReporteConteoOut(etiqueta=a, cantidad=c) for a, c in por_agente],
    )


# ---------------------------------------------------------------------------
# Listado de clientes del panel (agentes y administradores)
# ---------------------------------------------------------------------------

def _filtro_busqueda_cliente(texto: str):
    """Igual que _filtro_busqueda, pero sin el código de trámite: acá no hay
    ningún Tramite en el FROM de la consulta."""
    patron = f"%{_escapar_like(texto.strip())}%"
    patron_rut = f"%{_escapar_like(normalizar_rut(texto) or texto.strip())}%"
    return or_(
        models.Cliente.nombre.ilike(patron, escape="\\"),
        models.Cliente.rut.ilike(patron_rut, escape="\\"),
    )


def listar_clientes(
    db: Session,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> schemas.ClientesPaginaOut:
    """Clientes con su cantidad de trámites, los más recientes primero.
    Filtro opcional por nombre o RUT."""
    conteo = (
        db.query(
            models.Tramite.id_cliente.label("id_cliente"),
            func.count(models.Tramite.id_tramite).label("cantidad"),
        )
        .group_by(models.Tramite.id_cliente)
        .subquery()
    )

    base = db.query(models.Cliente, func.coalesce(conteo.c.cantidad, 0)).outerjoin(
        conteo, conteo.c.id_cliente == models.Cliente.id_cliente
    )
    if q and q.strip():
        base = base.filter(_filtro_busqueda_cliente(q))

    total = base.count()
    filas = (
        base.order_by(models.Cliente.fecha_creacion.desc(), models.Cliente.id_cliente.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return schemas.ClientesPaginaOut(
        total=total,
        items=[
            schemas.ClienteResumenOut(
                id_cliente=cliente.id_cliente,
                nombre=cliente.nombre,
                rut=cliente.rut,
                email=cliente.email,
                telefono=cliente.telefono,
                cantidad_tramites=cantidad,
                fecha_creacion=cliente.fecha_creacion,
            )
            for cliente, cantidad in filas
        ],
    )


def obtener_cliente_detalle(db: Session, id_cliente: int) -> schemas.ClienteDetalleOut | None:
    """Ficha de cliente 360°: datos de contacto, las empresas que vinculó en
    alguno de sus trámites, y el historial completo de trámites. None si el
    cliente no existe -- el router responde 404."""
    cliente = db.get(models.Cliente, id_cliente)
    if not cliente:
        return None

    tramites = (
        db.query(models.Tramite)
        .filter(models.Tramite.id_cliente == id_cliente)
        .options(
            joinedload(models.Tramite.servicio),
            joinedload(models.Tramite.usuario_responsable),
        )
        .order_by(models.Tramite.fecha_creacion.desc(), models.Tramite.id_tramite.desc())
        .all()
    )

    empresas = (
        db.query(models.Empresa)
        .join(models.Tramite, models.Tramite.id_empresa == models.Empresa.id_empresa)
        .filter(models.Tramite.id_cliente == id_cliente)
        .distinct()
        .all()
    )

    return schemas.ClienteDetalleOut(
        id_cliente=cliente.id_cliente,
        nombre=cliente.nombre,
        rut=cliente.rut,
        email=cliente.email,
        telefono=cliente.telefono,
        fecha_creacion=cliente.fecha_creacion,
        empresas=[schemas.EmpresaResumenOut.model_validate(e) for e in empresas],
        tramites=[
            schemas.TramiteClienteOut(
                id_tramite=t.id_tramite,
                codigo_seguimiento=t.codigo_seguimiento,
                nombre_servicio=t.servicio.nombre,
                estado_actual=t.estado_actual,
                nombre_agente=t.usuario_responsable.nombre if t.usuario_responsable else None,
                fecha_creacion=t.fecha_creacion,
                fecha_actualizacion=t.fecha_actualizacion,
                tiene_documento=bool(t.ruta_documento_generado),
                folio=t.folio,
            )
            for t in tramites
        ],
    )