# AI Audio Guide — Flutter client

Thin WebSocket client for the backend: simulates a walk (sends positions),
shows the guide's narration/replies, and lets you ask questions.

## Status
- ✅ **Web / Windows desktop** — runs now, no Android toolchain needed.
- ⏳ **Mobile (Android/iOS)** — Stage 6b: real GPS + compass + mic. Needs Android
  Studio + SDK (`flutter doctor` shows it as the only missing piece).

## Run (web)
1. Start the backend (`../backend`) on `:8000`
   — for the live model set `AGENT_BACKEND=openai` + LM Studio running.
2. ```bash
   cd mobile
   flutter run -d chrome      # or: flutter run -d windows
   ```
3. In the app: **Подключиться** → **▶ Прогулка** → watch the narration; type a
   question (e.g. "пропускай магазины") and **Спросить**.

The WebSocket URL defaults to `ws://localhost:8000/ws` (editable in the app).

## Checks
```bash
flutter analyze
flutter test
flutter build web
```

## Next (mobile)
Replace the simulated walk with real sensors and add audio/mic; uncomment the
plugins in `pubspec.yaml` (geolocator, flutter_compass, just_audio, record).
