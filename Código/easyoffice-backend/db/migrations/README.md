# Migraciones

Cambios al esquema para bases de datos **ya creadas**. Una base nueva no las
necesita: se crea completa desde `db/init/`.

## Línea base

El esquema v4 (`db/init/`, octubre 2026) es la línea base. Reemplazó al
esquema anterior desde cero, sin migrar datos (`docker compose down -v`), así
que las migraciones 001–006 del esquema anterior se eliminaron: referenciaban
tablas y columnas que ya no existen. Siguen disponibles en el historial de git.

## Cómo agregar una migración

1. Crear `NNN_descripcion.sql`, numerado desde `001` en adelante.
2. Que se pueda ejecutar más de una vez sin error: `IF NOT EXISTS`,
   `CREATE OR REPLACE`, `DROP ... IF EXISTS` antes de crear un trigger, etc.
3. Explicar en la cabecera qué cambia y por qué.
4. Aplicar el **mismo cambio** en el archivo que corresponda de `db/init/`,
   para que una base nueva quede igual que una migrada.
5. Actualizar `app/models.py` si cambian tablas o columnas.

Para aplicarla sobre la base de Docker:

```bash
docker compose exec -T db psql -U easyoffice -d crm_easyoffice < db/migrations/NNN_descripcion.sql
```
