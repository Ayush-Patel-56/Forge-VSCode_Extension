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

    async def stream(self, messages: list, model_id: str | None, context_chunks: list[str]):
        if context_chunks:
            ctx = '\n\n'.join(f'```\n{c}\n```' for c in context_chunks)
            messages = [{'role': 'system', 'content': f'Relevant code from codebase:\n{ctx}'}] + messages

        task_type = self._classify_task(messages[-1].get('content', '') if messages else '')
        candidates = self._get_candidates_with_default(task_type, model_id)

        total_chars = sum(len(m.get('content', '') or '') for m in messages)
        tokens_in = total_chars // 4

        for candidate in candidates:
            if candidate in self._rate_limited: continue

            provider, model = candidate.split('/', 1)
            try:
                client = self._get_client(provider)
                stream = await client.chat.completions.create(
                    model=model, messages=messages, stream=True, max_tokens=4096
                )
                tokens_out = 0
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ''
                    if delta:
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
