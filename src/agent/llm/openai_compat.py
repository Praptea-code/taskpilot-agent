import httpx


class OpenAICompatError(RuntimeError):
    pass


class OpenAICompatClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "qwen2.5:7b-instruct",
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
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
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
                response.raise_for_status()
            except httpx.ConnectError as error:
                raise OpenAICompatError(f"Cannot reach LLM endpoint at {self.base_url}") from error
            except httpx.HTTPStatusError as error:
                detail = f"LLM endpoint failed: {error.response.status_code}"
                raise OpenAICompatError(detail) from error
        finally:
            if self._owns_client:
                await client.aclose()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return str(content)
