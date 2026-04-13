"""
HTTP-Adapter für den TOON-Service.
TOON läuft als eigenständiger Docker-Container (pkb-toon).
Fallback: Standard-Modell wenn TOON nicht erreichbar.
"""
import os
import logging
import httpx
from .models import ToonRequest, ToonResult, AlternativeModel

log = logging.getLogger("pkb.l2.toon")

TOON_URL          = os.getenv("TOON_URL", "http://pkb-toon:8080")
TOON_TIMEOUT_S    = float(os.getenv("TOON_TIMEOUT_S", "5.0"))
DEFAULT_MODEL     = os.getenv("TOON_DEFAULT_MODEL", "llama3.1:8b")
DEFAULT_MODEL_NAME = os.getenv("TOON_DEFAULT_MODEL_NAME", "Llama 3.1 8B (lokal)")


def _fallback_result(request: ToonRequest, reason: str) -> ToonResult:
    return ToonResult(
        model_id=DEFAULT_MODEL,
        model_display_name=DEFAULT_MODEL_NAME,
        is_local=True,
        toon_confidence=0.0,
        reasoning=f"Standard (TOON nicht verfügbar: {reason})",
        original_prompt=request.prompt,
        refined_prompt=request.prompt,
        prompt_refined=False,
        is_fallback=True,
    )


async def analyze(request: ToonRequest) -> ToonResult:
    try:
        async with httpx.AsyncClient(timeout=TOON_TIMEOUT_S) as client:
            resp = await client.post(
                f"{TOON_URL}/analyze",
                json={
                    "prompt":           request.prompt,
                    "context_hint":     request.context_hint,
                    "request_id":       request.request_id,
                    "available_models": request.available_models,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return ToonResult(
            model_id=data["model_id"],
            model_display_name=data.get("model_display_name", data["model_id"]),
            is_local=data.get("is_local", True),
            toon_confidence=float(data.get("confidence", 0.8)),
            reasoning=data.get("reasoning", ""),
            alternative_models=[
                AlternativeModel(m["model_id"], m.get("reason", ""))
                for m in data.get("alternatives", [])
            ],
            original_prompt=request.prompt,
            refined_prompt=data.get("refined_prompt", request.prompt),
            prompt_refined=bool(data.get("refined_prompt")),
            is_fallback=False,
        )

    except httpx.TimeoutException:
        log.warning("TOON timeout nach %.1fs — Fallback", TOON_TIMEOUT_S)
        return _fallback_result(request, "timeout")
    except httpx.HTTPStatusError as e:
        log.warning("TOON HTTP %d — Fallback", e.response.status_code)
        return _fallback_result(request, f"HTTP {e.response.status_code}")
    except Exception as e:
        log.warning("TOON unavailable: %s — Fallback", e)
        return _fallback_result(request, str(e))
