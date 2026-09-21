from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.agent.memory import get_short_term_memory
from app.agent.intake import suggested_intake
from app.agent.intake_review import legacy_doctor_followup_cards
from app.api.auth import get_current_user
from app.database.PostgreSQL import get_postgres_db
from app.model.conversation import Conversation
from app.model.user import User

#创建路由实例

router = APIRouter()

#会话创建请求的 模型
class ConversationCreate(BaseModel):
    id: str

    title: str



#创建新会话 接口
@router.post("/create")
async def create_conversation(
        conversation: ConversationCreate,
        user_id: Optional[int] = Query(None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_postgres_db)
    ):

    try:
        if user_id is not None and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="禁止为其他用户创建会话")

        existing_conv = db.query(Conversation).filter(Conversation.id == conversation.id).first()

        if existing_conv:
            raise HTTPException(status_code=400, detail="会话id已存在")

        #创建新会话 ORM 对象（强制绑定登录用户的真实 ID）
        from datetime import datetime
        new_conv = Conversation(
            id=conversation.id,
            title=conversation.title,
            user_id=current_user.id,
            last_message="",
            last_active=datetime.now(),
            created_at=datetime.now()
        )

        db.add(new_conv)

        db.commit()

        db.refresh(new_conv)

        return {
            "message": "会话创建成功",
            "conversation": {
                "id": new_conv.id,
                "title": new_conv.title,
                "user_id": new_conv.user_id,
                "last_message": new_conv.last_message,
                "last_active": new_conv.last_active,
                "created_at": new_conv.created_at
            }
        }

    except HTTPException :
        raise

    except Exception as e :
        raise HTTPException(status_code=500, detail=f"会话创建失败: {str(e)}")



#获取会话列表
@router.get("/list")
async def list_conversations(
        user_id: Optional[int] = Query(None),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_postgres_db)
):
    try:
        if user_id is not None and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权查看其他用户的会话列表")

        conversations = (
            db.query(Conversation)
            .filter(Conversation.user_id == current_user.id)
            .order_by(Conversation.last_active.desc())
            .all()
        )

        result = []

        for conversation in conversations:
            result.append({
                "id": conversation.id,
                "title": conversation.title,
                "user_id": conversation.user_id,
                "last_message": conversation.last_message,
                "last_active": conversation.last_active,
                "created_at": conversation.created_at
            })

        return {
            "conversations": result
        }
    except HTTPException :
        raise
    except Exception as e :
        raise HTTPException(status_code=500, detail=f"会话列表获取失败: {str(e)}")

#删除会话接口
@router.delete("/delete")
async def delete_conversation(
        conversation_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_postgres_db)
    ):

    try:
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="会话不存在")
        if conversation.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权删除该会话")

        #删除会话 会话列表中删除 +  短期记忆删除
        try:
            checkpointer = get_short_term_memory()

            if checkpointer:
                checkpointer.delete_thread(thread_id=conversation_id)
                print("清理短记忆成功")
        except Exception as e :
            print(f"清理短记忆失败 :{str(e)} ")

        db.delete(conversation)
        db.commit()

        return {
            "message": "会话删除成功"
        }
    except HTTPException :
        raise
    except Exception as e :
        raise HTTPException(status_code=500, detail=f"会话删除失败: {str(e)}")


#获取会话详情接口

@router.get("/get")
async def get_conversation(
        conversation_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_postgres_db)
    ):

    try:

        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="会话不存在")
        if conversation.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权查看该会话")

        #消息列表
        message_list = []
        intake_questions = []
        try:
            checkpointer = get_short_term_memory()

            config = {"configurable":{"thread_id":conversation_id}}

            checkpoints = list(checkpointer.list(config))

            if checkpoints:
                latest = checkpoints[0]

                checkpoint_data = latest.checkpoint

                channel_values = checkpoint_data.get("channel_values", {})
                intake_questions = channel_values.get("intake_questions") or []

                messages = channel_values.get("messages", [])
                legacy_questions = []

                # Older conversations may contain a text-only examiner question from
                # before structured intake was introduced. Reconstruct the cards on
                # read so a refresh upgrades that unfinished turn without an LLM call.
                if (not intake_questions and messages
                        and getattr(messages[-1], "type", None) == "ai"
                        and "【体检员】" in str(getattr(messages[-1], "content", ""))):
                    _, intake_questions = suggested_intake(messages)
                elif not intake_questions and messages:
                    legacy_questions = legacy_doctor_followup_cards(messages)
                    intake_questions = legacy_questions

                for msg in messages:
                    if hasattr(msg,'content') and hasattr(msg,'type'):

                        #过滤
                        if msg.type in ['human','ai']:
                            if msg.content and str(msg.content).strip():

                                role = "user" if msg.type == "human" else "assistant"
                                msg_timestamp = getattr(msg, 'additional_kwargs', {}).get('timestamp') or datetime.now().isoformat()

                                content = msg.content
                                if (legacy_questions and msg is messages[-1]
                                        and role == "assistant"):
                                    content = "主治医生还需要确认少量信息，请继续选择卡片。"
                                message_list.append({
                                    "role": role,
                                    "content": content,
                                    "timestamp": msg_timestamp
                                })
        except Exception as e :
            print(f"读取短记忆失败: {str(e)}")
            import traceback
            print(traceback.format_exc())

        return {
            "conversation": {
                "id": conversation.id,
                "title": conversation.title,
                "user_id": conversation.user_id,
                "last_message": conversation.last_message,
                "last_active": conversation.last_active,
                "created_at": conversation.created_at,
            },
            "messages": message_list,
            "intake_questions": intake_questions,
        }

    except HTTPException :
        raise
    except Exception as e :
        raise HTTPException(
            status_code=500,
            detail=f"会话详情获取失败: {str(e)}"
        )
