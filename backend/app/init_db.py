"""Explicit database initialisation:  python -m app.init_db

Kept out of app/database.py on purpose: running a module with -m executes it as `__main__`,
a second copy of that module with its own `Base`, so the models would register on a different
metadata object and no tables would be created.
"""
from app.config import get_settings
from app.database import create_db_engine, init_db


def main() -> None:
    engine = create_db_engine(get_settings().database_url)
    init_db(engine)
    print(f"Database initialised: {engine.url.render_as_string(hide_password=True)}")
    engine.dispose()


if __name__ == "__main__":
    main()
