"""
Loads operator-tunable signal configuration from config/signal_config.yaml
and environment variables. All engines import from here — never from the YAML directly.
"""
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "signal_config.yaml"

with open(_CONFIG_PATH) as _f:
    _cfg = yaml.safe_load(_f)

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./gtm_engine.db")

# ── Scoring ───────────────────────────────────────────────────────────────────
SIGNAL_BASE_SCORES: dict[str, float] = _cfg["scoring"]["base_scores"]
ICP_MULTIPLIERS: dict[int, float] = {
    int(k): float(v) for k, v in _cfg["scoring"]["icp_multipliers"].items()
}
DEFAULT_BASE_SCORE: float = float(_cfg["scoring"]["default_base_score"])

# ── Decay ─────────────────────────────────────────────────────────────────────
SIGNAL_DECAY_DAYS: dict[str, int] = _cfg["decay"]["shelf_life_days"]
DEFAULT_DECAY_DAYS: int = int(_cfg["decay"]["default_shelf_life_days"])

# ── Persona Routing ───────────────────────────────────────────────────────────
PERSONA_ROUTING_MATRIX: dict[str, list[str]] = _cfg["persona_routing"]["matrix"]
EXEC_HIRE_KEYWORD_MAP: dict[str, str] = _cfg["persona_routing"]["exec_hire_keyword_map"]

# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_CACHE_TTL_DAYS: int = int(
    os.getenv("LLM_CACHE_TTL_DAYS", str(_cfg["llm"]["cache_ttl_days"]))
)
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
PROMPTS_PATH: Path = Path(__file__).parent.parent / "config" / "prompts.yaml"

# ── Suppression ───────────────────────────────────────────────────────────────
# Signals are blocked for accounts with any of these statuses.
SUPPRESSED_STATUSES: set[str] = {"customer", "open_opp", "dnc"}
