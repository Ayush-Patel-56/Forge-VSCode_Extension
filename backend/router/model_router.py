# backend/router/model_router.py
import asyncio, json, os
from datetime import datetime, timezone
from openai import AsyncOpenAI
from db import get_session
from db.models import UsageLog, Settings

TASK_PROFILES = {
    'quick':   ['groq/llama-3.3-70b-versatile', 'cerebras/llama-3.3-70b', 'gemini/gemini-2.5-flash'],
    'coding':  ['groq/llama-3.3-70b-versatile', 'openrouter/qwen3-32b:free', 'gemini/gemini-2.5-flash'],
    'long':    ['gemini/gemini-2.5-flash', 'openrouter/qwen3-32b:free'],
    'vision':  ['gemini/gemini-2.5-flash'],
    'fim':     ['groq/llama-3.1-8b-instant', 'groq/llama-3.3-70b-versatile'],
}

EFFORT_MAX_TOKENS = {'low': 1024, 'medium': 4096, 'high': 8192, 'max': 16384}

PROVIDER_CONFIGS = {
    'groq':       {'base_url': 'https://api.groq.com/openai/v1',                         'env_key': 'FORGE_GROQ_KEY'},
    'gemini':     {'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai', 'env_key': 'FORGE_GEMINI_KEY'},
    'cerebras':   {'base_url': 'https://api.cerebras.ai/v1',                              'env_key': 'FORGE_CEREBRAS_KEY'},
    'openrouter': {'base_url': 'https://openrouter.ai/api/v1',                            'env_key': 'FORGE_OPENROUTER_KEY'},
    'nvidia':     {'base_url': 'https://integrate.api.nvidia.com/v1',                     'env_key': 'FORGE_NVIDIA_KEY'},
    'anthropic':  {'base_url': 'https://api.anthropic.com/v1',                            'env_key': 'FORGE_ANTHROPIC_KEY'},
    'ollama':     {'base_url': 'http://localhost:11434/v1',                                'env_key': None},
}


class ModelRouter:
    def __init__(self):
        self._clients: dict[str, AsyncOpenAI] = {}
        self._rate_limited: set[str] = set()
        self._default_model = 'groq/llama-3.3-70b-versatile'
        self._daily_budget_usd = 0.0  # 0 = unlimited
        self._today_cost_usd = 0.0
        self._today_tokens = 0
        self._model_costs: dict[str, tuple[float, float]] = {}
        self._model_costs_loaded = False
        self._load_settings()

    def _load_settings(self):
        try:
            with get_session() as db:
                s = db.query(Settings).filter_by(key='default_model').first()
                if s: self._default_model = s.value
                b = db.query(Settings).filter_by(key='daily_budget_usd').first()
                if b: self._daily_budget_usd = float(b.value)

                # Restore today's running totals so a backend restart doesn't zero the day.
                today_midnight = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                rows = db.query(UsageLog).filter(UsageLog.timestamp >= today_midnight).all()
                self._today_tokens = sum((r.tokens_in or 0) + (r.tokens_out or 0) for r in rows)
                self._today_cost_usd = sum((r.cost_usd or 0.0) for r in rows)
        except Exception:
            pass  # DB not initialized yet (first run) - keep defaults; init_db() runs at startup

    def _get_model_costs(self, model_id: str) -> tuple[float, float]:
        """Returns (cost_per_1k_input, cost_per_1k_output) for model_id, cached, default (0,0)."""
        if not self._model_costs_loaded:
            try:
                from db.models import Model
                with get_session() as db:
                    for m in db.query(Model).all():
                        self._model_costs[m.id] = (m.cost_per_1k_input or 0.0, m.cost_per_1k_output or 0.0)
                self._model_costs_loaded = True
            except Exception:
                pass
        return self._model_costs.get(model_id, (0.0, 0.0))

    def _get_client(self, provider: str) -> AsyncOpenAI:
        if provider not in self._clients:
            cfg = PROVIDER_CONFIGS[provider]
            key = os.environ.get(cfg['env_key'] or '', 'ollama') if cfg['env_key'] else 'ollama'
            self._clients[provider] = AsyncOpenAI(api_key=key, base_url=cfg['base_url'])
        return self._clients[provider]

    def _is_free(self, model_id: str) -> bool:
        # Simple heuristic: known free models
        free_prefixes = ['groq/', 'cerebras/', 'openrouter/qwen3-32b:free', 'ollama/']
        return any(model_id.startswith(p) for p in free_prefixes) or 'gemini-2.5-flash' in model_id

    def _should_use_free_only(self) -> bool:
        if self._daily_budget_usd <= 0: return False
        return self._today_cost_usd >= self._daily_budget_usd * 0.9  # 90% threshold

    def _classify_task(self, text: str) -> str:
        text_lower = text.lower()
        if len(text) > 8000: return 'long'
        coding_words = ['fix', 'write', 'implement', 'debug', 'refactor', 'test', 'function', 'class', 'error', 'bug']
        if any(w in text_lower for w in coding_words): return 'coding'
        return 'quick'

    def _get_candidates(self, task_type: str, model_id: str | None) -> list[str]:
        if model_id:
            return [model_id] + [m for m in TASK_PROFILES.get(task_type, []) if m != model_id]
        candidates = TASK_PROFILES.get(task_type, TASK_PROFILES['quick'])
        if self._should_use_free_only():
            candidates = [c for c in candidates if self._is_free(c)]
        return candidates

    def _get_candidates_with_default(self, task_type: str, model_id: str | None) -> list[str]:
        # When the caller doesn't request a specific model, honor the configured
        # default model (forge.set.model / _default_model) as the first candidate,
        # then fall back to the task-profile chain (still respecting the free-only
        # budget logic in _get_candidates for that fallback portion).
        if model_id:
            return self._get_candidates(task_type, model_id)
        fallback = self._get_candidates(task_type, None)
        return [self._default_model] + [m for m in fallback if m != self._default_model]

    async def stream(
        self, messages: list, model_id: str | None, context_chunks: list[str], tools_provider=None,
        thinking: bool = False, effort: str = 'medium',
    ):
        if context_chunks:
            ctx = '\n\n'.join(f'```\n{c}\n```' for c in context_chunks)
            messages = [{'role': 'system', 'content': f'Relevant code from codebase:\n{ctx}'}] + messages

        task_type = self._classify_task(messages[-1].get('content', '') if messages else '')
        candidates = self._get_candidates_with_default(task_type, model_id)

        total_chars = sum(len(m.get('content', '') or '') for m in messages)
        tokens_in = total_chars // 4

        openai_tools = None
        tool_executor = None
        event_queue = None
        if tools_provider is not None:
            provided = tools_provider()
            if provided:
                if len(provided) == 3:
                    openai_tools, tool_executor, event_queue = provided
                else:
                    openai_tools, tool_executor = provided

        for candidate in candidates:
            if candidate in self._rate_limited: continue

            provider, model = candidate.split('/', 1)
            try:
                client = self._get_client(provider)

                used_tool_loop = False
                if openai_tools:
                    try:
                        async for out in self._run_tool_loop(
                            client, model, messages, openai_tools, tool_executor,
                            provider, candidate, task_type, tokens_in,
                            thinking=thinking, effort=effort, event_queue=event_queue,
                        ):
                            yield out
                        used_tool_loop = True
                    except Exception:
                        # Model/provider likely doesn't support tools, or the
                        # tool loop otherwise blew up. Fall back to plain
                        # streaming below for this SAME candidate -- chat must
                        # never get worse than it was before tool support.
                        used_tool_loop = False

                if used_tool_loop:
                    return

                yield json.dumps({'event': 'status', 'label': 'thinking'})
                stream = await self._create_with_thinking(
                    client, thinking, effort, model=model, messages=messages, stream=True,
                )
                tokens_out = 0
                first_chunk = True
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ''
                    if delta:
                        if first_chunk:
                            yield json.dumps({'event': 'status', 'label': 'responding'})
                            first_chunk = False
                        tokens_out += len(delta) // 4
                        yield f'{{"content": {json.dumps(delta)}}}'

                # Log usage + cost accounting
                cost_in, cost_out = self._get_model_costs(candidate)
                cost = tokens_in / 1000 * cost_in + tokens_out / 1000 * cost_out
                self._today_tokens += tokens_in + tokens_out
                self._today_cost_usd += cost
                self._log_usage(provider, candidate, tokens_in, tokens_out, task_type, cost)
                return

            except Exception as e:
                err_str = str(e)
                if '429' in err_str or 'rate limit' in err_str.lower():
                    self._rate_limited.add(candidate)
                    asyncio.create_task(self._clear_rate_limit(candidate, 60))
                elif 'auth' in err_str.lower() or '401' in err_str:
                    continue  # No key for this provider
                else:
                    continue

        yield f'{{"content": "Error: all configured providers exhausted. Add an API key via forge.add.provider"}}'

    async def _run_tool_loop(
        self, client, model: str, messages: list, openai_tools: list, tool_executor,
        provider: str, candidate: str, task_type: str, tokens_in: int,
        thinking: bool = False, effort: str = 'medium', event_queue: asyncio.Queue | None = None,
    ):
        """Non-streaming tool-calling loop (max 5 round-trips). Yields typed
        SSE-chunk JSON strings: a status/thinking event per round, a
        tool_call/tool_result event pair per tool invocation, and a single
        final content chunk once the model responds without further
        tool_calls. Logs usage/cost on success. Raises on any failure so the
        caller can fall back to plain streaming.
        """
        loop_messages = list(messages)
        tokens_out_total = 0
        call_seq = 0

        for _ in range(5):
            yield json.dumps({'event': 'status', 'label': 'thinking'})
            response = await self._create_with_thinking(
                client, thinking, effort, model=model, messages=loop_messages, tools=openai_tools,
            )
            choice = response.choices[0]
            msg = choice.message
            tool_calls = getattr(msg, 'tool_calls', None)

            usage = getattr(response, 'usage', None)
            completion_tokens = getattr(usage, 'completion_tokens', None) if usage else None
            if completion_tokens is not None:
                tokens_out_total += completion_tokens
            else:
                tokens_out_total += len(msg.content or '') // 4

            if not tool_calls:
                content = msg.content or ''
                if content:
                    yield json.dumps({'event': 'status', 'label': 'responding'})
                    yield f'{{"content": {json.dumps(content)}}}'

                cost_in, cost_out = self._get_model_costs(candidate)
                cost = tokens_in / 1000 * cost_in + tokens_out_total / 1000 * cost_out
                self._today_tokens += tokens_in + tokens_out_total
                self._today_cost_usd += cost
                self._log_usage(provider, candidate, tokens_in, tokens_out_total, task_type, cost)
                return

            loop_messages.append({
                'role': 'assistant',
                'content': msg.content or '',
                'tool_calls': [
                    {
                        'id': tc.id,
                        'type': 'function',
                        'function': {'name': tc.function.name, 'arguments': tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                raw_name = tc.function.name
                server, _, tool_name = raw_name.partition('__')
                display = f'{server}.{tool_name}' if tool_name else raw_name

                try:
                    args = json.loads(tc.function.arguments or '{}')
                except Exception:
                    args = {}

                call_seq += 1
                call_id = f'tc_{call_seq}'
                yield json.dumps({'event': 'tool_call', 'id': call_id, 'name': display, 'args': args})

                if event_queue is not None:
                    task = asyncio.ensure_future(tool_executor(raw_name, args))
                    async for evline in self._drain_queue_while(task, event_queue):
                        yield evline
                    try:
                        result = task.result()
                    except Exception as exc:
                        result = {'error': str(exc)}
                else:
                    try:
                        result = await tool_executor(raw_name, args)
                    except Exception as exc:
                        result = {'error': str(exc)}

                if isinstance(result, dict):
                    content_str = result.get('text') or json.dumps(result)
                elif isinstance(result, str):
                    content_str = result
                else:
                    content_str = json.dumps(result)

                tool_ok = not (isinstance(result, dict) and 'error' in result)
                capped_text = content_str if len(content_str) <= 4000 else content_str[:4000] + '...[truncated]'
                yield json.dumps({'event': 'tool_result', 'id': call_id, 'ok': tool_ok, 'text': capped_text})

                loop_messages.append({
                    'role': 'tool',
                    'tool_call_id': tc.id,
                    'content': content_str,
                })

        # Exceeded max iterations without a final answer. Report what we can
        # and stop cleanly rather than raising (raising here would trigger a
        # duplicate plain-streaming call for the same candidate).
        cost_in, cost_out = self._get_model_costs(candidate)
        cost = tokens_in / 1000 * cost_in + tokens_out_total / 1000 * cost_out
        self._today_tokens += tokens_in + tokens_out_total
        self._today_cost_usd += cost
        self._log_usage(provider, candidate, tokens_in, tokens_out_total, task_type, cost)
        yield f'{{"content": {json.dumps(chr(10) + "(stopped: tool loop exceeded max iterations)")}}}'

    async def _drain_queue_while(self, task: 'asyncio.Future', event_queue: 'asyncio.Queue'):
        """Yield SSE-ready JSON strings for any events pushed onto
        event_queue while `task` is still running, so events (e.g.
        approval_request) reach the client BEFORE the executor blocks on
        something the client must respond to (e.g. an approval decision).
        Deadlock-free: the queue is drained concurrently with the task via
        asyncio.wait, never after it.
        """
        pending_get = asyncio.ensure_future(event_queue.get())
        try:
            while True:
                done, _ = await asyncio.wait({task, pending_get}, return_when=asyncio.FIRST_COMPLETED)
                if pending_get in done:
                    yield json.dumps(pending_get.result())
                    pending_get = asyncio.ensure_future(event_queue.get())
                if task in done:
                    break
        finally:
            if not pending_get.done():
                pending_get.cancel()
        while not event_queue.empty():
            yield json.dumps(event_queue.get_nowait())

    async def _create_with_thinking(self, client, thinking: bool, effort: str, **kwargs):
        """Wraps client.chat.completions.create() with the effort -> max_tokens
        mapping and, when thinking is requested, a reasoning_effort kwarg.
        If the provider rejects reasoning_effort (unsupported param / 400),
        retries once without it so a thinking request never breaks a provider
        that doesn't support it."""
        kwargs['max_tokens'] = EFFORT_MAX_TOKENS.get(effort, EFFORT_MAX_TOKENS['medium'])

        if not thinking:
            return await client.chat.completions.create(**kwargs)

        reasoning_effort = 'low' if effort == 'low' else 'medium' if effort == 'medium' else 'high'
        try:
            return await client.chat.completions.create(**kwargs, reasoning_effort=reasoning_effort)
        except Exception as e:
            err_str = str(e).lower()
            if 'reasoning_effort' in err_str or 'unsupported' in err_str or '400' in err_str or 'bad request' in err_str:
                return await client.chat.completions.create(**kwargs)
            raise

    async def complete_fim(self, prefix: str, suffix: str, language: str) -> str | None:
        # Groq/Gemini expose only the chat endpoint, so FIM runs as a strict
        # insert-only chat prompt instead of the legacy completions API
        candidates = TASK_PROFILES['fim']
        system = (
            'You are a code completion engine. Insert the code that belongs exactly '
            'between the prefix and suffix. Output ONLY the inserted code: no '
            'explanations, no markdown fences, and never repeat the prefix or suffix. '
            'If nothing sensible fits, output nothing.'
        )
        user = (
            f'Language: {language}\n'
            f'<PREFIX>\n{prefix}\n</PREFIX>\n<SUFFIX>\n{suffix}\n</SUFFIX>'
        )
        tokens_in = (len(system) + len(user)) // 4

        for candidate in candidates:
            if candidate in self._rate_limited: continue
            provider, model = candidate.split('/', 1)
            try:
                client = self._get_client(provider)
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': user},
                    ],
                    max_tokens=256, temperature=0.1,
                )
                text = (resp.choices[0].message.content or '').strip('\n')
                text = self._strip_code_fences(text)

                tokens_out = len(text) // 4
                cost_in, cost_out = self._get_model_costs(candidate)
                cost = tokens_in / 1000 * cost_in + tokens_out / 1000 * cost_out
                self._today_tokens += tokens_in + tokens_out
                self._today_cost_usd += cost
                self._log_usage(provider, candidate, tokens_in, tokens_out, 'complete', cost)

                return text or None
            except Exception:
                continue
        return None

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith('```'):
            lines = stripped.split('\n')
            lines = lines[1:]  # drop opening fence (possibly with language tag)
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            return '\n'.join(lines)
        return text

    def register_provider(self, provider_id: str, api_key: str):
        os.environ[f'FORGE_{provider_id.upper()}_KEY'] = api_key
        # Reset cached client to use new key
        self._clients.pop(provider_id, None)

    def set_default_model(self, model_id: str):
        self._default_model = model_id

    def set_daily_budget(self, value: float):
        self._daily_budget_usd = value

    def get_default_model(self) -> str:
        return self._default_model

    def list_models(self) -> list:
        from db.models import Model
        with get_session() as db:
            return [
                {
                    'id': m.id, 'display_name': m.display_name,
                    'is_free': m.is_free, 'cost_per_1k_output': m.cost_per_1k_output,
                    'recommended_for': json.loads(m.recommended_for or '[]'),
                }
                for m in db.query(Model).all()
            ]

    def get_usage_stats(self) -> dict:
        by_model: dict[str, dict] = {}
        try:
            today_midnight = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            with get_session() as db:
                rows = db.query(UsageLog).filter(UsageLog.timestamp >= today_midnight).all()
            for r in rows:
                entry = by_model.setdefault(r.model_id, {'model_id': r.model_id, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0})
                entry['tokens_in'] += r.tokens_in or 0
                entry['tokens_out'] += r.tokens_out or 0
                entry['cost_usd'] += r.cost_usd or 0.0
        except Exception:
            pass

        return {
            'today_usd': round(self._today_cost_usd, 6),
            'today_tokens': self._today_tokens,
            'by_model': [
                {**v, 'cost_usd': round(v['cost_usd'], 6)}
                for v in by_model.values()
            ],
        }

    def _log_usage(self, provider: str, model_id: str, tokens_in: int, tokens_out: int, task_type: str, cost_usd: float = 0.0):
        with get_session() as db:
            db.add(UsageLog(
                provider_id=provider, model_id=model_id,
                tokens_in=tokens_in, tokens_out=tokens_out,
                cost_usd=cost_usd, task_type=task_type
            ))
            db.commit()

    async def _clear_rate_limit(self, model_id: str, delay_s: int):
        await asyncio.sleep(delay_s)
        self._rate_limited.discard(model_id)
