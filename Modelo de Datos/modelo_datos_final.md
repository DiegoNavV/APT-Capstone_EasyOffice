# Modelo de datos — CRM Easy Office (versión final, con catálogos y triggers)

Este documento explica y justifica la versión final del modelo de datos, tal
como quedó definida en el diagrama (markup provisto por el equipo). Es la
evolución de `esquema_modelo_datos.txt` / `justificacion_modelo_datos.md`
(borrador inicial derivado de `Fase 1/modelo de datos, prueba.jpeg`): se
mantiene todo lo que seguía siendo válido y se agregan las decisiones
tomadas después — normalización de catálogos, triggers de integridad e
índices de rendimiento.

**No reemplaza los archivos anteriores automáticamente** — quedan como
registro del razonamiento incremental; este archivo es el estado actual
consolidado.

---

## 1. Resumen del modelo

Motor recomendado: **PostgreSQL** (ver razones en la sección 6, heredadas
del análisis original — dominio relacional, necesidad de ACID para
documentos legales, agregaciones para el Panel del administrador).

Tablas:

- `rol` — catálogo de roles de sistema.
- `usuario` — agentes y administradores que usan el CRM (los clientes no
  tienen cuenta).
- `tipo_cliente` — catálogo de tipos de cliente (persona / empresa).
- `cliente` — entidad central del negocio.
- `estado_tramite` — catálogo de estados posibles de un trámite.
- `tramite` — corazón del MVP: cada fila es un contrato o una autorización
  de domicilio tributario en proceso.
- `historial_estado` — auditoría append-only de cambios de estado de un
  trámite.
- `plantilla_documento` — versiones de las plantillas usadas para generar
  documentos.

Relaciones:

```
rol 1───N usuario
tipo_cliente 1───N cliente
usuario 1───N tramite            (tramite.agente_id)
usuario 1───N historial_estado   (historial_estado.usuario_id)
cliente 1───N tramite
estado_tramite 1───N tramite            (tramite.estado_actual_id)
estado_tramite 1───N historial_estado   (historial_estado.estado_id)
tramite 1───N historial_estado
plantilla_documento 1───N tramite  (tramite.plantilla_documento_id, opcional)
```

---

## 2. Tablas y justificación

### 2.1 `rol`

Catálogo de roles en vez de un valor hardcodeado, para poder agregar un rol
nuevo (ej. "supervisor") sin migrar el esquema — mismo criterio que ya
traía el borrador original.

Valores esperados: `'agente'` y `'administrador'` (el catálogo venía con
`'operador'`; se acordó renombrarlo a `'agente'` para que el lenguaje del
esquema coincida con el resto de la documentación del proyecto, que usa
siempre "agente").

**Regla de negocio clave, acordada explícitamente:** `agente` y
`administrador` no son niveles de un mismo permiso, son funciones
mutuamente excluyentes:

- `administrador`: solo puede ver el Panel de administración (KPIs). No
  puede tener trámites asignados, nunca.
- `agente`: es el único rol asignable como responsable de un trámite.

Esta regla se aplica a nivel de base de datos con un trigger sobre
`tramite` (ver sección 3.3), no con un `CHECK` — un `CHECK` no puede hacer
lookup contra otra tabla en PostgreSQL estándar.

### 2.2 `usuario`

Agentes y administradores que usan el sistema (los clientes no tienen
cuenta, no inician sesión).

| Columna | Justificación |
|---|---|
| `password_hash` | El mockup tiene pantalla de Login — se guarda el hash, nunca la contraseña en texto plano. |
| `rol_id` | Define si es agente u administrador — de ahí depende qué ve en el sistema y si puede ser `tramite.agente_id`. |
| `estado` | Permite dar de baja a un agente que deja la empresa sin borrar su historial de trámites (trazabilidad se conserva). |
| `correo` | Se normaliza a minúsculas + `trim` con un trigger `BEFORE INSERT/UPDATE` (ver 3.2), para que el índice único funcione de forma case-insensitive y no se puedan crear "duplicados" solo por capitalización. |

### 2.3 `tipo_cliente`

Catálogo que reemplaza el campo de texto libre `tipo_cliente` del borrador
original (`'persona'` / `'empresa'`). Se nombra en singular (`tipo_cliente`,
no `tipos_cliente`) para mantener consistencia con el resto de las tablas
catálogo (`rol`, `estado_tramite`).

### 2.4 `cliente`

Entidad central del negocio: todo trámite cuelga de un cliente.

| Columna | Justificación |
|---|---|
| `tipo_cliente_id` | **NOT NULL.** Determina qué otros campos son obligatorios (`razon_social` real, `representante_legal` solo aplican a empresa) — sin este dato la aplicación no puede validar el resto del registro. |
| `rut` | Identificador único ante el SII; se normaliza (minúsculas + trim) con trigger antes de insertar/actualizar. |
| `rut_representante` | Se normaliza igual que `rut`. **Ver observación en sección 5** sobre su unicidad. |
| `estado` | `'activo'` / `'inactivo'`, con `CHECK` simple (no catálogo — ver justificación en 4.1). |

### 2.5 `estado_tramite`

Catálogo compartido entre `tramite.estado_actual_id` e
`historial_estado.estado_id`. Es la decisión de normalización más
importante del modelo: antes, ambas columnas eran `varchar` con su propia
lista de valores permitidos escrita dos veces (en dos `CHECK` distintos),
lo que arriesgaba que quedaran desalineadas si se agregaba un estado nuevo
en un solo lugar. Con el catálogo, ambas columnas son FK al mismo `id`, así
que es estructuralmente imposible que un trámite llegue a un estado que su
propio historial no pueda registrar.

### 2.6 `tramite`

Corazón del MVP.

| Columna | Justificación |
|---|---|
| `folio` | **Único global** (no único por `tipo_documento`). Existe para que agente/cliente lo mencionen sin ambigüedad; si fuera único solo por tipo, podría haber un "folio 0001" de contrato y otro de autorización coexistiendo, y perdería su propósito como identificador hablado. |
| `agente_id` | Quién gestiona el trámite — base de la trazabilidad por ejecutivo. Debe referenciar un `usuario` con `rol = 'agente'`, forzado por trigger (sección 3.3). |
| `estado_actual_id` | FK al catálogo `estado_tramite` — copia "cacheada" del último estado para no recalcularlo recorriendo `historial_estado` en cada listado. |
| `plantilla_documento_id` | FK **nullable** a `plantilla_documento`. Nullable porque un trámite en `borrador` todavía no tiene documento generado, por lo tanto no hay plantilla que registrar. Se llena al momento de generar el documento, y queda fijo desde ahí — aunque la plantilla se actualice a una versión nueva después, el trámite sigue apuntando a la versión exacta que realmente se usó (trazabilidad de versión, mismo principio que `historial_estado.usuario_id`). |
| `tipo_documento` | Se mantiene como campo propio aunque exista `plantilla_documento.tipo_documento` — permite filtrar/clasificar el trámite desde que se crea, antes de que se elija una plantilla específica, sin necesitar un JOIN. |

### 2.7 `historial_estado`

Tabla de auditoría append-only (nunca se edita ni se borra una fila).

| Columna | Justificación |
|---|---|
| `usuario_id` | Quién ejecutó el cambio — sin este campo no se puede cumplir el objetivo de "trazabilidad por ejecutivo" declarado en el proyecto (`tramite.agente_id` solo dice quién es el dueño, no quién tocó cada paso). |
| `estado_id` | FK al mismo catálogo `estado_tramite` que usa `tramite.estado_actual_id` (ver 2.5). |
| `comentario` | Justificación libre de un cambio (ej. motivo de un rechazo de firma). |

**Índice compuesto `(tramite_id, fecha_cambio)`:** el patrón de acceso
principal es `WHERE tramite_id = ? ORDER BY fecha_cambio` para armar la
línea de tiempo del Detalle de trámite del mockup. El índice compuesto deja
esa consulta indexada y ya ordenada, sin sort aparte. De paso resuelve que
Postgres no indexa automáticamente las columnas FK (a diferencia de
MySQL) — `tramite_id` necesitaba índice de todas formas.

### 2.8 `plantilla_documento`

Antes marcada como opcional/no crítica para el MVP; se activó en esta
versión. Permite versionar las plantillas Word/PDF usadas para generar
documentos, en vez de mantenerlas como archivos fijos sin registro en el
backend.

---

## 3. Triggers requeridos (PL/pgSQL)

Ninguna de las siguientes reglas se puede expresar con un `CHECK` de
columna simple, porque todas requieren comparar contra otra fila o otra
tabla — PostgreSQL no permite eso en un `CHECK` estándar. Por eso se
resuelven con triggers `BEFORE INSERT`/`UPDATE`.

### 3.1 No permitir dos cambios de estado idénticos consecutivos (`historial_estado`)

Evita que el mismo `estado_id` quede registrado dos veces seguidas para un
mismo trámite (ruido de auditoría, típicamente causado por reintentos o
bugs de la aplicación, no por un cambio de negocio real).

```sql
CREATE OR REPLACE FUNCTION trg_historial_estado_no_duplicado()
RETURNS trigger AS $$
DECLARE v_last_estado_id integer;
BEGIN
  SELECT he.estado_id
  INTO v_last_estado_id
  FROM historial_estado he
  WHERE he.tramite_id = NEW.tramite_id
  ORDER BY he.fecha_cambio DESC, he.id DESC
  LIMIT 1;

  IF v_last_estado_id IS NOT NULL AND v_last_estado_id = NEW.estado_id THEN
    RAISE EXCEPTION 'No se permite insertar un estado igual al último estado para el mismo tramite';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_historial_estado_no_duplicado_ins
BEFORE INSERT ON historial_estado
FOR EACH ROW
EXECUTE FUNCTION trg_historial_estado_no_duplicado();
```

*Nota:* esta versión compara solo `estado_id`. Si en el futuro se decide
que un mismo estado con un `comentario` distinto (ej. un reenvío a firma
tras un error) sí debe poder registrarse, hay que sumar `comentario` a la
comparación.

### 3.2 Normalización de `correo` y `rut` (`usuario`, `cliente`)

Normaliza a minúsculas + `trim` antes de guardar, para que los índices
únicos funcionen de forma case-insensitive y no se generen "duplicados"
por diferencias de capitalización o espacios de copiar/pegar.

```sql
CREATE OR REPLACE FUNCTION normalize_usuario_correo()
RETURNS trigger AS $$
BEGIN
  IF NEW.correo IS NOT NULL THEN
    NEW.correo := lower(trim(NEW.correo));
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_usuario_normalize_correo_ins
BEFORE INSERT ON usuario FOR EACH ROW EXECUTE FUNCTION normalize_usuario_correo();
CREATE TRIGGER trg_usuario_normalize_correo_upd
BEFORE UPDATE ON usuario FOR EACH ROW EXECUTE FUNCTION normalize_usuario_correo();

CREATE OR REPLACE FUNCTION normalize_cliente_rut()
RETURNS trigger AS $$
BEGIN
  IF NEW.rut IS NOT NULL THEN
    NEW.rut := lower(trim(NEW.rut));
  END IF;
  IF NEW.rut_representante IS NOT NULL THEN
    NEW.rut_representante := lower(trim(NEW.rut_representante));
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cliente_normalize_rut_ins
BEFORE INSERT ON cliente FOR EACH ROW EXECUTE FUNCTION normalize_cliente_rut();
CREATE TRIGGER trg_cliente_normalize_rut_upd
BEFORE UPDATE ON cliente FOR EACH ROW EXECUTE FUNCTION normalize_cliente_rut();
```

### 3.3 `tramite.agente_id` solo puede ser un usuario con rol `agente`

Aplica la separación de funciones de la sección 2.1: un `administrador` no
puede quedar asignado a un trámite bajo ninguna circunstancia.

```sql
CREATE OR REPLACE FUNCTION trg_tramite_agente_must_be_agente()
RETURNS trigger AS $$
DECLARE v_rol_nombre text;
BEGIN
  IF NEW.agente_id IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT r.nombre
  INTO v_rol_nombre
  FROM usuario u
  JOIN rol r ON r.id = u.rol_id
  WHERE u.id = NEW.agente_id;

  IF v_rol_nombre IS NULL THEN
    RAISE EXCEPTION 'agente_id % no referencia un usuario válido', NEW.agente_id;
  END IF;

  IF v_rol_nombre <> 'agente' THEN
    RAISE EXCEPTION 'No se permite asignar tramite.agente_id a un usuario con rol %, solo se permite rol = agente', v_rol_nombre;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tramite_agente_must_be_agente_biud
BEFORE INSERT OR UPDATE OF agente_id ON tramite
FOR EACH ROW
EXECUTE FUNCTION trg_tramite_agente_must_be_agente();
```

**Alcance de la validación:** solo se aplica en el momento de la
asignación (INSERT/UPDATE de `agente_id`). Si un usuario cambia de rol
después (ej. un agente asciende a administrador), los `tramite.agente_id`
históricos que ya lo referencian siguen siendo válidos — eran correctos en
el momento en que se asignaron. No hace falta un trigger adicional en
`usuario` que revalide retroactivamente los trámites existentes.

**Migración de datos pendiente** (una sola vez, antes de activar el
trigger):

```sql
UPDATE rol SET nombre = 'agente' WHERE nombre = 'operador';
```

---

## 4. Decisiones de normalización — resumen del criterio usado

### 4.1 Por qué se catalogó `estado_tramite` y `tipo_cliente`, pero no `usuario.estado`/`cliente.estado`

Se aplicó un criterio parejo, no "normalizar todo" ni "no normalizar nada":

- **Se cataloga** cuando el dominio de valores es compartido entre varias
  tablas (como `estado_tramite`, usado por `tramite` **e**
  `historial_estado` — evita que ambos queden desalineados) o cuando hay
  probabilidad real de crecer (`tipo_cliente` podría sumar un tercer valor
  como "organismo público").
- **Se deja como `CHECK` simple** cuando el dominio es binario, estable, y
  conceptualmente independiente entre tablas aunque el texto coincida
  (`usuario.estado` y `cliente.estado` significan cosas distintas — una
  cuenta que puede loguearse vs. una relación comercial vigente — aunque
  ambas usen `'activo'/'inactivo'`). Catalogarlos igual habría sido una
  abstracción falsa sin beneficio real.

### 4.2 Por qué `agente_id` usa un trigger y no una tabla `agente` separada

Se evaluó una alternativa "más pura" a nivel de modelo: una tabla `agente`
(subtipo de `usuario`) donde `tramite.agente_id` apuntara ahí en vez de a
`usuario.id`, haciendo la regla estructuralmente imposible de violar sin
trigger. Se descartó por ser sobre-ingeniería para la escala del proyecto
(equipo de 3, MVP) — agrega una tabla, joins extra, y la necesidad de mover
filas entre tablas cada vez que cambia el rol de alguien, para un riesgo
que hoy es bajo.

### 4.3 Qué se dejó fuera a propósito

No hay tablas de pago, orden de compra ni cobranza: ninguna pantalla del
mockup de Figma las contempla, y el Alcance del MVP acordado con el
cliente es solo el contrato y la autorización de domicilio tributario, sin
venta ni pago en línea.

---

## 5. Observaciones a revisar en el diagrama antes de implementar

Estas son inconsistencias puntuales detectadas al leer el markup pegado,
no cambios de diseño — se documentan acá para que se revisen en la
herramienta donde se está armando el diagrama (no se tocó ningún archivo
del esquema para corregirlas):

1. **`rol.nombre` — el índice no está marcado `unique`.** Sin unicidad, se
   podrían crear dos filas con `nombre = 'agente'`, lo que rompe la
   confiabilidad de cualquier lookup por nombre de rol (incluido el
   trigger de la sección 3.3).
2. **`usuario.correo` tiene dos índices únicos redundantes**
   (`usuario_correo_idx` y `uq_usuario_correo`) — hacen exactamente lo
   mismo, conviene dejar uno solo.
3. **`cliente.rut` tiene triple redundancia**: `unique` en la columna +
   `idx_cliente_rut` + `uq_cliente_rut`, los tres únicos sobre la misma
   columna.
4. **`cliente.rut_representante` como `unique` es cuestionable.** Un mismo
   representante legal puede perfectamente representar a más de un
   cliente/empresa (es un escenario común en el rubro de Easy Office —
   formalización de emprendimientos). Un `unique` global bloquearía ese
   caso real. Vale la pena confirmar si es intencional o un descuido, y de
   paso también tiene el mismo problema de índice duplicado que `rut`
   (`unique` inline + `uq_cliente_rut_representante`).
5. **`tramite`: el `CHECK chk_tramite_estado_actual` y el índice
   `idx_tramite_estado_actual` referencian una columna `estado_actual`**
   que ya no existe en la tabla — se reemplazó por `estado_actual_id` (FK
   al catálogo) en esta misma versión. Parecen residuos de antes de
   catalogar los estados; con la FK, la integridad ya la garantiza la
   referencia al catálogo, el `CHECK` de texto sobra.
6. **`tipo_cliente`: el índice `idx_tipos_cliente_nombre_tipo_cliente`
   referencia una columna `nombre_tipo_cliente`** que no existe en la
   tabla (solo existe `nombre`) — parece un error de tipeo.
7. **`historial_estado`: `idx_historial_estado_tramite_fecha` e
   `idx_historial_estado_tramite_fecha_cambio` son el mismo índice
   compuesto** `(tramite_id, fecha_cambio)` con dos nombres distintos —
   redundante, dejar uno.
8. **`usuario.fecha_creacion` está marcado `null`** (nullable). En el resto
   de las tablas `fecha_creacion` es `NOT NULL` con default — vale la pena
   confirmar si es intencional.
9. **`plantilla_documento`: el índice `(tipo_documento, version)` no está
   marcado `unique`.** Si el objetivo es que cada versión de una plantilla
   exista una sola vez (para que `tramite.plantilla_documento_id` apunte
   siempre a una fila inequívoca), convendría que sí lo fuera.
10. **`tramite.fecha_actualizacion` no tiene default ni un trigger que la
    actualice en cada `UPDATE`** — a diferencia de `fecha_creacion`, que sí
    tiene `def(CURRENT_TIMESTAMP)`. Si el objetivo es que refleje "última
    modificación", falta un trigger `BEFORE UPDATE` que la fije a `now()`
    en cada cambio (patrón estándar en Postgres, no viene gratis como en
    otros motores).

---

## 6. SQL vs. NoSQL (se mantiene la recomendación original)

**PostgreSQL**, sin cambios respecto al análisis anterior: dominio
altamente relacional (consultas tipo "todos los trámites de este cliente
con su historial y agente responsable"), necesidad de ACID para documentos
legales, integridad reforzada por FKs/constraints a nivel de motor, y
agregaciones (`GROUP BY`) para los KPIs del Panel del administrador. Volumen
bajo-moderado (tres agentes, un puñado de documentos), no es un escenario
donde NoSQL aporte ventaja. Ver `justificacion_modelo_datos.md` para el
detalle completo del razonamiento.
