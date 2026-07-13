# backend/main.py
import argparse, asyncio, os, re
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
    ApprovalRequest, ChatRequest, CompleteRequest, IndexRequest,
    MCPInstallRequest, MCPStartRequest, ProviderRequest, SettingsPatch
)
from tools.approvals import resolve_approval, run_terminal_with_approval

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


def _sanitize_tool_name(name: str) -> str:
    """OpenAI function names must match [a-zA-Z0-9_-]{1,64}."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:64]


def _mcp_tools_to_openai(tools: list) -> list:
    openai_tools = []
    for t in tools:
        fn_name = _sanitize_tool_name(f"{t['server']}__{t['name']}")
        openai_tools.append({
            'type': 'function',
            'function': {
                'name': fn_name,
                'description': t.get('description') or '',
                'parameters': t.get('input_schema') or {'type': 'object', 'properties': {}},
            },
        })
    return openai_tools


def _mcp_tools_provider():
    """Snapshot of currently-available MCP tools + an executor that routes a
    sanitized `server__tool` function name back to mcp_manager.call_tool.
    Returns None when no MCP servers are running -- stream() then behaves
    exactly as it did before tool support existed.
    """
    tools = mcp_manager.get_all_tools()
    if not tools:
        return None

    openai_tools = _mcp_tools_to_openai(tools)

    # Exact sanitized-name map, plus a bare-name map because models sometimes
    # drop the "server__" prefix when emitting tool calls
    exact: dict = {}
    by_bare_name: dict = {}
    for t in tools:
        exact[_sanitize_tool_name(f"{t['server']}__{t['name']}")] = (t['server'], t['name'])
        by_bare_name.setdefault(t['name'], []).append((t['server'], t['name']))

    async def executor(raw_name: str, arguments: dict):
        target = exact.get(raw_name)
        if target is None:
            bare = raw_name.partition('__')[2] or raw_name
            candidates = by_bare_name.get(bare, [])
            if len(candidates) == 1:
                target = candidates[0]
        if target is None:
            server, _, tool_name = raw_name.partition('__')
            target = (server, tool_name)
        return await mcp_manager.call_tool(target[0], target[1], arguments)

    return openai_tools, executor


TERMINAL_TOOL = {
    'type': 'function',
    'function': {
        'name': 'terminal__run_command',
        'description': "Run a shell command in the user's workspace (git, build tools, etc.). The user must approve each command.",
        'parameters': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': 'The shell command to run.'},
                'cwd': {'type': 'string', 'description': "Working directory (defaults to the user's workspace)."},
            },
            'required': ['command'],
        },
    },
}


def _build_tools_provider(workspace_path: str):
    """Builds a per-request tools_provider for model_router.stream(). Always
    exposes the built-in approval-gated terminal__run_command tool, alongside
    whatever MCP tools are currently running. Returns a 3-tuple
    (openai_tools, executor, event_queue) -- the event_queue lets the terminal
    tool's approval flow push an approval_request event into the SSE stream
    while stream() is mid-iteration (see ModelRouter._drain_queue_while)."""
    def provider():
        mcp_result = _mcp_tools_provider()
        mcp_tools, mcp_executor = mcp_result if mcp_result else ([], None)

        openai_tools = list(mcp_tools) + [TERMINAL_TOOL]
        event_queue: asyncio.Queue = asyncio.Queue()

        async def executor(raw_name: str, arguments: dict):
            if raw_name == 'terminal__run_command':
                return await run_terminal_with_approval(event_queue, workspace_path, arguments)
            if mcp_executor is not None:
                return await mcp_executor(raw_name, arguments)
            return {'error': f'Unknown tool: {raw_name}'}

        return openai_tools, executor, event_queue

    return provider


@app.post('/api/chat')
async def chat(body: ChatRequest):
    messages = [m.model_dump() for m in body.messages]
    workspace_path = body.workspace_path or os.getcwd()

    # Convert the last user message's content into the OpenAI multimodal
    # array form when images are attached: [{'type':'text',...}, {'type':
    # 'image_url',...}, ...]. Only the LAST user message carries images --
    # that's the one the user just attached them to.
    if body.images:
        for m in reversed(messages):
            if m.get('role') == 'user':
                original_text = m.get('content') or ''
                content_parts: list = [{'type': 'text', 'text': original_text}]
                for img in body.images:
                    content_parts.append({
                        'type': 'image_url',
                        'image_url': {'url': f'data:{img.mime};base64,{img.data_base64}'},
                    })
                m['content'] = content_parts
                break

    async def generate():
        async for chunk in model_router.stream(
            messages, body.model_id, body.context_chunks or [],
            tools_provider=_build_tools_provider(workspace_path),
            thinking=body.thinking or False,
            effort=body.effort or 'medium',
            has_images=bool(body.images),
        ):
            yield f'data: {chunk}\n\n'
        yield 'data: [DONE]\n\n'
    return StreamingResponse(generate(), media_type='text/event-stream')


@app.post('/api/chat/approval')
async def chat_approval(body: ApprovalRequest):
    ok = resolve_approval(body.approval_id, body.decision, body.detail)
    return {'status': 'ok' if ok else 'not_found'}


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
    return await asyncio.to_thread(context_engine.search, q, k)


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


@app.post('/api/mcp/start')
async def start_mcp(body: MCPStartRequest):
    result = await mcp_manager.start(body.mcp_id, body.workspace_path)
    return result


@app.get('/api/mcp/list')
async def list_mcp():
    return mcp_manager.list_all()


@app.get('/api/mcp/tools')
async def list_mcp_tools():
    return mcp_manager.get_all_tools()


@app.delete('/api/mcp/{mcp_id}')
async def uninstall_mcp(mcp_id: str):
    await mcp_manager.uninstall(mcp_id)
    return {'status': 'ok'}


@app.post('/api/mcp/relaunch')
async def relaunch_mcp(body: IndexRequest):
    return await mcp_manager.relaunch_installed(body.workspace_path)


@app.get('/api/usage')
async def usage():
    return model_router.get_usage_stats()


@app.patch('/api/settings')
async def patch_settings(body: SettingsPatch):
    with get_session() as db:
        if body.default_model:
            db.merge(Settings(key='default_model', value=body.default_model))
        if body.daily_budget_usd is not None:
            db.merge(Settings(key='daily_budget_usd', value=str(body.daily_budget_usd)))
        db.commit()
    if body.default_model:
        model_router.set_default_model(body.default_model)
    if body.daily_budget_usd is not None:
        model_router.set_daily_budget(body.daily_budget_usd)
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
