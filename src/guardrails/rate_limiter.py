"""Rate Limiter Plugin — Prevent abuse"""
import time
from collections import defaultdict, deque
from typing import Any

from core.openai_adk import BasePlugin, Content, Part


class RateLimitPlugin(BasePlugin):
    """Rate limiter using sliding window per user."""

    def __init__(self, max_requests=10, window_seconds=60):
        super().__init__(name="rate_limiter")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.user_windows = defaultdict(deque)  # user_id -> deque of timestamps
        self.blocked_count = 0
        self.total_count = 0

    async def on_user_message_callback(
        self, *, invocation_context: Any, user_message: Content
    ) -> Content | None:
        self.total_count += 1
        user_id = (
            getattr(invocation_context, "user_id", "anonymous")
            if invocation_context
            else "anonymous"
        )
        now = time.time()
        window = self.user_windows[user_id]

        # Remove expired timestamps
        while window and window[0] < now - self.window_seconds:
            window.popleft()

        # Check rate limit
        if len(window) >= self.max_requests:
            self.blocked_count += 1
            oldest = window[0]
            wait_time = int(self.window_seconds - (now - oldest)) + 1
            return Content(
                role="model",
                parts=[
                    Part.from_text(
                        f"Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau {wait_time} giây."
                    )
                ],
            )

        # Allow request
        window.append(now)
        return None
