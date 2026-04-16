"""Audit Log Plugin — Record all interactions"""
import json
import time
from typing import Any
from datetime import datetime

from core.openai_adk import BasePlugin, Content


class AuditLogPlugin(BasePlugin):
    """Log all interactions for security audit.
    
    Note: Only logs requests that reach the LLM (not blocked by input guardrails).
    For complete logging including blocked requests, place this plugin first.
    """

    def __init__(self):
        super().__init__(name="audit_log")
        self.logs = []
        self._pending = {}  # Track pending requests by session

    def _extract_text(self, content: Content) -> str:
        if not content or not content.parts:
            return ""
        return "".join(
            p.text for p in content.parts if hasattr(p, "text") and p.text
        )

    async def on_user_message_callback(
        self, *, invocation_context: Any, user_message: Content
    ) -> Content | None:
        # Create unique ID for this request
        request_id = id(user_message)
        
        # Store pending request
        self._pending[request_id] = {
            "timestamp": datetime.now().isoformat(),
            "user_id": (
                getattr(invocation_context, "user_id", "anonymous")
                if invocation_context
                else "anonymous"
            ),
            "input": self._extract_text(user_message),
            "start_time": time.time(),
            "blocked_by": None,
            "output": None,
            "latency_ms": 0,
        }
        return None

    async def after_model_callback(self, *, callback_context: Any, llm_response):
        # Find the most recent pending request and complete it
        if self._pending:
            # Get the last added request
            request_id = list(self._pending.keys())[-1]
            log_entry = self._pending.pop(request_id)
            
            log_entry["output"] = self._extract_text(llm_response.content)
            log_entry["latency_ms"] = int(
                (time.time() - log_entry["start_time"]) * 1000
            )
            del log_entry["start_time"]
            
            self.logs.append(log_entry)
        
        return llm_response
        return llm_response

    def export_json(self, filepath="audit_log.json"):
        """Export logs to JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.logs, f, indent=2, ensure_ascii=False)
        print(f"Audit log exported to {filepath} ({len(self.logs)} entries)")

    def get_stats(self):
        """Get summary statistics."""
        total = len(self.logs)
        blocked = sum(1 for log in self.logs if log.get("blocked_by"))
        avg_latency = (
            sum(log.get("latency_ms", 0) for log in self.logs) / total if total else 0
        )
        return {
            "total_requests": total,
            "blocked_requests": blocked,
            "block_rate": blocked / total if total else 0,
            "avg_latency_ms": avg_latency,
        }
