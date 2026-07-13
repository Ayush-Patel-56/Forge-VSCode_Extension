# backend/tests/test_agent_engine.py
"""
Proves the agent-engine upgrade end to end, no network / no main.py import:

  1. backend/tools/terminal.py::run_command -- echoes, propagates a failing
     exit code, and enforces its timeout by killing the process.
  2. ModelRouter typed SSE events -- status/tool_call/tool_result/content,
     effort -> max_tokens mapping, and the thinking/reasoning_effort retry
     path (fake client rejects it once, router retries without it).
  3. Approval flow -- backend/tools/approvals.py wired the way main.py wires
     it: the terminal tool executor pushes an approval_request event onto the
     router's event_queue *before* blocking, resolve_approval() (the same
     function /api/chat/approval calls) wakes it, and 'allow' / 'other'
     decisions produce the expected tool result.

Run with:  python backend/tests/test_agent_engine.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

# Isolate this test from the user's real ~/.forge/forge.db BEFORE importing db
# (ModelRouter() reads Settings/UsageLog at construction time).
os.environ['FORGE_DB_PATH'] = str(Path(tempfile.mkdtemp(prefix='forge-test-db-')) / 'forge.db')

# backend/ must be on sys.path so `from router.model_router import ModelRouter`
# etc. resolve the same way they do inside the backend package itself.
# Do NOT import main.py.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
except Exception:
    pass

from tools.terminal import run_command  # noqa: E402
from tools import approvals as approvals_mod  # noqa: E402
from tools.approvals import (  # noqa: E402
    request_approval, resolve_approval, run_terminal_with_approval,
)
from router.model_router import ModelRouter  # noqa: E402


# ---------------------------------------------------------------------------
# Part 1: run_command
# ---------------------------------------------------------------------------

async def run_terminal_tests() -> bool:
    ok = True

    with tempfile.TemporaryDirectory(prefix='forge-terminal-test-') as tmp:
        result = await run_command('echo hello', tmp)
        if result.get('exit_code') != 0 or 'hello' not in (result.get('output') or ''):
            print(f"FAIL: run_command('echo hello', ...) expected exit_code 0 with 'hello' in output, got {result}")
            ok = False
        else:
            print(f"PASS: run_command('echo hello', ...) -> {result}")

        fail_result = await run_command('exit 3', tmp)
        if fail_result.get('exit_code') != 3:
            print(f"FAIL: run_command('exit 3', ...) expected exit_code 3, got {fail_result}")
            ok = False
        else:
            print(f"PASS: run_command('exit 3', ...) -> exit_code 3")

        timeout_cmd = f'{sys.executable} -c "import time; time.sleep(5)"'
        timeout_result = await run_command(timeout_cmd, tmp, timeout_s=1)
        if timeout_result.get('exit_code') == 0 or 'timed out' not in (timeout_result.get('output') or '').lower():
            print(f"FAIL: run_command(sleep 5, timeout_s=1) expected a timeout report, got {timeout_result}")
            ok = False
        else:
            print(f"PASS: run_command(sleep 5, timeout_s=1) reported timeout: {timeout_result}")

    return ok


# ---------------------------------------------------------------------------
# Part 2: router typed events, effort -> max_tokens, thinking retry path
# ---------------------------------------------------------------------------

def _make_tool_call(call_id: str, name: str, arguments_json: str) -> SimpleNamespace:
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments_json))


def _make_response(content, tool_calls=None, usage=None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
        usage=usage,
    )


def _tc_delta(index: int, id=None, name=None, arguments=None) -> SimpleNamespace:
    """One streamed tool_calls delta fragment (providers split name /
    arguments across multiple chunks, keyed by index)."""
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


def _chunk(content=None, tool_calls=None) -> SimpleNamespace:
    """One streamed chat-completion chunk, shaped like the real OpenAI SDK."""
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))])


class _FakeChunkStream:
    """Async-iterable of pre-built chunk namespaces (mirrors a real
    streaming chat-completion response)."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


async def run_router_typed_events_test() -> bool:
    ok = True
    router = ModelRouter()
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]

    fake_tool = {
        'type': 'function',
        'function': {
            'name': 'fakeserver__faketool',
            'description': 'a fake tool for testing',
            'parameters': {'type': 'object', 'properties': {'x': {'type': 'number'}}},
        },
    }

    async def fake_executor(raw_name: str, arguments: dict):
        return {'text': 'tool result text'}

    def fake_tools_provider():
        return [fake_tool], fake_executor

    call_count = {'n': 0}
    seen_max_tokens = []

    async def fake_create(**kwargs):
        call_count['n'] += 1
        seen_max_tokens.append(kwargs.get('max_tokens'))
        if call_count['n'] == 1:
            if 'tools' not in kwargs or not kwargs['tools']:
                raise AssertionError('expected tools to be passed on the first tool-loop call')
            # Real providers split a tool call's name and arguments across
            # multiple streamed chunks -- name in one, arguments fragmented
            # across two more, all keyed by the same index.
            return _FakeChunkStream([
                _chunk(tool_calls=[_tc_delta(0, id='call_1', name='fakeserver__faketool')]),
                _chunk(tool_calls=[_tc_delta(0, arguments='{"x":')]),
                _chunk(tool_calls=[_tc_delta(0, arguments='1}')]),
            ])
        # Final round: plain content, streamed as multiple chunks.
        return _FakeChunkStream([
            _chunk(content='final answer '),
            _chunk(content='from the model'),
        ])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    router._get_client = lambda provider: fake_client  # type: ignore[method-assign]

    events = []
    async for raw in router.stream(
        messages=[{'role': 'user', 'content': 'please use the fake tool'}],
        model_id=None,
        context_chunks=[],
        tools_provider=fake_tools_provider,
        thinking=False,
        effort='high',
    ):
        events.append(json.loads(raw))

    status_events = [e for e in events if e.get('event') == 'status']
    if not status_events:
        print(f"FAIL: expected at least one status event, got {events!r}")
        ok = False
    else:
        print(f"PASS: router yielded status event(s): {status_events!r}")

    tool_call_events = [e for e in events if e.get('event') == 'tool_call']
    if not tool_call_events or tool_call_events[0].get('name') != 'fakeserver.faketool' or tool_call_events[0].get('args') != {'x': 1}:
        print(f"FAIL: expected a tool_call event for 'fakeserver.faketool' with args {{'x': 1}}, got {tool_call_events!r}")
        ok = False
    else:
        print(f"PASS: router yielded a tool_call event: {tool_call_events[0]!r}")

    tool_result_events = [e for e in events if e.get('event') == 'tool_result']
    if not tool_result_events or tool_result_events[0].get('ok') is not True or 'tool result text' not in tool_result_events[0].get('text', ''):
        print(f"FAIL: expected a tool_result event with ok=True and text containing 'tool result text', got {tool_result_events!r}")
        ok = False
    else:
        print(f"PASS: router yielded a tool_result event: {tool_result_events[0]!r}")

    final_content_chunks = [e['content'] for e in events if 'content' in e]
    joined_final = ''.join(final_content_chunks)
    if 'final answer from the model' not in joined_final:
        print(f"FAIL: expected final content 'final answer from the model', got {final_content_chunks!r}")
        ok = False
    else:
        print("PASS: router yielded the model's final content after the tool call")

    if len(final_content_chunks) < 2:
        print(f"FAIL: expected the final round's content to stream as multiple chunks (not one blob), got {final_content_chunks!r}")
        ok = False
    else:
        print(f"PASS: final round content streamed as multiple chunks: {final_content_chunks!r}")

    if any(mt != 8192 for mt in seen_max_tokens):
        print(f"FAIL: expected effort='high' to map every create() call to max_tokens=8192, got {seen_max_tokens!r}")
        ok = False
    else:
        print(f"PASS: effort='high' mapped to max_tokens=8192 on every create() call: {seen_max_tokens!r}")

    return ok


async def run_thinking_retry_test() -> bool:
    ok = True
    router = ModelRouter()
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]

    call_kwargs_log = []
    reject_next = {'n': 1}

    async def fake_create(**kwargs):
        call_kwargs_log.append(kwargs)
        if 'reasoning_effort' in kwargs and reject_next['n'] > 0:
            reject_next['n'] -= 1
            raise Exception("400 Bad Request: unsupported parameter 'reasoning_effort'")
        # Streamed plain response (no tools) -- return an async-iterable of chunks
        return _FakeStream(['ok'])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    router._get_client = lambda provider: fake_client  # type: ignore[method-assign]

    events = []
    async for raw in router.stream(
        messages=[{'role': 'user', 'content': 'hi'}],
        model_id=None,
        context_chunks=[],
        thinking=True,
        effort='medium',
    ):
        events.append(json.loads(raw))

    if len(call_kwargs_log) != 2:
        print(f"FAIL: expected exactly 2 create() calls (reasoning_effort rejected, then retried without), got {len(call_kwargs_log)}: {call_kwargs_log!r}")
        ok = False
    else:
        first, second = call_kwargs_log
        if 'reasoning_effort' not in first:
            print(f"FAIL: expected thinking=True to add reasoning_effort on the first call, got {first!r}")
            ok = False
        elif first['reasoning_effort'] != 'medium':
            print(f"FAIL: expected effort='medium' -> reasoning_effort='medium', got {first['reasoning_effort']!r}")
            ok = False
        elif 'reasoning_effort' in second:
            print(f"FAIL: expected the retry call to omit reasoning_effort, got {second!r}")
            ok = False
        elif second.get('max_tokens') != 4096:
            print(f"FAIL: expected effort='medium' -> max_tokens=4096 on the retry call, got {second!r}")
            ok = False
        else:
            print(f"PASS: thinking=True added reasoning_effort='medium', provider rejection triggered a clean retry without it: {call_kwargs_log!r}")

    content = ''.join(e['content'] for e in events if 'content' in e)
    if content != 'ok':
        print(f"FAIL: expected streamed content 'ok' after the retry succeeded, got {content!r}")
        ok = False
    else:
        print("PASS: streaming succeeded after the reasoning_effort retry")

    return ok


class _FakeStream:
    """Minimal async iterator shaped like an OpenAI streaming response."""

    def __init__(self, contents):
        self._contents = list(contents)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._contents:
            raise StopAsyncIteration
        content = self._contents.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


async def run_tool_loop_failure_fallback_test() -> bool:
    """Reproduces the live bug: round 1 executes a tool, round 2 blows up
    (e.g. provider rate-limited mid-turn). The tool loop must NOT leak
    role:'tool' messages into the plain-streaming fallback (providers 400 on
    those without accompanying tool-call context, which is what turned every
    fallback into a failure and produced the "all providers exhausted"
    error) -- and it must not silently drop the tool's already-executed
    result either. Instead the fallback should get a compact system-message
    summary of what already ran, and still produce a real answer."""
    ok = True
    router = ModelRouter()
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]

    fake_tool = {
        'type': 'function',
        'function': {
            'name': 'fakeserver__faketool',
            'description': 'a fake tool for testing',
            'parameters': {'type': 'object', 'properties': {'x': {'type': 'number'}}},
        },
    }

    async def fake_executor(raw_name: str, arguments: dict):
        return {'text': 'tool result text from the executed call'}

    def fake_tools_provider():
        return [fake_tool], fake_executor

    call_log = []

    async def fake_create(**kwargs):
        call_log.append(kwargs)
        n = len(call_log)
        if n == 1:
            # Round 1: model calls the fake tool (streamed, split across chunks).
            return _FakeChunkStream([
                _chunk(tool_calls=[_tc_delta(0, id='call_1', name='fakeserver__faketool')]),
                _chunk(tool_calls=[_tc_delta(0, arguments='{"x":')]),
                _chunk(tool_calls=[_tc_delta(0, arguments='1}')]),
            ])
        if n == 2:
            # Round 2: provider blows up after a tool already executed.
            raise Exception('429 rate limit exceeded')
        # Call 3: the plain-streaming fallback for this same candidate.
        return _FakeStream(['final ', 'answer ', 'from fallback'])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    router._get_client = lambda provider: fake_client  # type: ignore[method-assign]

    events = []
    async for raw in router.stream(
        messages=[{'role': 'user', 'content': 'please use the fake tool'}],
        model_id=None,
        context_chunks=[],
        tools_provider=fake_tools_provider,
    ):
        events.append(json.loads(raw))

    final_content = ''.join(e['content'] for e in events if 'content' in e)
    if 'exhausted' in final_content.lower() or 'final answer from fallback' not in final_content:
        print(f"FAIL: expected the fallback's final content, not the exhausted-providers error, got {final_content!r}")
        ok = False
    else:
        print(f"PASS: stream produced the fallback's final content instead of the exhausted-providers error: {final_content!r}")

    if len(call_log) != 3:
        print(f"FAIL: expected exactly 3 create() calls (tool round, failing round, fallback), got {len(call_log)}: {call_log!r}")
        ok = False
    else:
        fallback_messages = call_log[2].get('messages', [])
        tool_msgs = [m for m in fallback_messages if m.get('role') == 'tool']
        if tool_msgs:
            print(f"FAIL: fallback messages must never contain role:'tool' entries, got {tool_msgs!r}")
            ok = False
        else:
            print("PASS: fallback messages contain no role:'tool' entries")

        summary_msgs = [
            m for m in fallback_messages
            if m.get('role') == 'system' and 'already executed' in (m.get('content') or '')
        ]
        if not summary_msgs or 'tool result text from the executed call' not in summary_msgs[0]['content']:
            print(f"FAIL: expected a system message summarizing the executed tool's result, got {fallback_messages!r}")
            ok = False
        else:
            print(f"PASS: fallback messages carry a system-message summary of the executed tool: {summary_msgs[0]!r}")

        original_messages = [{'role': 'user', 'content': 'please use the fake tool'}]
        if fallback_messages[:len(original_messages)] != original_messages:
            print(f"FAIL: expected the fallback to still start with the original pristine messages, got {fallback_messages!r}")
            ok = False
        else:
            print("PASS: fallback messages still start with the original pristine conversation")

    return ok


# ---------------------------------------------------------------------------
# Part 3: approval flow, wired the way main.py wires it
# ---------------------------------------------------------------------------

async def run_approval_flow_test() -> bool:
    ok = True

    # --- 3a: request_approval() pushes an approval_request event onto the
    # queue BEFORE blocking, and resolve_approval() (what /api/chat/approval
    # calls) wakes it with the decision. -------------------------------
    event_queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.ensure_future(request_approval(event_queue, 'git status', '/tmp/ws', timeout_s=5))

    # Drain the event the same way ModelRouter._drain_queue_while does:
    # the event must be visible on the queue while the task is still pending.
    ev = await asyncio.wait_for(event_queue.get(), timeout=2)
    if ev.get('event') != 'approval_request' or ev.get('command') != 'git status':
        print(f"FAIL: expected an approval_request event for 'git status', got {ev!r}")
        ok = False
    else:
        print(f"PASS: request_approval() surfaced an approval_request event before blocking: {ev!r}")

    if task.done():
        print("FAIL: expected request_approval() task to still be pending (awaiting a decision)")
        ok = False
    else:
        print("PASS: request_approval() is still pending, awaiting a decision")

    resolved = resolve_approval(ev['id'], 'allow')
    if not resolved:
        print(f"FAIL: resolve_approval({ev['id']!r}, 'allow') returned False")
        ok = False
    decision, detail = await asyncio.wait_for(task, timeout=2)
    if decision != 'allow':
        print(f"FAIL: expected decision 'allow', got {decision!r}")
        ok = False
    else:
        print("PASS: resolve_approval('allow') woke request_approval() with decision 'allow'")

    # Resolving an already-resolved / unknown id returns False.
    if resolve_approval('nonexistent_id', 'allow'):
        print("FAIL: resolve_approval() on an unknown approval_id should return False")
        ok = False
    else:
        print("PASS: resolve_approval() on an unknown approval_id returns False")

    # --- 3b: run_terminal_with_approval end to end -- 'allow' actually runs
    # the command. --------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix='forge-approval-test-') as tmp:
        event_queue2: asyncio.Queue = asyncio.Queue()
        exec_task = asyncio.ensure_future(
            run_terminal_with_approval(event_queue2, tmp, {'command': 'echo approved'})
        )
        ev2 = await asyncio.wait_for(event_queue2.get(), timeout=2)
        resolve_approval(ev2['id'], 'allow')
        result = await asyncio.wait_for(exec_task, timeout=5)
        text = result.get('text', '') if isinstance(result, dict) else str(result)
        if 'approved' not in text or 'exit_code=0' not in text:
            print(f"FAIL: expected the allowed command's output in the tool result, got {result!r}")
            ok = False
        else:
            print(f"PASS: 'allow' decision ran the command and returned its output: {result!r}")

        # --- 3c: 'other' + detail surfaces the detail in the tool result. --
        event_queue3: asyncio.Queue = asyncio.Queue()
        exec_task2 = asyncio.ensure_future(
            run_terminal_with_approval(event_queue3, tmp, {'command': 'rm -rf /'})
        )
        ev3 = await asyncio.wait_for(event_queue3.get(), timeout=2)
        resolve_approval(ev3['id'], 'other', "use git status instead")
        result2 = await asyncio.wait_for(exec_task2, timeout=5)
        text2 = result2.get('text', '') if isinstance(result2, dict) else str(result2)
        if 'use git status instead' not in text2:
            print(f"FAIL: expected the 'other' detail in the tool result, got {result2!r}")
            ok = False
        else:
            print(f"PASS: 'other' decision surfaced the user's detail in the tool result: {result2!r}")

        # --- 3d: 'deny' produces the declined-message tool result. ---------
        event_queue4: asyncio.Queue = asyncio.Queue()
        exec_task3 = asyncio.ensure_future(
            run_terminal_with_approval(event_queue4, tmp, {'command': 'echo should-not-run'})
        )
        ev4 = await asyncio.wait_for(event_queue4.get(), timeout=2)
        resolve_approval(ev4['id'], 'deny')
        result3 = await asyncio.wait_for(exec_task3, timeout=5)
        text3 = result3.get('text', '') if isinstance(result3, dict) else str(result3)
        if 'declined' not in text3.lower():
            print(f"FAIL: expected a declined-command message, got {result3!r}")
            ok = False
        else:
            print(f"PASS: 'deny' decision produced the declined-command message: {result3!r}")

    # --- 3e: build the router-driven executor/queue wiring the way main.py
    # does (tools_provider returns a 3-tuple with an event_queue) and confirm
    # the approval_request event surfaces through router.stream() itself,
    # not just through the raw helper functions. --------------------------
    router = ModelRouter()
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]

    with tempfile.TemporaryDirectory(prefix='forge-approval-router-test-') as tmp:
        terminal_tool = {
            'type': 'function',
            'function': {
                'name': 'terminal__run_command',
                'description': 'run a shell command',
                'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}}},
            },
        }

        def tools_provider():
            q: asyncio.Queue = asyncio.Queue()

            async def executor(raw_name, arguments):
                if raw_name == 'terminal__run_command':
                    return await run_terminal_with_approval(q, tmp, arguments)
                return {'error': 'unknown tool'}

            return [terminal_tool], executor, q

        call_count = {'n': 0}

        async def fake_create(**kwargs):
            call_count['n'] += 1
            if call_count['n'] == 1:
                return _FakeChunkStream([
                    _chunk(tool_calls=[_tc_delta(0, id='call_1', name='terminal__run_command')]),
                    _chunk(tool_calls=[_tc_delta(0, arguments='{"command": "echo ')]),
                    _chunk(tool_calls=[_tc_delta(0, arguments='hi-from-router"}')]),
                ])
            return _FakeChunkStream([_chunk(content='done')])

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
        router._get_client = lambda provider: fake_client  # type: ignore[method-assign]

        # Approval is resolved from within the consuming loop itself, below,
        # the moment the approval_request event is observed -- this is what
        # proves the event reached the "client" while router.stream() is
        # still suspended mid-iteration (task in flight), not after.
        events = []
        async for raw in router.stream(
            messages=[{'role': 'user', 'content': 'run something'}],
            model_id=None,
            context_chunks=[],
            tools_provider=tools_provider,
        ):
            payload = json.loads(raw)
            events.append(payload)
            if payload.get('event') == 'approval_request':
                # This is the crux of the deadlock-safety requirement: the
                # event must already be visible to the (simulated) client
                # here, *while* router.stream() is suspended mid-iteration
                # awaiting the next queue item / task completion -- not
                # after the whole tool call has finished.
                resolve_approval(payload['id'], 'allow')

        approval_events = [e for e in events if e.get('event') == 'approval_request']
        if not approval_events:
            print(f"FAIL: expected router.stream() to surface an approval_request event, got {events!r}")
            ok = False
        else:
            print(f"PASS: router.stream() surfaced approval_request mid-stream: {approval_events[0]!r}")

        tool_results = [e for e in events if e.get('event') == 'tool_result']
        if not tool_results or 'hi-from-router' not in tool_results[0].get('text', ''):
            print(f"FAIL: expected a tool_result containing the command's output, got {tool_results!r}")
            ok = False
        else:
            print(f"PASS: router.stream() completed the approved command and yielded its tool_result: {tool_results[0]!r}")

        final_content = [e['content'] for e in events if 'content' in e]
        if 'done' not in final_content:
            print(f"FAIL: expected final content 'done' after the approved tool call, got {final_content!r}")
            ok = False
        else:
            print("PASS: router.stream() yielded the model's final content after the approved tool call")

    return ok


# ---------------------------------------------------------------------------
# Part 4: vision candidate filtering (has_images routing)
# ---------------------------------------------------------------------------

async def run_vision_routing_test() -> bool:
    """has_images=True must restrict candidates to vision-capable models
    (querying db Models.supports_vision, cached on router._vision_models
    exactly like _get_model_costs caches cost data -- tests set the cache
    directly to avoid touching the db). A non-vision selected model_id must
    be skipped in favor of a vision-capable candidate; if none exist at all,
    stream() must yield a clear content error instead of trying (and 400ing
    on) a non-vision model."""
    ok = True

    # --- 4a: non-vision selected model -> only vision candidates are tried
    router = ModelRouter()
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]
    router._vision_models_loaded = True  # type: ignore[attr-defined]
    router._vision_models = {'gemini/gemini-2.5-flash'}  # type: ignore[attr-defined]

    models_tried = []

    async def fake_create(**kwargs):
        models_tried.append(kwargs.get('model'))
        return _FakeStream(['ok'])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    router._get_client = lambda provider: fake_client  # type: ignore[method-assign]

    events = []
    async for raw in router.stream(
        messages=[{'role': 'user', 'content': 'what is in this image?'}],
        model_id='groq/llama-3.3-70b-versatile',  # explicitly selected, but NOT vision-capable
        context_chunks=[],
        has_images=True,
    ):
        events.append(json.loads(raw))

    if models_tried != ['gemini-2.5-flash']:
        print(f"FAIL: expected only the vision-capable model to be tried, got {models_tried!r}")
        ok = False
    else:
        print(f"PASS: has_images=True skipped the non-vision selected model and tried only vision candidates: {models_tried!r}")

    content = ''.join(e['content'] for e in events if 'content' in e)
    if content != 'ok':
        print(f"FAIL: expected the vision-capable candidate to stream 'ok', got {content!r}")
        ok = False
    else:
        print("PASS: vision-capable candidate streamed the response")

    # --- 4b: no vision-capable model at all -> clear content error --------
    router2 = ModelRouter()
    router2._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]
    router2._vision_models_loaded = True  # type: ignore[attr-defined]
    router2._vision_models = set()  # type: ignore[attr-defined]

    async def fake_create_should_not_run(**kwargs):
        raise AssertionError('create() should never be called when no vision model is available')

    fake_client2 = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create_should_not_run)))
    router2._get_client = lambda provider: fake_client2  # type: ignore[method-assign]

    events2 = []
    async for raw in router2.stream(
        messages=[{'role': 'user', 'content': 'what is in this image?'}],
        model_id=None,
        context_chunks=[],
        has_images=True,
    ):
        events2.append(json.loads(raw))

    content2 = ''.join(e['content'] for e in events2 if 'content' in e)
    if 'vision' not in content2.lower():
        print(f"FAIL: expected a clear vision-capability error, got {content2!r}")
        ok = False
    else:
        print(f"PASS: no vision-capable model available produced a clear error: {content2!r}")

    return ok


def main() -> int:
    ok_terminal = asyncio.run(run_terminal_tests())
    ok_router_events = asyncio.run(run_router_typed_events_test())
    ok_thinking_retry = asyncio.run(run_thinking_retry_test())
    ok_tool_loop_fallback = asyncio.run(run_tool_loop_failure_fallback_test())
    ok_approval = asyncio.run(run_approval_flow_test())
    ok_vision_routing = asyncio.run(run_vision_routing_test())

    ok = (
        ok_terminal and ok_router_events and ok_thinking_retry and ok_tool_loop_fallback
        and ok_approval and ok_vision_routing
    )
    if ok:
        print("PASS: all agent-engine assertions succeeded")
        return 0
    print("FAIL: one or more agent-engine assertions failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
