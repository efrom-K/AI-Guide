# AI Audio Guide — Flutter client

Stage 0 skeleton: proves the WebSocket transport against the backend `/ws`.
Sensors (GPS/compass), streaming audio playback, and mic/barge-in arrive in Stage 6.

## Requirements
- Flutter SDK `>=3.4` (not yet installed in this environment — install from
  https://docs.flutter.dev/get-started/install)

## Run
```bash
cd mobile
flutter pub get
flutter run        # device or emulator
```

The backend must be running (`backend/`). On the Android emulator the host is
reachable at `10.0.2.2`; the WS URL is set in `lib/main.dart` (`_wsUrl`).
