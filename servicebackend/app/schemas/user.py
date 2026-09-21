from pydantic import BaseModel
from typing import Optional
from datetime import datetime

#用户基础模型
class UserBase(BaseModel):
    username:str
    email:str

#注册模型   
class UserCreate(UserBase):
    password:str

#用户模型
class UserResponse(UserBase):
    id:int
    created_at:datetime
    updated_at:datetime

    #启用ORM属性映射模式 允许从ORM实例自动读取
    class Config:
        from_attributes=True

#Token模型    
class Token(BaseModel):
    access_token:str
    token_type:str    
    user_id:int  

#token数据模型 用于解析jwt
class TokenData(BaseModel):
    user_id:Optional[int]=None  


