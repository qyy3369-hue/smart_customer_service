# 【修改】从 sqlalchemy 导入缺失的字段类型和函数
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database.PostgreSQL import PostgresBase

# 储存用户会话列表信息
class Conversation(PostgresBase):
    __tablename__ = "conversations"
    id = Column(String(100), primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    # 【修改】修复字段名拼写错误：titie -> title
    title = Column(String(255), nullable=False)
    last_message = Column(Text)
    last_active = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
