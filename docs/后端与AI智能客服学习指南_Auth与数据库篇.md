# 📚 后端与 AI 智能客服技术栈学习指南（Auth 认证与数据库篇）

> 💡 **导读**：本项目（`smart_customer_service`）是一个结合了 **FastAPI 后端**、**MySQL 业务存储**、**PostgreSQL 向量与记忆存储** 以及 **LangChain / AI Agent** 的现代化全栈系统。
> 本笔记将认证模块（`auth.py`）及数据存储层所需掌握的技术栈，拆解为清晰的图文段落，详细列出每个技术的**作用**、**掌握深度**及**最新权威的学习资源（已全部经过有效性与时效性核验）**。

---

## 🗺️ 架构全局与数据流向

```
┌────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Web 应用层                            │
│  - 路由管理 (APIRouter)                                               │
│  - 依赖注入 (Depends: get_db, oauth2_scheme, get_current_user)        │
│  - 异常处理 (HTTPException, 401 Unauthorized)                          │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
                   ▼                                 ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│        用户认证与安全 (Auth)          │  │       数据模型与校验         │
│  - OAuth2 密码模式与 Bearer Token    │  │  - Pydantic Schemas          │
│  - JWT (Header / Payload / Sign)     │  │  - Python Type Hints         │
│  - 密码哈希 (Bcrypt 加盐截断)         │  └──────────────┬───────────────┘
└──────────────────┬───────────────────┘                 │
                   │                                     │
                   ▼                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          SQLAlchemy ORM 映射层                         │
│  - 数据模型 (User, MedicalDocuments)                                  │
│  - 会话管理 (Session, get_db 生成器)                                   │
│  - 事务生命周期 (commit, rollback, close)                               │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
                   ▼                                 ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│           MySQL 存储引擎             │  │      PostgreSQL + pgvector   │
│  - 传统结构化业务数据                │  │  - RAG 知识库向量检索 (HNSW) │
│  - 用户表 (users), 角色权限, 登录日志│  │  - Agent 长短期记忆 (Session)│
└──────────────────────────────────────┘  └──────────────────────────────┘
```

---

## 📖 核心技术栈详解

---

### 一、 FastAPI 核心特性（Web 框架层）

> 💡 **通俗理解**：整个后端服务的“交通指挥中心”与骨架，负责接收前端 HTTP 请求、调用业务逻辑并返回响应。

#### 📌 在本项目中的位置与代码
* `APIRouter()`：创建独立的认证路由模块。
* `Depends(oauth2_scheme)` / `Depends(get_db)`：自动提取 Token、自动创建/释放数据库连接。
* `HTTPException`：抛出标准 401（未授权）等异常信息。

#### 🎯 掌握深度要求（达到【熟练】级别）
1. **依赖注入（Dependency Injection / `Depends`）**：这是 FastAPI 最核心的设计模式，必须理解它是如何在请求到来时自动执行依赖函数（如 `get_db` 获取数据库 Session），并在请求结束时自动释放资源的。
2. **路由模块化拆分（`APIRouter`）**：掌握如何将不同业务（Auth、User、Medical Documents、Chat）分别写在不同文件，最后汇总注册到主 `FastAPI()` 实例中。
3. **状态码与异常处理**：掌握 `HTTPException` 的使用，理解常用的 HTTP 状态码规范（`200 成功`, `201 已创建`, `400 请求错误`, `401 未登录/Token无效`, `403 无权限`, `404 资源不存在`, `500 服务器内部错误`）。

#### 🔗 最新官方与权威学习资源
* 📘 [FastAPI 官方文档（中文）](https://fastapi.tiangolo.com/zh/)
* 📘 [FastAPI 官方安全与鉴权教程](https://fastapi.tiangolo.com/zh/tutorial/security/)
* 🎬 [B站 - GeekHour FastAPI 快速入门视频](https://www.bilibili.com/video/BV15i4y1i7f6)

---

### 二、 OAuth2 与 JWT（认证协议与 Token）

> 💡 **通俗理解**：用户的“电子身份证”。登录成功后后端盖章发证，后续请求用户只要亮出这张证件，后端就知道他是谁，不需要重复输入账号密码。

#### 📌 在本项目中的位置与代码
* `OAuth2PasswordBearer(tokenUrl="/auth/token")`：声明从 HTTP 请求头的 `Authorization: Bearer <token>` 提取凭证。
* `create_access_token(...)`：登录成功后生成 JWT。
* `jwt.encode(header, payload, key)` / `jwt.decode(token, key)`：JWT 的签名与解密验签。

#### 🎯 掌握深度要求（达到【掌握原理与用法】级别）
1. **认证机制演进**：理解为什么传统 Web 用 Cookie/Session，而前后端分离 / 移动端 / 微服务更推荐使用 **Token 无状态认证**。
2. **JWT 三段式结构**：
   * **Header（头部）**：记录算法（如 `{"alg": "HS256"}`）。
   * **Payload（负载）**：公开的用户数据与声明，如 `sub`（代表用户 ID / 用户名）、`exp`（过期时间戳）。
   * **Signature（签名）**：服务端使用 `SECRET_KEY` 对前两部分进行的加密防篡改签名。
3. **掌握 Authlib 常用 API**：熟练编写生成 Token（`encode(header, payload, key)`）与校验解析 Token（`decode`）的代码。

#### 🔗 最新官方与权威学习资源
* 🛠️ [JWT 官方在线 Debug 调试工具 (jwt.io)](https://jwt.io/)
* 📰 [阮一峰 - JSON Web Token 入门教程](https://www.ruanyifeng.com/blog/2018/07/json_web_token-tutorial.html)
* 📘 [Authlib 官方文档（JWT 模块使用指南）](https://docs.authlib.org/en/latest/jose/jwt.html)
* 📘 [FastAPI 官方 OAuth2 with JWT 完整教程](https://fastapi.tiangolo.com/zh/tutorial/security/oauth2-jwt/)

---

### 三、 密码安全与 Bcrypt（现代密码学哈希）

> 💡 **通俗理解**：防止“数据库泄露”导致用户密码被脱裤。密码进数据库前必须经过不可逆的单向混淆。

#### 📌 在本项目中的位置与代码
* `get_password_hash(password)`：通过 `bcrypt.hashpw()` 生成加盐密码哈希。
* `verify_password(plain_password, hashed_password)`：通过 `bcrypt.checkpw()` 安全比对密码。
* `password[:72]`：对输入密码做 72 字节截断（Bcrypt 算法硬性限制）。

#### 🎯 掌握深度要求（达到【理解原理，熟练调用】级别）
1. **密码安全常识**：理解为什么数据库**绝不能明文存密码**，为什么单纯用 `MD5` 或 `SHA256` 容易被“彩虹表”秒破解。
2. **加盐机制（Salt）**：理解为什么每次调用 `gensalt()` 生成的随机盐，即使两个用户密码完全相同，存入数据库的哈希值也完全不同。
3. **慢哈希设计**：理解 Bcrypt 专门设计为计算密集型算法，大幅增加黑客暴力破解的时间成本。
4. **技术选型警示**：早期的 `passlib` 库已停止维护且在现代 Python 3.12+ 存在兼容性问题，目前业界标准直接使用 `bcrypt` 官方库或 `pwdlib`。

#### 🔗 最新官方与权威学习资源
* 🛡️ [OWASP 官方密码存储安全规范 (Password Storage Cheat Sheet)](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
* 📘 [Python Bcrypt 官方仓库与文档 (PyCA)](https://github.com/pyca/bcrypt)
* 📦 [Python Bcrypt PyPI 官方包指南](https://pypi.org/project/bcrypt/)

---

### 四、 SQLAlchemy ORM（对象关系映射）

> 💡 **通俗理解**：用写 Python 面向对象代码的方式来操作数据库，避免手写容易出错的 SQL 拼接字符串。

#### 📌 在本项目中的位置与代码
* `db: Session`：数据库会话对象。
* `db.query(User).filter(User.username == username).first()`：查询单条用户记录。
* `get_db()`：通过 `yield` 生成器模式管理 Session 的打开与关闭。

#### 🎯 掌握深度要求（达到【熟练 CRUD】级别）
1. **模型映射概念**：理解 Python 类（`class User(Base)`）是如何与数据库中的真实物理表（`users` 表）一一对应的。
2. **基础增删改查（CRUD）**：熟练使用 `db.add()`, `db.commit()`, `db.query().filter().first()`, `db.delete()` 等。
3. **Session 会话与事务**：理解为什么写操作后必须调用 `db.commit()` 生效，发生异常时如何 `db.rollback()`，以及在依赖项中用 `try...finally: db.close()` 防止连接池泄漏。

#### 🔗 最新官方与权威学习资源
* 📘 [SQLAlchemy 2.0 官方统一教程 (Unified Tutorial)](https://docs.sqlalchemy.org/en/20/tutorial/index.html)
* 📰 [廖雪峰 - Python SQLAlchemy 快速入门教程](https://www.liaoxuefeng.com/wiki/1016959663602400/1017803857459008)

---

### 五、 MySQL 关系型数据库（业务数据存储）

> 💡 **通俗理解**：成熟稳定、严谨规范的传统关系型数据库，负责存放系统的“账本”。

#### 📌 在本项目中的位置与作用
* 文件：`smart_customer_service/servicebackend/app/database/mysql.py`
* 负责存储系统最核心的业务数据：如 `users`（用户基本信息、角色、密码哈希）、工单系统、权限管理、审计日志等。

#### 🎯 掌握深度要求（达到【掌握基础 SQL 与表结构】级别）
1. **表结构与约束设计**：理解主键（`Primary Key`，自增 ID 或 UUID）、唯一索引（`Unique`，防止用户名或手机号重复）、外键（`Foreign Key`，关联两个表）。
2. **原生 SQL 阅读能力**：虽然日常写 ORM，但必须要能看懂并手写基础 SQL 语句（`SELECT ... WHERE`, `INSERT INTO`, `UPDATE`, `DELETE`, `INNER JOIN`）。
3. **图形化客户端使用**：熟练使用 **DBeaver** 或 **Navicat** 连接 MySQL，直观查看表结构、字段和数据。

#### 🔗 最新官方与权威学习资源
* 📘 [菜鸟教程 - MySQL 极简基础教程](https://www.runoob.com/mysql/mysql-tutorial.html)
* 🎬 [B站 - 狂神说 MySQL 入门视频教程（经典优质）](https://www.bilibili.com/video/BV1NJ411J79W)
* 🛠️ [DBeaver 官方下载（免费、全平台、功能强大的数据库可视化客户端）](https://dbeaver.io/)

---

### 六、 PostgreSQL + pgvector（AI 向量库与对话记忆）

> 💡 **通俗理解**：现代 AI / 大模型时代不可或缺的“全能数据库”，既能做传统存储，又能做高维向量的语义相似度检索。

#### 📌 在本项目中的位置与作用
* 文件：`smart_customer_service/servicebackend/app/database/PostgreSQL.py`
* 承担本系统两大 AI 核心能力：
  1. **医学文档知识库（RAG 检索增强生成）**：结合 `pgvector` 插件，将医疗文档的文本 Embedding 向量存入数据库，做语义相似度搜索。
  2. **Agent 记忆系统（Memory / Session Checkpointer）**：存储 LangChain / LangGraph 多轮会话状态、短期记忆与长期上下文。

#### 🎯 掌握深度要求（达到【重点掌握向量检索应用】级别）
1. **PostgreSQL 扩展机制**：了解如何启用 `CREATE EXTENSION vector;` 插件。
2. **向量类型与相似度度量**：理解向量字段类型 `vector(1536)`，掌握余弦相似度（`<=>` 操作符）、L2 欧氏距离的基本概念。
3. **向量索引优化（进阶）**：了解什么是 **HNSW** 索引和 **IVFFlat** 索引，以及为什么大批量检索时需要建向量索引提速。
4. **LangChain 集成**：熟练掌握如何配置 `PGVector` 作为 LangChain 的向量检索后端。

#### 🔗 最新官方与权威学习资源
* 📘 [PostgreSQL 官方最新文档手册](https://www.postgresql.org/docs/current/)
* 💻 [pgvector 官方 GitHub 仓库与使用指南](https://github.com/pgvector/pgvector)
* 📘 [LangChain 官方集成文档：PGVector 向量存储](https://python.langchain.com/docs/integrations/vectorstores/pgvector/)

---

### 七、 Pydantic 与 Python 类型提示（数据契约层）

> 💡 **通俗理解**：给动态类型的 Python 加上“安全护栏”，自动完成前端传入 JSON 数据的类型转换与校验。

#### 📌 在本项目中的位置与代码
* 文件：`app/schemas/user.py`
* `TokenData(user_id=...)`：定义 Token 解析后的合法数据结构。
* 函数签名：`create_access_token(data: dict, expires_delta: timedelta | None = None)`。

#### 🎯 掌握深度要求（达到【熟练定义与转换】级别）
1. **Pydantic BaseModel**：熟练继承 `BaseModel` 定义请求 Body、返回 Response 的数据模型。
2. **Schema 与 ORM Model 分离**：深刻理解为什么 `schemas/user.py`（对外数据接口契约）要与 `model/user.py`（对内数据库物理表映射）分开编写。
3. **类型提示（Type Hints）**：熟练使用 Python 3.10+ 的联合类型（`int | None`）、泛型容器（`list[str]`, `dict[str, Any]`）。

#### 🔗 最新官方与权威学习资源
* 📘 [Pydantic V2 官方最新文档](https://docs.pydantic.dev/latest/)
* 📘 [FastAPI 官方数据模型与 Pydantic 教程](https://fastapi.tiangolo.com/zh/tutorial/body/)

---

## 🔍 代码实战逐行对照解析（以 `auth.py` 为例）

```python
# 1. 【密码学哈希】注册或修改密码时，将明文密码转化为安全哈希存入数据库
def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password[:72].encode("utf-8"), salt).decode("utf-8")

# 2. 【SQLAlchemy + 密码校验】用户登录时，先查库找人，再比对哈希密码
def authenticate_user(db: Session, username: str, password: str):
    # 用 SQLAlchemy 从 MySQL 查出 User 对象
    user = db.query(User).filter(User.username == username).first()
    # 如果用户不存在 或 密码哈希不匹配，返回 False
    if not user or not verify_password(password, user.password_hash):
        return False
    return user

# 3. 【JWT 编码】账密核验成功后，制作并颁发一张带有效期的 JWT Token 字符串
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    
    # 按照 Authlib 标准规范：在 header 指定算法，传入 payload 与 secret_key 签名
    header = {"alg": settings.ALGORITHM}
    return jwt.encode(header, to_encode, settings.SECRET_KEY).decode("utf-8")

# 4. 【FastAPI 依赖注入鉴权】客户端请求受保护接口时，自动从请求头提取 Token 并验签
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # 定义通用的 401 认证失败异常
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 解码并验证 Token 签名是否有效
        payload = jwt.decode(token, settings.SECRET_KEY)
        user_id = payload.get("sub")
        token_data = TokenData(user_id=int(user_id))
    except Exception:
        raise credentials_exception
    
    # 从数据库中获取该用户对象
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise credentials_exception
    return user
```

---

## 🚀 建议学习路线规划

* **第 1 阶段：认证闭环基础（预计耗时 1~2 天）**
  * 观看 JWT 动画视频，理解 Token 签名和载荷机制。
  * 阅读 FastAPI 官方文档中的 Security 教程，理解 `Depends` 是如何拦截请求的。
  * 掌握 SQL 基础增删改查与 SQLAlchemy 基本用法。
* **第 2 阶段：业务联调打通（预计耗时 2~3 天）**
  * 使用 Postman / Swagger UI 跑通：`注册 -> 登录获取 Token -> 携带 Token 请求受保护接口` 完整链路。
  * 用 DBeaver 连接本地 MySQL，观察用户数据和密码哈希值。
* **第 3 阶段：AI 客服进阶（预计耗时 3~5 天）**
  * 深入学习 PostgreSQL + `pgvector` 插件。
  * 跑通 LangChain RAG 医学知识库向量存取与 LangGraph 多轮会话记忆。
