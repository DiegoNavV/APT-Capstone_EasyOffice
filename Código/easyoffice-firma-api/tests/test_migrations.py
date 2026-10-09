"""Las migraciones deben poder aplicarse y revertirse de punta a punta."""
from pathlib import Path

from alembic import command
from alembic.config import Config

RAIZ = Path(__file__).resolve().parent.parent


def _config(url: str) -> Config:
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_y_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    # env.py toma la URL de la configuración de la app.
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        cfg = _config(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
    finally:
        get_settings.cache_clear()
