"""
Chat API endpoints.

POST /chat/send      — send a message and get an AI answer (RAG pipeline)
GET  /chat/history   — retrieve past chat messages for the current user
POST /chat/sessions  — create a new chat session
"""

import uuid
import json
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db.session import get_db
from db.models import ChatMessage, GitHubConnection, PushEvent, ResumeVersion
from core.workspace import get_workspace_owner as get_current_user
from agents.chat_agent import chat_with_career_data
from agents.llm_client import LLMClient
from services.text_extraction import extract_text, extract_zip_files
from services.multimodal_service import analyze_image

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


# ─── Request / Response models ──────────────────────────────────────

class ChatSource(BaseModel):
    chunk_text: str
    score: float
    source_filename: Optional[str]
    resume_version_id: Optional[str]


class PushEventDetail(BaseModel):
    id: str
    repo_name: str
    description: Optional[str] = None
    files: Optional[List[dict]] = None


class TailoredResumeDetail(BaseModel):
    resume_id: str
    original_resume_id: Optional[str] = None
    changes_summary: str


class ChatSendResponse(BaseModel):
    answer: str
    sources: List[ChatSource]
    session_id: str
    user_message_id: str
    assistant_message_id: str
    push_event: Optional[PushEventDetail] = None
    tailor_event: Optional[TailoredResumeDetail] = None


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    session_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class NewSessionResponse(BaseModel):
    session_id: str


# ─── Endpoints ──────────────────────────────────────────────────────

@router.post("/send", response_model=ChatSendResponse)
async def send_message(
    message: str = Form(...),
    session_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Send a user message with an optional file/image attachment.
    If a document is uploaded, text is extracted.
    If an image is uploaded, Gemini 1.5 Flash transcribes/describes it.
    Both message and answer are saved to chat_messages.
    """
    user_id = current_user.id
    resolved_session_id = session_id or str(uuid.uuid4())


    extracted_content = ""
    attachment_tag = ""
    extracted_files = []
    is_zip = False

    if file:
        try:
            file_bytes = await file.read()
            lower_name = file.filename.lower()
            if lower_name.endswith(".zip"):
                is_zip = True
                extracted_files = extract_zip_files(file_bytes)
                attachment_tag = f"\n\n[Attached ZIP Archive: {file.filename} containing {len(extracted_files)} files]"
            elif file.content_type and file.content_type.startswith("image/"):
                # Multimodal analysis for image
                extracted_content = analyze_image(file_bytes, file.content_type)
                attachment_tag = f"\n\n[Attached Image: {file.filename}]"
                extracted_files = [{"path": file.filename, "content": extracted_content}]
            else:
                # Text/Doc extraction
                extracted_content = extract_text(file_bytes, file.filename)
                attachment_tag = f"\n\n[Attached Document: {file.filename}]"
                extracted_files = [{"path": file.filename, "content": extracted_content}]
        except Exception as e:
            logger.error(f"Attachment processing failed: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to process attached file: {str(e)}"
            )

    # Combine text + attachment tag for storage & display
    full_user_content = message + attachment_tag
    
    # 1. Save user's message
    user_msg = ChatMessage(
        user_id=user_id,
        session_id=resolved_session_id,
        role="user",
        content=full_user_content,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 2. Check for intent (push OR tailor)
    is_push = False
    is_tailor = False
    suggested_repo_name = "my-career-project"
    description = ""
    
    try:
        classifier = LLMClient(agent_name="intent_classifier")
        system_prompt = (
            "You are an intent classification assistant. Analyze the user's chat message and "
            "determine the user's intent. Return a JSON object with: \n"
            "{\n"
            "  \"is_push_intent\": true/false (user wants to push/upload code to GitHub),\n"
            "  \"is_tailor_intent\": true/false (user wants to tailor/edit/optimize their resume for a job description),\n"
            "  \"suggested_repo_name\": \"a clean, url-friendly git repository name or null\",\n"
            "  \"description\": \"a short project description or null\"\n"
            "}\n"
            "Examples of tailor intent: 'tailor my resume to this JD', 'edit my resume for this job', "
            "'optimize my resume according to this job description', 'make my resume match this role'."
        )
        res_text = classifier.generate(system_prompt=system_prompt, user_prompt=message, json_mode=True)
        res_data = json.loads(res_text)
        is_push = res_data.get("is_push_intent", False)
        is_tailor = res_data.get("is_tailor_intent", False)
        suggested_repo_name = res_data.get("suggested_repo_name") or "my-career-project"
        description = res_data.get("description") or "Pushed via CareerOS"
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}")

    # Programmatic fallbacks for high reliability
    lower_message = message.lower()
    if any(k in lower_message for k in ["tailor", "optimize", "edit", "rewrite", "adapt", "match"]) and \
       any(k in lower_message for k in ["resume", "cv", "job description", "jd", "role"]):
        is_tailor = True

    if any(k in lower_message for k in ["push to", "upload to", "publish to"]) and \
       any(k in lower_message for k in ["github", "git"]):
        is_push = True

    if is_push:
        # Check if connected to GitHub
        github_conn = db.query(GitHubConnection).filter(GitHubConnection.user_id == user_id).first()
        if not github_conn:
            ans = "I detected that you want to push this to GitHub, but your account is not connected yet. Please head to the GitHub settings page in the sidebar to link your account, then come back here!"
            assistant_msg = ChatMessage(
                user_id=user_id,
                session_id=resolved_session_id,
                role="assistant",
                content=ans,
            )
            db.add(assistant_msg)
            db.commit()
            db.refresh(assistant_msg)
            return ChatSendResponse(
                answer=ans,
                sources=[],
                session_id=resolved_session_id,
                user_message_id=str(user_msg.id),
                assistant_message_id=str(assistant_msg.id),
            )
            
        # Check if they attached a file
        if not file:
            ans = "I can help you push a repository to GitHub, but it looks like you haven't attached any files yet. Please use the paperclip button to attach a code file first, and tell me to push it!"
            assistant_msg = ChatMessage(
                user_id=user_id,
                session_id=resolved_session_id,
                role="assistant",
                content=ans,
            )
            db.add(assistant_msg)
            db.commit()
            db.refresh(assistant_msg)
            return ChatSendResponse(
                answer=ans,
                sources=[],
                session_id=resolved_session_id,
                user_message_id=str(user_msg.id),
                assistant_message_id=str(assistant_msg.id),
            )

        # Create the PushEvent row
        push_files = extracted_files
        push_event = PushEvent(
            user_id=user_id,
            repo_name=suggested_repo_name,
            files=push_files,
            status="pending_confirmation",
            triggered_by_message_id=user_msg.id,
        )
        db.add(push_event)
        db.commit()
        db.refresh(push_event)

        ans = "I've prepared a GitHub repository setup for you. Please confirm the details below to complete the push!"
        assistant_msg = ChatMessage(
            user_id=user_id,
            session_id=resolved_session_id,
            role="assistant",
            content=ans,
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)

        return ChatSendResponse(
            answer=ans,
            sources=[],
            session_id=resolved_session_id,
            user_message_id=str(user_msg.id),
            assistant_message_id=str(assistant_msg.id),
            push_event=PushEventDetail(
                id=push_event.id,
                repo_name=push_event.repo_name,
                description=description,
                files=push_files,
            )
        )

    # Tailoring must use the master source and explicit skill confirmation.
    if is_tailor:
        ans = ('Open [Tailor](http://127.0.0.1:3000/tailor) to select up to five missing JD skills, '
               'confirm the ones you know, and generate a PDF from your master LaTeX. '
               'Chat does not rewrite your resume.')
        assistant_msg = ChatMessage(user_id=user_id, session_id=resolved_session_id,
                                    role="assistant", content=ans)
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        return ChatSendResponse(answer=ans, sources=[], session_id=resolved_session_id,
                                user_message_id=str(user_msg.id), assistant_message_id=str(assistant_msg.id))

    # Build RAG query — if file content is extracted, we inject it directly
    # into the user query text so the RAG agent answers about it
    rag_query = message
    if extracted_content:
        rag_query += f"\n\n[Attached Content from {file.filename}]:\n{extracted_content}"

    # 3. Run the RAG pipeline
    try:
        result = chat_with_career_data(
            db=db,
            user_id=str(user_id),
            question=rag_query,
        )
    except Exception as e:
        logger.error(f"Chat RAG pipeline failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI chat failed: {str(e)}"
        )

    # 4. Save assistant's response
    assistant_msg = ChatMessage(
        user_id=user_id,
        session_id=resolved_session_id,
        role="assistant",
        content=result["answer"],
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return ChatSendResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        session_id=resolved_session_id,
        user_message_id=str(user_msg.id),
        assistant_message_id=str(assistant_msg.id),
    )


@router.get("/history", response_model=List[ChatMessageResponse])
def get_chat_history(
    session_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Retrieve chat history. If session_id is provided, return only that
    session's messages. Otherwise, return all messages for the user.
    """
    user_id = current_user.id


    query = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)

    if session_id:
        query = query.filter(ChatMessage.session_id == session_id)

    messages = query.order_by(ChatMessage.created_at.asc()).all()
    return messages


@router.post("/sessions", response_model=NewSessionResponse)
def create_session():
    """Generate a new session ID for a fresh conversation."""
    return NewSessionResponse(session_id=str(uuid.uuid4()))
