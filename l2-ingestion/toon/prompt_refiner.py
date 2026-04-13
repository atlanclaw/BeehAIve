"""
Prompt-Refining-Adapter für L2-05.
Wird von:
  1. Gateway-Flow: analyze() → ToonResult.refined_prompt an L3
  2. AutoEvolution TOON_PROMPT_REFINE Tick (ATL-83): batch_refine_prompts()
"""
import logging
from pathlib import Path
from .toon_client import analyze
from .models import ToonRequest

log = logging.getLogger("pkb.l2.toon.refiner")


async def refine_for_gateway(
    prompt: str,
    context_hint: str = "",
    request_id: str = "",
) -> "ToonResult":
    request = ToonRequest(
        prompt=prompt,
        context_hint=context_hint,
        request_id=request_id,
    )
    return await analyze(request)


async def batch_refine_prompts(wal_insights_path: Path | None = None) -> dict:
    """
    AutoEvolution TOON_PROMPT_REFINE Tick (ATL-83).
    Stats: {prompts_analyzed, prompts_refined, errors}
    """
    import datetime
    stats = {"prompts_analyzed": 0, "prompts_refined": 0, "errors": 0}

    if wal_insights_path and wal_insights_path.exists():
        content = wal_insights_path.read_text(encoding="utf-8")
        request = ToonRequest(
            prompt=f"Analysiere folgende WAL-Insights und schlage Prompt-Verbesserungen vor:\n\n{content}",
            context_hint="prompt_refinement",
        )
        try:
            result = await analyze(request)
            stats["prompts_analyzed"] += 1
            if result.prompt_refined:
                stats["prompts_refined"] += 1
                date = datetime.date.today().isoformat()
                out_path = Path(f"/srv/pkb/memory/topics/prompt-refinements-{date}.md")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    f"# Prompt-Refinements {date}\n\n{result.refined_prompt}\n",
                    encoding="utf-8",
                )
                log.info("prompt-refinements geschrieben: %s", out_path)
        except Exception as e:
            log.error("batch_refine_prompts Fehler: %s", e)
            stats["errors"] += 1

    return stats
