# backend/db/models.py
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Provider(Base):
    __tablename__ = 'providers'
    id = Column(String, primary_key=True)        # 'groq', 'gemini', 'openrouter'
    display_name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_free = Column(Boolean, default=False)
    rpm_limit = Column(Integer, nullable=True)   # requests per minute
    tpm_limit = Column(Integer, nullable=True)   # tokens per minute
    rpd_limit = Column(Integer, nullable=True)   # requests per day
    created_at = Column(DateTime, default=datetime.utcnow)


class Model(Base):
    __tablename__ = 'models'
    id = Column(String, primary_key=True)         # 'groq/llama-3.3-70b-versatile'
    provider_id = Column(String, nullable=False)
    model_id = Column(String, nullable=False)     # provider's model string
    display_name = Column(String, nullable=False)
    context_window = Column(Integer, default=8192)
    supports_vision = Column(Boolean, default=False)
    supports_tools = Column(Boolean, default=False)
    supports_fim = Column(Boolean, default=False) # fill-in-middle for completions
    is_free = Column(Boolean, default=False)
    cost_per_1k_input = Column(Float, default=0.0)
    cost_per_1k_output = Column(Float, default=0.0)
    recommended_for = Column(Text, default='[]')  # JSON array: ["coding","quick"]


class MCPServer(Base):
    __tablename__ = 'mcp_servers'
    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    description = Column(Text)
    category = Column(String)                      # 'filesystem','git','web','memory'
    install_command = Column(String)               # 'npx @mcp/server-filesystem'
    config_template = Column(Text)                 # JSON template
    required_env_keys = Column(Text, default='[]') # JSON array
    is_installed = Column(Boolean, default=False)
    is_running = Column(Boolean, default=False)
    installed_at = Column(DateTime, nullable=True)


class UsageLog(Base):
    __tablename__ = 'usage_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(String)
    model_id = Column(String)
    tokens_in = Column(Integer, default=0)
    tokens_out = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    task_type = Column(String)                     # 'chat', 'complete', 'explain'
    conversation_id = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Settings(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(Text)
    # Stored keys: default_model, daily_budget_usd, telemetry_enabled, student_mode
