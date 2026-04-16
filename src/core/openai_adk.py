"""
OpenAI-based replacements for google.adk and google.genai types.
Provides drop-in compatible classes so the rest of the codebase
changes as little as possible.
"""
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI


# ---------------------------------------------------------------------------
# Minimal types to replace google.genai.types
# ---------------------------------------------------------------------------

@dataclass
class Part:
    text: str = ""

    @staticmethod
    def from_text(text: str) -> "Part":
        return Part(text=text)


@dataclass
class Content:
    role: str = "user"
    parts: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Session / SessionService
# ---------------------------------------------------------------------------

@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    history: list = field(default_factory=list)  # list of Content


class InMemorySessionService:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    async def create_session(self, app_name: str, user_id: str) -> Session:
        session = Session()
        self._sessions[session.id] = session
        return session

    async def get_session(self, app_name: str, user_id: str, session_id: str) -> Session:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        return self._sessions[session_id]


# ---------------------------------------------------------------------------
# Plugin base class (replaces google.adk.plugins.base_plugin.BasePlugin)
# ---------------------------------------------------------------------------

class BasePlugin:
    def __init__(self, name: str):
        self.name = name

    async def on_user_message_callback(
        self, *, invocation_context: Any, user_message: Content
    ) -> Content | None:
        """Return None to pass through, or Content to block."""
        return None

    async def after_model_callback(
        self, *, callback_context: Any, llm_response: Any
    ) -> Any:
        """Return (possibly modified) llm_response."""
        return llm_response


# ---------------------------------------------------------------------------
# LlmAgent (replaces google.adk.agents.llm_agent.LlmAgent)
# ---------------------------------------------------------------------------

class LlmAgent:
    def __init__(self, model: str, name: str, instruction: str):
        self.model = model
        self.name = name
        self.instruction = instruction


# ---------------------------------------------------------------------------
# Streaming event wrapper
# ---------------------------------------------------------------------------

@dataclass
class AgentEvent:
    content: Content


# ---------------------------------------------------------------------------
# InMemoryRunner (replaces google.adk.runners.InMemoryRunner)
# ---------------------------------------------------------------------------

class InMemoryRunner:
    def __init__(self, agent: LlmAgent, app_name: str, plugins: list = None):
        self.agent = agent
        self.app_name = app_name
        self.plugins: list[BasePlugin] = plugins or []
        self.session_service = InMemorySessionService()
        self._client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    async def run_async(self, user_id: str, session_id: str, new_message: Content):
        """Run the agent and yield AgentEvent objects."""
        session = await self.session_service.get_session(
            app_name=self.app_name, user_id=user_id, session_id=session_id
        )

        # --- Input guardrail plugins ---
        for plugin in self.plugins:
            result = await plugin.on_user_message_callback(
                invocation_context=None, user_message=new_message
            )
            if result is not None:
                # Blocked — return the block message directly
                yield AgentEvent(content=result)
                return

        # Build message history for OpenAI
        messages = [{"role": "system", "content": self.agent.instruction}]
        for msg in session.history:
            role = "assistant" if msg.role == "model" else msg.role
            text = "".join(p.text for p in msg.parts if p.text)
            messages.append({"role": role, "content": text})

        user_text = "".join(p.text for p in new_message.parts if p.text)
        messages.append({"role": "user", "content": user_text})

        # Call OpenAI
        completion = await self._client.chat.completions.create(
            model=self.agent.model,
            messages=messages,
        )
        response_text = completion.choices[0].message.content or ""

        llm_response = AgentEvent(
            content=Content(role="model", parts=[Part.from_text(response_text)])
        )

        # --- Output guardrail plugins ---
        for plugin in self.plugins:
            llm_response = await plugin.after_model_callback(
                callback_context=None, llm_response=llm_response
            )

        # Save to history
        session.history.append(new_message)
        session.history.append(llm_response.content)

        yield llm_response
