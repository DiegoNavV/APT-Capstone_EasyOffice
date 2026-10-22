-- Migracion 006: triggers (Nivel 2 del pulido del esquema) -- normalizar
-- usuario.email y cliente.rut, y no permitir estados consecutivos repetidos
-- en historial_estado. Para bases YA creadas. Se puede ejecutar mas de una
-- vez sin problema (CREATE OR REPLACE FUNCTION + DROP TRIGGER IF EXISTS).
--
-- NO se incluye el trigger "id_usuario_responsable solo puede ser agente"
-- que proponia el diseno original: routers/solicitudes.py permite a
-- proposito que un administrador convierta una solicitud y quede como
-- responsable del tramite (ver docstring de convertir_solicitud) -- agregar
-- ese trigger bloquearia esa funcion real.

BEGIN;

CREATE OR REPLACE FUNCTION normalizar_usuario_email()
RETURNS trigger AS $$
BEGIN
    IF NEW.email IS NOT NULL THEN
        NEW.email := lower(trim(NEW.email));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_usuario_normalizar_email ON usuario;
CREATE TRIGGER trg_usuario_normalizar_email
BEFORE INSERT OR UPDATE OF email ON usuario
FOR EACH ROW
EXECUTE FUNCTION normalizar_usuario_email();

-- El RUT se normaliza a MAYUSCULAS, no a minusculas: la app guarda la K del
-- digito verificador en mayuscula (normalizar_rut en app/utils.py) y busca
-- clientes por comparacion exacta (crud.py). Con minusculas, un RUT terminado
-- en K no se reconoceria y se crearia un cliente duplicado.
CREATE OR REPLACE FUNCTION normalizar_cliente_rut()
RETURNS trigger AS $$
BEGIN
    IF NEW.rut IS NOT NULL THEN
        NEW.rut := upper(trim(NEW.rut));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cliente_normalizar_rut ON cliente;
CREATE TRIGGER trg_cliente_normalizar_rut
BEFORE INSERT OR UPDATE OF rut ON cliente
FOR EACH ROW
EXECUTE FUNCTION normalizar_cliente_rut();

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

DROP TRIGGER IF EXISTS trg_historial_estado_no_duplicado ON historial_estado;
CREATE TRIGGER trg_historial_estado_no_duplicado
BEFORE INSERT ON historial_estado
FOR EACH ROW
EXECUTE FUNCTION historial_estado_no_duplicado();

-- Normaliza los datos que ya existan, para que queden consistentes con las
-- filas nuevas que estos triggers van a normalizar de aqui en adelante.
UPDATE usuario SET email = lower(trim(email)) WHERE email IS NOT NULL AND email <> lower(trim(email));
UPDATE cliente SET rut = upper(trim(rut)) WHERE rut IS NOT NULL AND rut <> upper(trim(rut));

COMMIT;
