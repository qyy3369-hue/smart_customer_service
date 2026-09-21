# 【修改】从 sqlalchemy 导入 DateTime 和 func
from sqlalchemy import Column, Integer, String, DateTime, func
# 【修改】基类导入名称修改为 PostgresBase
from app.database.PostgreSQL import PostgresBase

# 用户模型
class User(PostgresBase):
    # 表名 ORM框架
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # 【修改】SQLAlchemy 参数为 onupdate
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())