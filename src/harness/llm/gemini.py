"""harness/llm/gemini.py - Google Gemini adapter.

Reads GEMINI_API_KEY from the environment (never hardcoded).
Returns structured ToolActions so the controller can route them through
the permission gate before anything touches the workspace.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

try:
    import google.generativeai as genai
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "google-generativeai is required: pip install google-generativeai"
    ) from exc


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class ToolAction:
    """A single action the model wants to take."""
    kind: str            # "shell" | "edit" | "read" | "done"
    argv: list[str]      # for shell
    path: str = ""       # for edit / read
    content: str = ""    # for edit (new file content)
    description: str = ""


@dataclass
class ModelTurn:
    """Everything the model produced in one round-trip."""
    actions: list[ToolAction]
    explanation: str
    raw_text: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    model: str


# ---------------------------------------------------------------------------
# System prompt (instructions the LLM follows)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a coding agent operating inside a verified-execution
harness. Every action you propose will be checked by a permission gate before
it executes. Respond ONLY with valid JSON matching this schema:

{
  "explanation": "<one sentence describing what you will do>",
  "actions": [
    {"kind": "shell", "argv": ["<abs_or_rel_cmd>", "arg1"], "description": "..."},
    {"kind": "edit",  "path": "<workspace-relative path>", "content": "<full new file content>", "description": "..."},
    {"kind": "read",  "path": "<workspace-relative path>", "description": "..."},
    {"kind": "done",  "description": "task complete, no further actions"}
  ]
}

Rules:
- Keep paths workspace-relative (no leading /).
- Never output secrets or API keys.
- When the task is complete emit a single "done" action.
- If verification failed, the diagnostics will be in the user message - fix
  the specific issue reported rather than rewriting everything.
- Actions are executed in order; later actions can depend on earlier ones.
"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class GeminiClient:
    """Stateless Gemini client.  Pass history externally for multi-turn."""

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
    ) -> None:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY environment variable is not set. "
                "Export it before running the harness."
            )
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self._gen_cfg = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
        )
        self._model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=_SYSTEM_PROMPT,
            generation_config=self._gen_cfg,
        )

    # ------------------------------------------------------------------
    def send(
        self,
        user_message: str,
        history: list[dict] | None = None,
    ) -> ModelTurn:
        """Send one user message (with optional prior history) and parse the
        model response into a ModelTurn.  Raises on non-recoverable errors."""
        contents: list[Any] = []
        if history:
            for h in history:
                contents.append({"role": h["role"], "parts": [h["content"]]})
        contents.append({"role": "user", "parts": [user_message]})

        t0 = time.monotonic()
        response = self._model.generate_content(contents)
        duration_ms = int((time.monotonic() - t0) * 1000)

        raw = response.text or ""
        usage = response.usage_metadata
        in_tok  = getattr(usage, "prompt_token_count",  0) or 0
        out_tok = getattr(usage, "candidates_token_count", 0) or 0

        actions, explanation = _parse_response(raw)
        return ModelTurn(
            actions=actions,
            explanation=explanation,
            raw_text=raw,
            input_tokens=int(in_tok),
            output_tokens=int(out_tok),
            duration_ms=duration_ms,
            model=self.model_name,
        )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> tuple[list[ToolAction], str]:
    """Extract JSON from model text and build ToolAction list."""
    # Strip markdown code fences if present
    clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    clean = re.sub(r"```\s*$", "", clean.strip(), flags=re.MULTILINE)

    try:
        obj = json.loads(clean)
    except json.JSONDecodeError:
        # Fall back: treat entire output as a "done" if JSON fails
        return (
            [ToolAction(kind="done", argv=[], description=f"parse_error: {text[:200]}")],
            "model response was not valid JSON",
        )

    explanation = str(obj.get("explanation", ""))
    raw_actions = obj.get("actions", [])
    if not isinstance(raw_actions, list):
        raw_actions = []

    actions: list[ToolAction] = []
    for a in raw_actions:
        if not isinstance(a, dict):
            continue
        kind = str(a.get("kind", "done"))
        actions.append(
            ToolAction(
                kind=kind,
                argv=[str(x) for x in a.get("argv", [])],
                path=str(a.get("path", "")),
                content=str(a.get("content", "")),
                description=str(a.get("description", "")),
            )
        )

    if not actions:
        actions = [ToolAction(kind="done", argv=[], description="no actions")]

    return actions, explanation
