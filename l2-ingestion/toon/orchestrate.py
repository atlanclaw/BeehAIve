"""
OrchestrateRequest Builder für L2-05.
Baut den vollständigen OrchestrateRequest mit toon_result eingebettet.
ATL-64: toon_result wird 1:1 an L3/BeeAI weitergegeben (Pass-Through).
"""
from dataclasses import dataclass, field
from typing import Optional
from .models import ToonResult


@dataclass
class OrchestrateRequest:
    prompt: str
    request_id: str
    context_hint: str = ""
    channel: str = ""
    user_id: str = ""
    toon_result: Optional[ToonResult] = None

    def effective_prompt(self) -> str:
        if self.toon_result and self.toon_result.prompt_refined:
            return self.toon_result.refined_prompt
        return self.prompt

    def to_beeai_payload(self) -> dict:
        payload = {
            "prompt":       self.effective_prompt(),
            "request_id":   self.request_id,
            "context_hint": self.context_hint,
            "channel":      self.channel,
            "user_id":      self.user_id,
        }
        if self.toon_result:
            payload["model_recommendation"] = self.toon_result.to_model_recommendation()
            payload["preferred_model"]      = self.toon_result.model_id
        return payload


def build_orchestrate_request(
    raw_prompt: str,
    toon_result: ToonResult,
    request_id: str,
    context_hint: str = "",
    channel: str = "",
    user_id: str = "",
) -> OrchestrateRequest:
    return OrchestrateRequest(
        prompt=raw_prompt,
        request_id=request_id,
        context_hint=context_hint,
        channel=channel,
        user_id=user_id,
        toon_result=toon_result,
    )
