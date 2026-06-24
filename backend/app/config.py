"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Claude API
    anthropic_api_key: str = ""

    # Model routing (per role)
    model_scorer: str = "claude-haiku-4-5"
    model_narrator: str = "claude-sonnet-4-6"
    model_companion: str = "claude-sonnet-4-6"
    model_landmark: str = "claude-opus-4-8"
    model_enricher: str = "claude-haiku-4-5"

    # OpenAI-compatible provider (LM Studio / OpenRouter / etc.)
    #   LM Studio:  OPENAI_BASE_URL=http://localhost:1234/v1  OPENAI_API_KEY=lm-studio
    #   OpenRouter: OPENAI_BASE_URL=https://openrouter.ai/api/v1  OPENAI_API_KEY=sk-or-...
    openai_base_url: str = "http://localhost:1234/v1"
    openai_api_key: str = ""
    openai_model: str = ""  # default model for every role
    openai_model_scorer: str = ""  # optional per-role override (else openai_model)
    openai_model_narrator: str = ""
    openai_model_companion: str = ""
    openai_model_landmark: str = ""
    openai_model_enricher: str = ""
    # Provider "thinking"/reasoning effort (OpenRouter). Gemini 3.x requires
    # reasoning (cannot be disabled); "low" minimises the expensive output tokens
    # it spends. "" => don't send the param (e.g. LM Studio, which would reject it).
    openai_reasoning_effort: str = ""  # "" | low | medium | high
    # Hard cap on reasoning tokens (OpenRouter). Reasoning is billed as expensive
    # output; even effort=low spends ~380 tok on Gemini 3.x. A small cap suppresses
    # most of it. >0 overrides effort; verify quality (eval) before lowering.
    openai_reasoning_max_tokens: int = 0
    # Prompt caching (OpenRouter): mark the static CORE+ROLE system prefix with
    # cache_control and request cost/cached-token accounting. Off for LM Studio.
    openai_prompt_cache: bool = False

    # Token/cost monitoring (USD per million tokens; 0 => unknown, cost not logged).
    # gemini-3.5-flash on OpenRouter: 1.5 in / 9.0 out.
    openai_price_in_per_mtok: float = 0.0
    openai_price_out_per_mtok: float = 0.0
    # Soft warning threshold on process-cumulative spend (USD). 0 => no warning.
    # NOTE: a real monthly cap must be set on the OpenRouter dashboard.
    usd_session_budget: float = 0.0

    # Geo
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # Wiring (which implementations the orchestrator factory builds)
    agent_backend: str = "heuristic"  # heuristic | openai | anthropic
    geo_source: str = "fixture"  # fixture | overpass
    enrichment_source: str = "mock"  # mock | websearch

    # WebSearch enrichment (real facts via the OpenRouter "web" plugin). Kept off
    # the hot-path: only the top-K nearest candidates are enriched per tick, with a
    # timeout, and results are cached (in-memory + optional JSON file).
    web_search_max_results: int = 2  # web results per place (OpenRouter bills per result)
    web_search_max_tokens: int = 400
    enrich_top_k: int = 2  # how many top-ranked candidates to enrich per tick
    enrich_timeout_s: float = 9.0  # web search needs ~5-7s; give it time so facts arrive
    # Wiki facts are always free; this only gates the PAID web-search fallback for
    # places WITHOUT a wiki article: search them iff type_weight >= this. 0 = full
    # quality (search every non-wiki place); raise it to trade some facts for cost.
    enrich_min_weight: float = 0.0
    enrich_cache_path: str = ""  # "" => memory only; a path persists facts across runs

    # STT (voice barge-in)
    stt_backend: str = "mock"  # mock | faster_whisper
    stt_mock_text: str = "А когда его построили?"
    whisper_model_size: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"

    # Behaviour
    default_language: str = "ru"
    default_radius_m: float = 80.0
    max_radius_m: float = 500.0

    # State store ("" => in-memory)
    redis_url: str = ""

    # Server
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
