"""
PatrAI — Intent classifier.

Primary LLM: Ollama (llama3.1:8b, local)
Fallback LLM: OpenAI GPT-4o-mini
"""
import json
import logging
import re

import requests
import openai

import config
from models import ClassificationResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an email intent classifier. Analyze the email and respond with JSON only (no markdown).\n"
    "Classify the intent as exactly one of: scheduling_request, availability_query, status_update, other.\n"
    'Respond with this exact JSON structure:\n'
    '{"intent": "<label>", "confidence": <float 0.0-1.0>, "chain_of_thought": "<reasoning>"}'
)

VALID_INTENTS = frozenset({
    "scheduling_request",
    "availability_query",
    "status_update",
    "other",
})


def _build_prompt(body: str, subject: str, history: list[str]) -> str:
    """Build the full user prompt including conversation history and current email."""
    parts: list[str] = []

    if history:
        parts.append("Prior messages in this thread:")
        for i, msg in enumerate(history, start=1):
            parts.append(f"{i}. {msg}")
        parts.append("")

    parts.append(f"Subject: {subject}")
    parts.append(f"Body:\n{body}")

    return "\n".join(parts)


def _parse_llm_response(response_text: str) -> dict:
    """Extract JSON from LLM response text, handling markdown code blocks."""
    # Strip markdown code fences if present
    text = response_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    try:
        data = json.loads(text)
        return {
            "intent": data.get("intent", "needs_human_review"),
            "confidence": float(data.get("confidence", 0.0)),
            "chain_of_thought": data.get("chain_of_thought", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "intent": "needs_human_review",
            "confidence": 0.0,
            "chain_of_thought": "Failed to parse LLM response",
        }


def _call_ollama(prompt: str) -> str:
    """POST to Ollama /api/generate and return the response text."""
    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": "llama3.1:8b",
        "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
        "stream": False,
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["response"]


def _call_openai(prompt: str) -> str:
    """Call OpenAI GPT-4o-mini and return the response text."""
    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return completion.choices[0].message.content


def classify(
    body: str,
    subject: str,
    history: list[str] = [],
) -> ClassificationResult:
    """Classify email intent using Ollama (primary) with OpenAI fallback."""
    prompt = _build_prompt(body, subject, history)

    response_text: str | None = None

    try:
        response_text = _call_ollama(prompt)
    except Exception as exc:
        logger.warning("Ollama call failed, falling back to OpenAI: %s", exc)
        try:
            response_text = _call_openai(prompt)
        except Exception as exc2:
            logger.warning("OpenAI fallback also failed: %s", exc2)
            return ClassificationResult(
                intent="needs_human_review",
                confidence=0.0,
                chain_of_thought="Both LLMs failed",
            )

    parsed = _parse_llm_response(response_text)

    confidence = parsed["confidence"]
    intent = parsed["intent"]

    if confidence < 0.6:
        intent = "needs_human_review"

    return ClassificationResult(
        intent=intent,
        confidence=confidence,
        chain_of_thought=parsed["chain_of_thought"],
    )
