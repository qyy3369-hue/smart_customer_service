# 【修改】从 sqlalchemy 导入 DateTime 和 func
from sqlalchemy import Column, Integer, String, DateTime, func
from app.database.PostgreSQL import PostgresBase

# 文件上传记录
class Medical_documents(PostgresBase):
    __tablename__ = "medical_documents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    document_name = Column(String(255), nullable=False)
    document_type = Column(String(100), nullable=False)
    file_path = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())    
    processed = Column(Integer, default=0)