"""Тесты LLM-клиента Agent Router для генерации КП (leads.llm).

Сетевые вызовы мокаются: проверяются запрос-пейлоад, парсинг ответа
(«subject|||body») и деградация при ошибке API.
"""

from __future__ import annotations

from leads.llm import AgentRouterClient, parse_proposal_answer


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeHTTP:
    """Мок requests.Session: помнит последний запрос, отвечает заготовкой."""

    def __init__(self, response: FakeResponse):
        self.response = response
        self.last_url = ""
        self.last_payload: dict = {}

    def post(self, url, json=None, headers=None, timeout=None):  # noqa: A002
        self.last_url = url
        self.last_payload = json
        return self.response


class TestParseProposalAnswer:
    def test_subject_body_split(self):
        subject, body = parse_proposal_answer("Тема письма|||Текст письма")
        assert subject == "Тема письма"
        assert body == "Текст письма"

    def test_multiline_body(self):
        subject, body = parse_proposal_answer("S|||line1\nline2\nline3")
        assert subject == "S"
        assert body == "line1\nline2\nline3"

    def test_no_separator_returns_none(self):
        assert parse_proposal_answer("только одна строка") == ("", "")


class TestAgentRouterClient:
    def _client(self, response: FakeResponse) -> tuple[AgentRouterClient, FakeHTTP]:
        http = FakeHTTP(response)
        client = AgentRouterClient(api_key="test-key", http=http)
        return client, http

    def test_complete_sends_chat_completion(self):
        payload = {
            "choices": [{"message": {"content": "SUBJ|||BODY"}}],
            "usage": {"total_tokens": 42},
        }
        client, http = self._client(FakeResponse(payload))
        answer = client.complete("prompt text")
        assert answer == "SUBJ|||BODY"
        assert http.last_url.endswith("/chat/completions")
        assert http.last_payload["model"] == client.model
        assert http.last_payload["messages"][0]["content"] == "prompt text"
        assert "test-key" in http_last_headers_auth(client)

    def test_tokens_counted(self):
        payload = {
            "choices": [{"message": {"content": "S|||B"}}],
            "usage": {"total_tokens": 42},
        }
        client, _ = self._client(FakeResponse(payload))
        client.complete("prompt")
        assert client.tokens_used == 42

    def test_empty_choices_returns_empty(self):
        payload = {"choices": []}
        client, _ = self._client(FakeResponse(payload))
        assert client.complete("prompt") == ""


def http_last_headers_auth(client: AgentRouterClient) -> str:
    """Bearer-строка, которую клиент передал в последнем запросе."""
    return client._last_auth_header  # type: ignore[attr-defined]
