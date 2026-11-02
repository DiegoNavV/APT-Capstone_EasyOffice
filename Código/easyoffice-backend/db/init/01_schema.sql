-- =========================================================
-- CRM Easy Office — Modelo de datos v4: estructura
-- Base de datos: crm_easyoffice (PostgreSQL)
--
-- Los archivos de db/init/ los ejecuta Postgres en orden alfabetico, y solo
-- cuando el volumen de datos esta vacio:
--   01_schema.sql      tablas, PK, UNIQUE, FK, CHECK e indices (este archivo)
--   02_funciones.sql   funciones, triggers y vistas
--   03_catalogos.sql   catalogos fijos que la app necesita en todo ambiente
--   04_datos_base.sql  datos reales del negocio (roles, sucursales, servicios)
--   05_seed_dev.sql    datos SOLO para desarrollo
--
-- Fechas: TIMESTAMP en UTC sin zona horaria, igual que ahora_utc() en la app.
-- Para recrear la base desde cero: docker compose down -v (o db/reset.sql).
-- =========================================================


-- =========================================================
-- 1. TABLAS
-- =========================================================

-- Catalogo de ciclos de pago (UNICO, ANUAL, ...). Clave natural: la app y las
-- condiciones del contrato guardan el codigo, no un id.
CREATE TABLE ciclo_pago_defecto
    (
     codigo VARCHAR (20)  NOT NULL ,
     meses  SMALLINT ,
     orden  SMALLINT  NOT NULL ,
     activo BOOLEAN  NOT NULL DEFAULT TRUE ,
     nombre VARCHAR (100)  NOT NULL
    )
;

-- Persona que contrata un servicio. Sin login; se busca o crea por RUN al
-- convertir una solicitud_contacto en tramite.
CREATE TABLE cliente
    (
     id              SERIAL  NOT NULL ,
     nombre          VARCHAR (150)  NOT NULL ,
     run             VARCHAR (15)  NOT NULL ,
     email           VARCHAR (150) ,
     numero_contacto VARCHAR (15) ,
     fecha_creacion  TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
    )
;

-- Comprobante del envio UNICO de datos que hace el cliente con su codigo de
-- seguimiento: cuando, quien lo lleno y que version del consentimiento acepto.
-- La PK en tramite_id garantiza el "solo una vez" a nivel de base de datos.
-- Los datos de la empresa viven en la tabla empresa.
CREATE TABLE datos_empresa_tramite
    (
     tramite_id                   INTEGER  NOT NULL ,
     solicitante_es_representante BOOLEAN  NOT NULL ,
     version_consentimiento       VARCHAR (20)  NOT NULL ,
     fecha_envio                  TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
    )
;

-- Empresa cliente para la que se hace el tramite. Sus datos se guardan UNA
-- sola vez y se reutilizan entre tramites; el cliente solo puede completar
-- campos vacios. La autorizacion de domicilio solo usa razon social, RUT y
-- representante: el resto lo pide el contrato y por eso es nullable. "datos"
-- queda para campos extra que Easy Office agregue despues.
CREATE TABLE empresa
    (
     id                     SERIAL  NOT NULL ,
     rut                    VARCHAR (15)  NOT NULL ,
     razon_social           VARCHAR (200)  NOT NULL ,
     giro_comercial         VARCHAR (200) ,
     email                  VARCHAR (150) ,
     contacto               CHAR (9) ,
     fecha_escritura        DATE ,
     notaria                VARCHAR (200) ,
     datos                  JSONB ,
     fecha_creacion         TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     fecha_actualizacion    TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     representante_legal_id INTEGER  NOT NULL
    )
;

-- Catalogo de estados del tramite. Clave natural: los CHECK, los triggers y la
-- app comparan por codigo.
CREATE TABLE estado_tramite
    (
     codigo               VARCHAR (30)  NOT NULL ,
     etiqueta             VARCHAR (50)  NOT NULL ,
     orden                SMALLINT  NOT NULL ,
     es_final             BOOLEAN  NOT NULL ,
     documento_disponible BOOLEAN  NOT NULL ,
     permite_regenerar    BOOLEAN  NOT NULL
    )
;

-- Bitacora append-only de cambios de estado de cada tramite: que, cuando y
-- quien. "origen" distingue al autor: un agente del panel, el cliente con su
-- codigo de seguimiento, o el sistema (por ejemplo la API de firma).
CREATE TABLE historial_estado
    (
     id                    SERIAL  NOT NULL ,
     tramite_id            INTEGER  NOT NULL ,
     origen                VARCHAR (50)  NOT NULL ,
     comentario            TEXT ,
     fecha                 TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     usuario_id            INTEGER ,
     estado_tramite_codigo VARCHAR (30)  NOT NULL
    )
;

-- Versiones de la plantilla Word de cada tipo de tramite. El archivo vive en
-- disco; aqui van sus metadatos. No se borra ninguna version y solo una esta
-- activa por tipo de tramite.
CREATE TABLE plantilla_documento
    (
     id              SERIAL  NOT NULL ,
     tipo_tramite_id INTEGER  NOT NULL ,
     nombre          VARCHAR (150)  NOT NULL ,
     version         INTEGER  NOT NULL DEFAULT 1 ,
     ruta_archivo    VARCHAR (255)  NOT NULL ,
     activo          BOOLEAN  NOT NULL DEFAULT TRUE ,
     fecha_creacion  TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     nombre_original VARCHAR (255)  NOT NULL ,
     hash_sha256     CHAR (64)  NOT NULL ,
     tamano_bytes    INTEGER  NOT NULL ,
     marcas          JSONB  NOT NULL DEFAULT '[]'::jsonb ,
     usuario_id      INTEGER  NOT NULL
    )
;

-- Una fila por sesion del panel; solo se guarda el hash SHA-256 del token. Al
-- renovarse, el token usado queda revocado y apunta al nuevo (refresh_token_id).
CREATE TABLE refresh_token
    (
     id               SERIAL  NOT NULL ,
     usuario_id       INTEGER  NOT NULL ,
     token_hash       VARCHAR (64)  NOT NULL ,
     creado_en        TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     expira_en        TIMESTAMP  NOT NULL ,
     revocado         BOOLEAN  NOT NULL DEFAULT FALSE ,
     refresh_token_id INTEGER
    )
;

-- Persona natural que representa a una o mas empresas y firma los documentos.
-- Puede ser o no el cliente que hizo la solicitud (ver
-- datos_empresa_tramite.solicitante_es_representante).
CREATE TABLE representante_legal
    (
     id             SERIAL  NOT NULL ,
     run            VARCHAR (15)  NOT NULL ,
     nombre         VARCHAR (150)  NOT NULL ,
     domicilio      VARCHAR (200) ,
     comuna         VARCHAR (200) ,
     region         VARCHAR (200) ,
     fecha_creacion TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
    )
;

CREATE TABLE rol
    (
     id          SERIAL  NOT NULL ,
     nombre      VARCHAR (50)  NOT NULL ,
     descripcion VARCHAR (500)  NOT NULL
    )
;

-- Catalogo de lo que vende Easy Office, con precio y ciclo de pago de
-- referencia. El agente puede ajustarlos en cada contrato (tramite.condiciones).
CREATE TABLE servicio_ofrecido
    (
     id                        SERIAL  NOT NULL ,
     nombre                    VARCHAR (150)  NOT NULL ,
     descripcion               TEXT ,
     precio_referencia         INTEGER ,
     ciclo_pago_defecto_codigo VARCHAR (20) ,
     activo                    BOOLEAN  NOT NULL DEFAULT TRUE
    )
;

-- Formulario "Contrata aqui" del sitio publico; sin login ni codigo. Un agente
-- la toma desde la bandeja compartida y la cierra de dos formas: la convierte
-- en tramite al confirmar el pago, o la descarta con un motivo. Las descartadas
-- no se borran: pasado el plazo de retencion se anonimizan. El vinculo con el
-- tramite vive en tramite.solicitud_contacto_id.
CREATE TABLE solicitud_contacto
    (
     id                  SERIAL  NOT NULL ,
     tipo_tramite_id     INTEGER ,
     nombre              VARCHAR (150) ,
     run                 VARCHAR (15) ,
     email               VARCHAR (150) ,
     numero_contacto     VARCHAR (15) ,
     mensaje             VARCHAR (500) ,
     estado              VARCHAR (30)  NOT NULL DEFAULT 'pendiente' ,
     usuario_id          INTEGER ,
     fecha_asignacion    TIMESTAMP ,
     motivo_descarte     VARCHAR (500) ,
     fecha_cierre        TIMESTAMP ,
     fecha_anonimizacion TIMESTAMP ,
     fecha_creacion      TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     fecha_actualizacion TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
    )
;

-- Oficinas de Easy Office. Su direccion es el domicilio tributario que se le
-- presta a la empresa del cliente (por eso rol_propiedad, el rol de avaluo SII)
-- y sus iniciales forman el folio del contrato (LF-01-2026).
CREATE TABLE sucursal
    (
     id            SERIAL  NOT NULL ,
     iniciales     VARCHAR (10)  NOT NULL ,
     nombre        VARCHAR (150)  NOT NULL ,
     direccion     VARCHAR (150)  NOT NULL ,
     comuna        VARCHAR (100)  NOT NULL ,
     region        VARCHAR (100)  NOT NULL ,
     rol_propiedad VARCHAR (30)  NOT NULL ,
     activa        BOOLEAN  NOT NULL DEFAULT TRUE
    )
;

-- Tipos de tramite que automatiza la plataforma (contrato de servicio,
-- autorizacion de domicilio tributario). No confundir con servicio_ofrecido.
CREATE TABLE tipo_tramite
    (
     id              SERIAL  NOT NULL ,
     nombre          VARCHAR (150)  NOT NULL ,
     descripcion     VARCHAR (150)  NOT NULL ,
     revision_humana BOOLEAN  NOT NULL DEFAULT FALSE ,
     activo          BOOLEAN  NOT NULL DEFAULT TRUE
    )
;

-- Se crea unicamente cuando un agente confirma el pago y convierte una
-- solicitud_contacto; nunca directo desde el sitio publico. condiciones es una
-- COPIA de lo pactado: un cambio en el catalogo no altera contratos ya hechos.
-- La sucursal es opcional: el agente puede convertir sin fijarla todavia, pero
-- sin sucursal no hay folio ni condiciones (ver los CHECK del tramite).
CREATE TABLE tramite
    (
     id                      SERIAL  NOT NULL ,
     cliente_id              INTEGER  NOT NULL ,
     usuario_id              INTEGER  NOT NULL ,
     tipo_tramite_id         INTEGER  NOT NULL ,
     solicitud_contacto_id   INTEGER  NOT NULL ,
     empresa_id              INTEGER ,
     sucursal_id             INTEGER ,
     folio                   VARCHAR (20) ,
     condiciones             JSONB ,
     codigo_seguimiento      CHAR (8)  NOT NULL ,
     estado_tramite_codigo   VARCHAR (30)  NOT NULL DEFAULT 'esperando_datos' ,
     ruta_documento_generado VARCHAR (255) ,
     fecha_creacion          TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     fecha_actualizacion     TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     plantilla_documento_id  INTEGER
    )
;

-- Cuentas del panel (administradores y agentes); los clientes no tienen cuenta.
CREATE TABLE usuario
    (
     id                SERIAL  NOT NULL ,
     rol_id            INTEGER  NOT NULL ,
     nombre            VARCHAR (150)  NOT NULL ,
     email             VARCHAR (250)  NOT NULL ,
     hash_pswd         VARCHAR (255)  NOT NULL ,
     activo            BOOLEAN  NOT NULL DEFAULT TRUE ,
     fecha_creacion    TIMESTAMP  NOT NULL DEFAULT (now() AT TIME ZONE 'utc') ,
     -- Bloqueo por fuerza bruta y ultimo acceso (login del panel)
     intentos_fallidos INTEGER  NOT NULL DEFAULT 0 ,
     bloqueado_hasta   TIMESTAMP ,
     ultimo_login      TIMESTAMP
    )
;


-- =========================================================
-- 2. CLAVES PRIMARIAS
-- =========================================================
ALTER TABLE ciclo_pago_defecto    ADD CONSTRAINT ciclo_pago_defecto_PK    PRIMARY KEY ( codigo ) ;
ALTER TABLE cliente               ADD CONSTRAINT cliente_PK               PRIMARY KEY ( id ) ;
ALTER TABLE datos_empresa_tramite ADD CONSTRAINT datos_empresa_tramite_PK PRIMARY KEY ( tramite_id ) ;
ALTER TABLE empresa               ADD CONSTRAINT empresa_PK               PRIMARY KEY ( id ) ;
ALTER TABLE estado_tramite        ADD CONSTRAINT estado_tramite_PK        PRIMARY KEY ( codigo ) ;
ALTER TABLE historial_estado      ADD CONSTRAINT historial_estado_PK      PRIMARY KEY ( id ) ;
ALTER TABLE plantilla_documento   ADD CONSTRAINT plantilla_documento_PK   PRIMARY KEY ( id ) ;
ALTER TABLE refresh_token         ADD CONSTRAINT refresh_token_PK         PRIMARY KEY ( id ) ;
ALTER TABLE representante_legal   ADD CONSTRAINT representante_legal_PK   PRIMARY KEY ( id ) ;
ALTER TABLE rol                   ADD CONSTRAINT rol_PK                   PRIMARY KEY ( id ) ;
ALTER TABLE servicio_ofrecido     ADD CONSTRAINT servicio_ofrecido_PK     PRIMARY KEY ( id ) ;
ALTER TABLE solicitud_contacto    ADD CONSTRAINT solicitud_contacto_PK    PRIMARY KEY ( id ) ;
ALTER TABLE sucursal              ADD CONSTRAINT sucursal_PK              PRIMARY KEY ( id ) ;
ALTER TABLE tipo_tramite          ADD CONSTRAINT tipo_tramite_PK          PRIMARY KEY ( id ) ;
ALTER TABLE tramite               ADD CONSTRAINT tramite_PK               PRIMARY KEY ( id ) ;
ALTER TABLE usuario               ADD CONSTRAINT usuario_PK               PRIMARY KEY ( id ) ;


-- =========================================================
-- 3. UNIQUE
-- =========================================================
ALTER TABLE rol                 ADD CONSTRAINT uq_rol_nombre                 UNIQUE (nombre);
ALTER TABLE usuario             ADD CONSTRAINT uq_usuario_email              UNIQUE (email);
ALTER TABLE refresh_token       ADD CONSTRAINT uq_refresh_token_hash         UNIQUE (token_hash),
                                -- Un token reemplaza a uno solo (autorrelacion 1:1).
                                ADD CONSTRAINT uq_refresh_token_reemplazo    UNIQUE (refresh_token_id);
ALTER TABLE tipo_tramite        ADD CONSTRAINT uq_tipo_tramite_nombre        UNIQUE (nombre);
ALTER TABLE plantilla_documento ADD CONSTRAINT uq_plantilla_tipo_version     UNIQUE (tipo_tramite_id, version),
                                -- Un mismo archivo no se sube dos veces para el mismo tipo de tramite.
                                ADD CONSTRAINT uq_plantilla_tipo_hash        UNIQUE (tipo_tramite_id, hash_sha256),
                                ADD CONSTRAINT uq_plantilla_ruta_archivo     UNIQUE (ruta_archivo);
ALTER TABLE cliente             ADD CONSTRAINT uq_cliente_run                UNIQUE (run);
ALTER TABLE empresa             ADD CONSTRAINT uq_empresa_rut                UNIQUE (rut);
ALTER TABLE representante_legal ADD CONSTRAINT uq_representante_run          UNIQUE (run);
ALTER TABLE sucursal            ADD CONSTRAINT uq_sucursal_iniciales         UNIQUE (iniciales),
                                ADD CONSTRAINT uq_sucursal_nombre            UNIQUE (nombre);
ALTER TABLE servicio_ofrecido   ADD CONSTRAINT uq_servicio_ofrecido_nombre   UNIQUE (nombre);
ALTER TABLE estado_tramite      ADD CONSTRAINT uq_estado_tramite_orden       UNIQUE (orden);
ALTER TABLE tramite             ADD CONSTRAINT uq_tramite_codigo_seguimiento UNIQUE (codigo_seguimiento),
                                ADD CONSTRAINT uq_tramite_folio              UNIQUE (folio),
                                -- Una solicitud genera como maximo un tramite (relacion 1:1).
                                ADD CONSTRAINT uq_tramite_solicitud_contacto UNIQUE (solicitud_contacto_id);


-- =========================================================
-- 4. CLAVES FORANEAS
-- =========================================================
ALTER TABLE datos_empresa_tramite
    ADD CONSTRAINT datos_empresa_tramite_tramite_FK FOREIGN KEY ( tramite_id )
    REFERENCES tramite ( id ) ;

ALTER TABLE empresa
    ADD CONSTRAINT empresa_representante_legal_FK FOREIGN KEY ( representante_legal_id )
    REFERENCES representante_legal ( id ) ;

ALTER TABLE historial_estado
    ADD CONSTRAINT historial_estado_estado_tramite_FK FOREIGN KEY ( estado_tramite_codigo )
    REFERENCES estado_tramite ( codigo ) ;

ALTER TABLE historial_estado
    ADD CONSTRAINT historial_estado_tramite_FK FOREIGN KEY ( tramite_id )
    REFERENCES tramite ( id ) ;

ALTER TABLE historial_estado
    ADD CONSTRAINT historial_estado_usuario_FK FOREIGN KEY ( usuario_id )
    REFERENCES usuario ( id ) ;

ALTER TABLE plantilla_documento
    ADD CONSTRAINT plantilla_documento_tipo_tramite_FK FOREIGN KEY ( tipo_tramite_id )
    REFERENCES tipo_tramite ( id ) ;

ALTER TABLE plantilla_documento
    ADD CONSTRAINT plantilla_documento_usuario_FK FOREIGN KEY ( usuario_id )
    REFERENCES usuario ( id ) ;

-- ON DELETE SET NULL: la limpieza de tokens expirados puede borrar un token
-- aunque otro apunte a el.
ALTER TABLE refresh_token
    ADD CONSTRAINT refresh_token_refresh_token_FK FOREIGN KEY ( refresh_token_id )
    REFERENCES refresh_token ( id )
    ON DELETE SET NULL ;

ALTER TABLE refresh_token
    ADD CONSTRAINT refresh_token_usuario_FK FOREIGN KEY ( usuario_id )
    REFERENCES usuario ( id ) ;

ALTER TABLE servicio_ofrecido
    ADD CONSTRAINT servicio_ofrecido_ciclo_pago_defecto_FK FOREIGN KEY ( ciclo_pago_defecto_codigo )
    REFERENCES ciclo_pago_defecto ( codigo ) ;

ALTER TABLE solicitud_contacto
    ADD CONSTRAINT solicitud_contacto_tipo_tramite_FK FOREIGN KEY ( tipo_tramite_id )
    REFERENCES tipo_tramite ( id ) ;

ALTER TABLE solicitud_contacto
    ADD CONSTRAINT solicitud_contacto_usuario_FK FOREIGN KEY ( usuario_id )
    REFERENCES usuario ( id ) ;

ALTER TABLE tramite
    ADD CONSTRAINT tramite_cliente_FK FOREIGN KEY ( cliente_id )
    REFERENCES cliente ( id ) ;

ALTER TABLE tramite
    ADD CONSTRAINT tramite_empresa_FK FOREIGN KEY ( empresa_id )
    REFERENCES empresa ( id ) ;

ALTER TABLE tramite
    ADD CONSTRAINT tramite_estado_tramite_FK FOREIGN KEY ( estado_tramite_codigo )
    REFERENCES estado_tramite ( codigo ) ;

ALTER TABLE tramite
    ADD CONSTRAINT tramite_plantilla_documento_FK FOREIGN KEY ( plantilla_documento_id )
    REFERENCES plantilla_documento ( id ) ;

ALTER TABLE tramite
    ADD CONSTRAINT tramite_solicitud_contacto_FK FOREIGN KEY ( solicitud_contacto_id )
    REFERENCES solicitud_contacto ( id ) ;

ALTER TABLE tramite
    ADD CONSTRAINT tramite_sucursal_FK FOREIGN KEY ( sucursal_id )
    REFERENCES sucursal ( id ) ;

ALTER TABLE tramite
    ADD CONSTRAINT tramite_tipo_tramite_FK FOREIGN KEY ( tipo_tramite_id )
    REFERENCES tipo_tramite ( id ) ;

ALTER TABLE tramite
    ADD CONSTRAINT tramite_usuario_FK FOREIGN KEY ( usuario_id )
    REFERENCES usuario ( id ) ;

ALTER TABLE usuario
    ADD CONSTRAINT usuario_rol_FK FOREIGN KEY ( rol_id )
    REFERENCES rol ( id ) ;


-- =========================================================
-- 5. CHECK
-- Formato canonico que guarda la app: RUT/RUN sin puntos, con guion y K
-- mayuscula. Los triggers de normalizacion (02_funciones.sql) corren ANTES que
-- estos CHECK, asi que un RUT con puntos se limpia primero y despues se valida.
-- Por eso las columnas de RUT/RUN son VARCHAR(15) y no (10): Postgres revisa el
-- largo ANTES de los triggers, y '12.345.678-5' (12) se rechazaria sin llegar a
-- normalizarse. El CHECK garantiza que lo guardado siempre tenga 9 o 10 caracteres.
-- =========================================================
ALTER TABLE usuario
    ADD CONSTRAINT ck_usuario_intentos_no_negativos CHECK (intentos_fallidos >= 0);

ALTER TABLE refresh_token
    ADD CONSTRAINT ck_refresh_token_expira_despues CHECK (expira_en > creado_en),
    ADD CONSTRAINT ck_refresh_token_no_se_reemplaza_a_si_mismo CHECK (refresh_token_id <> id);

ALTER TABLE plantilla_documento
    ADD CONSTRAINT ck_plantilla_version_positiva CHECK (version > 0),
    ADD CONSTRAINT ck_plantilla_tamano_positivo  CHECK (tamano_bytes > 0),
    ADD CONSTRAINT ck_plantilla_hash_formato     CHECK (hash_sha256 ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT ck_plantilla_marcas_es_lista  CHECK (jsonb_typeof(marcas) = 'array');

ALTER TABLE cliente
    ADD CONSTRAINT ck_cliente_run_formato    CHECK (run ~ '^[0-9]{7,8}-[0-9K]$'),
    ADD CONSTRAINT ck_cliente_algun_contacto CHECK (email IS NOT NULL OR numero_contacto IS NOT NULL);

ALTER TABLE solicitud_contacto
    ADD CONSTRAINT ck_solicitud_estado
        CHECK (estado IN ('pendiente', 'convertida', 'descartada')),
    ADD CONSTRAINT ck_solicitud_run_formato
        CHECK (run ~ '^[0-9]{7,8}-[0-9K]$'),
    -- Tomada = agente y fecha de asignacion juntos.
    ADD CONSTRAINT ck_solicitud_asignacion_completa
        CHECK ((usuario_id IS NULL) = (fecha_asignacion IS NULL)),
    -- Solo una solicitud cerrada tiene fecha de cierre.
    ADD CONSTRAINT ck_solicitud_cierre
        CHECK ((estado = 'pendiente') = (fecha_cierre IS NULL)),
    -- El motivo es obligatorio al descartar y no existe en los otros estados.
    ADD CONSTRAINT ck_solicitud_motivo_descarte
        CHECK ((estado = 'descartada') = (motivo_descarte IS NOT NULL)),
    -- Mientras no este anonimizada: nombre y al menos una forma de contacto.
    ADD CONSTRAINT ck_solicitud_datos_contacto
        CHECK (fecha_anonimizacion IS NOT NULL
               OR (nombre IS NOT NULL AND (email IS NOT NULL OR numero_contacto IS NOT NULL))),
    -- Solo se anonimizan las descartadas, y sin dejar ningun dato personal.
    ADD CONSTRAINT ck_solicitud_anonimizacion
        CHECK (fecha_anonimizacion IS NULL
               OR (estado = 'descartada'
                   AND nombre IS NULL AND run IS NULL AND email IS NULL
                   AND numero_contacto IS NULL AND mensaje IS NULL));

ALTER TABLE empresa
    ADD CONSTRAINT ck_empresa_rut_formato      CHECK (rut ~ '^[0-9]{7,8}-[0-9K]$'),
    ADD CONSTRAINT ck_empresa_contacto_formato CHECK (contacto ~ '^9[0-9]{8}$'),
    ADD CONSTRAINT ck_empresa_email_formato    CHECK (email LIKE '%_@_%._%'),
    ADD CONSTRAINT ck_empresa_fecha_escritura  CHECK (fecha_escritura >= DATE '1900-01-01'),
    ADD CONSTRAINT ck_empresa_datos_es_objeto  CHECK (jsonb_typeof(datos) = 'object');

ALTER TABLE representante_legal
    ADD CONSTRAINT ck_representante_run_formato CHECK (run ~ '^[0-9]{7,8}-[0-9K]$');

ALTER TABLE sucursal
    ADD CONSTRAINT ck_sucursal_iniciales_formato CHECK (iniciales ~ '^[A-Z]{2,5}$'),
    ADD CONSTRAINT ck_sucursal_rol_formato       CHECK (rol_propiedad ~ '^[0-9]+-[0-9]+$');

ALTER TABLE servicio_ofrecido
    ADD CONSTRAINT ck_servicio_precio_rango CHECK (precio_referencia BETWEEN 0 AND 100000000);

ALTER TABLE ciclo_pago_defecto
    ADD CONSTRAINT ck_ciclo_meses_positivos CHECK (meses > 0);

ALTER TABLE tramite
    ADD CONSTRAINT ck_tramite_folio_formato
        CHECK (folio ~ '^[A-Z]{2,5}-[0-9]{2,}-[0-9]{4}$'),
    -- El folio sale de las iniciales de la sucursal: uno no existe sin el otro.
    ADD CONSTRAINT ck_tramite_folio_con_sucursal
        CHECK ((folio IS NULL) = (sucursal_id IS NULL)),
    -- Las condiciones del contrato exigen sucursal (app/crud.py).
    ADD CONSTRAINT ck_tramite_condiciones_con_sucursal
        CHECK (condiciones IS NULL OR sucursal_id IS NOT NULL),
    ADD CONSTRAINT ck_tramite_condiciones_es_objeto
        CHECK (jsonb_typeof(condiciones) = 'object'),
    -- Documento generado = se sabe con que version de plantilla se genero.
    ADD CONSTRAINT ck_tramite_documento_con_plantilla
        CHECK ((ruta_documento_generado IS NULL) = (plantilla_documento_id IS NULL));

ALTER TABLE historial_estado
    ADD CONSTRAINT ck_historial_origen
        CHECK (origen IN ('agente', 'cliente', 'sistema')),
    -- Solo los agentes tienen cuenta: hay usuario si y solo si el origen es un agente.
    ADD CONSTRAINT ck_historial_usuario_segun_origen
        CHECK ((origen = 'agente') = (usuario_id IS NOT NULL));


-- =========================================================
-- 6. INDICES
-- Postgres no indexa las FK automaticamente (a diferencia de MySQL). Las PK y
-- los UNIQUE ya crean su propio indice, por eso no se repiten aca.
-- =========================================================

-- Solo una plantilla activa por tipo de tramite (no se puede expresar como constraint).
CREATE UNIQUE INDEX uq_plantilla_activa_por_tipo ON plantilla_documento (tipo_tramite_id) WHERE activo;

CREATE INDEX idx_refresh_token_usuario_id       ON refresh_token (usuario_id);
CREATE INDEX idx_empresa_representante_legal_id ON empresa (representante_legal_id);
CREATE INDEX idx_solicitud_tipo_tramite_id      ON solicitud_contacto (tipo_tramite_id);
CREATE INDEX idx_solicitud_usuario_id           ON solicitud_contacto (usuario_id);
-- La bandeja muestra casi siempre las pendientes.
CREATE INDEX idx_solicitud_pendientes           ON solicitud_contacto (fecha_creacion) WHERE estado = 'pendiente';
CREATE INDEX idx_tramite_cliente_id             ON tramite (cliente_id);
CREATE INDEX idx_tramite_tipo_tramite_id        ON tramite (tipo_tramite_id);
CREATE INDEX idx_tramite_usuario_id             ON tramite (usuario_id);
CREATE INDEX idx_tramite_empresa_id             ON tramite (empresa_id);
CREATE INDEX idx_tramite_sucursal_id            ON tramite (sucursal_id);
CREATE INDEX idx_tramite_plantilla_documento_id ON tramite (plantilla_documento_id);
CREATE INDEX idx_tramite_estado_tramite_codigo  ON tramite (estado_tramite_codigo);
-- "Ultimo estado del tramite" (trigger) y listado del historial en orden.
CREATE INDEX idx_historial_tramite_fecha        ON historial_estado (tramite_id, fecha DESC);
-- KPI "firmados en las ultimas 24 h".
CREATE INDEX idx_historial_estado_fecha         ON historial_estado (estado_tramite_codigo, fecha);
