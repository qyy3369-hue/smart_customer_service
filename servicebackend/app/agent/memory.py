# 短记忆数据库连接池
from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver
from app.config.settings import settings
from psycopg_pool import ConnectionPool

short_term_pool = None
# 长记忆数据库连接池
long_term_pool = None
# 会话向量数据库
short_term_memory = None
# 用户画像向量数据库
long_term_memory = None


# 创建数据库连接池
def init_memory_system():
    global short_term_pool, long_term_pool, short_term_memory, long_term_memory

    if short_term_pool is None:
        try:
            print("短记忆连接池初始化中")
            short_term_pool = ConnectionPool(
                conninfo=settings.POSTGRES_SHORT_TERM_URL,
                min_size=2,
                max_size=10,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 3
                }
            )
            short_term_memory = PostgresSaver(short_term_pool)
            short_term_memory.setup()
            print("短记忆连接池初始化成功")

            # 长记忆数据库连接池
            long_term_pool = ConnectionPool(
                conninfo=settings.POSTGRES_LONG_TERM_URL,
                min_size=2,
                max_size=10,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 3
                }
            )
            long_term_memory = PostgresStore(long_term_pool)
            long_term_memory.setup()
            print("长记忆连接池初始化成功")

        except Exception as e:
            print(f"数据库连接池初始化失败: {e}")
            raise


# 获取短记忆实例
def get_short_term_memory():
    global short_term_memory
    if short_term_memory is None:
        init_memory_system()
    return short_term_memory


# 获取长记忆实例
def get_long_term_memory():
    global long_term_memory
    if long_term_memory is None:
        init_memory_system()
    return long_term_memory


# 长记忆管理

# 保存用户个人数据到长记忆
def save_user_long_memory(store, namespace: tuple, item_id: str, data: dict):
    if store is None:
        store = get_long_term_memory()
    try:
        store.put(namespace, item_id, data)
    except Exception as e:
        print(f"保存长记忆失败: {e}")


# 获取单条长记忆项目
def get_user_long_memory_item(store, namespace: tuple, item_id: str):
    if store is None:
        store = get_long_term_memory()
    try:
        return store.get(namespace, item_id)
    except Exception as e:
        print(f"获取长记忆失败: {e}")
        return None


# 获取用户长记忆聚合文本
def get_user_long_memory(user_id: str, store=None):
    if store is None:
        store = get_long_term_memory()

    user_info = []

    try:
        preference = store.search(("user_preference", str(user_id)))
        if preference:
            pref_dict = {}

            for item in preference:
                # langgraph存储数据时自动用这个连接
                key_parts = item.key.split("|") if "|" in item.key else [item.key]
                item_id = key_parts[-1] if key_parts else item.key
                # 去重
                pref_dict[item_id] = item.value

            pref_text = "\n".join([
                f"{value.get('key')}:{value.get('value')}"
                for value in pref_dict.values()
            ])
            user_info.append(
                f"【用户基本信息】:\n{pref_text}"
            )

        # 获取用户医疗信息
        medical_history = store.search(("user_medical_history", str(user_id)))

        if medical_history:
            medical_by_category = {}
            for item in medical_history:
                category = item.value.get("category", "unknow")
                content = item.value.get("content", "")

                if category not in medical_by_category:
                    medical_by_category[category] = []
                medical_by_category[category].append(content)

            # 格式化输出
            history_lines = []
            for category, contents in medical_by_category.items():
                # 如果只有一条
                if len(contents) == 1:
                    history_lines.append(
                        f"{category}: {contents[0]}"
                    )
                else:
                    items_text = "\n".join([
                        f"{i+1}.{c}" for i, c in enumerate(contents)
                    ])
                    history_lines.append(
                        f"{category}:\n{items_text}"
                    )

            medical_text = "\n".join(history_lines)
            user_info.append(
                f"【用户医疗历史】:\n{medical_text}"
            )

    except Exception as e:
        print(f"获取用户长记忆失败: {e}")

    return "\n\n".join(user_info) if user_info else ""