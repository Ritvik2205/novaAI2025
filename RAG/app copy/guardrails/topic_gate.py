from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, cast

import yaml

from app.core.config import get_settings
import app.guardrails.actions.actions  # noqa: F401 - ensure actions are registered

try:  # pragma: no cover - optional dependency
    from nemoguardrails import LLMRails, RailsConfig
except Exception:  # pragma: no cover - exported for runtime use only
    LLMRails = None  # type: ignore
    RailsConfig = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - typing helper only
    from nemoguardrails import LLMRails as LLMRailsType
else:  # pragma: no cover - runtime stub
    LLMRailsType = object

logger = logging.getLogger(__name__)

ALLOW_TOKEN = "ALLOW"
DENY_TOKEN = "DENY"
TOPIC_GATE_CACHE_VERSION = 2
_CACHED_TOPIC_GATE: Optional["TopicGate"] = None
_CACHED_TOPIC_GATE_KEY: Optional[Tuple] = None


@dataclass(frozen=True)
class TopicGateResult:
    """Outcome of running the guardrail classifier."""

    allow: bool
    source: str
    detail: Optional[str] = None
    raw_response: Optional[str] = None


class TopicGate:
    """Wraps a NeMo Guardrails configuration that filters off-topic questions."""

    def __init__(
        self,
        dataset_path: Path,
        model_name: str,
        model_engine: str,
        max_examples_per_label: int,
    ) -> None:
        self.dataset_path = dataset_path
        self.model_name = model_name
        self.model_engine = model_engine
        self.max_examples_per_label = max_examples_per_label
        self._rails = self._build_rails()

    def is_available(self) -> bool:
        return self._rails is not None

    def evaluate(self, question: str) -> TopicGateResult:
        """Run the guardrail and return whether the question should be allowed."""
        if not question.strip():
            return TopicGateResult(
                allow=False,
                source="guardrails",
                detail="Empty question is not permitted.",
            )

        if self._rails is None:
            return TopicGateResult(allow=True, source="guardrails_disabled")

        try:
            response = self._rails.generate(
                messages=[{"role": "user", "content": question}]
            )
        except Exception as exc:  # pragma: no cover - network/LLM failures
            logger.warning("NeMo Guardrails failed to classify input: %s", exc)
            return TopicGateResult(
                allow=True,
                source="guardrails_error",
                detail=str(exc),
            )

        decision = _extract_text(response)
        allow = decision.upper().strip() == ALLOW_TOKEN
        detail = None if allow else "Guardrails classified the query as off-topic."
        if decision.upper().strip() not in {ALLOW_TOKEN, DENY_TOKEN}:
            # If the guardrail produces an unexpected response we fail closed.
            allow = False
            detail = f"Unexpected guardrail response: {decision!r}"

        logger.debug(
            "Guardrail verdict for '%s': allow=%s raw=%r",
            question,
            allow,
            decision,
        )

        return TopicGateResult(
            allow=allow,
            source="guardrails",
            detail=detail,
            raw_response=decision,
        )

    def _build_rails(self) -> Optional["LLMRailsType"]:
        if LLMRails is None or RailsConfig is None:
            logger.warning(
                "nemoguardrails is not installed; topic gating will use keyword fallback."
            )
            return None

        if not self.dataset_path.exists():
            logger.warning(
                "Guardrails dataset %s does not exist; classifier will fall back to defaults.",
                self.dataset_path,
            )

        yaml_config = yaml.safe_dump(
            {
                "models": [
                    {
                        "type": "main",
                        "engine": self.model_engine,
                        "model": self.model_name,
                    }
                ],
                "rails": {
                    "input": {
                        "flows": ["guard topic gate"],
                    }
                },
                "instructions": [
                    {
                        "type": "behavior",
                        "content": (
                            "You are a classifier that decides if a user question is "
                            "related to our business, its products, services, or policies. "
                            f"Reply with '{ALLOW_TOKEN}' when it is on topic and '{DENY_TOKEN}' when it is not."
                        ),
                    }
                ],
            },
            sort_keys=False,
        )

        colang_content = _build_colang()

        actions_path = (Path(__file__).resolve().parent / "actions").resolve()
        config = RailsConfig.from_content(
            colang_content=colang_content,
            yaml_content=yaml_config,
            config={
                "import_paths": [
                    str(actions_path),
                ]
            },
        )
        return cast(LLMRailsType, LLMRails(config))


def _extract_text(response: object) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        candidate = response.get("content")  # type: ignore[call-arg]
        if isinstance(candidate, str):
            return candidate
        if isinstance(candidate, dict):
            text = candidate.get("text")
            if isinstance(text, str):
                return text
    return ""


def _build_colang() -> str:
    return "\n".join(
        [
            "define bot allow topic question",
            f'  "{ALLOW_TOKEN}"',
            "",
            "define bot reject off topic question",
            f'  "{DENY_TOKEN}"',
            "",
            "define subflow guard topic gate",
            "  $classification = execute classify_topic(user_message=$user_message)",
            "  if $classification.label == \"on_topic\"",
            "    bot allow topic question",
            "    stop",
            "",
            "  bot reject off topic question",
            "  stop",
        ]
    )


def get_topic_gate() -> Optional[TopicGate]:
    """Return a singleton TopicGate configured via environment variables."""
    settings = get_settings()
    if not settings.guardrails_enabled:
        return None

    global _CACHED_TOPIC_GATE, _CACHED_TOPIC_GATE_KEY

    cache_key = (
        settings.guardrails_model,
        settings.guardrails_model_engine,
        settings.guardrails_dataset_path,
        settings.guardrails_examples_per_label,
        TOPIC_GATE_CACHE_VERSION,
    )

    if _CACHED_TOPIC_GATE is None or _CACHED_TOPIC_GATE_KEY != cache_key:
        _CACHED_TOPIC_GATE = TopicGate(
            dataset_path=Path(settings.guardrails_dataset_path),
            model_name=settings.guardrails_model,
            model_engine=settings.guardrails_model_engine,
            max_examples_per_label=settings.guardrails_examples_per_label,
        )
        _CACHED_TOPIC_GATE_KEY = cache_key

    return _CACHED_TOPIC_GATE


def reset_topic_gate_cache() -> None:
    """Clear the cached guardrail so the next call rebuilds it."""
    global _CACHED_TOPIC_GATE, _CACHED_TOPIC_GATE_KEY
    _CACHED_TOPIC_GATE = None
    _CACHED_TOPIC_GATE_KEY = None
