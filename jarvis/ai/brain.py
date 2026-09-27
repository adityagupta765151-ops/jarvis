"""The AI layer: history, tool calling, and the loop that keeps going
until the job is done. The HTTP side lives in llm.py."""
from __future__ import annotations

from ..app.config import log
from ..tools.registry import TOOL_SCHEMAS, execute_tool
from .prompts import SYSTEM
from .provider import call_gemini

MAX_STEPS = 25
MAX_MESSAGES = 40
TYPE_MAP = {"string": "STRING", "integer": "INTEGER", "number": "NUMBER", "boolean": "BOOLEAN"}


def _to_gemini_tools() -> list[dict]:
    declarations = []
    for tool in TOOL_SCHEMAS:
        schema = tool["input_schema"]
        declaration = {"name": tool["name"], "description": tool["description"]}
        if schema.get("properties"):
            declaration["parameters"] = {
                "type": "OBJECT",
                "properties": {
                    key: {"type": TYPE_MAP.get(value.get("type", "string"), "STRING")}
                    for key, value in schema["properties"].items()
                },
                "required": schema.get("required", []),
            }
        declarations.append(declaration)
    return [{"functionDeclarations": declarations}]


GEMINI_TOOLS = _to_gemini_tools()


class Brain:
    def __init__(self) -> None:
        self.history: list[dict] = []

    def reset(self) -> None:
        self.history.clear()

    def _trim(self) -> None:
        """Drop old turns, cutting only at a plain user message so a
        function call is never separated from its response."""
        while len(self.history) > MAX_MESSAGES:
            self.history.pop(0)
            while self.history and not (
                self.history[0]["role"] == "user" and "text" in self.history[0]["parts"][0]
            ):
                self.history.pop(0)

    def ask(self, text: str, on_action=None) -> str:
        self.history.append({"role": "user", "parts": [{"text": text}]})
        self._trim()

        for _ in range(MAX_STEPS):
            data = call_gemini({
                "systemInstruction": {"parts": [{"text": SYSTEM}]},
                "contents": self.history,
                "tools": GEMINI_TOOLS,
            })
            candidates = data.get("candidates")
            if not candidates:
                return "The model returned nothing. It may have blocked that request."

            parts = candidates[0].get("content", {}).get("parts", [])
            self.history.append({"role": "model", "parts": parts})

            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not calls:
                reply = " ".join(p["text"] for p in parts if "text" in p).strip()
                return reply or "Done."

            responses = []
            for call in calls:
                name, args = call["name"], call.get("args") or {}
                if on_action:
                    on_action(name, args)
                responses.append({"functionResponse": {
                    "name": name, "response": {"result": execute_tool(name, args)}}})
            self.history.append({"role": "user", "parts": responses})

        return "That took more steps than I allow in one go. Tell me to continue if you want."
