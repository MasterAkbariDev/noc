from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from noc.config import get_settings
from noc.db import models
from noc.db.base import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata


def run_migrations() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
