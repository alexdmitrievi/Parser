"""LLM-клиент Agent Router для генерации коммерческих предложений.

Agent Router (agentrouter.org) — OpenAI-совместимый шлюз; модель по
решению владельца — glm-5.3 (reasoning high). Клиент минимален: один
метод :meth:`AgentRouterClient.complete`, совместим с протоколом
``ProposalLLM`` из :mod:`leads.outreach`.

Ключ берётся из ``AGENT_ROUTER_API_KEY`` и никогда не логируется.
"""

from __future__ import annotations

import os
from typing import Any

from engine.observability.logger import get_logger

logger = get_logger("leads.llm")

DEFAULT_BASE_URL = "https://agentrouter.org/v1"
DEFAULT_MODEL = "glm-5.3"
DEFAULT_TIMEOUT_SECONDS = 60

PROPOSAL_SEPARATOR = "|||"


def parse_proposal_answer(answer: str) -> tuple[str, str]:
    """Разобрать ответ LLM в ``(subject, body)``.

    Ожидается формат «тема|||текст» (инструкция в промпте КП).

    Args:
        answer: Сырой текст ответа модели.

    Returns:
        Кортеж ``(subject, body)``; ``("", "")`` если разделителя нет.
    """
    if PROPOSAL_SEPARATOR not in answer:
        return "", ""
    subject, body = answer.split(PROPOSAL_SEPARATOR, 1)
    return subject.strip(), body.strip()


class AgentRouterClient:
    """Минимальный OpenAI-совместимый клиент Agent Router."""

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        http: Any = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.api_key = api_key or os.environ.get("AGENT_ROUTER_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.tokens_used = 0
        self._last_auth_header = ""

        if http is None:
            import requests

            http = requests.Session()
        self._http = http

    def complete(self, prompt: str) -> str:
        """Выполнить один запрос генерации.

        Args:
            prompt: Полный промпт (например, из ``_proposal_prompt``).

        Returns:
            Текст ответа модели. Пустая строка при ошибке — вызывающий
            код (``CrmBridge``) деградирует до шаблона КП.
        """
        if not self.api_key:
            logger.warning("AGENT_ROUTER_API_KEY не задан — LLM недоступен")
            return ""

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Agent Router гейтит по User-Agent — обязателен идентифицируемый UA.
            "User-Agent": "hermes-agent/1.0",
        }
        self._last_auth_header = headers["Authorization"]

        try:
            response = self._http.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:  # noqa: BLE001 - ошибка API не роняет рассылку
            logger.warning(f"Agent Router запрос не удался: {type(e).__name__}")
            return ""

        usage = data.get("usage") or {}
        self.tokens_used += int(usage.get("total_tokens") or 0)

        choices = data.get("choices") or []
        if not choices:
            logger.warning("Agent Router: пустой choices в ответе")
            return ""
        message = choices[0].get("message") or {}
        return str(message.get("content") or "").strip()


__all__ = [
    "AgentRouterClient",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "PROPOSAL_SEPARATOR",
    "parse_proposal_answer",
]
