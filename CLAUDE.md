# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is at the **planning stage**. The only artifact is `BUSINESS_LOGICS.pdf`
(Russian) — the business-logic specification for an AI Audio Guide. There is no source
code, build system, or test suite yet. When implementation begins, update this file with
the actual build/run/test commands and the chosen stack/layout.

## What is being built

An autonomous, real-time **audio guide for everyday walks**. The app continuously tracks
the user's GPS position and gaze/heading and narrates the surrounding places aloud, with
no user interaction required — the user just opens the app and walks.

## Agent pipeline (core domain logic)

The runtime is a continuous loop. Understanding this sequence is essential before touching
any of it:

1. **Find objects (1.1)** — pull places within radius N from the map. Weight by type
   (museum/park/shop) and boost objects that are closer and inside the user's gaze cone.
2. **Persist + resolve address (1.2)** — store found objects (also used to track what's
   already been seen) and resolve the user's current country/city/district/street.
3. **Enrich + score significance (1.3)** — LLMs know little about obscure places, so use
   **WebSearch** to gather real facts per place (a subagent may do this later). Assign a
   significance level from proximity, gaze alignment, and historical/cultural value:
   `SKIP` → `LOW` → `MEDIUM` → `HIGH` → `LANDMARK`.
4. **Generate SUMMARY + stream TTS (1.4)** — LLM writes a short SUMMARY; TTS speaks it in
   chunks. Discovery never stops: if a more relevant object appears mid-narration, generate
   a new SUMMARY and switch **seamlessly**.
5. **Adaptive radius (1.5)** — if no new objects appear and heading is unchanged, expand
   the search radius automatically so the user is never left in silence.
6. **Context dedup (1.6)** — only places the user has **not yet seen** are passed into the
   LLM context, preventing repetition.

## Invariants to preserve

These are product requirements, not suggestions — preserve them in any implementation:

- **Real-time**: minimize latency between position update and start of narration.
- **No repeats**: pass only unseen places into LLM context (see 1.6).
- **Facts only**: never fabricate; rely on WebSearch for verifiable data. If unsure, stay silent.
- **Gaze priority**: objects in the user's gaze direction get higher scoring weight.
- **Seamless switching**: when a more interesting object appears, transition narration smoothly.
- **Adaptive radius**: expand search when nothing new is nearby.
- **Narration style**: friendly and conversational; avoid clichés like "unique place" or
  "important landmark". Do not inflate ordinary places into attractions.

## Known design constraint

Gaze direction relies on the compass, which is unreliable when the phone is in a pocket.
Fallback: infer approximate gaze from movement direction — this only resolves
forward/backward, not left/right.

## Data sources / intended stack

- **Maps**: OpenStreetMap via the Overpass API (place data + coordinates).
- **Web search**: WebSearch tools for facts about lesser-known places.
- **Text generation**: OpenAI GPT.
- **Voice**: a local text-to-speech model.

## System prompt

A preliminary Russian system prompt (`SYSTEM_PROMPT_RU`, without context-optimization
logic) lives in `BUSINESS_LOGICS.pdf`. Reuse it as the basis for the narration prompt; it
already encodes the significance levels, the "facts only / no clichés" rules, and the
anti-repetition guidance.
