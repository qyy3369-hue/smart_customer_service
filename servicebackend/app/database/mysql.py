from app.config.settings import settings
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine

#创建MySQL链接引擎
engine=create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600
)

#创建一个同步会话
SessionLocal=sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)
#创建模型基类
Base=declarative_base()

def get_db():
    """获取数据库会话"""
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()
    