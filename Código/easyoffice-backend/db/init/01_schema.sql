-- =========================================================
-- CRM Easy Office — Modelo de datos v3
-- Base de datos: crm_easyoffice (PostgreSQL)
-- =========================================================

-- =========================
-- TABLA: rol
-- =========================
CREATE TABLE rol (
    id_rol      SERIAL PRIMARY KEY,
    nombre      VARCHAR(50) NOT NULL UNIQUE,
    descripcion TEXT
);

-- =========================
-- TABLA: cliente
-- (sin login; solo datos de contacto asociados a sus trámites)
-- =========================
CREATE TABLE cliente (
    id_cliente      SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL,
    rut             VARCHAR(15) UNIQUE,
    email           VARCHAR(150),
    telefono        VARCHAR(20),
    fecha_creacion  TIMESTAMP NOT NULL DEFAULT now()
);

-- =========================
-- TABLA: usuario
-- (admins y agentes; los clientes no tienen cuenta propia)
-- =========================
CREATE TABLE usuario (
    id_usuario      SERIAL PRIMARY KEY,
    id_rol          INTEGER NOT NULL REFERENCES rol(id_rol),
    nombre          VARCHAR(150) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion  TIMESTAMP NOT NULL DEFAULT now(),
    -- Bloqueo por fuerza bruta y último acceso (login del panel)
    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta   TIMESTAMP,
    ultimo_login      TIMESTAMP
);

-- =========================
-- TABLA: refresh_token
-- (una fila por sesión del panel; solo se guarda el hash SHA-256 del token.
--  Al renovarse, el token usado queda revocado y apunta al nuevo)
-- =========================
CREATE TABLE refresh_token (
    id_refresh_token   SERIAL PRIMARY KEY,
    id_usuario         INTEGER NOT NULL REFERENCES usuario(id_usuario),
    token_hash         VARCHAR(64) NOT NULL UNIQUE,
    creado_en          TIMESTAMP NOT NULL DEFAULT now(),
    expira_en          TIMESTAMP NOT NULL,
    revocado           BOOLEAN NOT NULL DEFAULT FALSE,
    reemplazado_por_id INTEGER REFERENCES refresh_token(id_refresh_token)
);

CREATE INDEX idx_refresh_token_id_usuario ON refresh_token(id_usuario);

-- =========================
-- TABLA: servicio_contratado
-- =========================
CREATE TABLE servicio_contratado (
    id_servicio             SERIAL PRIMARY KEY,
    nombre                  VARCHAR(150) NOT NULL,
    descripcion             TEXT,
    requiere_revision_humana BOOLEAN NOT NULL DEFAULT FALSE,
    activo                  BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion          TIMESTAMP NOT NULL DEFAULT now()
);

-- =========================
-- TABLA: plantilla_documento
-- =========================
CREATE TABLE plantilla_documento (
    id_plantilla    SERIAL PRIMARY KEY,
    id_servicio     INTEGER NOT NULL REFERENCES servicio_contratado(id_servicio),
    nombre          VARCHAR(150) NOT NULL,
    version         VARCHAR(20) NOT NULL DEFAULT '1.0',
    ruta_archivo    VARCHAR(255) NOT NULL,
    activa          BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion  TIMESTAMP NOT NULL DEFAULT now(),
    nombre_original  VARCHAR(255),
    hash_sha256      VARCHAR(64),
    tamano_bytes     INTEGER,
    marcas           JSONB,
    id_usuario_subio INTEGER REFERENCES usuario(id_usuario)
);

-- Cada subida es una version nueva (no se borra ninguna) y solo una puede estar activa por servicio.
CREATE UNIQUE INDEX uq_plantilla_servicio_version ON plantilla_documento(id_servicio, version);
CREATE UNIQUE INDEX uq_plantilla_activa_por_servicio ON plantilla_documento(id_servicio) WHERE activa;
-- id_servicio se filtra en cada subida/activacion de plantilla (app/plantillas.py, app/documentos.py).
CREATE INDEX idx_plantilla_documento_id_servicio ON plantilla_documento(id_servicio);

-- =========================
-- TABLA: solicitud_contacto
-- (formulario "Contrata aquí" del sitio público; sin login, sin código.
--  Un agente la gestiona y, al confirmar el pago manual, la convierte en
--  un tramite real)
-- =========================
CREATE TABLE solicitud_contacto (
    id_solicitud        SERIAL PRIMARY KEY,
    id_servicio         INTEGER REFERENCES servicio_contratado(id_servicio),
    nombre              VARCHAR(150) NOT NULL,
    rut                 VARCHAR(15),
    email               VARCHAR(150),
    telefono            VARCHAR(20),
    mensaje             TEXT,
    estado              VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    id_usuario_asignado INTEGER REFERENCES usuario(id_usuario),
    id_tramite_generado INTEGER,
    fecha_creacion      TIMESTAMP NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT now()
);

-- =========================
-- TABLA: empresa
-- (datos de cada empresa cliente, guardados UNA sola vez y reutilizados
--  entre tramites. razon_social y rut_empresa son columnas propias porque el
--  panel las muestra y las busca; el resto de los campos va en "datos", que
--  varia segun el servicio. El cliente solo puede COMPLETAR campos que faltan,
--  nunca sobrescribir; los cambios los hace un agente)
-- =========================
CREATE TABLE empresa (
    id_empresa          SERIAL PRIMARY KEY,
    rut_empresa         VARCHAR(15) NOT NULL UNIQUE,
    razon_social        VARCHAR(200) NOT NULL,
    datos               JSONB NOT NULL DEFAULT '{}'::jsonb,
    fecha_creacion      TIMESTAMP NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT now()
);

-- =========================
-- TABLA: sucursal
-- (datos fijos de cada sucursal de Easy Office; van en el contrato. Las iniciales
--  forman el folio, por ejemplo LF-01-2026)
-- =========================
CREATE TABLE sucursal (
    id_sucursal    SERIAL PRIMARY KEY,
    iniciales      VARCHAR(5) NOT NULL UNIQUE,
    nombre         VARCHAR(100) NOT NULL,
    direccion      VARCHAR(200) NOT NULL,
    comuna         VARCHAR(100) NOT NULL,
    region         VARCHAR(100) NOT NULL,
    rol_propiedad  VARCHAR(30),
    activa         BOOLEAN NOT NULL DEFAULT TRUE
);

-- =========================
-- TABLA: servicio_ofrecido
-- (catalogo de lo que vende Easy Office, con precio y ciclo de pago de referencia.
--  No es lo mismo que servicio_contratado, que son los tramites de la plataforma)
-- =========================
CREATE TABLE servicio_ofrecido (
    id_servicio_ofrecido SERIAL PRIMARY KEY,
    nombre               VARCHAR(150) NOT NULL UNIQUE,
    descripcion          TEXT,
    precio_referencia    INTEGER CHECK (precio_referencia IS NULL OR precio_referencia >= 0),
    ciclo_pago_defecto   VARCHAR(20),
    activo               BOOLEAN NOT NULL DEFAULT TRUE
);

-- =========================
-- TABLA: tramite
-- (se crea únicamente cuando un agente confirma el pago y convierte
--  una solicitud_contacto; nunca se crea directo desde el sitio público.
--  folio, id_sucursal y condiciones son las condiciones del contrato: las ingresa el agente)
-- =========================
CREATE TABLE tramite (
    id_tramite              SERIAL PRIMARY KEY,
    id_cliente              INTEGER NOT NULL REFERENCES cliente(id_cliente),
    id_servicio             INTEGER NOT NULL REFERENCES servicio_contratado(id_servicio),
    id_usuario_responsable  INTEGER REFERENCES usuario(id_usuario),
    id_solicitud_origen     INTEGER REFERENCES solicitud_contacto(id_solicitud),
    id_empresa              INTEGER REFERENCES empresa(id_empresa),
    id_sucursal             INTEGER REFERENCES sucursal(id_sucursal),
    folio                   VARCHAR(20),
    condiciones             JSONB,
    codigo_seguimiento      VARCHAR(8) NOT NULL UNIQUE,
    estado_actual           VARCHAR(30) NOT NULL DEFAULT 'generado',
    ruta_documento_generado VARCHAR(255),
    fecha_creacion          TIMESTAMP NOT NULL DEFAULT now(),
    fecha_actualizacion     TIMESTAMP NOT NULL DEFAULT now()
);

-- codigo_seguimiento ya es UNIQUE arriba (Postgres crea su propio indice);
-- no se repite como indice aparte.
CREATE UNIQUE INDEX uq_tramite_folio ON tramite(folio);
CREATE INDEX idx_tramite_id_sucursal ON tramite(id_sucursal);

-- Postgres no indexa automaticamente las columnas FK (a diferencia de MySQL).
-- Estas 4 se filtran o se unen hoy en el codigo (ver app/crud.py) -- sin indice,
-- cada consulta hace un seq scan sobre tramite, y cada UPDATE/DELETE en cliente,
-- servicio_contratado, usuario o empresa escanea toda la tabla para revisar la FK.
CREATE INDEX idx_tramite_id_cliente ON tramite(id_cliente);
CREATE INDEX idx_tramite_id_servicio ON tramite(id_servicio);
CREATE INDEX idx_tramite_id_usuario_responsable ON tramite(id_usuario_responsable);
CREATE INDEX idx_tramite_id_empresa ON tramite(id_empresa);

ALTER TABLE solicitud_contacto
    ADD CONSTRAINT fk_solicitud_tramite_generado
    FOREIGN KEY (id_tramite_generado) REFERENCES tramite(id_tramite);

-- =========================
-- TABLA: historial_estado
-- =========================
CREATE TABLE historial_estado (
    id_historial    SERIAL PRIMARY KEY,
    id_tramite      INTEGER NOT NULL REFERENCES tramite(id_tramite),
    estado          VARCHAR(30) NOT NULL,
    comentario      TEXT,
    id_usuario      INTEGER REFERENCES usuario(id_usuario),
    fecha           TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_historial_id_tramite ON historial_estado(id_tramite);

-- =========================
-- TABLA: datos_empresa_tramite (datos que el cliente entrega UNA sola vez con su código de seguimiento.
--  El solicitante vive en solicitud_contacto/cliente; aquí va la empresa. razon_social y rut_empresa son columnas propias 
--  porque la lista del panel las muestra y las busca; el resto de los campos varía según el servicio y se guarda en "datos" 
--  con los nombres de columna de los Excel de Easy Office)
-- =========================
-- =========================
-- TABLA: datos_empresa_tramite
-- (registro del envio UNICO de datos que hace el cliente con su codigo.
--  La clave unica en id_tramite garantiza el "solo una vez" a nivel de base
--  de datos. Los datos de la empresa viven en la tabla empresa)
-- =========================
CREATE TABLE datos_empresa_tramite (
    id_datos                     SERIAL PRIMARY KEY,
    id_tramite                   INTEGER NOT NULL UNIQUE REFERENCES tramite(id_tramite),
    solicitante_es_representante BOOLEAN NOT NULL,
    consentimiento_aceptado      BOOLEAN NOT NULL CHECK (consentimiento_aceptado),
    fecha_envio                  TIMESTAMP NOT NULL DEFAULT now()
);

-- =========================
-- TRIGGERS (Nivel 2 del pulido del esquema, 2026-10-22)
-- Ninguno de estos lo aplica hoy la app en Python -- son la ultima linea de
-- defensa a nivel de base de datos, por si alguna vez se escribe sin pasar
-- por el ORM (un script, una migracion de datos, etc).
-- =========================

-- usuario.email y cliente.rut son UNIQUE: se normalizan a minusculas + trim
-- antes de guardar para que esa unicidad sea realmente case-insensitive y no
-- se puedan crear "duplicados" solo por mayusculas o espacios de copiar/pegar.
CREATE OR REPLACE FUNCTION normalizar_usuario_email()
RETURNS trigger AS $$
BEGIN
    IF NEW.email IS NOT NULL THEN
        NEW.email := lower(trim(NEW.email));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_usuario_normalizar_email
BEFORE INSERT OR UPDATE OF email ON usuario
FOR EACH ROW
EXECUTE FUNCTION normalizar_usuario_email();

CREATE OR REPLACE FUNCTION normalizar_cliente_rut()
RETURNS trigger AS $$
BEGIN
    IF NEW.rut IS NOT NULL THEN
        NEW.rut := lower(trim(NEW.rut));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cliente_normalizar_rut
BEFORE INSERT OR UPDATE OF rut ON cliente
FOR EACH ROW
EXECUTE FUNCTION normalizar_cliente_rut();

-- historial_estado es append-only: no permite insertar el mismo estado dos
-- veces seguidas para el mismo tramite (ruido de auditoria por reintentos o
-- bugs de la app, no un cambio de negocio real). No se aplico el trigger de
-- "id_usuario_responsable solo puede ser agente" que proponia el diseno
-- original porque routers/solicitudes.py permite a proposito que un
-- administrador convierta una solicitud y quede como responsable.
CREATE OR REPLACE FUNCTION historial_estado_no_duplicado()
RETURNS trigger AS $$
DECLARE
    v_ultimo_estado VARCHAR(30);
BEGIN
    SELECT he.estado INTO v_ultimo_estado
    FROM historial_estado he
    WHERE he.id_tramite = NEW.id_tramite
    ORDER BY he.fecha DESC, he.id_historial DESC
    LIMIT 1;

    IF v_ultimo_estado IS NOT NULL AND v_ultimo_estado = NEW.estado THEN
        RAISE EXCEPTION 'No se puede repetir el mismo estado (%) dos veces seguidas para el tramite %', NEW.estado, NEW.id_tramite;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_historial_estado_no_duplicado
BEFORE INSERT ON historial_estado
FOR EACH ROW
EXECUTE FUNCTION historial_estado_no_duplicado();