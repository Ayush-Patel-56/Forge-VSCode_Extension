# backend/main.py
import argparse, asyncio, os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from router.model_router import ModelRouter
from context.indexer import ContextEngine
from mcp.manager import MCPManager
from db import init_db, get_session
from db.models import Settings
from schemas import (
    ChatRequest, CompleteRequest, IndexRequest,
    MCPInstallRequest, ProviderRequest, SettingsPatch
)

model_router = ModelRouter()
context_engine = ContextEngine()
mcp_manager = MCPManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await context_engine.start_watcher()
    yield
    await mcp_manager.stop_all()
    await context_engine.stop_watcher()


app = FastAPI(title='Forge Backend', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['vscode-webview://*'], allow_methods=['*'], allow_headers=['*'])


@app.get('/api/health')
async def health():
    return {'status': 'ok', 'model': model_router.get_default_model()}


@app.post('/api/chat')
async def chat(body: ChatRequest):
    async def generate():
        async for chunk in model_router.stream(body.messages, body.model_id, body.context_chunks or []):
            yield f'data: {chunk}\n\n'
        yield 'data: [DONE]\n\n'
    return StreamingResponse(generate(), media_type='text/event-stream')


@app.post('/api/complete')
async def complete(body: CompleteRequest):
    result = await model_router.complete_fim(body.prefix, body.suffix, body.language)
    return {'completion': result}


@app.post('/api/index')
async def index(body: IndexRequest):
    asyncio.create_task(context_engine.index(body.workspace_path))
    return {'status': 'indexing_started'}


@app.get('/api/index/status')
async def index_status():
    return context_engine.get_status()


@app.get('/api/context/chunks')
async def context_chunks(q: str, k: int = 8):
    return context_engine.search(q, k)


@app.post('/api/providers')
async def add_provider(body: ProviderRequest):
    model_router.register_provider(body.provider_id, body.api_key)
    return {'status': 'ok'}


@app.get('/api/models')
async def list_models():
    return model_router.list_models()


@app.post('/api/mcp/install')
async def install_mcp(body: MCPInstallRequest):
    result = await mcp_manager.install(body.mcp_id, body.config)
    return result


@app.get('/api/mcp/list')
async def list_mcp():
    return mcp_manager.list_all()


@app.delete('/api/mcp/{mcp_id}')
async def uninstall_mcp(mcp_id: str):
    await mcp_manager.uninstall(mcp_id)
    return {'status': 'ok'}


@app.get('/api/usage')
async def usage():
    return model_router.get_usage_stats()


@app.patch('/api/settings')
async def patch_settings(body: SettingsPatch):
    with get_session() as db:
        if body.default_model:
            db.merge(Settings(key='default_model', value=body.default_model))
        db.commit()
    if body.default_model:
        model_router.set_default_model(body.default_model)
    return {'status': 'ok'}


@app.post('/api/explain-repo')
async def explain_repo(body: IndexRequest):
    """Generate README + architecture doc for entire workspace."""
    summary = await context_engine.summarize_repo(body.workspace_path)
    return {'summary': summary}


if __name__ == '__main__':
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=7822)
    args = parser.parse_args()
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
