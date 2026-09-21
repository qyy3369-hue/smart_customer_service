# 智能医疗助手后端服务 (servicebackend)

基于 **FastAPI** + **LangChain 1.0** + **LangGraph** + **PostgreSQL** + **MySQL** 构建的智能医疗问诊与长短记忆对话系统。

---

## 🛠️ 环境要求

- **Python**: 3.10 ~ 3.13 (推荐 3.11 或 3.12)
- **数据库**:
  - MySQL 8.0+ (用户认证与权限管理)
  - PostgreSQL 15+ (短记忆 Checkpointer + 长记忆 Store + 会话管理)

---

## 🚀 快速上手

### 1. 创建并激活虚拟环境

在 `servicebackend` 目录下创建独立的 Python 虚拟环境，确保依赖环境纯净隔离：

```bash
cd servicebackend

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
# macOS / Linux:
source .venv/bin/activate

# Windows (CMD / PowerShell):
# .venv\Scripts\activate
```

### 2. 安装项目依赖

在激活的虚拟环境中，执行依赖安装：

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

从示例文件创建实际的环境变量配置文件：

```bash
cp .env.example .env
```

打开 `.env` 文件，填入你的实际配置：
- `DASHSCOPE_API_KEY`: 阿里云百炼 API Key（通义千问模型）
- `TAVILY_API_KEY`: Tavily 联网搜索 Key
- `DATABASE_URL`: MySQL 数据库连接串
- `POSTGRES_*`: PostgreSQL 短记忆、长记忆、会话库连接串

---

## 💻 标准启动方式

确保虚拟环境已激活，并处于 `servicebackend` 目录下：

### 方式一：直接运行入口脚本（推荐）

```bash
python main.py
```
> 该脚本会自动从配置读取 `HOST` 与 `PORT`，并开启 `--reload` 热重载模式。

### 方式二：使用 uvicorn CLI 启动

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动后控制台将输出服务运行状态：
```text
智能医疗助手API服务启动中...
访问地址：http://0.0.0.0:8000
访问文档：http://0.0.0.0:8000/docs
```

---

## 📖 API 文档

服务启动成功后，可在浏览器直接访问交互式接口文档：
- **Swagger UI 交互式文档**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Redoc 文档**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## 药理学教材 RAG（本地练习）

《药理学》第九版 PDF 放在仓库根目录 `PDF/`。全书扫描页先由 macOS Vision
在内存中 OCR；页面文本与 1024 维向量分别存入 `smart_long` 的
`medical_book_pages`、`medical_book_chunks` 表，来源及入库状态存入
`medical_book_sources`。需要先在该 PostgreSQL 数据库安装并启用 pgvector。

在仓库根目录、已有 `langGraph` 环境中运行：

```bash
conda run -n langGraph python servicebackend/scripts/book_vector_ingest01.py --dry-run
conda run --no-capture-output -n langGraph python -u servicebackend/scripts/book_vector_ingest01.py --run --max-cost-cny 0.20
```

脚本按页缓存 OCR 文本、按批提交向量，可以中断续跑；会尽量复用之前
Chroma 试运行的药理学向量。默认的 ¥0.20 是基于公开同步单价的新增向量
费用上限估算，不是平台实际账单上限，也不包含问答模型费用。完成后报告在
`book_vector_report02.json`。药师节点检索 `status=ready` 的教材片段，回答引用
PDF 页码；这与书内印刷页码可能不同。

PDF 原件及 OCR 文本留在本机；向量化时文本片段会发送至百炼 API。教材仅用于
个人练习，不应把来源不明或受版权保护的 PDF 推送到公开仓库。

### 继续导入《内科学》和《诊断学》

两本书使用同一套 `smart_long`/pgvector 表，来源分别标记为
`internal_medicine` 和 `diagnostics`。执行前应备份数据库；以下脚本可中断续跑，
只对缺少的切块调用向量化 API：

```bash
conda run -n langGraph python servicebackend/scripts/book_vector_ingest.py --book internal_medicine --dry-run
conda run --no-capture-output -n langGraph python -u servicebackend/scripts/book_vector_ingest.py --book internal_medicine --run --max-cost-cny 0.35
conda run -n langGraph python servicebackend/scripts/book_vector_ingest.py --book diagnostics --dry-run
conda run --no-capture-output -n langGraph python -u servicebackend/scripts/book_vector_ingest.py --book diagnostics --run --max-cost-cny 0.20
```

各书的页码、OCR 覆盖、切块数量和 API Token 用量记录在
`book_vector_report03.json`、`book_vector_report04.json`。这一步仅完成向量入库；
问诊时体检员先生成结构化病例摘要；继续分析旧病例也先重整摘要，
避免仅以“继续分析”等短语检索。信息足够时在同一轮进入教材检索，
分别查《诊断学》和《内科学》。首次无命中会改写检索问题并重试一次，
随后证据监督者先审查片段是否真的对应本次症状，再按结构化命中状态选择
`book_only`、`book_plus_web` 或 `web_only`；无关片段不会传给医生。
需要联网时，搜索节点保留网页标题和 URL，再交给医生融合；药师仍单独检索《药理学》。
医生回答中的 `[教材N]`、`[网页N]` 必须对应本轮实际命中的来源，末尾由程序写入
书名/PDF 页码或网页链接；两类来源都没有时不假称有依据。
编号校验只能证明来源页存在，不能自动证明每一句医学推断都被该页充分支持；
用于个人学习前仍应抽查片段与回答的对应关系。

医生检索的余弦距离上限当前暂定为 0.50，双书检索时还要求候选片段与全局最佳
距离相差不超过 0.08；药理学上限为 0.60。这些都是防止明显误命中的
初步阈值，不代表已通过医学问答评测。通常每轮生成一次查询向量，首次无命中时
最多再生成一次查询向量；需要联网时还会产生 Tavily 查询与额外模型费用，
不会重新向量化整本书。
有候选片段时还需一次模型相关性审查。症状轮通常也会调用监督者、体检员、结构化评估和医生模型，因此响应时间与
费用并不只取决于向量检索；体检员和医生目前关闭了模型思考模式以控制延迟。

可运行离线测试：

```bash
cd servicebackend
conda run -n langGraph python -m unittest discover -s tests -v
```

---

## 📦 核心目录结构

```text
servicebackend/
├── app/
│   ├── agent/               # 医疗 Agent 与记忆系统
│   ├── api/                 # FastAPI 路由层 (auth, chat, conversations, preferences, documents)
│   ├── config/              # 全局配置 (settings.py)
│   ├── database/            # 数据库连接与引擎 (MySQL, PostgreSQL)
│   ├── model/               # ORM 数据表实体模型
│   ├── RAG/                 # 文档抽取与向量检索
│   └── schemas/             # Pydantic 请求与响应验证模型
├── .env.example             # 环境变量配置模板
├── main.py                  # 服务统一入口文件
├── README.md                # 后端部署与开发指引
└── requirements.txt         # 锁定的完整依赖清单
```
