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
        self._vision_models: set[str] = set()
        self._vision_models_loaded = False
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

    def _get_vision_models(self) -> set[str]:
        """Returns the set of model_ids with supports_vision=True, cached like
        _get_model_costs. Tests may set self._vision_models_loaded = True and
        self._vision_models directly to bypass the db query."""
        if not self._vision_models_loaded:
            try:
                from db.models import Model
                with get_session() as db:
                    self._vision_models = {
                        m.id for m in db.query(Model).filter_by(supports_vision=True).all()
                    }
                self._vision_models_loaded = True
            except Exception:
                pass
        return self._vision_models

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

    @staticmethod
    def _extract_text(content) -> str:
        """Message content is normally a str, but main.py converts the last
        user message into the OpenAI multimodal array form (text + image_url
        parts) when images are attached. Extract just the text so task
        classification and token-count estimation keep working either way."""
        if isinstance(content, list):
            return '\n'.join(
                part.get('text') or ''
                for part in content
                if isinstance(part, dict) and part.get('type') == 'text'
            )
        return content or ''

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
        has_images: bool = False, auto_fallback: bool = True,
    ):
        if context_chunks:
            ctx = '\n\n'.join(f'```\n{c}\n```' for c in context_chunks)
            messages = [{'role': 'system', 'content': f'Relevant code from codebase:\n{ctx}'}] + messages

        task_type = self._classify_task(self._extract_text(messages[-1].get('content', '')) if messages else '')
        candidates = self._get_candidates_with_default(task_type, model_id)

        if has_images:
            vision_models = self._get_vision_models()
            vision_candidates = [c for c in candidates if c in vision_models]
            if not vision_candidates:
                # Task-profile chain may not include a vision model at all
                # (e.g. selected model isn't vision-capable) -- fall back to
                # trying every known vision-capable model directly rather
                # than sending image content to a model that will 400 on it.
                vision_candidates = list(vision_models)
            if not vision_candidates:
                yield f'{{"content": {json.dumps("Attach requires a vision-capable model — add a Gemini key")}}}'
                return
            candidates = vision_candidates

        if not auto_fallback and model_id:
            candidates = [model_id]

        total_chars = sum(len(self._extract_text(m.get('content'))) for m in messages)
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
                fallback_messages = messages
                if openai_tools:
                    try:
                        async for out in self._run_tool_loop(
                            client, model, messages, openai_tools, tool_executor,
                            provider, candidate, task_type, tokens_in,
                            thinking=thinking, effort=effort, event_queue=event_queue,
                        ):
                            yield out
                        used_tool_loop = True
                    except Exception as e:
                        # Model/provider likely doesn't support tools, or the
                        # tool loop otherwise blew up. Fall back to plain
                        # streaming below for this SAME candidate -- chat must
                        # never get worse than it was before tool support. If
                        # tool calls already executed this turn, don't just
                        # silently drop their results: summarize them into a
                        # system message so the fallback model can still
                        # answer from what already ran. (Raw role:'tool'
                        # messages are never carried into the fallback --
                        # providers 400 on those without accompanying
                        # tool-call context, which is what broke the
                        # exhausted-providers case in the first place.)
                        used_tool_loop = False
                        executed = getattr(e, 'forge_executed_tools', None)
                        if executed:
                            summary = 'Tool calls already executed this turn and their outputs:\n' + '\n'.join(
                                f'{name}: {text[:500]}' for name, text in executed
                            )
                            fallback_messages = messages + [{'role': 'system', 'content': summary}]

                if used_tool_loop:
                    return

                yield json.dumps({'event': 'status', 'label': 'thinking'})
                stream = await self._create_with_thinking(
                    client, thinking, effort, model=model, messages=fallback_messages, stream=True,
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

        if not auto_fallback and model_id:
            yield f'{{"content": {json.dumps(f"Error: model {model_id} failed and auto-fallback is disabled.")}}}'
            return
        yield f'{{"content": "Error: all configured providers exhausted. Add an API key via forge.add.provider"}}'

    async def _run_tool_loop(
        self, client, model: str, messages: list, openai_tools: list, tool_executor,
        provider: str, candidate: str, task_type: str, tokens_in: int,
        thinking: bool = False, effort: str = 'medium', event_queue: asyncio.Queue | None = None,
    ):
        """Streaming tool-calling loop (max 5 round-trips). Each round streams
        the model's response live -- content deltas are yielded as SSE
        content chunks the moment they arrive, instead of waiting for the
        whole round to finish, so the user never stares at "thinking" while
        a full generation happens invisibly. tool_calls deltas are
        accumulated by index across the round's chunks (provider may split
        name/arguments across several chunks) and only resolved into real
        tool invocations once the round's stream ends.

        Yields typed SSE-chunk JSON strings: a status/thinking event per
        round, a status/responding event before the first content chunk of
        a round, a tool_call/tool_result event pair per tool invocation, and
        streamed content chunks once the model responds without further
        tool_calls. Logs usage/cost on success.

        Raises on any failure so the caller can fall back to plain
        streaming. Operates on its own copy of `messages` (`loop_messages`)
        so the caller's list is never mutated -- the fallback and any
        subsequent candidate must see the pristine pre-tool-loop messages.
        If at least one tool call already executed this turn before the
        failure, the raised exception carries a `forge_executed_tools`
        attribute (list of (display_name, result_text) tuples) so the
        caller can summarize the completed work into the fallback instead
        of silently dropping it.
        """
        loop_messages = list(messages)
        tokens_out_total = 0
        call_seq = 0
        executed_tools_log: list[tuple[str, str]] = []

        for round_num in range(5):
            yield json.dumps({'event': 'status', 'label': 'thinking'})

            try:
                stream = await self._create_with_thinking(
                    client, thinking, effort, model=model, messages=loop_messages,
                    tools=openai_tools, stream=True,
                )

                round_content = ''
                tool_calls_acc: dict[int, dict] = {}
                responded = False

                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    content_piece = getattr(delta, 'content', None)
                    if content_piece:
                        if not responded:
                            yield json.dumps({'event': 'status', 'label': 'responding'})
                            responded = True
                        round_content += content_piece
                        tokens_out_total += len(content_piece) // 4
                        yield f'{{"content": {json.dumps(content_piece)}}}'

                    for tc_delta in (getattr(delta, 'tool_calls', None) or []):
                        idx = getattr(tc_delta, 'index', 0) or 0
                        entry = tool_calls_acc.setdefault(idx, {'id': None, 'name': None, 'arguments': ''})
                        if getattr(tc_delta, 'id', None):
                            entry['id'] = tc_delta.id
                        func = getattr(tc_delta, 'function', None)
                        if func is not None:
                            if getattr(func, 'name', None):
                                entry['name'] = func.name
                            if getattr(func, 'arguments', None):
                                entry['arguments'] += func.arguments
            except Exception as e:
                if executed_tools_log:
                    e.forge_executed_tools = executed_tools_log
                raise

            if not tool_calls_acc:
                cost_in, cost_out = self._get_model_costs(candidate)
                cost = tokens_in / 1000 * cost_in + tokens_out_total / 1000 * cost_out
                self._today_tokens += tokens_in + tokens_out_total
                self._today_cost_usd += cost
                self._log_usage(provider, candidate, tokens_in, tokens_out_total, task_type, cost)
                return

            ordered_calls = []
            for idx in sorted(tool_calls_acc):
                entry = tool_calls_acc[idx]
                call_id = entry['id'] or f'call_{round_num}_{idx}'
                ordered_calls.append({
                    'id': call_id,
                    'name': entry['name'] or '',
                    'arguments': entry['arguments'],
                })

            loop_messages.append({
                'role': 'assistant',
                'content': round_content or None,
                'tool_calls': [
                    {
                        'id': c['id'],
                        'type': 'function',
                        'function': {'name': c['name'], 'arguments': c['arguments']},
                    }
                    for c in ordered_calls
                ],
            })

            for c in ordered_calls:
                raw_name = c['name']
                server, _, tool_name = raw_name.partition('__')
                display = f'{server}.{tool_name}' if tool_name else raw_name

                try:
                    args = json.loads(c['arguments'] or '{}')
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

                executed_tools_log.append((display, content_str))

                loop_messages.append({
                    'role': 'tool',
                    'tool_call_id': c['id'],
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
