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
-- (admins y agentes; id_cliente queda nullable y sin uso por ahora,
--  reservado para cuando un cliente pueda tener cuenta propia a futuro)
-- =========================
CREATE TABLE usuario (
    id_usuario      SERIAL PRIMARY KEY,
    id_rol          INTEGER NOT NULL REFERENCES rol(id_rol),
    id_cliente      INTEGER REFERENCES cliente(id_cliente),
    nombre          VARCHAR(150) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion  TIMESTAMP NOT NULL DEFAULT now()
);

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
    fecha_creacion  TIMESTAMP NOT NULL DEFAULT now()
);

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
-- TABLA: tramite
-- (se crea únicamente cuando un agente confirma el pago y convierte
--  una solicitud_contacto; nunca se crea directo desde el sitio público)
-- =========================
CREATE TABLE tramite (
    id_tramite              SERIAL PRIMARY KEY,
    id_cliente              INTEGER NOT NULL REFERENCES cliente(id_cliente),
    id_servicio             INTEGER NOT NULL REFERENCES servicio_contratado(id_servicio),
    id_usuario_responsable  INTEGER REFERENCES usuario(id_usuario),
    id_solicitud_origen     INTEGER REFERENCES solicitud_contacto(id_solicitud),
    codigo_seguimiento      VARCHAR(8) NOT NULL UNIQUE,
    estado_actual           VARCHAR(30) NOT NULL DEFAULT 'generado',
    ruta_documento_generado VARCHAR(255),
    fecha_creacion          TIMESTAMP NOT NULL DEFAULT now(),
    fecha_actualizacion     TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_tramite_codigo_seguimiento ON tramite(codigo_seguimiento);

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