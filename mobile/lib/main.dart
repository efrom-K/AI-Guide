// AI Audio Guide — Flutter client.
//
// Map-first, dark, minimalist. The map fills the screen; a glassy bottom card
// shows the agent status, the current place + narration, one primary action
// (connect+walk / stop) and the mic. Dev controls (WS URL, simulated walk) live
// in a Settings sheet. Real device GPS is the default; the simulated Red Square
// walk is a demo fallback (emulator / no GPS).

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show defaultTargetPlatform, kIsWeb, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:record/record.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'compass.dart';
import 'l10n/app_localizations.dart';
import 'walk_history_screen.dart';

// Persisted-preference keys.
const _kPrefTheme = 'themeMode';
const _kPrefLang = 'lang';

ThemeMode _parseThemeMode(String? v) => switch (v) {
      'light' => ThemeMode.light,
      'dark' => ThemeMode.dark,
      _ => ThemeMode.system,
    };

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  runApp(GuideApp(
    initialThemeMode: _parseThemeMode(prefs.getString(_kPrefTheme)),
    initialLang: prefs.getString(_kPrefLang),
  ));
}

// Supported guide languages: code -> (native label for the picker, TTS BCP-47 tag).
// Codes are ISO-639-1 and match the backend's languages.py / Whisper.
const kLangs = <String, ({String label, String tts})>{
  'en': (label: 'English', tts: 'en-US'),
  'ru': (label: 'Русский', tts: 'ru-RU'),
  'es': (label: 'Español', tts: 'es-ES'),
  'fr': (label: 'Français', tts: 'fr-FR'),
  'de': (label: 'Deutsch', tts: 'de-DE'),
  'it': (label: 'Italiano', tts: 'it-IT'),
  'pt': (label: 'Português', tts: 'pt-BR'),
  'zh': (label: '中文', tts: 'zh-CN'),
};

// Map an arbitrary locale code to a supported one, else fall back to English.
String normLang(String code) => kLangs.containsKey(code) ? code : 'en';

// A stable session id for this app launch, sent as ?sid= on every (re)connect so a
// dropped link (WiFi/cell) resumes the SAME backend session — preserving the
// seen-list / history so the tour continues instead of repeating from scratch.
String _genSessionId() {
  // Random.secure() (CSPRNG), 32 chars: the sid resumes a session, so a guessable one
  // would let someone else resume your tour (GPS track + history). 36^32 ≈ 165 bits.
  final r = Random.secure();
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  return List.generate(32, (_) => chars[r.nextInt(chars.length)]).join();
}

// Default backend URL — baked at build time so a test build points at the host
// with no manual setup:  flutter build ... --dart-define=WS_URL=wss://host/ws
// The in-app Settings field overrides it. Falls back to localhost for dev/emulator.
const kDefaultWsUrl = String.fromEnvironment('WS_URL', defaultValue: 'ws://localhost:8000/ws');
// Shared access token for the /ws endpoint ('' => open). Baked in at build time.
const kWsToken = String.fromEnvironment('WS_TOKEN', defaultValue: '');
// Test-only: when set to a kRoutes key, the app auto-enables the simulated walk on
// that route and starts it on launch (for emulator acceptance runs). Empty = off.
const kAutoWalkRoute = String.fromEnvironment('AUTO_WALK_ROUTE', defaultValue: '');

// True under `flutter test` — lets us skip live map-tile network there.
bool _underTest() {
  try {
    return Platform.environment.containsKey('FLUTTER_TEST');
  } catch (_) {
    return false; // web has no Platform.environment
  }
}

// Palette — soft teal accent. Pin/marker accents are theme-independent (they must
// read over both the light Voyager and dark map tiles); the glassy chrome colours
// live in the AppColors theme extension below so they flip with light/dark.
const _accent = Color(0xFF2DD4BF); // teal
const _pinCurrent = Color(0xFFFBBF24); // amber — the place being narrated
const _pinPast = Color(0xFF64748B); // slate — already seen
const _pinLite = Color(0x803B82F6); // blue — found-but-not-narrated (inventory)
const _userArrow = Color(0xFF22D3EE); // cyan — the user's bearing

// App-specific surface/text colours that Material's ColorScheme doesn't model well
// (translucent "glass" card/pills/sheets over the map, hairlines, tiered text). One
// variant per brightness; looked up via `Theme.of(context).extension<AppColors>()!`.
@immutable
class AppColors extends ThemeExtension<AppColors> {
  final Color glassCard; // the bottom narration card
  final Color glassPill; // top-bar + FAB pills
  final Color sheetBg; // modal bottom sheets
  final Color hairline; // thin borders
  final Color textPrimary;
  final Color textSecondary;
  final Color textFaint;

  const AppColors({
    required this.glassCard,
    required this.glassPill,
    required this.sheetBg,
    required this.hairline,
    required this.textPrimary,
    required this.textSecondary,
    required this.textFaint,
  });

  static const dark = AppColors(
    glassCard: Color(0xF21A1B1F),
    glassPill: Color(0xCC18191D),
    sheetBg: Color(0xFF15161A),
    hairline: Colors.white12,
    textPrimary: Colors.white,
    textSecondary: Colors.white70,
    textFaint: Colors.white38,
  );

  static const light = AppColors(
    glassCard: Color(0xF2FFFFFF),
    glassPill: Color(0xF2FFFFFF),
    sheetBg: Color(0xFFF7F8FA),
    hairline: Colors.black12,
    textPrimary: Color(0xFF111317),
    textSecondary: Color(0xFF3F454D),
    textFaint: Color(0xFF8A9099),
  );

  @override
  AppColors copyWith({
    Color? glassCard,
    Color? glassPill,
    Color? sheetBg,
    Color? hairline,
    Color? textPrimary,
    Color? textSecondary,
    Color? textFaint,
  }) =>
      AppColors(
        glassCard: glassCard ?? this.glassCard,
        glassPill: glassPill ?? this.glassPill,
        sheetBg: sheetBg ?? this.sheetBg,
        hairline: hairline ?? this.hairline,
        textPrimary: textPrimary ?? this.textPrimary,
        textSecondary: textSecondary ?? this.textSecondary,
        textFaint: textFaint ?? this.textFaint,
      );

  @override
  AppColors lerp(AppColors? other, double t) => t < 0.5 ? this : (other ?? this);
}

// Convenience accessor used throughout the widget tree.
AppColors _c(BuildContext context) => Theme.of(context).extension<AppColors>()!;

class GuideApp extends StatefulWidget {
  final ThemeMode initialThemeMode;
  final String? initialLang; // null => derive from the system locale
  const GuideApp({super.key, required this.initialThemeMode, this.initialLang});

  @override
  State<GuideApp> createState() => _GuideAppState();
}

class _GuideAppState extends State<GuideApp> {
  late Locale _locale;
  late ThemeMode _themeMode;

  @override
  void initState() {
    super.initState();
    _themeMode = widget.initialThemeMode;
    // Use the saved language; else auto-select the system language (fall back to en).
    final sys = WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    _locale = Locale(normLang(widget.initialLang ?? sys));
  }

  Future<void> _persist(String key, String value) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(key, value);
  }

  void _setLocale(String code) {
    setState(() => _locale = Locale(normLang(code)));
    _persist(_kPrefLang, normLang(code));
  }

  void _setThemeMode(ThemeMode mode) {
    setState(() => _themeMode = mode);
    _persist(_kPrefTheme, mode.name);
  }

  ThemeData _theme(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(seedColor: _accent, brightness: brightness);
    final dark = brightness == Brightness.dark;
    return ThemeData(
      colorScheme: dark ? scheme.copyWith(surface: const Color(0xFF0E0F12)) : scheme,
      useMaterial3: true,
      scaffoldBackgroundColor: dark ? const Color(0xFF0E0F12) : const Color(0xFFF3F4F6),
      extensions: [dark ? AppColors.dark : AppColors.light],
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Guide',
      debugShowCheckedModeBanner: false,
      theme: _theme(Brightness.light),
      darkTheme: _theme(Brightness.dark),
      themeMode: _themeMode,
      locale: _locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: HomePage(
        locale: _locale,
        onLocaleChanged: _setLocale,
        themeMode: _themeMode,
        onThemeModeChanged: _setThemeMode,
      ),
    );
  }
}

class Msg {
  final String kind; // guide | reply | you | meta
  final String text;
  Msg(this.kind, this.text);
}

// A narrated place to pin on the map (tap a pin to read its story).
class PlaceMark {
  final String id;
  final LatLng point;
  final String name;
  String text; // accumulated narration(s) about this place
  PlaceMark(this.id, this.point, this.name, this.text);
}

// A found-but-not-yet-narrated object from the search disc (lite: name + type),
// pinned faintly on the map so the user sees everything around them, not only the
// place currently being narrated. Server pushes these in a "places" frame.
class NearbyObject {
  final String id;
  final LatLng point;
  final String name;
  final String category;
  NearbyObject(this.id, this.point, this.name, this.category);
}

// Angular spread of a small window of bearings (deg), handling the 360/0 wrap —
// the max gap from the first sample, mirrored for the short side. Used to decide
// whether the GPS course is steady enough to trust as a facing for "left/right".
double _bearingSpread(List<double> xs) {
  if (xs.length < 2) return 0;
  final ref = xs.first;
  var mx = 0.0;
  for (final x in xs) {
    var d = (x - ref).abs() % 360.0;
    if (d > 180.0) d = 360.0 - d;
    if (d > mx) mx = d;
  }
  return mx;
}

// One queued utterance for the TTS. Narration paragraphs signal `played` to the
// server (to pace the continuous story); replies don't.
class _Speech {
  final String text;
  final bool isNarration;
  _Speech(this.text, this.isNarration);
}

// Tour themes the user can switch to ("" = let the guide choose automatically).
// `code` is the backend-facing topic string (Russian — the agent maps it, don't
// change it); the visible label comes from l10n at render time, with an icon.
const List<({String code, IconData icon})> kThemes = [
  (code: '', icon: Icons.casino_rounded),
  (code: 'история', icon: Icons.account_balance_rounded),
  (code: 'архитектура', icon: Icons.architecture_rounded),
  (code: 'люди и судьбы', icon: Icons.people_alt_rounded),
  (code: 'культура и искусство', icon: Icons.theater_comedy_rounded),
  (code: 'легенды и тайны', icon: Icons.local_fire_department_rounded),
];

// The visible label for a theme code, localized.
String _themeLabel(AppLocalizations l, String code) => switch (code) {
      'история' => l.themeHistory,
      'архитектура' => l.themeArchitecture,
      'люди и судьбы' => l.themePeople,
      'культура и искусство' => l.themeCulture,
      'легенды и тайны' => l.themeLegends,
      _ => l.themeAuto,
    };

// Demo/test routes: real Moscow walks, waypoints joined in order (straight
// segments). Selectable in Settings when "simulated walk" is on; played back at
// kWalkSpeedMps (~7 km/h). R5 is the original demo route.
const Map<String, List<List<double>>> kRoutes = {
  'r1': [
    [55.792815, 37.587988],
    [55.795015, 37.584619],
    [55.808762, 37.580492],
  ],
  'r2': [
    [55.922993, 37.529511],
    [55.903751, 37.540102],
    [55.897771, 37.551916],
  ],
  'r3': [
    [55.639642, 37.793154],
    [55.639741, 37.801981],
    [55.637460, 37.801954],
  ],
  'r4': [
    [55.847738, 37.584899],
    [55.842658, 37.584763],
    [55.842470, 37.586884],
    [55.835994, 37.590916],
  ],
  'r5': [
    [55.725789, 37.685192],
    [55.728789, 37.677015],
    [55.741959, 37.653943],
    [55.732312, 37.639737],
  ],
};
// Display labels for the route picker (keys are ASCII so they pass cleanly via
// --dart-define on every platform).
const Map<String, String> kRouteLabels = {
  'r1': 'Маршрут 1',
  'r2': 'Маршрут 2',
  'r3': 'Маршрут 3',
  'r4': 'Маршрут 4',
  'r5': 'Маршрут 5 (демо)',
};

const double kWalkSpeedMps = 1.95; // ~7 km/h (brisk human pace)
const double kStepM = 8; // metres between simulated GPS fixes (matches the real distanceFilter)

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.locale,
    required this.onLocaleChanged,
    required this.themeMode,
    required this.onThemeModeChanged,
  });

  final Locale locale; // current UI/guide language
  final void Function(String code) onLocaleChanged; // swap MaterialApp.locale
  final ThemeMode themeMode; // current appearance (system/light/dark)
  final void Function(ThemeMode mode) onThemeModeChanged; // swap appearance + persist

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with TickerProviderStateMixin {
  final _askCtrl = TextEditingController();
  final _scroll = ScrollController();
  WebSocketChannel? _ch;
  bool _connected = false;
  String _state = '—';
  final List<Msg> _log = [];
  Timer? _walkTimer;
  List<Map<String, double>> _points = [];
  int _idx = 0;

  // Position source: false = real device GPS (default), true = simulated route.
  bool _simulate = false;
  String _routeKey = kRoutes.keys.first; // which simulated route to walk
  StreamSubscription<Position>? _gpsSub;

  // Device compass (real GPS only): when the phone is held up and steady, we send
  // its facing as the heading with gaze_confidence=high so the guide can say
  // "left/right"; otherwise we fall back to the GPS course (low).
  final CompassService _compass = CompassService();
  StreamSubscription<CompassReading>? _compassSub;
  CompassReading? _compassReading;
  final List<double> _recentCourses = []; // recent GPS courses, for a steady-walk check

  // On-device TTS — the guide speaks the narration aloud.
  final FlutterTts _tts = FlutterTts();
  bool _voice = true; // speaker on/off
  final List<_Speech> _speakQueue = []; // paragraphs/replies awaiting TTS (in order)
  String _theme = ''; // current tour theme code ("" = auto)
  late String _lang; // current guide language code (en|ru|es|…)

  // Microphone — ask the guide by voice (barge-in).
  final AudioRecorder _rec = AudioRecorder();
  bool _recording = false;
  StreamSubscription<Uint8List>? _audioSub; // mic capture stream (cross-platform)
  final List<int> _audioBuf = []; // accumulated PCM16 while recording

  // Map (CARTO dark tiles via flutter_map).
  final MapController _map = MapController();
  AnimationController? _camCtrl; // drives smooth recenter/follow camera moves
  AnimationController? _rotCtrl; // drives the "orient north" animation
  bool _mapReady = false;
  bool _follow = true; // auto-centre on the user vs free pan
  double _mapRotation = 0; // current map bearing (deg); 0 = north up
  LatLng _here = const LatLng(55.7525, 37.6231); // Red Square until first fix
  double _heading = 0; // degrees, for the bearing arrow
  double _screenH = 800; // logical screen height (for keeping the cursor above the card)
  final List<PlaceMark> _places = []; // narrated places pinned on the map
  List<NearbyObject> _nearby = []; // all found objects (lite pins from "places" frame)
  String? _currentPlaceId; // the place being narrated now (highlighted)

  // What the bottom card shows now.
  String? _curTitle; // current place name
  String? _curText; // current narration / reply text
  bool _curIsReply = false;

  bool _speaking = false; // TTS currently talking
  bool _wantConnected = false; // user intends a live connection (drives auto-reconnect)
  Timer? _reconnectTimer;
  int _retries = 0;
  Timer? _heartbeat; // app-level WS keepalive: ping the server so a NAT/proxy can't
  // reap the idle socket during a narration lull (the reconnect-storm fix).
  Timer? _watchdog; // liveness watchdog: force-reconnect if the socket goes silent
  DateTime _lastRxAt = DateTime.now(); // last inbound frame (any type) — resets the watchdog
  Map<String, dynamic>? _lastPositionMsg; // last position sent — replayed on reconnect
  final String _sid = _genSessionId(); // stable id for resume-on-reconnect

  bool get _active => _walkTimer != null || _gpsSub != null;

  @override
  void initState() {
    super.initState();
    _lang = normLang(widget.locale.languageCode);
    _initTts();
    // Ask for mic + location up front and centre the map on the real position,
    // rather than sitting on the Moscow default until a walk starts.
    WidgetsBinding.instance.addPostFrameCallback((_) => _initLocationAndPermissions());
    // Test-only headless acceptance run: auto-select the route and start walking.
    if (kAutoWalkRoute.isNotEmpty && kRoutes.containsKey(kAutoWalkRoute)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        setState(() {
          _simulate = true;
          _routeKey = kAutoWalkRoute;
        });
        Future.delayed(const Duration(seconds: 3), () {
          if (mounted && !_active) _primary();
        });
      });
    }
  }

  Future<void> _initLocationAndPermissions() async {
    // Mic permission up front (best-effort; some browsers only surface the prompt
    // on a user gesture — the mic button still requests it on tap as a fallback).
    try {
      await _rec.hasPermission();
    } catch (_) {}
    // Location permission, then centre the map on the user's real position now.
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return;
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
        return;
      }
      final pos =
          await Geolocator.getCurrentPosition().timeout(const Duration(seconds: 12));
      if (!mounted) return;
      setState(() {
        _here = LatLng(pos.latitude, pos.longitude);
        if (pos.heading >= 0) _heading = pos.heading;
      });
      if (_mapReady) _animateTo(_here);
    } catch (_) {/* keep the default centre if location is unavailable */}
  }

  Future<void> _initTts() async {
    await _applyTtsLanguage(_lang);
    // Web maps rate straight onto SpeechSynthesis (1.0 = normal), so 0.5 there is
    // half-speed and unpleasant; Android scales differently and 0.5 is a calm pace.
    await _tts.setSpeechRate(kIsWeb ? 1.0 : 0.5);
    await _tts.setPitch(1.0);
    await _tts.awaitSpeakCompletion(true);
    // iOS: a playback audio session lets narration keep playing with the screen
    // locked (paired with the `audio` UIBackgroundMode) and routes to a Bluetooth
    // earbud while ducking any music the user has on.
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.iOS) {
      await _tts.setIosAudioCategory(
        IosTextToSpeechAudioCategory.playback,
        [
          IosTextToSpeechAudioCategoryOptions.mixWithOthers,
          IosTextToSpeechAudioCategoryOptions.duckOthers,
          IosTextToSpeechAudioCategoryOptions.allowBluetoothA2DP,
          IosTextToSpeechAudioCategoryOptions.allowAirPlay,
        ],
        IosTextToSpeechAudioMode.spokenAudio,
      );
    }
    // The queue is driven by awaiting speak() in _speakNext (reliable across
    // platforms). On web the browser's SpeechSynthesis 'end' event is sometimes
    // dropped mid-utterance (a known Chrome bug, easy to hit when an overlay opens),
    // which used to leave _speaking stuck true and the guide permanently silent —
    // so we don't rely on these callbacks to advance, only to reflect UI state.
    _tts.setStartHandler(() {
      if (mounted) setState(() => _speaking = true);
    });
    _tts.setCancelHandler(() {
      if (mounted) setState(() => _speaking = false);
    });
  }

  // Queue a paragraph/reply for TTS (never cut a line mid-sentence). Narration
  // paragraphs are paced by the server via the `played` signal; with the voice
  // muted we still ack narration so the story keeps flowing on screen.
  void _enqueueSpeech(String text, {required bool isNarration}) {
    // Mic open: never speak a narration over the user. The server is already
    // paused, so don't ack `played` either — just drop this stray paragraph.
    if (_recording && isNarration) return;
    if (!_voice) {
      if (isNarration) _send({'type': 'played'});
      return;
    }
    _speakQueue.add(_Speech(text, isNarration));
    if (!_speaking) _speakNext();
  }

  Future<void> _speakNext() async {
    if (_speaking || _speakQueue.isEmpty) return;
    final s = _speakQueue.removeAt(0);
    setState(() => _speaking = true); // claim synchronously to avoid overlap
    // Pace the server the moment a paragraph starts (so it prepares the next one).
    // Sent here — not from the TTS start callback — because that callback is
    // unreliable on web; missing it stalled the whole story after one paragraph.
    if (s.isNarration) _send({'type': 'played'});
    // Chrome's SpeechSynthesis clips an utterance at ~15s, cutting long lines off
    // mid-phrase. Speak in sentence-sized chunks so each stays well under that.
    final chunks = kIsWeb ? _chunkForTts(s.text) : [s.text];
    for (final c in chunks) {
      if (!mounted || !_voice) break; // unmounted or muted mid-line
      try {
        if (kIsWeb) {
          // Per-chunk watchdog: release if the browser drops the 'end' event so the
          // queue can never get stuck (generous vs. a ~140-char chunk's real length).
          final estMs = (c.length / 9.0 * 1000).clamp(2500, 14000).toInt();
          await Future.any([
            _tts.speak(c),
            Future<void>.delayed(Duration(milliseconds: estMs + 4000)),
          ]);
        } else {
          await _tts.speak(c); // mobile: awaitSpeakCompletion is reliable
        }
      } catch (_) {/* keep the queue moving even if one chunk fails */}
    }
    if (!mounted) return;
    setState(() => _speaking = false);
    _speakNext(); // drive the next paragraph ourselves (don't depend on callbacks)
  }

  // Split a paragraph into <=~140-char chunks at sentence boundaries (then spaces
  // for an over-long sentence) so web TTS never hits Chrome's ~15s cutoff mid-phrase.
  List<String> _chunkForTts(String text, {int maxLen = 140}) {
    final out = <String>[];
    var buf = '';
    void flush() {
      if (buf.trim().isNotEmpty) out.add(buf.trim());
      buf = '';
    }
    for (var sent in text.split(RegExp(r'(?<=[.!?…])\s+'))) {
      sent = sent.trim();
      if (sent.isEmpty) continue;
      while (sent.length > maxLen) {
        var cut = sent.lastIndexOf(' ', maxLen);
        if (cut <= 0) cut = maxLen;
        flush();
        out.add(sent.substring(0, cut).trim());
        sent = sent.substring(cut).trim();
      }
      if (buf.isEmpty) {
        buf = sent;
      } else if (buf.length + 1 + sent.length <= maxLen) {
        buf = '$buf $sent';
      } else {
        flush();
        buf = sent;
      }
    }
    flush();
    return out.isEmpty ? [text] : out;
  }

  // Point the TTS voice at the given language (best-effort; unknown tags are no-ops).
  Future<void> _applyTtsLanguage(String code) async {
    try {
      await _tts.setLanguage(kLangs[code]!.tts);
    } catch (_) {/* some platforms lack the voice — the card still shows the text */}
  }

  // User picked a language: swap UI strings + TTS voice + tell the backend.
  Future<void> _changeLanguage(String code) async {
    code = normLang(code);
    if (code == _lang) return;
    final l = AppLocalizations.of(context)!; // capture before awaits
    setState(() => _lang = code);
    widget.onLocaleChanged(code); // rebuilds MaterialApp with the new locale
    await _applyTtsLanguage(code);
    if (_connected) _send({'type': 'language', 'language': code});
    final ok = await _tts.isLanguageAvailable(kLangs[code]!.tts);
    if (ok != true && mounted) {
      _toast(l.metaVoiceUnavailable(kLangs[code]!.label));
    }
  }

  // Hush whatever is playing and drop the queue (barge-in: the user is talking).
  Future<void> _hush() async {
    _speakQueue.clear();
    await _tts.stop();
    // Reset explicitly: on web stop() maps to onComplete, not onCancel, so the
    // cancel handler may not fire — leaving _speaking stuck and the queue frozen.
    if (mounted) setState(() => _speaking = false);
  }

  // The conversation feed holds ONLY real dialog (guide | you | reply). System and
  // status lines go to a transient toast instead, so the history stays readable.
  void _add(String kind, String text) {
    setState(() => _log.add(Msg(kind, text)));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  // A brief, non-intrusive status/error message (GPS, mic, connection). Never enters
  // the conversation history.
  void _toast(String text) {
    if (!mounted) return;
    final m = ScaffoldMessenger.maybeOf(context);
    m?.hideCurrentSnackBar();
    m?.showSnackBar(SnackBar(content: Text(text), duration: const Duration(seconds: 3)));
  }

  bool get _hasDialog =>
      _log.any((m) => m.kind == 'guide' || m.kind == 'reply' || m.kind == 'you');

  // Pin a narrated place on the map (dedup by id; the latest is "current").
  // Follow-up narrations about the same place accumulate into its story.
  void _addPlace(Map<String, dynamic> m) {
    final id = m['place_id'] as String?;
    final lat = (m['lat'] as num?)?.toDouble();
    final lon = (m['lon'] as num?)?.toDouble();
    if (id == null || lat == null || lon == null) return;
    final txt = (m['text'] as String?) ?? '';
    setState(() {
      _currentPlaceId = id;
      PlaceMark? existing;
      for (final p in _places) {
        if (p.id == id) existing = p;
      }
      if (existing == null) {
        _places.add(PlaceMark(id, LatLng(lat, lon), (m['place_name'] as String?) ?? '', txt));
      } else if (txt.isNotEmpty && !existing.text.contains(txt)) {
        existing.text = '${existing.text}\n\n$txt';
      }
    });
  }

  // Replace the lite map pins with the latest search disc (server pushes the full
  // set whenever the disc (re)fetches). Narrated places (`_places`) are drawn on top.
  void _setNearby(Map<String, dynamic> m) {
    final items = (m['items'] as List?) ?? const [];
    final next = <NearbyObject>[];
    for (final it in items) {
      final o = it as Map<String, dynamic>;
      final id = o['id'] as String?;
      final lat = (o['lat'] as num?)?.toDouble();
      final lon = (o['lon'] as num?)?.toDouble();
      if (id == null || lat == null || lon == null) continue;
      next.add(NearbyObject(id, LatLng(lat, lon), (o['name'] as String?) ?? '',
          (o['category'] as String?) ?? ''));
    }
    setState(() => _nearby = next);
  }

  void _connect() {
    _wantConnected = true;
    _reconnectTimer?.cancel();
    // Tear down any previous (possibly half-open) socket first so we never run two
    // overlapping connections — the churn seen in the prod logs on a flaky link.
    _heartbeat?.cancel();
    _watchdog?.cancel();
    _ch?.sink.close();
    _lastRxAt = DateTime.now();
    // Backend URL is baked in at build time (--dart-define WS_URL); not user-facing.
    var url = kDefaultWsUrl;
    final params = <String>['sid=$_sid']; // resume the same session on reconnect
    if (kWsToken.isNotEmpty) params.add('token=${Uri.encodeComponent(kWsToken)}');
    final sep = url.contains('?') ? '&' : '?';
    url += sep + params.join('&');
    final ch = WebSocketChannel.connect(Uri.parse(url));
    ch.stream.listen(
      (data) {
        _retries = 0; // a live message proves the link is healthy
        _lastRxAt = DateTime.now(); // any inbound frame (incl. server ping) = alive
        final m = jsonDecode(data as String) as Map<String, dynamic>;
        switch (m['type']) {
          case 'state':
            setState(() => _state = m['state'] as String);
            break;
          case 'narration':
            final t = m['text'] as String;
            _addPlace(m); // pin it on the map
            setState(() {
              _curTitle = m['place_name'] as String?;
              _curText = t;
              _curIsReply = false;
            });
            _add('guide', t);
            _enqueueSpeech(t, isNarration: true); // queued; paced by `played`
            break;
          case 'reply':
            final t = m['text'] as String;
            setState(() {
              _curText = t;
              _curIsReply = true;
            });
            _add('reply', t);
            _enqueueSpeech(t, isNarration: false); // answer; doesn't pace the story
            break;
          case 'places':
            _setNearby(m); // pin everything the search disc found (lite)
            break;
          case 'transcript':
            _add('you', m['text'] as String);
            break;
          case 'error':
            _toast('${m['message']}');
            break;
        }
      },
      onDone: _onDisconnected,
      onError: (e) => _toast('$e'),
    );
    setState(() {
      _ch = ch;
      _connected = true;
      _state = '—';
    });
    // (Re)send the language first so narration + STT use it before any
    // position/audio arrives, then the theme. With ?sid= the backend resumes the
    // same session, so this is idempotent and the tour continues where it left off.
    _send({'type': 'language', 'language': _lang});
    if (_theme.isNotEmpty) _send({'type': 'theme', 'theme': _theme});
    // Replay the last position so the tour resumes immediately on reconnect instead of
    // sitting idle until the next GPS fix. Only a real fix (never the startup default).
    if (_lastPositionMsg != null) _send(_lastPositionMsg!);
    // Keepalive: ping while connected so an idle socket isn't reaped mid-lull.
    _heartbeat = Timer.periodic(const Duration(seconds: 15), (_) {
      if (_connected) _send({'type': 'ping'});
    });
    // Liveness watchdog: a mobile socket can go half-open (no FIN — metro/elevator/cell
    // handover) so onDone/onError never fire and the guide silently freezes. The server
    // pings every ~20s and narrates, so >40s of total inbound silence means the link is
    // dead — force-close it to trigger the reconnect path.
    _watchdog = Timer.periodic(const Duration(seconds: 10), (_) {
      if (_wantConnected &&
          _connected &&
          DateTime.now().difference(_lastRxAt) > const Duration(seconds: 40)) {
        _ch?.sink.close(); // -> onDone -> _onDisconnected -> reconnect
      }
    });
  }

  // Socket dropped: reflect it, and auto-reconnect if the user still wants to be on.
  void _onDisconnected() {
    _heartbeat?.cancel();
    _watchdog?.cancel();
    setState(() => _connected = false);
    if (!_wantConnected) return;
    final base = (1 << _retries).clamp(1, 16); // 1,2,4,8,16s exponential backoff
    // Jitter (0–1000 ms) so a server restart doesn't trigger a synchronized reconnect
    // storm from every client at once (thundering herd).
    final delay = Duration(milliseconds: base * 1000 + Random().nextInt(1000));
    _retries++;
    _toast(AppLocalizations.of(context)!.metaConnectionLost(base));
    _reconnectTimer = Timer(delay, () {
      if (_wantConnected) _connect();
    });
  }

  void _disconnect() {
    _wantConnected = false;
    _reconnectTimer?.cancel();
    _heartbeat?.cancel();
    _watchdog?.cancel();
    _stopWalk();
    _hush();
    _ch?.sink.close();
    setState(() {
      _ch = null;
      _connected = false;
      _state = '—';
    });
  }

  void _send(Map<String, dynamic> obj) => _ch?.sink.add(jsonEncode(obj));

  // Primary action: one button to start the experience and to stop it.
  void _primary() {
    if (_active) {
      _stopWalk();
      _disconnect();
    } else {
      if (!_connected) _connect();
      _start();
    }
  }

  // ---- walk simulation ---------------------------------------------------
  static double _rad(double d) => d * pi / 180;

  static double _dist(List<double> a, List<double> b) {
    const r = 6371000.0;
    final dl = _rad(b[0] - a[0]), dn = _rad(b[1] - a[1]);
    final h = pow(sin(dl / 2), 2) +
        cos(_rad(a[0])) * cos(_rad(b[0])) * pow(sin(dn / 2), 2);
    return 2 * r * asin(sqrt(h.toDouble()));
  }

  static double _bearing(List<double> a, List<double> b) {
    final la1 = _rad(a[0]), la2 = _rad(b[0]), dn = _rad(b[1] - a[1]);
    final y = sin(dn) * cos(la2);
    final x = cos(la1) * sin(la2) - sin(la1) * cos(la2) * cos(dn);
    return (atan2(y, x) * 180 / pi + 360) % 360;
  }

  List<Map<String, double>> _buildPoints() {
    const stepM = kStepM;
    final route = kRoutes[_routeKey] ?? kRoutes.values.first;
    final pts = <Map<String, double>>[];
    for (var i = 0; i < route.length - 1; i++) {
      final a = route[i], b = route[i + 1];
      final len = _dist(a, b), brg = _bearing(a, b);
      for (var t = 0.0; t < len; t += stepM) {
        final f = t / len;
        pts.add({'lat': a[0] + (b[0] - a[0]) * f, 'lon': a[1] + (b[1] - a[1]) * f, 'dir': brg});
      }
    }
    final last = route.last;
    pts.add({'lat': last[0], 'lon': last[1], 'dir': 0});
    return pts;
  }

  // Start whichever source the toggle selects.
  void _start() => _simulate ? _startWalk() : _startGps();

  void _startWalk() {
    _points = _buildPoints();
    _idx = 0;
    _walkTimer?.cancel();
    // Fire one fix every kStepM metres at human pace (kStepM / speed seconds).
    final ms = (kStepM / kWalkSpeedMps * 1000).round();
    _walkTimer = Timer.periodic(Duration(milliseconds: ms), (_) {
      if (_idx >= _points.length) {
        _stopWalk();
        return;
      }
      final p = _points[_idx++];
      _sendPosition(p['lat']!, p['lon']!, p['dir']!, 'slow');
    });
    setState(() {});
  }

  // Send a position and reflect it on the map. `gaze` is 'low' by default (GPS
  // course / simulated walk); the real-GPS path passes 'high' when the held-up
  // compass gives a trustworthy facing.
  void _sendPosition(double lat, double lon, double dir, String pace,
      {String gaze = 'low'}) {
    final msg = {
      'type': 'position',
      'lat': lat,
      'lon': lon,
      'direction_deg': dir,
      'gaze_confidence': gaze,
      'pace': pace,
    };
    _lastPositionMsg = msg; // replayed on reconnect so the tour resumes at once
    _send(msg);
    setState(() {
      _here = LatLng(lat, lon);
      _heading = dir;
    });
    if (_mapReady && _follow) {
      _animateTo(_followCenter(), duration: const Duration(milliseconds: 400)); // smooth follow
    }
  }

  // ---- real GPS ----------------------------------------------------------
  // Facing (for left/right) comes from one of two trustworthy sources: a held-up
  // compass (phone raised + steady) OR a steady GPS course while walking — the user
  // moves the way they face. Either earns gaze_confidence=high; otherwise (standing,
  // wandering, pocketed) we fall back to the raw course at 'low'.
  Future<void> _startGps() async {
    final l = AppLocalizations.of(context)!;
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        _toast(l.metaGeoDisabled);
        return;
      }
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
        _toast(l.metaGeoNoPermission);
        return;
      }
    } catch (e) {
      _toast(l.metaGpsUnavailable('$e'));
      return;
    }

    // Start the compass so a held-up phone yields a real facing (left/right).
    _compass.start();
    _compassSub ??= _compass.readings.listen((r) => _compassReading = r);
    // Background operation: keep the tour going with the screen locked / phone in a
    // pocket. On Android a foreground LOCATION service (with an ongoing notification)
    // holds the process alive so GPS, the WebSocket and TTS keep running; on iOS we
    // enable background location updates. Either way the existing main-isolate logic
    // (heartbeat, watchdog, speech queue) keeps ticking without a second isolate.
    final LocationSettings settings;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      settings = AndroidSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 5,
        foregroundNotificationConfig: ForegroundNotificationConfig(
          notificationTitle: l.bgNotifTitle,
          notificationText: l.bgNotifText,
          enableWakeLock: true,
          setOngoing: true,
        ),
      );
    } else if (!kIsWeb && defaultTargetPlatform == TargetPlatform.iOS) {
      settings = AppleSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 5,
        allowBackgroundLocationUpdates: true,
        showBackgroundLocationIndicator: true,
        pauseLocationUpdatesAutomatically: false,
        activityType: ActivityType.fitness,
      );
    } else {
      settings = const LocationSettings(accuracy: LocationAccuracy.high, distanceFilter: 5);
    }
    _gpsSub = Geolocator.getPositionStream(locationSettings: settings).listen(
      (pos) {
        // Track recent GPS courses (only while actually moving) to tell a steady
        // walk from a wander. A steady course IS a trustworthy facing — the user
        // moves the way they look — so it earns gaze=high even without the compass.
        final course = pos.heading;
        final walking = pos.speed > 1.0 && course >= 0;
        if (walking) {
          _recentCourses.add(course);
          if (_recentCourses.length > 6) _recentCourses.removeAt(0);
        } else {
          _recentCourses.clear();
        }
        final steadyCourse =
            walking && _recentCourses.length >= 4 && _bearingSpread(_recentCourses) < 25.0;

        // Facing priority: held-up compass > steady walking course > raw course.
        final cr = _compassReading;
        final useCompass = cr != null && cr.confident;
        final dir = useCompass
            ? cr.headingDeg
            : (course >= 0 ? course : 0.0);
        _sendPosition(
          pos.latitude,
          pos.longitude,
          dir,
          pos.speed > 1.5 ? 'fast' : 'slow',
          gaze: (useCompass || steadyCourse) ? 'high' : 'low',
        );
      },
      onError: (e) => _toast(l.metaGpsError('$e')),
    );
    _toast(l.metaRealGpsOn);
    setState(() {});
  }

  void _stopWalk() {
    _walkTimer?.cancel();
    _walkTimer = null;
    _gpsSub?.cancel();
    _gpsSub = null;
    _compass.stop();
    _compassReading = null;
    _recentCourses.clear();
    setState(() {});
  }

  void _ask() {
    final t = _askCtrl.text.trim();
    if (t.isEmpty || _ch == null) return;
    _hush(); // barge-in: hush the narration while we ask
    _add('you', t);
    _send({'type': 'utterance', 'text': t});
    _askCtrl.clear();
  }

  void _toggleVoice() {
    setState(() => _voice = !_voice);
    if (!_voice) {
      _hush();
    } else if (!_speaking && _speakQueue.isEmpty && (_curText?.isNotEmpty ?? false)) {
      // Unmute: don't make the user wait for the next line — replay the current one
      // now. isNarration:false so it doesn't re-trigger server pacing (`played`).
      _enqueueSpeech(_curText!, isNarration: false);
    }
  }

  // User picked a tour theme: tell the backend to revolve the story around it.
  void _setTheme(String code) {
    setState(() => _theme = code);
    if (_connected) _send({'type': 'theme', 'theme': code});
  }

  // ---- voice barge-in (mic) ---------------------------------------------
  Future<void> _toggleMic() async {
    if (_recording) {
      await _stopRecAndSend();
    } else {
      await _startRec();
    }
  }

  Future<void> _startRec() async {
    if (_ch == null) return;
    final l = AppLocalizations.of(context)!; // capture before awaits
    if (!await _rec.hasPermission()) {
      _toast(l.metaMicNoPermission);
      return;
    }
    _hush(); // barge-in: stop the guide locally...
    _send({'type': 'listen', 'on': true}); // ...and tell the server to hold the tour
    _audioBuf.clear();
    try {
      // Stream PCM into memory — works on web AND mobile (no path_provider /
      // dart:io File, which throw on web and made the mic button do nothing there).
      final stream = await _rec.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1),
      );
      _audioSub = stream.listen(_audioBuf.addAll);
      setState(() => _recording = true);
    } catch (e) {
      _send({'type': 'listen', 'on': false}); // mic failed — let the tour resume
      _toast(l.metaMicNoPermission);
    }
  }

  Future<void> _stopRecAndSend() async {
    await _rec.stop();
    await _audioSub?.cancel();
    _audioSub = null;
    setState(() => _recording = false);
    if (_audioBuf.isEmpty) {
      _send({'type': 'listen', 'on': false}); // nothing captured — resume the tour
      return;
    }
    final wav = _wavFromPcm16(_audioBuf, sampleRate: 16000, channels: 1);
    _audioBuf.clear();
    // The audio frame is itself the barge-in; the server answers then resumes.
    _send({'type': 'audio', 'data_b64': base64Encode(wav), 'format': 'wav'});
  }

  // Wrap raw PCM16 (mono, 16 kHz) in a minimal WAV container so the backend's
  // Whisper STT can decode it. Built in memory — no filesystem, web-safe.
  List<int> _wavFromPcm16(List<int> pcm, {required int sampleRate, required int channels}) {
    final byteRate = sampleRate * channels * 2;
    final out = <int>[];
    void s(String x) => out.addAll(x.codeUnits);
    void u32(int v) => out.addAll([v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, (v >> 24) & 0xff]);
    void u16(int v) => out.addAll([v & 0xff, (v >> 8) & 0xff]);
    s('RIFF');
    u32(36 + pcm.length);
    s('WAVE');
    s('fmt ');
    u32(16); // PCM fmt chunk size
    u16(1); // audio format = PCM
    u16(channels);
    u32(sampleRate);
    u32(byteRate);
    u16(channels * 2); // block align
    u16(16); // bits per sample
    s('data');
    u32(pcm.length);
    out.addAll(pcm);
    return out;
  }

  @override
  void dispose() {
    _walkTimer?.cancel();
    _gpsSub?.cancel();
    _compassSub?.cancel();
    _compass.dispose();
    _reconnectTimer?.cancel();
    _heartbeat?.cancel();
    _watchdog?.cancel();
    _audioSub?.cancel();
    _tts.stop();
    _rec.dispose();
    _ch?.sink.close();
    _scroll.dispose();
    _camCtrl?.dispose();
    _rotCtrl?.dispose();
    _map.dispose();
    super.dispose();
  }

  // -- status -------------------------------------------------------------
  ({String label, Color color, bool active}) _status(AppLocalizations l) {
    if (!_connected && _wantConnected) return (label: l.chipReconnecting, color: Colors.orange, active: true);
    if (!_connected) return (label: l.chipNotConnected, color: Colors.grey, active: false);
    if (_speaking) return (label: l.chipSpeaking, color: _accent, active: true);
    return switch (_state) {
      'scoring' => (label: l.chipScoring, color: Colors.lightBlue, active: true),
      'narrating' => (label: l.chipNarrating, color: _accent, active: true),
      'switching' => (label: l.chipSwitching, color: _accent, active: true),
      'listening' => (label: l.chipListening, color: Colors.tealAccent, active: true),
      'answering' => (label: l.chipAnswering, color: Colors.tealAccent, active: true),
      'expanding' => (label: l.chipExpanding, color: Colors.lightBlue, active: true),
      // Upstream trouble: the guide can't reach its data/LLM source. Surface it
      // (was silently swallowed into "ready"/silence) so the user knows it's a
      // problem, not just "nothing nearby".
      'error' || 'recovery' => (label: l.chipError, color: Colors.orangeAccent, active: true),
      'offline' => (label: l.chipOffline, color: Colors.redAccent, active: false),
      _ => (label: l.chipReady, color: const Color(0xFF34D399), active: false),
    };
  }

  Widget _statusPill(AppLocalizations l) {
    final s = _status(l);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: s.color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: s.color.withValues(alpha: 0.45)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        _PulsingDot(color: s.color, active: s.active),
        const SizedBox(width: 8),
        Text(s.label, style: TextStyle(fontSize: 12.5, color: s.color, fontWeight: FontWeight.w600)),
      ]),
    );
  }

  // Camera target that keeps the user's cursor in the visible area ABOVE the
  // bottom card: shift the centre south so the user sits ~1/3 from the top.
  LatLng _followCenter() {
    if (!_mapReady) return _here;
    final shiftPx = _screenH * 0.18; // move the user from 50% up to ~32% of the screen
    final mpp = 156543.03392 * cos(_here.latitude * pi / 180) / pow(2, _map.camera.zoom);
    final shiftLat = (shiftPx * mpp) / 111320.0;
    return LatLng(_here.latitude - shiftLat, _here.longitude);
  }

  // Smoothly glide the camera to `dest` instead of snapping.
  void _animateTo(LatLng dest, {Duration duration = const Duration(milliseconds: 650)}) {
    if (!_mapReady) return;
    _camCtrl?.dispose();
    final startLat = _map.camera.center.latitude;
    final startLng = _map.camera.center.longitude;
    final zoom = _map.camera.zoom;
    final ctrl = AnimationController(vsync: this, duration: duration);
    _camCtrl = ctrl;
    final curve = CurvedAnimation(parent: ctrl, curve: Curves.easeInOutCubic);
    curve.addListener(() {
      final t = curve.value;
      _map.move(
        LatLng(startLat + (dest.latitude - startLat) * t,
            startLng + (dest.longitude - startLng) * t),
        zoom,
      );
    });
    ctrl.forward();
  }

  // Tap a narrated pin -> a card with the place's name and its accumulated story.
  void _showPlaceInfo(PlaceMark p) {
    final c = _c(context);
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: c.sheetBg,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.45,
        maxChildSize: 0.85,
        builder: (ctx, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(22, 18, 22, 28),
          children: [
            Row(children: [
              Icon(Icons.location_on, color: p.id == _currentPlaceId ? _pinCurrent : _pinPast),
              const SizedBox(width: 10),
              Expanded(
                child: Text(p.name.isEmpty ? '—' : p.name,
                    style: TextStyle(
                        fontSize: 20, fontWeight: FontWeight.w700, color: c.textPrimary)),
              ),
            ]),
            const SizedBox(height: 14),
            Text(
              p.text.isEmpty ? '…' : p.text,
              style: TextStyle(fontSize: 15, height: 1.55, color: c.textSecondary),
            ),
          ],
        ),
      ),
    );
  }

  // Tap a found-but-not-narrated pin -> a light card: name + type + a hint that the
  // guide will tell its story once you walk up to it (no facts yet). Outline icon and
  // the faint accent distinguish it from a narrated place.
  void _showNearbyInfo(NearbyObject o) {
    final c = _c(context);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: c.sheetBg,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (ctx) {
        final l = AppLocalizations.of(ctx)!;
        return Padding(
          padding: const EdgeInsets.fromLTRB(22, 20, 22, 28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.place_outlined, color: _pinLite),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(o.name.isEmpty ? o.category : o.name,
                      style: TextStyle(
                          fontSize: 19, fontWeight: FontWeight.w700, color: c.textPrimary)),
                ),
              ]),
              if (o.category.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(o.category, style: TextStyle(fontSize: 14, color: c.textSecondary)),
              ],
              const SizedBox(height: 14),
              Text(l.nearbyHint,
                  style: TextStyle(fontSize: 14, height: 1.5, color: c.textFaint)),
            ],
          ),
        );
      },
    );
  }

  // Zoom the map by one step (used by the +/- buttons). Instant move (no second
  // AnimationController to keep map lifecycle simple).
  void _zoomBy(double delta) {
    if (!_mapReady) return;
    final z = (_map.camera.zoom + delta).clamp(3.0, 19.0);
    _map.move(_map.camera.center, z);
  }

  // -- map ----------------------------------------------------------------
  Widget _mapView() {
    // CARTO light/dark basemaps — the light (Positron) and dark (Dark Matter)
    // counterparts share the exact same tile path, so the light theme is as
    // reliable as the dark one we already shipped. The ValueKey forces flutter_map
    // to rebuild the tile layer (re-fetch tiles) when the theme flips.
    final dark = Theme.of(context).brightness == Brightness.dark;
    final tileUrl = dark
        ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
        : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png';
    return FlutterMap(
      mapController: _map,
      options: MapOptions(
        initialCenter: _here,
        initialZoom: 16,
        onMapReady: () {
          _mapReady = true;
          _animateTo(_here); // snap to the real position if it resolved before the map
        },
        onPositionChanged: (camera, hasGesture) {
          if (hasGesture && _follow) setState(() => _follow = false);
          if (camera.rotation != _mapRotation) {
            setState(() => _mapRotation = camera.rotation);
          }
        },
      ),
      children: [
        if (!_underTest())
          TileLayer(
            key: ValueKey(dark),
            urlTemplate: tileUrl,
            subdomains: const ['a', 'b', 'c'],
            userAgentPackageName: 'com.example.ai_audio_guide',
          ),
        // Lite pins: every object the search disc found (drawn under narrated pins;
        // a narrated place's own pin overrides its lite dot by id).
        MarkerLayer(markers: [
          for (final o in _nearby)
            if (!_places.any((p) => p.id == o.id))
              Marker(
                point: o.point,
                width: 24,
                height: 24,
                child: GestureDetector(
                  onTap: () => _showNearbyInfo(o),
                  child: const Icon(Icons.circle, size: 10, color: _pinLite),
                ),
              ),
        ]),
        MarkerLayer(markers: [
          for (final p in _places)
            Marker(
              point: p.point,
              width: 44,
              height: 44,
              child: GestureDetector(
                onTap: () => _showPlaceInfo(p),
                child: Icon(
                  Icons.location_on,
                  size: p.id == _currentPlaceId ? 34 : 26,
                  color: p.id == _currentPlaceId ? _pinCurrent : _pinPast,
                ),
              ),
            ),
          Marker(
            point: _here,
            width: 44,
            height: 44,
            child: Transform.rotate(
              angle: _heading * pi / 180,
              child: const Icon(Icons.navigation, color: _userArrow, size: 34),
            ),
          ),
        ]),
        const RichAttributionWidget(
          attributions: [TextSourceAttribution('© OpenStreetMap, © CARTO')],
        ),
      ],
    );
  }

  // -- top bar ------------------------------------------------------------
  Widget _iconPill(IconData icon, String tooltip, VoidCallback onTap) {
    final c = _c(context);
    return Material(
      color: c.glassPill,
      shape: CircleBorder(side: BorderSide(color: c.hairline)),
      child: IconButton(
        tooltip: tooltip,
        icon: Icon(icon, size: 20, color: c.textSecondary),
        onPressed: onTap,
      ),
    );
  }

  Widget _topBar(AppLocalizations l) {
    final c = _c(context);
    return Row(children: [
      // Small reserved slot top-left for a future brand icon (logo/name removed —
      // the controls on the right need the room).
      const SizedBox(width: 40, height: 40),
      const Spacer(),
      Material(
        color: c.glassPill,
        shape: CircleBorder(side: BorderSide(color: c.hairline)),
        child: PopupMenuButton<String>(
          tooltip: l.language,
          icon: Icon(Icons.translate, size: 20, color: c.textSecondary),
          initialValue: _lang,
          onSelected: _changeLanguage,
          itemBuilder: (_) => [
            for (final e in kLangs.entries)
              PopupMenuItem(value: e.key, child: Text('${e.value.label}  ${e.key}')),
          ],
        ),
      ),
      const SizedBox(width: 8),
      Material(
        color: c.glassPill,
        shape: CircleBorder(side: BorderSide(color: c.hairline)),
        child: PopupMenuButton<String>(
          tooltip: l.themeTopic,
          icon: Icon(Icons.auto_stories_rounded, size: 20, color: c.textSecondary),
          initialValue: _theme,
          onSelected: _setTheme,
          itemBuilder: (_) => [
            for (final t in kThemes)
              PopupMenuItem(
                value: t.code,
                child: Row(children: [
                  Icon(t.icon, size: 18, color: c.textSecondary),
                  const SizedBox(width: 10),
                  Text(_themeLabel(l, t.code)),
                ]),
              ),
          ],
        ),
      ),
      const SizedBox(width: 8),
      _iconPill(_voice ? Icons.volume_up_rounded : Icons.volume_off_rounded,
          _voice ? l.voiceOn : l.voiceOff, _toggleVoice),
      const SizedBox(width: 8),
      _iconPill(Icons.route_rounded, l.walkHistory,
          () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const WalkHistoryScreen()))),
      const SizedBox(width: 8),
      _iconPill(Icons.tune_rounded, l.settings, _openSettings),
    ]);
  }

  // -- bottom card --------------------------------------------------------
  Widget _bottomCard(AppLocalizations l) {
    final c = _c(context);
    final hasNarration = _curText != null && _curText!.isNotEmpty;
    final title = _curIsReply ? l.chipAnswering : _curTitle;
    return Container(
      decoration: BoxDecoration(
        color: c.glassCard,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: c.hairline),
        boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 24, offset: Offset(0, 8))],
      ),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          _statusPill(l),
          const Spacer(),
          IconButton(
            tooltip: l.history,
            visualDensity: VisualDensity.compact,
            icon: Icon(Icons.history_rounded, size: 20, color: c.textFaint),
            onPressed: _hasDialog ? _openHistory : null,
          ),
        ]),
        const SizedBox(height: 6),
        if (hasNarration) ...[
          if (title != null && title.isNotEmpty)
            Text(title,
                style: TextStyle(
                    fontSize: 19, fontWeight: FontWeight.w700, color: c.textPrimary)),
          if (title != null && title.isNotEmpty) const SizedBox(height: 6),
          ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.26),
            child: SingleChildScrollView(
              child: Text(_curText!,
                  style: TextStyle(fontSize: 15, height: 1.45, color: c.textSecondary)),
            ),
          ),
        ] else
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: Text(l.emptyHint,
                style: TextStyle(fontSize: 15, height: 1.4, color: c.textFaint)),
          ),
        const SizedBox(height: 14),
        Row(children: [
          Expanded(
            child: FilledButton.icon(
              onPressed: _primary,
              style: FilledButton.styleFrom(
                backgroundColor: _active ? const Color(0xFF3A2230) : _accent,
                foregroundColor: _active ? const Color(0xFFFCA5A5) : Colors.black,
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              ),
              icon: Icon(_active ? Icons.stop_rounded : Icons.play_arrow_rounded),
              label: Text(_active ? l.stop : l.startWalk,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            ),
          ),
          const SizedBox(width: 10),
          _roundAction(
            icon: _recording ? Icons.stop_rounded : Icons.mic_rounded,
            tooltip: _recording ? l.micStop : l.micAsk,
            color: _recording ? const Color(0xFFEF4444) : c.glassPill,
            fg: _recording ? Colors.white : c.textSecondary,
            onTap: _connected ? _toggleMic : null,
          ),
          const SizedBox(width: 10),
          _roundAction(
            icon: Icons.keyboard_rounded,
            tooltip: l.ask,
            color: c.glassPill,
            fg: c.textSecondary,
            onTap: _connected ? _openAsk : null,
          ),
        ]),
      ]),
    );
  }

  Widget _roundAction({
    required IconData icon,
    required String tooltip,
    required Color color,
    required Color fg,
    VoidCallback? onTap,
  }) {
    return Opacity(
      opacity: onTap == null ? 0.4 : 1,
      child: Material(
        color: color,
        shape: CircleBorder(side: BorderSide(color: _c(context).hairline)),
        child: IconButton(
          tooltip: tooltip,
          padding: const EdgeInsets.all(14),
          icon: Icon(icon, color: fg),
          onPressed: onTap,
        ),
      ),
    );
  }

  // Smoothly rotate the map back to north (shortest way round).
  void _resetNorth() {
    if (!_mapReady) return;
    _rotCtrl?.dispose();
    final start = _map.camera.rotation;
    final delta = (-start + 540) % 360 - 180; // normalise to [-180, 180]
    final ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 400));
    _rotCtrl = ctrl;
    final curve = CurvedAnimation(parent: ctrl, curve: Curves.easeInOut);
    curve.addListener(() => _map.rotate(start + delta * curve.value));
    ctrl.forward();
  }

  // A small +/- zoom control column for the map.
  Widget _zoomFab(AppLocalizations l) {
    final c = _c(context);
    Widget btn(IconData icon, String tip, String tag, VoidCallback onTap) =>
        FloatingActionButton.small(
          heroTag: tag,
          tooltip: tip,
          backgroundColor: c.glassPill,
          foregroundColor: c.textSecondary,
          shape: CircleBorder(side: BorderSide(color: c.hairline)),
          onPressed: onTap,
          child: Icon(icon),
        );
    return Column(mainAxisSize: MainAxisSize.min, children: [
      btn(Icons.add_rounded, l.zoomIn, 'zoomIn', () => _zoomBy(1)),
      const SizedBox(height: 10),
      btn(Icons.remove_rounded, l.zoomOut, 'zoomOut', () => _zoomBy(-1)),
    ]);
  }

  // Compass button: the needle reflects the map bearing; tap orients to north.
  Widget _compassFab(AppLocalizations l) {
    final c = _c(context);
    return FloatingActionButton.small(
      heroTag: 'compass',
      tooltip: l.compassNorth,
      backgroundColor: c.glassPill,
      foregroundColor: c.textSecondary,
      shape: CircleBorder(side: BorderSide(color: c.hairline)),
      onPressed: _resetNorth,
      child: Transform.rotate(
        angle: -_mapRotation * pi / 180,
        child: const Icon(Icons.navigation_rounded, color: Color(0xFFEF4444), size: 20),
      ),
    );
  }

  // -- follow FAB ---------------------------------------------------------
  Widget _followFab(AppLocalizations l) {
    final c = _c(context);
    return FloatingActionButton.small(
      heroTag: 'follow',
      tooltip: _follow ? l.following : l.freeBrowse,
      backgroundColor: _follow ? _accent : c.glassPill,
      foregroundColor: _follow ? Colors.black : c.textSecondary,
      shape: CircleBorder(side: BorderSide(color: c.hairline)),
      onPressed: () {
        setState(() => _follow = true);
        _animateTo(_followCenter()); // smooth glide; keep the cursor above the card
      },
      child: Icon(_follow ? Icons.my_location_rounded : Icons.location_searching_rounded),
    );
  }

  // -- sheets -------------------------------------------------------------
  void _openAsk() {
    final l = AppLocalizations.of(context)!;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: _c(context).sheetBg,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(16, 16, 16, MediaQuery.of(ctx).viewInsets.bottom + 16),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: _askCtrl,
              autofocus: true,
              decoration: InputDecoration(
                hintText: l.askHint,
                filled: true,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
              ),
              onSubmitted: (_) {
                _ask();
                Navigator.pop(ctx);
              },
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: () {
              _ask();
              Navigator.pop(ctx);
            },
            child: Text(l.ask),
          ),
        ]),
      ),
    );
  }

  void _openHistory() {
    final l = AppLocalizations.of(context)!;
    // Conversation only: the guide's narration, its replies, and your questions —
    // never system/status lines (those are transient toasts).
    final dialog = _log.where((m) => m.kind != 'meta').toList();
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: _c(context).sheetBg,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.6,
        maxChildSize: 0.92,
        builder: (c, controller) => Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 4),
            child: Row(children: [
              Text(l.history, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              const Spacer(),
              TextButton.icon(
                onPressed: () {
                  setState(_log.clear);
                  Navigator.pop(ctx);
                },
                icon: const Icon(Icons.delete_sweep_outlined, size: 18),
                label: Text(l.clearFeed),
              ),
            ]),
          ),
          Expanded(
            child: ListView.builder(
              controller: controller,
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 16),
              itemCount: dialog.length,
              itemBuilder: (_, i) => _logTile(dialog[i]),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _logTile(Msg m) {
    final c = _c(context);
    final (bg, fg) = switch (m.kind) {
      'guide' => (_accent.withValues(alpha: 0.12), c.textPrimary),
      'reply' => (const Color(0x2234D399), c.textPrimary),
      _ => (c.hairline, c.textSecondary), // 'you'
    };
    final align = m.kind == 'you' ? Alignment.centerRight : Alignment.centerLeft;
    return Align(
      alignment: align,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.all(11),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.82),
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(14)),
        child: Text(m.text, style: TextStyle(color: fg, fontSize: 14, height: 1.35)),
      ),
    );
  }

  void _openSettings() {
    final l = AppLocalizations.of(context)!;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      // Transparent here so the panel colour is painted INSIDE the StatefulBuilder
      // below — that way the sheet recolours live when the theme is switched from
      // its own toggle (a fixed backgroundColor would stay the old colour until
      // the sheet is closed and reopened).
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (c, setSheet) {
          final cc = _c(context); // re-read on every (setSheet) rebuild → live theme
          return Container(
            decoration: BoxDecoration(
              color: cc.sheetBg,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
            ),
            padding: EdgeInsets.fromLTRB(16, 16, 16, MediaQuery.of(ctx).viewInsets.bottom + 24),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(l.settings, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 16),
            Text(l.appearance,
                style: TextStyle(
                    fontSize: 13, fontWeight: FontWeight.w600, color: cc.textSecondary)),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: SegmentedButton<ThemeMode>(
                segments: [
                  ButtonSegment(
                      value: ThemeMode.system,
                      icon: const Icon(Icons.brightness_auto_rounded, size: 18),
                      label: Text(l.themeSystem)),
                  ButtonSegment(
                      value: ThemeMode.light,
                      icon: const Icon(Icons.light_mode_rounded, size: 18),
                      label: Text(l.themeLight)),
                  ButtonSegment(
                      value: ThemeMode.dark,
                      icon: const Icon(Icons.dark_mode_rounded, size: 18),
                      label: Text(l.themeDark)),
                ],
                selected: {widget.themeMode},
                showSelectedIcon: false,
                onSelectionChanged: (s) {
                  widget.onThemeModeChanged(s.first);
                  setSheet(() {});
                },
              ),
            ),
            const SizedBox(height: 12),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(l.simulatedWalk),
              value: _simulate,
              // Can't switch source mid-walk.
              onChanged: _active ? null : (v) {
                setState(() => _simulate = v);
                setSheet(() {});
              },
            ),
            if (_simulate)
              DropdownButtonFormField<String>(
                initialValue: _routeKey,
                decoration: InputDecoration(
                  labelText: l.route,
                  filled: true,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                ),
                items: [
                  for (final k in kRoutes.keys)
                    DropdownMenuItem(value: k, child: Text(kRouteLabels[k] ?? k)),
                ],
                onChanged: _active
                    ? null
                    : (v) {
                        if (v == null) return;
                        setState(() => _routeKey = v);
                        setSheet(() {});
                      },
              ),
          ]),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    _screenH = MediaQuery.of(context).size.height;
    return Scaffold(
      body: Stack(children: [
        Positioned.fill(child: _mapView()),
        // top controls
        Positioned(
          top: 0,
          left: 12,
          right: 12,
          child: SafeArea(bottom: false, child: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: _topBar(l),
          )),
        ),
        // recenter FAB sits directly above the card (always visible).
        Positioned(left: 12, right: 12, bottom: 0, child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Align(
                alignment: Alignment.centerRight,
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    _zoomFab(l),
                    const SizedBox(height: 10),
                    if (_mapRotation.abs() > 0.5) ...[
                      _compassFab(l),
                      const SizedBox(height: 10),
                    ],
                    _followFab(l),
                  ]),
                ),
              ),
              _bottomCard(l),
            ]),
          ),
        )),
      ]),
    );
  }
}

// A small dot that gently pulses while the agent is active.
class _PulsingDot extends StatefulWidget {
  const _PulsingDot({required this.color, required this.active});
  final Color color;
  final bool active;

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot> with SingleTickerProviderStateMixin {
  late final AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));
    if (widget.active) _c.repeat(reverse: true);
  }

  @override
  void didUpdateWidget(_PulsingDot old) {
    super.didUpdateWidget(old);
    if (widget.active && !_c.isAnimating) {
      _c.repeat(reverse: true);
    } else if (!widget.active && _c.isAnimating) {
      _c.stop();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.active) return _dot(1);
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) => _dot(0.4 + 0.6 * _c.value),
    );
  }

  Widget _dot(double opacity) => Container(
        width: 9,
        height: 9,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: widget.color.withValues(alpha: opacity),
          boxShadow: [BoxShadow(color: widget.color.withValues(alpha: opacity * 0.6), blurRadius: 6)],
        ),
      );
}
