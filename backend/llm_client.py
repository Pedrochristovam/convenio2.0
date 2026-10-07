"""
Cliente Groq compartilhado para respostas JSON.

A conta gratuita tem limite de ~8.000 tokens/minuto e ~1.000 requisições/dia,
então todas as chamadas passam por um orçamento de tokens em janela deslizante
e respeitam o retry-after devolvido nos erros 429.
"""

import asyncio
import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 3.2
WINDOW_SECONDS = 60.0
COTA_DIARIA_SEG = 180.0


class LLMUnavailable(RuntimeError):
    pass


class GroqJSONClient:
    def __init__(self):
        api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        self.enabled = bool(api_key)
        self.model = (os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b").strip()
        self.fast_model = (os.getenv("GROQ_FAST_MODEL") or "openai/gpt-oss-20b").strip()
        self.tpm_budget = int(os.getenv("GROQ_TPM_BUDGET") or 7000)
        self.max_attempts = 4
        # O limite de tokens/minuto do Groq é por modelo
        self._usage: Dict[str, Deque[Tuple[float, int]]] = {}
        self._lock = threading.Lock()
        self.calls = 0
        self.tokens_used = 0
        self.client = None
        if self.enabled:
            from groq import Groq

            self.client = Groq(api_key=api_key, max_retries=0, timeout=90)

    def _estimate(self, messages, max_tokens: int) -> int:
        chars = sum(len(m.get("content") or "") for m in messages)
        return int(chars / CHARS_PER_TOKEN) + max_tokens

    def _reserve(self, model: str, tokens: int) -> None:
        """Bloqueia até caber `tokens` na janela de 60s do modelo."""
        tokens = min(tokens, self.tpm_budget)
        while True:
            with self._lock:
                usage = self._usage.setdefault(model, deque())
                now = time.monotonic()
                while usage and now - usage[0][0] > WINDOW_SECONDS:
                    usage.popleft()
                used = sum(t for _, t in usage)
                if used + tokens <= self.tpm_budget:
                    usage.append((now, tokens))
                    return
                wait = WINDOW_SECONDS - (now - usage[0][0]) + 0.5
            logger.info("Groq(%s): aguardando %.1fs pelo limite de tokens/minuto", model, wait)
            time.sleep(max(wait, 0.5))

    def _record_actual(self, model: str, estimated: int, actual: Optional[int]) -> None:
        if actual is None:
            return
        with self._lock:
            usage = self._usage.get(model) or deque()
            for i in range(len(usage) - 1, -1, -1):
                ts, tok = usage[i]
                if tok == min(estimated, self.tpm_budget):
                    usage[i] = (ts, actual)
                    break

    @staticmethod
    def _retry_after(exc: Exception) -> float:
        resp = getattr(exc, "response", None)
        headers = getattr(resp, "headers", None) or {}
        for key in ("retry-after", "x-ratelimit-reset-tokens"):
            val = headers.get(key)
            if not val:
                continue
            try:
                return float(str(val).rstrip("s"))
            except ValueError:
                continue
        return 20.0

    def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 1500,
        fast: bool = False,
    ) -> Dict[str, Any]:
        if not self.enabled or not self.client:
            raise LLMUnavailable("GROQ_API_KEY não configurada")

        from groq import APIStatusError, RateLimitError

        model = self.fast_model if fast else self.model
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        estimated = self._estimate(messages, max_tokens)
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_attempts + 1):
            self._reserve(model, estimated)
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0,
                    max_completion_tokens=max_tokens,
                    reasoning_effort="low",
                    response_format={"type": "json_object"},
                )
                self.calls += 1
                usage = getattr(resp, "usage", None)
                total = getattr(usage, "total_tokens", None)
                if total:
                    self.tokens_used += total
                self._record_actual(model, estimated, total)
                content = (resp.choices[0].message.content or "").strip()
                return json.loads(content)
            except RateLimitError as exc:
                last_error = exc
                wait = self._retry_after(exc)
                if wait > COTA_DIARIA_SEG:
                    # Espera longa = cota diária do modelo esgotada, não o limite por minuto
                    if model == self.fast_model and self.model != model:
                        logger.warning("Groq: cota esgotada em %s; usando %s", model, self.model)
                        model = self.model
                        continue
                    raise LLMUnavailable(f"Cota do Groq esgotada para {model} (liberação em ~{wait / 60:.0f} min)")
                logger.warning("Groq 429 (tentativa %s): aguardando %.1fs", attempt, wait)
                time.sleep(min(wait, 90))
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning("Groq devolveu JSON inválido (tentativa %s)", attempt)
            except APIStatusError as exc:
                last_error = exc
                if exc.status_code and exc.status_code < 500 and exc.status_code != 413:
                    break
                time.sleep(3 * attempt)
            except Exception as exc:
                last_error = exc
                time.sleep(3 * attempt)

        raise LLMUnavailable(f"Groq falhou após {self.max_attempts} tentativas: {last_error}")

    async def acomplete_json(self, system: str, user: str, max_tokens: int = 1500, fast: bool = False) -> Dict[str, Any]:
        return await asyncio.to_thread(self.complete_json, system, user, max_tokens, fast)


_shared: Optional[GroqJSONClient] = None


def get_llm() -> GroqJSONClient:
    global _shared
    if _shared is None:
        _shared = GroqJSONClient()
    return _shared
