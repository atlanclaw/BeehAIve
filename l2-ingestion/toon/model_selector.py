"""
L2-06 ModelSelector — Modellwahl-Agent.
Konsumiert ToonResult aus L2-05, validiert gegen AVAILABLE_MODELS,
schreibt WAL-Eintrag, gibt ModelOption + PromptDraft zurück.

Hard Constraint:
  - Kein LLM-Call in diesem Modul
  - Kein Qdrant-Zugriff
  - WAL-Write ist die einzige Seiteneffekt-Operation

Pflicht-Env (mit Defaults):
  AVAILABLE_MODELS    = "llama3.1:8b,qwen2.5:32b"
  DEFAULT_MODEL       = "llama3.1:8b"
  DEFAULT_MODEL_NAME  = "Llama 3.1 8B (lokal)"
  PKB_ROOT            = "/srv/pkb"
"""
import logging
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from .models import ToonResult

log = logging.getLogger("pkb.l2.model_selector")

PKB_ROOT = Path(os.getenv("PKB_ROOT", "/srv/pkb"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.1:8b")
DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "Llama 3.1 8B (lokal)")
AVAILABLE_MODELS: set[str] = {
    m.strip()
    for m in os.getenv("AVAILABLE_MODELS", "llama3.1:8b,qwen2.5:32b").split(",")
    if m.strip()
}


@dataclass
class ModelOption:
    model_id: str
    model_display_name: str
    is_local: bool
    toon_confidence: float
    selection_reason: str
    is_fallback: bool
    is_available: bool
    alternatives: list[str] = field(default_factory=list)


@dataclass
class PromptDraft:
    text: str
    original_text: str
    was_refined: bool
    tokens_estimate: int
    request_id: str = ""


class ModelSelector:
    def select(
        self,
        toon_result: ToonResult,
        request_id: str = "",
    ) -> tuple[ModelOption, PromptDraft]:
        model_id = toon_result.model_id
        is_available = model_id in AVAILABLE_MODELS

        if not is_available:
            log.warning("TOON empfiehlt %s — nicht in AVAILABLE_MODELS. Fallback auf %s", model_id, DEFAULT_MODEL)
            model_id = DEFAULT_MODEL
            selection_reason = "fallback_unavailable"
        elif toon_result.is_fallback:
            selection_reason = "fallback_default"
        else:
            selection_reason = "toon_recommendation"

        option = ModelOption(
            model_id=model_id,
            model_display_name=(toon_result.model_display_name if is_available else DEFAULT_MODEL_NAME),
            is_local=toon_result.is_local,
            toon_confidence=toon_result.toon_confidence,
            selection_reason=selection_reason,
            is_fallback=toon_result.is_fallback or not is_available,
            is_available=is_available,
            alternatives=[a.model_id for a in toon_result.alternative_models if a.model_id in AVAILABLE_MODELS],
        )

        effective_prompt = (
            toon_result.refined_prompt
            if toon_result.prompt_refined and toon_result.refined_prompt
            else toon_result.original_prompt
        )
        prompt_draft = PromptDraft(
            text=effective_prompt,
            original_text=toon_result.original_prompt,
            was_refined=toon_result.prompt_refined,
            tokens_estimate=max(1, len(effective_prompt) // 4),
            request_id=request_id,
        )

        try:
            from pkb.wal import append_wal
            append_wal(
                pkb_root=str(PKB_ROOT),
                event_type="model_selected",
                summary=(
                    f"{model_id} gewählt "
                    f"({'TOON-Empfehlung' if selection_reason == 'toon_recommendation' else 'Fallback'}, "
                    f"conf={toon_result.toon_confidence:.2f})"
                ),
                ticket_id="BASE-L2-06",
                metadata={
                    "model_id":               model_id,
                    "is_local":               option.is_local,
                    "toon_confidence":         toon_result.toon_confidence,
                    "is_fallback":             option.is_fallback,
                    "selection_reason":        selection_reason,
                    "prompt_draft_tokens_est": prompt_draft.tokens_estimate,
                    "request_id":              request_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("WAL-Write fehlgeschlagen (non-blocking): %s", exc)

        log.info("ModelSelector: %s ausgewählt (%s, conf=%.2f, tokens_est=%d)",
                 model_id, selection_reason, toon_result.toon_confidence, prompt_draft.tokens_estimate)
        return option, prompt_draft


model_selector = ModelSelector()
