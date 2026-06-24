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
- **Map-first dark UI** — the map fills the screen (CARTO dark tiles via `flutter_map`, no
  API key) with your bearing arrow and a pin per narrated place (current = amber, past = grey).
  A glassy bottom card shows the agent status (pulsing dot), the current place + narration,
  and **one primary action** that connects-and-walks / stops. Floating top pills: 🎧 brand,
  language, speaker, settings.
- **Tappable pins** — tap any place pin to open a sheet with its name and full story
  (follow-up narrations about the same place accumulate).
- **Smooth camera** — animated (eased) follow + recenter instead of snapping; a **compass**
  FAB (shown when the map is rotated) orients back to north; the camera keeps your **cursor
  above the bottom card** so it's never hidden. A follow / free-browse FAB re-centres after you pan.
- **Position source** — **real device GPS by default**; a *Simulated walk* toggle in
  **Settings** replays a real ~4 km Moscow route (Волгоградский проспект → Павелецкая) at
  **human walking speed (~7 km/h)** for demos / the emulator. Heading comes from the GPS
  course; `gaze_confidence=low` (the documented compass-in-pocket fallback).
- **Spoken narration** — on-device TTS (`flutter_tts`, voice follows the selected language);
  speaker toggle up top; asking (voice or text) hushes the guide (barge-in). Narration
  **never cuts a line mid-sentence** — a newer line waits, and only the freshest is queued.
- **Ask the guide** — tap-to-talk mic (`record`, 16 kHz WAV → backend STT) or the keyboard
  button for a typed question; the reply is shown and spoken back.
- **Settings & history** — dev controls (WebSocket URL, simulated-walk toggle) live in a
  Settings sheet; the full message feed is a swipe-up **History** sheet. Auto-reconnect with
  backoff is built in.

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
   tap **▶ Walk** (connects + starts; real GPS by default) → the guide narrates in that
   language and the map follows you; tap the mic or ⌨ to ask. The *Simulated walk* toggle in
   ⚙ Settings replays the demo route on the emulator / without GPS.

WS URL defaults to `ws://localhost:8000/ws` (works on the emulator via `adb reverse`).
On a real phone, set it in ⚙ Settings → `ws://<reachable-backend>:8000/ws`.

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
Run on a physical phone for real GPS, the system TTS voices, and the microphone (the
emulator has no real GPS/voice/mic input). A walking phone needs the backend reachable
**along the route**, not just on home Wi-Fi — over mobile data a private LAN IP won't work,
so use a tunnel (cloudflared/ngrok), a private VPN (Tailscale), or a cloud host, and put that
`wss://…/ws` URL in ⚙ Settings.
