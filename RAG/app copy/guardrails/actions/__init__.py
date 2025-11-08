"""Custom NeMo Guardrails actions for topic gating."""

from .actions import load_topic_examples  # re-export for tests

__all__ = ["load_topic_examples"]
