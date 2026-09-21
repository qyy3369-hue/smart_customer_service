from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from app.api.auth import get_current_user
from app.model.user import User
from app.agent.memory import get_long_term_memory
from app.schemas.preference import (
    PreferenceSaveRequest,
    PreferenceResponse,
    PreferenceListResponse,
    MedicalHistoryResponse
)

router = APIRouter()

def get_norm_user_ids(user_id: int):
    """返回标准化的 user_id 标识集合（带前缀与纯数字形式）以保证长短记忆兼容"""
    return [f"user_{user_id}", str(user_id)]

@router.post("/save", response_model=PreferenceResponse)
async def save_preference(
    body: Optional[PreferenceSaveRequest] = Body(None),
    key: Optional[str] = Query(None),
    value: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """
    保存用户偏好设置。
    支持 JSON 请求体（推荐）或 URL 查询参数（兼容老版本）。
    偏好强制绑定至当前认证用户，禁止伪造他人 user_id。
    """
    target_key = (body.key if body and body.key is not None else key)
    target_value = (body.value if body and body.value is not None else value)

    if not target_key or target_value is None:
        raise HTTPException(status_code=400, detail="必须提供 key 和 value")

    target_key = str(target_key).strip()
    target_value = str(target_value).strip()

    try:
        store = get_long_term_memory()
        user_ids = get_norm_user_ids(current_user.id)

        # 写入长记忆 PostgresStore
        for uid in user_ids:
            namespace = ("user_preference", uid)
            item_id = f"pref_{target_key}"
            store.put(namespace, item_id, {"key": target_key, "value": target_value})

        return PreferenceResponse(
            message="偏好设置保存成功",
            key=target_key,
            value=target_value
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存偏好失败: {str(e)}")

@router.get("/list", response_model=PreferenceListResponse)
async def list_preferences(
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的偏好设置。
    数据来源为长记忆 PostgresStore，数据以换行拼接格式（匹配前端解析）及字典格式返回。
    """
    try:
        store = get_long_term_memory()
        user_ids = get_norm_user_ids(current_user.id)

        pref_dict: Dict[str, str] = {}

        for uid in user_ids:
            results = store.search(("user_preference", uid))
            if results:
                for item in results:
                    val = item.value
                    if isinstance(val, dict):
                        k = val.get("key")
                        v = val.get("value")
                        if k and v is not None:
                            pref_dict[str(k)] = str(v)

        # 按照 PreferencesView.vue 的期待格式：每行 "key: value"
        pref_lines = [f"{k}: {v}" for k, v in pref_dict.items()]
        formatted_text = "\n".join(pref_lines)

        return PreferenceListResponse(
            preferences=formatted_text,
            data=pref_dict
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取偏好列表失败: {str(e)}")

@router.get("/get_medical_history", response_model=MedicalHistoryResponse)
async def get_medical_history(
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的医疗历史记录。
    数据来源为长记忆 PostgresStore 中的 user_medical_history 命名空间。
    """
    try:
        store = get_long_term_memory()
        user_ids = get_norm_user_ids(current_user.id)

        medical_items = []
        for uid in user_ids:
            results = store.search(("user_medical_history", uid))
            if results:
                for item in results:
                    val = item.value
                    if isinstance(val, dict):
                        category = val.get("category", "")
                        content = val.get("content", "")
                        if content:
                            medical_items.append(f"{category}: {content}" if category else content)

        if not medical_items:
            return MedicalHistoryResponse(medical_history="没有找到医疗历史")

        return MedicalHistoryResponse(medical_history="\n".join(medical_items))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取医疗历史失败: {str(e)}")
