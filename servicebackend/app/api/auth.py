from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from app.schemas.user import UserCreate
from app.schemas.user import UserResponse
from app.schemas.user import TokenData
from fastapi import HTTPException
from fastapi import status
from app.database.PostgreSQL import get_postgres_db
from fastapi import Depends
from jose import jwt, JWTError
from app.config.settings import settings
from datetime import datetime
from datetime import timedelta
from app.model.user import User
import bcrypt
from fastapi.security.oauth2 import OAuth2PasswordBearer
from fastapi import APIRouter
from sqlalchemy.orm import Session
from app.schemas.user import Token

#创建路由实例
router=APIRouter()

#OAuth2方案配置
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="/auth/token")

#验证密码 
def verify_password(plain_password:str,hashed_password:str) ->bool:
    truncated_password=plain_password[:72]

    return bcrypt.checkpw(truncated_password.encode("utf-8"),hashed_password.encode("utf-8"))

#获取密码哈希值
def get_password_hash(password:str)->str:
    truncated_password=password[:72]
    salt=bcrypt.gensalt()
    return bcrypt.hashpw(truncated_password.encode("utf-8"),salt).decode("utf-8")

#认证，验证用户名和密码是否正确
def authenticate_user(db:Session,username:str,password:str):
    user=db.query(User).filter(User.username==username).first()
    if not user:
        return False
    if not verify_password(password,user.password_hash):
        return False
    return user
#生成access_token
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    #避免修改原始数据
    to_encode = data.copy()
    #设置过期时间
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    #返回token
    return encoded_jwt

#解析token
async def get_current_user(token:str=Depends(oauth2_scheme),db:Session=Depends(get_postgres_db)):
    #定义认证异常
    credentials_exception=HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload=jwt.decode(token,settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
        user_id=payload.get("sub")
        token_data=TokenData(user_id=int(user_id))
    except JWTError:
        raise credentials_exception
    user=db.query(User).filter(User.id==token_data.user_id).first()
    if not user:
        raise credentials_exception
    return user
    
#注册
@router.post("/register",response_model=UserResponse)
def register(
    user:UserCreate,db:Session=Depends(get_postgres_db)
    ):
    existing_user=db.query(User).filter((User.username==user.username)|(User.email==user.email)).first()
    if existing_user:
        if existing_user.username==user.username:
            raise HTTPException(status_code=400,detail="用户名已存在")
        if existing_user.email==user.email:
            raise HTTPException(status_code=400,detail="邮箱已存在")
    hashed_password=get_password_hash(user.password)
    db_user=User(
        username=user.username,
        email=user.email,
        password_hash=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

#登录
@router.post("/token",response_model=Token)
def login(form_data: OAuth2PasswordRequestForm=Depends(),db:Session=Depends(get_postgres_db)):
    user=authenticate_user(db,form_data.username,form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token=create_access_token(
        data={"sub":str(user.id)},
        expires_delta=access_token_expires
    )
    return {
        "access_token":access_token,
        "token_type":"Bearer",
        "user_id":user.id}
    
        

