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

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'l10n/app_localizations.dart';

void main() => runApp(const GuideApp());

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

// True under `flutter test` — lets us skip live map-tile network there.
bool _underTest() {
  try {
    return Platform.environment.containsKey('FLUTTER_TEST');
  } catch (_) {
    return false; // web has no Platform.environment
  }
}

// Palette — dark, soft teal accent.
const _accent = Color(0xFF2DD4BF); // teal
const _cardBg = Color(0xF21A1B1F); // glassy dark card over the map
const _pillBg = Color(0xCC18191D);
const _pinCurrent = Color(0xFFFBBF24); // amber — the place being narrated
const _pinPast = Color(0xFF64748B); // slate — already seen
const _userArrow = Color(0xFF22D3EE); // cyan — the user's bearing

class GuideApp extends StatefulWidget {
  const GuideApp({super.key});

  @override
  State<GuideApp> createState() => _GuideAppState();
}

class _GuideAppState extends State<GuideApp> {
  late Locale _locale;

  @override
  void initState() {
    super.initState();
    // Auto-select the system language; fall back to English if unsupported.
    final sys = WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    _locale = Locale(normLang(sys));
  }

  void _setLocale(String code) => setState(() => _locale = Locale(normLang(code)));

  @override
  Widget build(BuildContext context) {
    final scheme = ColorScheme.fromSeed(
      seedColor: _accent,
      brightness: Brightness.dark,
    ).copyWith(surface: const Color(0xFF0E0F12));
    return MaterialApp(
      title: 'AI Audio Guide',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: scheme,
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFF0E0F12),
      ),
      locale: _locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: HomePage(locale: _locale, onLocaleChanged: _setLocale),
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

// Red Square waypoints (lat, lon) — same route as the backend sim.
const List<List<double>> kRoute = [
  [55.7525, 37.6231],
  [55.7537, 37.6205],
  [55.7547, 37.6196],
  [55.7553, 37.6178],
];

class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.locale, required this.onLocaleChanged});

  final Locale locale; // current UI/guide language
  final void Function(String code) onLocaleChanged; // swap MaterialApp.locale

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with TickerProviderStateMixin {
  final _urlCtrl = TextEditingController(text: 'ws://localhost:8000/ws');
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
  StreamSubscription<Position>? _gpsSub;

  // On-device TTS — the guide speaks the narration aloud.
  final FlutterTts _tts = FlutterTts();
  bool _voice = true; // speaker on/off
  late String _lang; // current guide language code (en|ru|es|…)

  // Microphone — ask the guide by voice (barge-in).
  final AudioRecorder _rec = AudioRecorder();
  bool _recording = false;

  // Map (CARTO dark tiles via flutter_map).
  final MapController _map = MapController();
  AnimationController? _camCtrl; // drives smooth recenter/follow camera moves
  bool _mapReady = false;
  bool _follow = true; // auto-centre on the user vs free pan
  LatLng _here = const LatLng(55.7525, 37.6231); // Red Square until first fix
  double _heading = 0; // degrees, for the bearing arrow
  final List<PlaceMark> _places = []; // narrated places pinned on the map
  String? _currentPlaceId; // the place being narrated now (highlighted)

  // What the bottom card shows now.
  String? _curTitle; // current place name
  String? _curText; // current narration / reply text
  bool _curIsReply = false;

  bool _speaking = false; // TTS currently talking
  bool _wantConnected = false; // user intends a live connection (drives auto-reconnect)
  Timer? _reconnectTimer;
  int _retries = 0;

  bool get _active => _walkTimer != null || _gpsSub != null;

  @override
  void initState() {
    super.initState();
    _lang = normLang(widget.locale.languageCode);
    _initTts();
  }

  Future<void> _initTts() async {
    await _applyTtsLanguage(_lang);
    await _tts.setSpeechRate(0.5); // calmer, guide-like pace
    await _tts.setPitch(1.0);
    await _tts.awaitSpeakCompletion(true);
    _tts.setStartHandler(() => setState(() => _speaking = true));
    _tts.setCompletionHandler(() => setState(() => _speaking = false));
    _tts.setCancelHandler(() => setState(() => _speaking = false));
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
      _add('meta', l.metaVoiceUnavailable(kLangs[code]!.label));
    }
  }

  // Speak text now, cutting off whatever is playing (seamless switch / barge-in).
  Future<void> _say(String text) async {
    if (!_voice) return;
    await _tts.stop();
    await _tts.speak(text);
  }

  void _add(String kind, String text) {
    setState(() => _log.add(Msg(kind, text)));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

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

  void _connect() {
    _wantConnected = true;
    _reconnectTimer?.cancel();
    final ch = WebSocketChannel.connect(Uri.parse(_urlCtrl.text.trim()));
    ch.stream.listen(
      (data) {
        _retries = 0; // a live message proves the link is healthy
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
            _say(t);
            break;
          case 'reply':
            final t = m['text'] as String;
            setState(() {
              _curText = t;
              _curIsReply = true;
            });
            _add('reply', t);
            _say(t);
            break;
          case 'transcript':
            _add('you', m['text'] as String);
            break;
          case 'error':
            _add('meta', '⚠ ${m['message']}');
            break;
        }
      },
      onDone: _onDisconnected,
      onError: (e) => _add('meta', '⚠ $e'),
    );
    setState(() {
      _ch = ch;
      _connected = true;
      _state = '—';
      _add('meta', AppLocalizations.of(context)!.metaConnecting(_urlCtrl.text));
    });
    // New WS connection => fresh backend session; (re)send the language first so
    // narration + STT use it before any position/audio arrives.
    _send({'type': 'language', 'language': _lang});
  }

  // Socket dropped: reflect it, and auto-reconnect if the user still wants to be on.
  void _onDisconnected() {
    setState(() => _connected = false);
    if (!_wantConnected) return;
    final delay = Duration(seconds: (1 << _retries).clamp(1, 16)); // 1,2,4,8,16s
    _retries++;
    _add('meta', AppLocalizations.of(context)!.metaConnectionLost(delay.inSeconds));
    _reconnectTimer = Timer(delay, () {
      if (_wantConnected) _connect();
    });
  }

  void _disconnect() {
    _wantConnected = false;
    _reconnectTimer?.cancel();
    _stopWalk();
    _tts.stop();
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
    const stepM = 10.0;
    final pts = <Map<String, double>>[];
    for (var i = 0; i < kRoute.length - 1; i++) {
      final a = kRoute[i], b = kRoute[i + 1];
      final len = _dist(a, b), brg = _bearing(a, b);
      for (var t = 0.0; t < len; t += stepM) {
        final f = t / len;
        pts.add({'lat': a[0] + (b[0] - a[0]) * f, 'lon': a[1] + (b[1] - a[1]) * f, 'dir': brg});
      }
    }
    final last = kRoute.last;
    pts.add({'lat': last[0], 'lon': last[1], 'dir': 0});
    return pts;
  }

  // Start whichever source the toggle selects.
  void _start() => _simulate ? _startWalk() : _startGps();

  void _startWalk() {
    _points = _buildPoints();
    _idx = 0;
    _walkTimer?.cancel();
    _walkTimer = Timer.periodic(const Duration(milliseconds: 1200), (_) {
      if (_idx >= _points.length) {
        _stopWalk();
        return;
      }
      final p = _points[_idx++];
      _sendPosition(p['lat']!, p['lon']!, p['dir']!, 'slow');
    });
    setState(() {});
  }

  // Send a position and reflect it on the map.
  void _sendPosition(double lat, double lon, double dir, String pace) {
    _send({
      'type': 'position',
      'lat': lat,
      'lon': lon,
      'direction_deg': dir,
      'gaze_confidence': 'low',
      'pace': pace,
    });
    setState(() {
      _here = LatLng(lat, lon);
      _heading = dir;
    });
    if (_mapReady && _follow) {
      _animateTo(_here, duration: const Duration(milliseconds: 400)); // smooth follow
    }
  }

  // ---- real GPS ----------------------------------------------------------
  // Heading comes from the GPS course (movement vector), not a compass — so
  // gaze_confidence is always 'low' here, matching the documented fallback
  // (compass is unreliable when the phone is in a pocket).
  Future<void> _startGps() async {
    final l = AppLocalizations.of(context)!;
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        _add('meta', l.metaGeoDisabled);
        return;
      }
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
        _add('meta', l.metaGeoNoPermission);
        return;
      }
    } catch (e) {
      _add('meta', l.metaGpsUnavailable('$e'));
      return;
    }

    const settings = LocationSettings(accuracy: LocationAccuracy.high, distanceFilter: 5);
    _gpsSub = Geolocator.getPositionStream(locationSettings: settings).listen(
      (pos) => _sendPosition(
        pos.latitude,
        pos.longitude,
        pos.heading >= 0 ? pos.heading : 0.0,
        pos.speed > 1.5 ? 'fast' : 'slow',
      ),
      onError: (e) => _add('meta', l.metaGpsError('$e')),
    );
    _add('meta', l.metaRealGpsOn);
    setState(() {});
  }

  void _stopWalk() {
    _walkTimer?.cancel();
    _walkTimer = null;
    _gpsSub?.cancel();
    _gpsSub = null;
    setState(() {});
  }

  void _ask() {
    final t = _askCtrl.text.trim();
    if (t.isEmpty || _ch == null) return;
    _tts.stop(); // barge-in: hush the narration while we ask
    _add('you', t);
    _send({'type': 'utterance', 'text': t});
    _askCtrl.clear();
  }

  void _toggleVoice() {
    setState(() => _voice = !_voice);
    if (!_voice) _tts.stop();
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
      _add('meta', l.metaMicNoPermission);
      return;
    }
    _tts.stop(); // barge-in: hush the guide while the user speaks
    final dir = await getTemporaryDirectory();
    final path = '${dir.path}/ask.wav';
    await _rec.start(
      const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 16000, numChannels: 1),
      path: path,
    );
    setState(() => _recording = true);
  }

  Future<void> _stopRecAndSend() async {
    final l = AppLocalizations.of(context)!; // capture before awaits
    final path = await _rec.stop();
    setState(() => _recording = false);
    if (path == null) return;
    final bytes = await File(path).readAsBytes();
    if (bytes.isEmpty) return;
    _send({'type': 'audio', 'data_b64': base64Encode(bytes), 'format': 'wav'});
    _add('meta', l.metaSentByVoice(bytes.length));
  }

  @override
  void dispose() {
    _walkTimer?.cancel();
    _gpsSub?.cancel();
    _reconnectTimer?.cancel();
    _tts.stop();
    _rec.dispose();
    _ch?.sink.close();
    _scroll.dispose();
    _camCtrl?.dispose();
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

  // Tap a map pin -> show the place's name and its story.
  void _showPlaceInfo(PlaceMark p) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF15161A),
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.45,
        maxChildSize: 0.85,
        builder: (c, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          children: [
            Row(children: [
              Icon(Icons.location_on, color: p.id == _currentPlaceId ? _pinCurrent : _pinPast),
              const SizedBox(width: 8),
              Expanded(
                child: Text(p.name.isEmpty ? '—' : p.name,
                    style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
              ),
            ]),
            const SizedBox(height: 12),
            Text(
              p.text.isEmpty ? '…' : p.text,
              style: const TextStyle(fontSize: 15, height: 1.5, color: Colors.white70),
            ),
          ],
        ),
      ),
    );
  }

  // -- map ----------------------------------------------------------------
  Widget _mapView() {
    return FlutterMap(
      mapController: _map,
      options: MapOptions(
        initialCenter: _here,
        initialZoom: 16,
        onMapReady: () => _mapReady = true,
        onPositionChanged: (camera, hasGesture) {
          if (hasGesture && _follow) setState(() => _follow = false);
        },
      ),
      children: [
        if (!_underTest())
          TileLayer(
            urlTemplate: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
            subdomains: const ['a', 'b', 'c'],
            userAgentPackageName: 'com.example.ai_audio_guide',
          ),
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
    return Material(
      color: _pillBg,
      shape: const CircleBorder(side: BorderSide(color: Colors.white12)),
      child: IconButton(
        tooltip: tooltip,
        icon: Icon(icon, size: 20, color: Colors.white70),
        onPressed: onTap,
      ),
    );
  }

  Widget _topBar(AppLocalizations l) {
    return Row(children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: _pillBg,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white12),
        ),
        child: const Text('🎧  AI Guide',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
      ),
      const Spacer(),
      Material(
        color: _pillBg,
        shape: const CircleBorder(side: BorderSide(color: Colors.white12)),
        child: PopupMenuButton<String>(
          tooltip: l.language,
          icon: const Icon(Icons.translate, size: 20, color: Colors.white70),
          initialValue: _lang,
          onSelected: _changeLanguage,
          itemBuilder: (_) => [
            for (final e in kLangs.entries)
              PopupMenuItem(value: e.key, child: Text('${e.value.label}  ${e.key}')),
          ],
        ),
      ),
      const SizedBox(width: 8),
      _iconPill(_voice ? Icons.volume_up_rounded : Icons.volume_off_rounded,
          _voice ? l.voiceOn : l.voiceOff, _toggleVoice),
      const SizedBox(width: 8),
      _iconPill(Icons.tune_rounded, l.settings, _openSettings),
    ]);
  }

  // -- bottom card --------------------------------------------------------
  Widget _bottomCard(AppLocalizations l) {
    final hasNarration = _curText != null && _curText!.isNotEmpty;
    final title = _curIsReply ? l.chipAnswering : _curTitle;
    return Container(
      decoration: BoxDecoration(
        color: _cardBg,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white12),
        boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 24, offset: Offset(0, 8))],
      ),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          _statusPill(l),
          const Spacer(),
          IconButton(
            tooltip: l.history,
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.history_rounded, size: 20, color: Colors.white54),
            onPressed: _log.isEmpty ? null : _openHistory,
          ),
        ]),
        const SizedBox(height: 6),
        if (hasNarration) ...[
          if (title != null && title.isNotEmpty)
            Text(title, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
          if (title != null && title.isNotEmpty) const SizedBox(height: 6),
          ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.26),
            child: SingleChildScrollView(
              child: Text(_curText!, style: const TextStyle(fontSize: 15, height: 1.45, color: Colors.white70)),
            ),
          ),
        ] else
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: Text(l.emptyHint,
                style: const TextStyle(fontSize: 15, height: 1.4, color: Colors.white54)),
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
              label: Text(_active ? l.stop.replaceAll('⏸ ', '') : l.startWalk.replaceAll('▶ ', ''),
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            ),
          ),
          const SizedBox(width: 10),
          _roundAction(
            icon: _recording ? Icons.stop_rounded : Icons.mic_rounded,
            tooltip: _recording ? l.micStop : l.micAsk,
            color: _recording ? const Color(0xFFEF4444) : _pillBg,
            fg: _recording ? Colors.white : Colors.white70,
            onTap: _connected ? _toggleMic : null,
          ),
          const SizedBox(width: 10),
          _roundAction(
            icon: Icons.keyboard_rounded,
            tooltip: l.ask,
            color: _pillBg,
            fg: Colors.white70,
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
        shape: const CircleBorder(side: BorderSide(color: Colors.white12)),
        child: IconButton(
          tooltip: tooltip,
          padding: const EdgeInsets.all(14),
          icon: Icon(icon, color: fg),
          onPressed: onTap,
        ),
      ),
    );
  }

  // -- follow FAB ---------------------------------------------------------
  Widget _followFab(AppLocalizations l) {
    return FloatingActionButton.small(
      heroTag: 'follow',
      tooltip: _follow ? l.following : l.freeBrowse,
      backgroundColor: _follow ? _accent : _pillBg,
      foregroundColor: _follow ? Colors.black : Colors.white70,
      shape: const CircleBorder(side: BorderSide(color: Colors.white12)),
      onPressed: () {
        setState(() => _follow = true);
        _animateTo(_here); // smooth glide back to the user
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
      backgroundColor: const Color(0xFF15161A),
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
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF15161A),
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
              itemCount: _log.length,
              itemBuilder: (_, i) => _logTile(_log[i]),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _logTile(Msg m) {
    final (bg, fg) = switch (m.kind) {
      'guide' => (_accent.withValues(alpha: 0.12), Colors.white),
      'reply' => (const Color(0x2234D399), Colors.white),
      'you' => (Colors.white10, Colors.white70),
      _ => (Colors.white10, Colors.white38),
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
      backgroundColor: const Color(0xFF15161A),
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => StatefulBuilder(
        builder: (c, setSheet) => Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, MediaQuery.of(ctx).viewInsets.bottom + 24),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(l.settings, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            TextField(
              controller: _urlCtrl,
              enabled: !_active,
              decoration: InputDecoration(
                labelText: l.wsUrl,
                filled: true,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 6),
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
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
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
                child: Padding(padding: const EdgeInsets.only(bottom: 10), child: _followFab(l)),
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
