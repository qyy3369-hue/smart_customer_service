from app.config.settings import settings
import os

#模型初始化
from langchain_openai import ChatOpenAI
def get_model(*, enable_thinking: bool | None = None):
    options = {}
    if enable_thinking is not None:
        options["extra_body"] = {"enable_thinking": enable_thinking}
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.3,
        **options,
    )

# Embedding 模型初始化
from langchain_community.embeddings import DashScopeEmbeddings

def get_embedding_model():
    """获取文本嵌入模型实例"""
    return DashScopeEmbeddings(
        model=settings.EMBEDDING_MODEL,
        dashscope_api_key=settings.DASHSCOPE_API_KEY
    )

get_embeddings = get_embedding_model

    
