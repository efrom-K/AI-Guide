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
    # Reverse geocoding (city/district/street for the "general -> specific" monologue).
    #   overpass -> derive admin areas + street from the Overpass endpoint above
    #   none     -> no geocoding (guide won't name the area)
    geocoder_source: str = "overpass"  # overpass | none
    geocoder_min_move_m: float = 150.0  # only re-resolve the address after moving this far

    # Area-level monologue (the spine that fills gaps between objects)
    area_enrich: bool = True  # fetch verified facts about the district/city (web search)
    area_max_beats: int = 4  # area beats per area before easing off (objects reset this)

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
    # Start the search at a medium radius so ONE Overpass query covers both dense
    # city centres and spread-out suburbs (where the nearest object is 150-300 m
    # away). Starting tiny (80 m) forced a slow expand-to-500 m chain in suburbs
    # that blew the tick deadline → "talks about the district but never any object".
    default_radius_m: float = 300.0
    max_radius_m: float = 500.0
    # An object is narrated as "right here" if it's within this radius. 300 m is a
    # few minutes' walk — fine for "ahead of you is …" — and it matches the default
    # search radius so suburban objects actually get narrated, not just found. (A
    # sparse-area fallback in the orchestrator still narrates the nearest object even
    # beyond this, so the guide never goes silent when there IS something around.)
    weave_radius_m: float = 300.0
    # Cap how many (nearest) candidates are considered per tick — bounds the
    # Scorer's input/output size (its JSON grows linearly with candidate count).
    scorer_max_candidates: int = 6

    # State store ("" => in-memory)
    redis_url: str = ""
    session_ttl_s: float = 3600.0  # evict idle in-memory sessions after this (0 => never)
    max_sessions: int = 2000  # hard LRU cap on in-memory sessions (0 => unbounded)

    # --- Security & limits (protect the public /ws and cap spend) ---------------
    # Shared access token for /ws. "" => open (dev/local). In prod set it and the
    # client must connect with ?token=<value> (baked into the built clients).
    ws_token: str = ""
    max_connections_per_ip: int = 8  # concurrent WS connections per client IP (0 => off)
    # Hard spend ceiling (USD) on cumulative process spend; 0 => off. Once reached,
    # LLM calls are blocked (the guide degrades to silence) instead of burning money.
    usd_hard_cap: float = 0.0
    max_utterance_chars: int = 2000  # reject longer text/voice questions
    max_audio_b64_chars: int = 8_000_000  # ~6 MB decoded clip ceiling (anti-DoS)
    stats_token: str = ""  # admin token for /stats; "" => endpoint disabled

    # Server
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()
