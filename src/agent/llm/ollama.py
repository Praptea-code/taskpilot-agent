import httpx


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen2.5:7b-instruct",
        fallback_model: str = "llama3.2:3b",
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None

    async def complete(
        self, system: str, user: str, *, json_mode: bool = False, temperature: float = 0.2
    ) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            try:
                response = await client.post(f"{self.host}/api/chat", json=payload)
                response.raise_for_status()
            except httpx.ConnectError as error:
                message = (
                    "Cannot reach Ollama. Run 'ollama serve' then "
                    "'ollama pull qwen2.5:7b-instruct'."
                )
                raise OllamaError(message) from error
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 404 and self.fallback_model != self.model:
                    payload["model"] = self.fallback_model
                    response = await client.post(f"{self.host}/api/chat", json=payload)
                    response.raise_for_status()
                else:
                    detail = f"Ollama request failed: {error.response.status_code}"
                    raise OllamaError(detail) from error
        finally:
            if self._owns_client:
                await client.aclose()

        data = response.json()
        message = data["message"]["content"]
        return str(message)
