from datetime import datetime
import json
import traceback
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from langchain_core.messages import AIMessage, HumanMessage

from app.model.conversation import Conversation
from app.model.user import User
from app.api.auth import get_current_user
from app.database.PostgreSQL import get_postgres_db
from app.agent.multi_agent import create_medical_agent_system

router = APIRouter()

class ChatRequest(BaseModel):
    user_id: str
    thread_id: str
    message: str
    card_answers: Optional[dict] = None


def _prepare_chat(request: ChatRequest, current_user: User, db: Session):
    norm_user_id = f"user_{current_user.id}"
    if request.user_id and request.user_id not in [norm_user_id, str(current_user.id)]:
        raise HTTPException(status_code=403, detail="用户身份不匹配，禁止跨用户发送消息")
    conversation = db.query(Conversation).filter(Conversation.id == request.thread_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")
    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该会话")
    if not request.message.strip() and request.card_answers is None:
        raise HTTPException(status_code=422, detail="消息或卡片答案不能为空")

    display_text = request.message.strip() or "已提交问诊卡片"
    conversation.last_message = (display_text[:50] + "...") if len(display_text) > 50 else display_text
    conversation.last_active = datetime.now()
    db.commit()

    initial_state = {
        "messages": [HumanMessage(content=display_text)],
        "user_id": norm_user_id,
        "thread_id": request.thread_id,
        "medical_documents": [], "diagnosis": None, "prescription": None, "next": None,
        "case_summary": None, "ready_for_doctor": False, "sources": [],
        "retrieval_status": None, "textbook_hits": [], "textbook_status": None,
        "unavailable_books": [], "retrieval_queries": [], "evidence_route": None,
        "evidence_reason": None, "web_hits": [], "web_status": None,
        "intake_submission": request.card_answers,
        "intake_review_reason": None,
        "stream_response": False,
    }
    config = {"configurable": {"user_id": norm_user_id, "thread_id": request.thread_id}}
    return initial_state, config


def _answer_payload(response: dict) -> dict:
    content = next((msg.content for msg in reversed(response.get("messages") or [])
                    if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip()), "")
    return {
        "success": True, "message": content,
        "intake_questions": response.get("intake_questions") or [],
        "sources": response.get("sources", []),
        "retrieval_status": response.get("retrieval_status"),
        "evidence_route": response.get("evidence_route"),
        "evidence_reason": response.get("evidence_reason"),
        "textbook_status": response.get("textbook_status"),
        "web_status": response.get("web_status"),
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@router.post("/send")
async def send_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_postgres_db)
):
    try:
        initial_state, config = _prepare_chat(request, current_user, db)
        graph = create_medical_agent_system()
        try:
            response = graph.invoke(initial_state, config=config)
        except Exception as e:
            print(f"智能体系统执行出错：{str(e)}")
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))

        return JSONResponse(content=_answer_payload(response), status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        print(f"发送消息接口出错：{str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_postgres_db),
):
    # Authorization is completed before any bytes are sent.
    initial_state, config = _prepare_chat(request, current_user, db)
    initial_state["stream_response"] = True
    graph = create_medical_agent_system()

    def events():
        updates = {}
        try:
            yield _sse("status", {"stage": "intake" if request.card_answers is None else "processing"})
            for mode, data in graph.stream(initial_state, config=config, stream_mode=["custom", "updates"]):
                if mode == "custom" and isinstance(data, dict) and data.get("type") == "doctor_delta":
                    yield _sse("delta", {"text": data["text"]})
                elif mode == "updates":
                    for node, result in data.items():
                        if isinstance(result, dict):
                            updates.update(result)
                            if node in {"intake_gate", "intake_review", "attending_doctor"} and result.get("intake_questions"):
                                yield _sse("status", {"stage": "questions"})
                            elif node in {"textbook_retriever", "web_retriever"}:
                                yield _sse("status", {"stage": "retrieving"})
                            elif node == "attending_doctor":
                                yield _sse("status", {"stage": "verifying"})
            yield _sse("final", _answer_payload(updates))
        except Exception:
            print(traceback.format_exc())
            yield _sse("error", {"message": "回答暂时失败，请稍后重试。"})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
