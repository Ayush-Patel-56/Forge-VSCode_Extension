# backend/schemas.py
from pydantic import BaseModel
from typing import Optional


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model_id: Optional[str] = None
    context_chunks: Optional[list[str]] = None
    conversation_id: Optional[str] = None


class CompleteRequest(BaseModel):
    prefix: str
    suffix: str
    language: str
    filepath: Optional[str] = None


class IndexRequest(BaseModel):
    workspace_path: str


class MCPInstallRequest(BaseModel):
    mcp_id: str
    config: dict[str, str] = {}


class ProviderRequest(BaseModel):
    provider_id: str
    api_key: str


class SettingsPatch(BaseModel):
    default_model: Optional[str] = None
    daily_budget_usd: Optional[float] = None
    telemetry_enabled: Optional[bool] = None
