# l2-ingestion/toon/models.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class AlternativeModel:
    model_id: str
    reason: str

@dataclass
class ToonResult:
    """
    Output von TOON für eine eingehende Anfrage.
    Wird 1:1 in OrchestrateRequest.toon_result eingebettet
    und via L3 in channelresponse.model_recommendation propagiert (ATL-64).
    """
    model_id: str
    model_display_name: str
    is_local: bool
    toon_confidence: float
    reasoning: str
    alternative_models: list[AlternativeModel] = field(default_factory=list)

    original_prompt: str = ""
    refined_prompt: str = ""
    prompt_refined: bool = False

    is_fallback: bool = False

    def to_model_recommendation(self) -> dict:
        """Serialisiert zu ATL-64 model_recommendation Schema."""
        return {
            "model_id":           self.model_id,
            "model_display_name": self.model_display_name,
            "reasoning":          self.reasoning,
            "is_local":           self.is_local,
            "toon_confidence":    self.toon_confidence,
            "alternative_models": [
                {"model_id": a.model_id, "reason": a.reason}
                for a in self.alternative_models
            ],
        }


@dataclass
class ToonRequest:
    prompt: str
    context_hint: str = ""
    request_id: str = ""
    available_models: list[str] = field(default_factory=list)
