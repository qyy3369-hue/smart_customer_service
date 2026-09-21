from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config.settings import settings
from sqlalchemy import create_engine
postgresql_engine=create_engine(
    settings.POSTGRES_SESSION_URL,
    pool_pre_ping=True,
    pool_recycle=3600
)

postgres_sessionLocal=sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=postgresql_engine
)

PostgresBase=declarative_base()

def get_postgres_db():
    db=postgres_sessionLocal()
    try:
        yield db
    finally:
        db.close()

# 别名兼容
get_session = get_postgres_db
    