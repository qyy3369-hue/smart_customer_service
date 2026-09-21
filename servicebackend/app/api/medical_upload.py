import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException
from sqlalchemy.orm import Session

from app.agent.memory import get_long_term_memory
from app.api.auth import get_current_user
from app.database.PostgreSQL import get_postgres_db
from app.model.user import User
from app.model.medicle_documents import Medical_documents
from app.RAG.document_extractor import extract_medical_info_from_pdf, save_extracted_info_to_store

router = APIRouter()

UPLOAD_DIR = "./uploads"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    user_id: Optional[str] = Form(None),
    document_name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_postgres_db)
):
    try:
        norm_user_id = f"user_{current_user.id}"
        # 严格核对前端传入的 user_id 是否与登录用户匹配
        if user_id and user_id not in [norm_user_id, str(current_user.id)]:
            raise HTTPException(status_code=403, detail="用户身份不匹配，禁止跨用户上传文档")

        filename = file.filename or "medical_doc.pdf"
        print(f"开始上传文档: {filename}, 用户: {norm_user_id}")

        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="不支持的文档格式，仅支持PDF文件")

        # 生成保存文件路径
        safe_filename = f"{norm_user_id}_{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        print(f"文件保存成功: {file_path}")

        # 提取PDF中的结构化医疗信息
        record = extract_medical_info_from_pdf(file_path)

        store=get_long_term_memory()

        # 绑定至登录用户的记忆
        saved_items=save_extracted_info_to_store(
            store=store,
            user_id=norm_user_id,
            record=record,
            filename=filename
        )
        db_document=Medical_documents(
            user_id=norm_user_id,
            document_type=document_type,
            file_path=file_path,
            document_name=filename,
            processed=1
        )
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        return {
            "message": "文档上传并解析成功",
            "document_id": db_document.id,
            "extracted_items":saved_items,
            "total_items":len(saved_items)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"文档处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



        

        
