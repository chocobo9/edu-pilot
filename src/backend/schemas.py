from pydantic import BaseModel
from typing import Optional, List


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: Optional[str] = "user"
    admin_code: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class CurrentUserResponse(BaseModel):
    username: str
    role: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class MessageInfo(BaseModel):
    type: str
    content: str
    timestamp: str


class SessionMessagesResponse(BaseModel):
    messages: List[MessageInfo]


class SessionInfo(BaseModel):
    session_id: str
    updated_at: str
    message_count: int


class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]


class SessionDeleteResponse(BaseModel):
    session_id: str
    message: str
