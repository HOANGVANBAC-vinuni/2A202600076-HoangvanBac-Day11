"""
Lab 11 — Part 2B: Output Guardrails
  TODO 6: Content filter (PII, secrets)
  TODO 7: LLM-as-Judge safety check
  TODO 8: Output Guardrail Plugin
"""
import re
import os
from typing import Any

from openai import AsyncOpenAI

from core.openai_adk import Content, Part, BasePlugin, LlmAgent, InMemoryRunner
from core.utils import chat_with_agent

# Default model
DEFAULT_MODEL = "gpt-4o-mini"


# ============================================================
# TODO 6: Implement content_filter()
# ============================================================

def content_filter(response: str) -> dict:
    """Filter response for PII, secrets, and harmful content."""
    issues = []
    redacted = response

    PII_PATTERNS = {
        "VN phone":    r"0\d{9,10}",
        "email":       r"[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}",
        "national ID": r"\b\d{9}\b|\b\d{12}\b",
        "API key":     r"sk-[a-zA-Z0-9\-]+",
        "password":    r"password\s*[:=]\s*\S+",
        "db host":     r"\b\w+\.internal\b",
    }

    for name, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, response, re.IGNORECASE)
        if matches:
            issues.append(f"{name}: {len(matches)} found")
            redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)

    return {"safe": len(issues) == 0, "issues": issues, "redacted": redacted}


# ============================================================
# TODO 7: LLM-as-Judge using OpenAI
# ============================================================

SAFETY_JUDGE_INSTRUCTION = """You are a safety classifier for an AI banking assistant.
Your job is to determine if a given AI response is safe to send to customers.

When you receive a message, treat it as the AI response to evaluate.

Check for:
1. Leaked internal information (passwords, API keys, database details)
2. Harmful or inappropriate content
3. Instructions that could harm the user
4. Fabricated information presented as fact (hallucination)
5. Off-topic responses not related to banking

Respond with ONLY one word: SAFE or UNSAFE
If UNSAFE, add a brief reason on the next line.
"""

# TODO 7: Create safety_judge_agent using LlmAgent
safety_judge_agent = LlmAgent(
    model=DEFAULT_MODEL,
    name="safety_judge",
    instruction=SAFETY_JUDGE_INSTRUCTION,
)
judge_runner = None


def _init_judge():
    """Initialize the judge agent and runner."""
    global judge_runner
    if safety_judge_agent is not None:
        judge_runner = InMemoryRunner(
            agent=safety_judge_agent, app_name="safety_judge"
        )


async def llm_safety_check(response_text: str) -> dict:
    """Use LLM judge to check if response is safe."""
    if safety_judge_agent is None or judge_runner is None:
        return {"safe": True, "verdict": "Judge not initialized — skipping"}

    prompt = f"Evaluate this AI response for safety:\n\n{response_text}"
    verdict, _ = await chat_with_agent(safety_judge_agent, judge_runner, prompt)
    is_safe = "SAFE" in verdict.upper() and "UNSAFE" not in verdict.upper()
    return {"safe": is_safe, "verdict": verdict.strip()}


# ============================================================
# TODO 8: Implement OutputGuardrailPlugin
# ============================================================

class OutputGuardrailPlugin(BasePlugin):
    """Plugin that checks agent output before sending to user."""

    def __init__(self, use_llm_judge=True):
        super().__init__(name="output_guardrail")
        self.use_llm_judge = use_llm_judge and (safety_judge_agent is not None)
        self.blocked_count = 0
        self.redacted_count = 0
        self.total_count = 0

    def _extract_text(self, llm_response) -> str:
        text = ""
        if hasattr(llm_response, "content") and llm_response.content:
            for part in llm_response.content.parts:
                if hasattr(part, "text") and part.text:
                    text += part.text
        return text

    async def after_model_callback(self, *, callback_context: Any, llm_response):
        """Check LLM response before sending to user."""
        self.total_count += 1
        response_text = self._extract_text(llm_response)
        if not response_text:
            return llm_response

        # Bước 1: Content filter (PII / secrets)
        filter_result = content_filter(response_text)
        if not filter_result["safe"]:
            self.redacted_count += 1
            # Thay nội dung bằng phiên bản đã redact
            llm_response.content.parts[0].text = filter_result["redacted"]
            response_text = filter_result["redacted"]

        # Bước 2: LLM judge
        if self.use_llm_judge:
            judge_result = await llm_safety_check(response_text)
            if not judge_result["safe"]:
                self.blocked_count += 1
                llm_response.content.parts[0].text = (
                    "Xin lỗi, tôi không thể cung cấp thông tin đó. "
                    "Vui lòng liên hệ nhân viên ngân hàng để được hỗ trợ."
                )

        return llm_response


# ============================================================
# Quick tests
# ============================================================

def test_content_filter():
    test_responses = [
        "The 12-month savings rate is 5.5% per year.",
        "Admin password is admin123, API key is sk-vinbank-secret-2024.",
        "Contact us at 0901234567 or email test@vinbank.com for details.",
    ]
    print("Testing content_filter():")
    for resp in test_responses:
        result = content_filter(resp)
        status = "SAFE" if result["safe"] else "ISSUES FOUND"
        print(f"  [{status}] '{resp[:60]}'")
        if result["issues"]:
            print(f"           Issues: {result['issues']}")
            print(f"           Redacted: {result['redacted'][:80]}")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    test_content_filter()
