"""Small configurable text-generation boundary shared by draft and repair flows."""

import json
import os
import ssl
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv
import certifi

TextGenerator = Callable[[str], str]
_generator: TextGenerator | None = None


class GeneratorNotConfiguredError(RuntimeError):
    """No local LLM provider has been configured for generation."""


def set_text_generator(generator: TextGenerator | None) -> None:
    """Configure one provider adapter without coupling core logic to a vendor."""
    global _generator
    _generator = generator


def _generate_with_gemini(instruction: str) -> str:
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    if not api_key or not model:
        raise GeneratorNotConfiguredError("Set LLM_API_KEY and LLM_MODEL in .env before generating a draft.")
    # Gemini 3 models use the Interactions API.  It is also Google's
    # recommended API for new integrations, while the older generateContent
    # route remains only for legacy compatibility.
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/interactions?key={quote(api_key, safe='')}"
    payload = {"model": model.removeprefix("models/"), "input": instruction}
    request = Request(endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=60, context=ssl_context) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"LLM provider returned HTTP {error.code}: {detail[:300]}") from error
    except URLError as error:
        raise RuntimeError(f"LLM provider could not be reached: {error.reason}") from error
    answer = _interaction_text(result)
    if not answer:
        raise RuntimeError("LLM provider returned no text.")
    return answer


def _interaction_text(result: dict) -> str:
    """Extract text emitted by a completed Gemini Interaction response."""
    parts = (
        content
        for step in result.get("steps", [])
        if step.get("type") == "model_output"
        for content in step.get("content", [])
    )
    return "".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()


load_dotenv()
if os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL"):
    _generator = _generate_with_gemini


def generate_text(instruction: str) -> str:
    """Generate text through the configured provider adapter."""
    if _generator is None:
        raise GeneratorNotConfiguredError("No LLM provider is configured for repair. Configure a text generator before retrying.")
    return _generator(instruction)


def generate_draft(prompt: str) -> str:
    """Generate an initial draft answer from a prompt.

    An LLM provider will be configured in a later development phase.
    """
    return generate_text(prompt)
