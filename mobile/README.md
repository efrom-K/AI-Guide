# AI Audio Guide — Flutter client

Mobile/desktop/web client for the AI Audio Guide backend. Streams position to the
backend over WebSocket, **speaks** the guide's narration aloud, shows where you are on
an **OpenStreetMap** map, lets you **ask by voice or text**, and runs in **8 languages**.

## Features
- **Multilingual** — 8 languages (English, Русский, Español, Français, Deutsch, Italiano,
  Português, 中文). The picker in the app bar switches the **UI**, the **TTS voice**, and the
  **guide's narration + speech recognition** at once; the chosen language is sent to the
  backend (`{type:"language"}`) on every (re)connect. On first launch it auto-selects the
  **system language**, falling back to English. UI strings come from `lib/l10n/*.arb` via
  Flutter `gen-l10n`.
- **Position source** — simulated Red Square walk *or* real device GPS (toggle). Heading
  comes from the GPS course; `gaze_confidence=low` (the documented compass-in-pocket fallback).
- **Spoken narration** — on-device TTS (`flutter_tts`, voice follows the selected language).
  Speaker toggle in the app bar; asking (voice or text) hushes the guide (barge-in).
- **Voice barge-in** — tap-to-talk mic (`record`): records 16 kHz WAV, sends it to the
  backend STT, the reply is spoken back.
- **Map** — OpenStreetMap via `flutter_map` (no API key): your position + bearing arrow,
  a pin for each narrated place (current one highlighted), and a **follow / free-browse**
  toggle (panning the map drops follow; the FAB re-centres).
- **UX** — coloured agent-state chip, auto-reconnect with backoff, live position/place
  footer, clear-feed button, auto-scroll.

## Platforms
- ✅ **Android** — builds an APK, runs on the `guide_emu` emulator (and real devices).
- ✅ **Web / Windows desktop** — `flutter run -d chrome` / `-d windows` (mic/GPS/audio vary
  by platform; the simulated walk always works).

## Run
1. Start the backend on `:8000` (see `../backend`, host `0.0.0.0` for devices/emulator).
2. Android emulator:
   ```bash
   flutter build apk --debug
   adb -s emulator-5554 install -r build/app/outputs/flutter-apk/app-debug.apk
   adb -s emulator-5554 reverse tcp:8000 tcp:8000          # localhost:8000 -> host
   adb -s emulator-5554 shell pm grant com.example.ai_audio_guide android.permission.RECORD_AUDIO
   ```
   Or just `flutter run -d chrome` for the web build.
3. In the app: pick a language from the 🌐 menu (defaults to your system language) →
   **Connect** → **▶ Walk** (or flip **GPS** for real positions) → the guide narrates in that
   language and the map follows you; tap the mic or type to ask.

WS URL defaults to `ws://localhost:8000/ws` (works on the emulator via `adb reverse`).
On a real phone, set `ws://<your-PC-LAN-IP>:8000/ws` (editable in the app).

## Checks
```bash
flutter analyze
flutter test          # widget smoke test
flutter build apk --debug
```

## Dependencies
`web_socket_channel` (WS), `geolocator` (GPS), `flutter_tts` (speech), `record` +
`path_provider` (mic), `flutter_map` + `latlong2` (OpenStreetMap), `flutter_localizations` +
`intl` (8-language UI via `gen-l10n`).

## Notes
- `android/gradle.properties` sets `kotlin.incremental=false` — required when the pub cache
  (`C:`) and the project (`D:`) live on different drives, otherwise the Kotlin build fails
  with "this and base files have different roots".
- Public OSM tiles are fine for the prototype but not for production load — switch to a tile
  provider or self-host before shipping.

## Next (real device)
Run on a physical phone for real GPS, the system Russian TTS voice, and the microphone
(the emulator has no real GPS/voice/mic input).
