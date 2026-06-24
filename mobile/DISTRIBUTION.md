# Test builds — Android + iOS (for your lead to test)

Same Flutter app, built for two platforms. The backend host URL is **baked at build time**
so the tester installs and it just connects — no manual setup.

## Point the apps at the host

When the host is ready, build with its URL via `--dart-define`:

```bash
# wss:// (recommended — TLS, works over mobile data, no security exceptions)
flutter build apk     --release --dart-define=WS_URL=wss://178.83.121.62.sslip.io/ws
flutter build ipa     --release --dart-define=WS_URL=wss://178.83.121.62.sslip.io/ws   # on a Mac / CI
```

- No `--dart-define` → falls back to `ws://localhost:8000/ws` (dev/emulator).
- The tester can still override it in the app: **⚙ Settings → WebSocket URL**.
- `ws://` (no TLS) also works — Android allows cleartext (`usesCleartextTraffic`) and iOS has
  an ATS exception in `Info.plist`. For an **App Store** build with a `wss://` host, remove the
  `NSAllowsArbitraryLoads` exception so iOS uses TLS-only.

## Android — ready now

A release APK is built here and is installable by sideload (debug-signed, fine for testing):

```
build/app/outputs/flutter-apk/app-release.apk
```

Give it to the tester → they enable "Install unknown apps" → install. Or push over USB:
```bash
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

**Cleaner distribution (optional):** Google Play **Internal testing** track — upload an
`.aab` (`flutter build appbundle --release`), add the lead's email as a tester, they install
from a Play link. Needs a Google Play Console account ($25 once) and a real upload keystore
(the current build uses the debug key — replace it via `android/key.properties` +
`signingConfigs` for Play).

## iOS — Xcode-ready project (build on a Mac or in the cloud)

`ios/` is scaffolded with permissions (location, microphone) and an ATS exception. iOS can't
be built on Windows, so use one of:

**A. Codemagic (no Mac needed — recommended for you).** `codemagic.yaml` is in this folder.
1. Sign up at codemagic.io, connect this git repo.
2. In the Codemagic UI add: an **Apple Developer / App Store Connect API key**, your
   **bundle id** (see note below), and set the project working directory to `mobile/`.
3. Set the `WS_URL` env var (or edit `codemagic.yaml`).
4. Run the workflow → it builds the IPA and uploads to **TestFlight** → your lead installs via
   the TestFlight app from an email/public link.

**B. On a Mac with Xcode.**
```bash
cd mobile
flutter pub get
flutter build ipa --release --dart-define=WS_URL=wss://178.83.121.62.sslip.io/ws
# then upload build/ios/ipa/*.ipa via Xcode Organizer or `xcrun altool` to TestFlight
```

**Apple prerequisites for installing on a device (either path):** an **Apple Developer
account** ($99/yr) for TestFlight/ad-hoc. Without it you can only run on the iOS **Simulator**
or on your own device via free signing (7-day cert).

## Before store submission (not needed for TestFlight/sideload testing)

- **Bundle id / org:** currently `com.example.ai_audio_guide`. Apple/Google reject `com.example`.
  Change it to your own, e.g. re-scaffold platforms with `--org com.yourcompany`, or edit
  `android` `applicationId` + the iOS bundle id in Xcode.
- **Signing:** real Android upload keystore; iOS distribution certificate + provisioning
  (Codemagic/Xcode automatic signing handles iOS).
- **App icon:** still the default Flutter icon — add a real one (e.g. `flutter_launcher_icons`).
