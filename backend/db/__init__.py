# backend/db/__init__.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from pathlib import Path
from .models import Base, Model, Provider, MCPServer

# FORGE_DB_PATH override keeps tests off the user's real database
DB_PATH = Path(os.environ.get('FORGE_DB_PATH') or (Path.home() / '.forge' / 'forge.db'))
DB_PATH.parent.mkdir(exist_ok=True)
engine = create_engine(f'sqlite:///{DB_PATH}', connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)
    _seed_defaults()


def _seed_defaults():
    """Seed model catalog and provider defaults on first run."""
    with get_session() as db:
        if db.query(Model).count() > 0:
            return  # already seeded

        providers = [
            Provider(id='groq', display_name='Groq', base_url='https://api.groq.com/openai/v1', is_free=True, rpm_limit=30, rpd_limit=1000),
            Provider(id='gemini', display_name='Google Gemini', base_url='https://generativelanguage.googleapis.com/v1beta/openai', is_free=True),
            Provider(id='cerebras', display_name='Cerebras', base_url='https://api.cerebras.ai/v1', is_free=True),
            Provider(id='openrouter', display_name='OpenRouter', base_url='https://openrouter.ai/api/v1', is_free=True),
            Provider(id='nvidia', display_name='NVIDIA NIM', base_url='https://integrate.api.nvidia.com/v1'),
            Provider(id='anthropic', display_name='Anthropic', base_url='https://api.anthropic.com/v1'),
            Provider(id='ollama', display_name='Local Ollama', base_url='http://localhost:11434/v1', is_free=True),
        ]
        db.add_all(providers)

        models = [
            Model(id='groq/llama-3.3-70b-versatile', provider_id='groq', model_id='llama-3.3-70b-versatile', display_name='Llama 3.3 70B (Groq)', is_free=True, context_window=32768, recommended_for='["quick","coding"]'),
            Model(id='groq/llama-3.1-8b-instant', provider_id='groq', model_id='llama-3.1-8b-instant', display_name='Llama 3.1 8B Instant (Groq)', is_free=True, supports_fim=True, recommended_for='["fim"]'),
            Model(id='gemini/gemini-2.5-flash', provider_id='gemini', model_id='gemini-2.5-flash', display_name='Gemini 2.5 Flash', is_free=True, context_window=1000000, supports_vision=True, recommended_for='["long","vision"]'),
            Model(id='cerebras/llama-3.3-70b', provider_id='cerebras', model_id='llama3.3-70b', display_name='Llama 3.3 70B (Cerebras)', is_free=True, recommended_for='["quick"]'),
            Model(id='openrouter/qwen3-32b:free', provider_id='openrouter', model_id='qwen/qwen3-32b:free', display_name='Qwen3 32B (Free)', is_free=True, recommended_for='["coding","long"]'),
        ]
        db.add_all(models)
        db.commit()


@contextmanager
def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
