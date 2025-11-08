from __future__ import annotations

import asyncio
import csv
import json
import logging
import random
import re
import textwrap
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

from nemoguardrails.actions import action
from openai import OpenAI

from app.core.config import get_settings

_CLIENT = OpenAI()

BUSINESS_KEYWORDS = {
    "order",
    "shipping",
    "delivery",
    "refund",
    "return",
    "warranty",
    "account",
    "subscription",
    "billing",
    "product",
    "support",
    "policy",
    "price",
    "exchange",
    "gift card",
    "store credit",
    "delivery",
    "address",
    "cart",
    "checkout",
    "coupon",
    "track",
    "invoice",
    "charge",
    "payment",
    "contact",
}

OFF_TOPIC_KEYWORDS = {
    "weather",
    "temperature",
    "forecast",
    "president",
    "government",
    "politics",
    "election",
    "stock",
    "sports",
    "game",
    "movie",
    "music",
    "recipe",
    "bitcoin",
    "crypto",
    "science",
    "history",
    "news",
    "celebrity",
}


@lru_cache(maxsize=1)
def load_topic_examples(
    dataset_path: Path,
    sample_size: int,
) -> Tuple[List[str], List[str]]:
    """Return sampled on-topic and off-topic examples from the CSV dataset."""
    if not dataset_path.exists():
        return (["How do I track my order?"], ["Who won the football game last night?"])

    on_topic: List[str] = []
    off_topic: List[str] = []

    with dataset_path.open("r", encoding="utf-8", newline="") as handle:
        reader = list(csv.DictReader(handle))

    random.seed(13)  # deterministic selection
    random.shuffle(reader)

    for row in reader:
        query = (row.get("query") or "").strip()
        label = (row.get("label") or "").strip().lower()
        if not query:
            continue

        tone = (row.get("tone") or "").strip().lower()
        try:
            flags = json.loads(row.get("flags") or "[]")
        except json.JSONDecodeError:
            flags = []
        if tone == "adversarial" or "adversarial" in flags:
            continue

        normalized = re.sub(r"\{[^}]+\}", "our product", query)
        normalized = " ".join(normalized.split())
        if '"' in normalized:
            normalized = normalized.replace('"', "'")

        if label == "on_topic" and len(on_topic) < sample_size:
            on_topic.append(normalized)
        elif label != "on_topic" and len(off_topic) < sample_size:
            off_topic.append(normalized)

        if len(on_topic) >= sample_size and len(off_topic) >= sample_size:
            break

    if not on_topic:
        on_topic.append("How do I track my order?")
    if not off_topic:
        off_topic.append("Who won the football game last night?")

    return on_topic, off_topic


def _build_prompt(question: str, positives: List[str], negatives: List[str]) -> str:
    def _format_block(examples: List[str], label: str) -> str:
        reason = (
            "This question concerns our customers or offerings."
            if label == "on_topic"
            else "This question is unrelated to our business."
        )
        lines = []
        for example in examples:
            lines.append(f"- Question: {example}")
            lines.append(f"  Label: {label}")
            lines.append(f"  Reason: {reason}")
        return "\n".join(lines)

    template = textwrap.dedent(
        """
        You are a classifier for a customer-support assistant. Decide if the user's
        question is ABOUT THE BUSINESS (products, services, pricing, policies,
        accounts, support) or OFF TOPIC.

        Respond with a compact JSON object:
        {{
          "label": "on_topic" | "off_topic",
          "reason": "<short justification>"
        }}

        Use the examples below as guidance.

        Example positives (on_topic):
        {positive_block}

        Example negatives (off_topic):
        {negative_block}

        Now classify the next question.
        Question: {question}
        JSON:
        """
    ).strip()

    return template.format(
        positive_block=_format_block(positives, "on_topic"),
        negative_block=_format_block(negatives, "off_topic"),
        question=question.replace('"', "'"),
    )


def _normalize_label(raw_text: str) -> str:
    cleaned_text = raw_text.strip()

    json_candidate = None
    if cleaned_text.startswith("```"):
        match = re.search(r"\{.*\}", cleaned_text, flags=re.DOTALL)
        if match:
            json_candidate = match.group(0)
    else:
        json_candidate = cleaned_text

    if json_candidate:
        try:
            data = json.loads(json_candidate)
            label = str(data.get("label", "")).strip().lower()
            if label in {"on_topic", "off_topic"}:
                return label
        except json.JSONDecodeError:
            pass

    lowered = cleaned_text.lower()
    if "off_topic" in lowered:
        return "off_topic"
    if "on_topic" in lowered or "allow" in lowered or "business" in lowered:
        return "on_topic"
    return "off_topic"


@action()
async def classify_topic(user_message: str) -> dict:
    """LLM-backed classifier used by NeMo Guardrails input rail."""
    settings = get_settings()

    message_lower = user_message.lower()
    if any(keyword in message_lower for keyword in OFF_TOPIC_KEYWORDS):
        return {"label": "off_topic", "raw": "rule_based_block"}

    positives, negatives = load_topic_examples(
        Path(settings.guardrails_dataset_path),
        settings.guardrails_examples_per_label,
    )

    prompt = _build_prompt(user_message, positives, negatives)

    def _call_openai() -> str:
        response = _CLIENT.responses.create(
            model=settings.guardrails_model,
            input=prompt,
            temperature=0,
            max_output_tokens=150,
        )
        return response.output_text.strip()

    try:
        output_text = await asyncio.to_thread(_call_openai)
    except Exception as exc:  # pragma: no cover - network failures
        logging.getLogger(__name__).warning(
            "Failed to classify topic via OpenAI: %s", exc
        )
        return {"label": "on_topic", "error": str(exc)}

    label = _normalize_label(output_text)

    if label == "off_topic":
        if any(keyword in message_lower for keyword in OFF_TOPIC_KEYWORDS):
            return {"label": "off_topic", "raw": output_text}
        if any(keyword in message_lower for keyword in BUSINESS_KEYWORDS):
            label = "on_topic"

    return {"label": label, "raw": output_text}
