from __future__ import annotations

import json
from urllib import request, error


BASE_URL = "http://127.0.0.1:11434"


class OllamaError(RuntimeError):
    pass


def _json_request(path: str, payload: dict | None = None, timeout: int = 120) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise OllamaError("O Ollama local não respondeu. Verifique se ele está aberto.") from exc


def list_models() -> list[str]:
    try:
        payload = _json_request("/api/tags", timeout=5)
    except OllamaError:
        return []
    return [m.get("name") or m.get("model") for m in payload.get("models", []) if (m.get("name") or m.get("model"))]


def choose_default_model(models: list[str]) -> str | None:
    preferred = ["qwen3.5:4b", "qwen3.5:9b", "qwen3:8b", "qwen3:14b"]
    for p in preferred:
        if p in models:
            return p
    return models[0] if models else None


def improve_subtitle(
    current_ptbr: str,
    previous_ptbr: str = "",
    next_ptbr: str = "",
    english_reference: str = "",
    model: str | None = None,
) -> dict:
    models = list_models()
    model = model or choose_default_model(models)
    if not model:
        raise OllamaError("Nenhum modelo local foi encontrado no Ollama.")

    schema = {
        "type": "object",
        "properties": {
            "changed": {"type": "boolean"},
            "suggestion": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["changed", "suggestion", "reason"],
    }
    prompt = f"""
Revise APENAS a legenda atual para português do Brasil natural e adequado a filmes/séries.
Se ela já estiver boa, não altere. Seja conservador e preserve o sentido, nomes próprios,
palavrões, tom e concisão de legenda. Não invente informação.

Contexto anterior (PT-BR): {previous_ptbr or '(não disponível)'}
Legenda atual (PT-BR): {current_ptbr}
Contexto seguinte (PT-BR): {next_ptbr or '(não disponível)'}
Original em inglês correspondente: {english_reference or '(não disponível)'}

Retorne changed=false se não houver melhoria necessária.
""".strip()
    payload = {
        "model": model,
        "prompt": prompt,
        "system": "Você é um revisor profissional de legendas em português do Brasil.",
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": 0.1},
        "keep_alive": "5m",
    }
    response = _json_request("/api/generate", payload, timeout=180)
    raw = response.get("response", "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaError("O modelo local respondeu em um formato inesperado.") from exc
    suggestion = str(parsed.get("suggestion", current_ptbr)).strip() or current_ptbr
    return {
        "changed": bool(parsed.get("changed", suggestion != current_ptbr)),
        "suggestion": suggestion,
        "reason": str(parsed.get("reason", "")).strip(),
        "model": model,
    }
