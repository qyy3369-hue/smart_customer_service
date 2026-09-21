from app.api import chat
from app.api import conversation
from app.api import auth
from app.api import medical_upload
from app.api import preferences
from starlette.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from app.database.PostgreSQL import postgresql_engine
from app.config.settings import settings
import os
from app.database.PostgreSQL import PostgresBase
from app.model.conversation import Conversation
from app.model.user import User
from app.model.medicle_documents import Medical_documents

__all__=["Conversation","User","Medical_documents"]

#初始化langsmith
os.environ["LANGCHAIN_TRACING_V2"] = str(settings.LANGCHAIN_TRACING_V2).lower()
os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT

try:
    #根据模型定义生成表
    PostgresBase.metadata.create_all(bind=postgresql_engine)
    print("数据库连接成功，表已创建")
except Exception as e:
    print(f"数据库连接失败: {e}")

app=FastAPI(
    title="智能医疗助手后端",
    description="基于LangChain和Qwen的智能医疗助手API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
    
#注册路由
app.include_router(auth.router,prefix="/auth",tags=["登录注册"])
app.include_router(conversation.router,prefix="/conversations",tags=["会话"])
app.include_router(chat.router,prefix="/chat",tags=["聊天"])
app.include_router(medical_upload.router,prefix="/documents",tags=["文档上传"])
app.include_router(preferences.router,prefix="/preferences",tags=["偏好设置"])

@app.get("/")
async def root():
    """根路径"""
    return {
        "messages":"智能医疗助手 API",
        "version":"1.0.0",
        "docs":"/docs",
        "author":"yyq"
        }
        
if __name__=="__main__":
    import uvicorn
    print("智能医疗助手API服务启动中...")
    print(f"访问地址：http://{settings.HOST}:{settings.PORT}")
    print(f"访问文档：http://{settings.HOST}:{settings.PORT}/docs")
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
        )
    



