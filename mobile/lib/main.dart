// AI Audio Guide — Flutter client (web/desktop).
//
// Thin WebSocket client: connect to the backend /ws, simulate a walk along a
// route (sends positions), and show the guide's narration/replies. On mobile
// (Stage 6b) the simulated walk is replaced by real GPS + compass + mic.
//
//   cd mobile && flutter run -d chrome      (backend must be running on :8000)

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

void main() => runApp(const GuideApp());

class GuideApp extends StatelessWidget {
  const GuideApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Audio Guide',
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      home: const HomePage(),
    );
  }
}

class Msg {
  final String kind; // guide | reply | you | meta
  final String text;
  Msg(this.kind, this.text);
}

// Red Square waypoints (lat, lon) — same route as the backend sim.
const List<List<double>> kRoute = [
  [55.7525, 37.6231],
  [55.7537, 37.6205],
  [55.7547, 37.6196],
  [55.7553, 37.6178],
];

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
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

  // Position source: false = simulated route, true = real device GPS.
  bool _useRealGps = false;
  StreamSubscription<Position>? _gpsSub;

  // On-device TTS — the guide speaks the narration aloud.
  final FlutterTts _tts = FlutterTts();
  bool _voice = true; // speaker on/off

  // Microphone — ask the guide by voice (barge-in).
  final AudioRecorder _rec = AudioRecorder();
  bool _recording = false;

  // UI state.
  bool _speaking = false; // TTS currently talking
  String? _lastPos; // "55.7525, 37.6231"
  String? _lastPlace; // place_id of the current narration
  bool _wantConnected = false; // user intends a live connection (drives auto-reconnect)
  Timer? _reconnectTimer;
  int _retries = 0;

  @override
  void initState() {
    super.initState();
    _initTts();
  }

  Future<void> _initTts() async {
    await _tts.setLanguage('ru-RU');
    await _tts.setSpeechRate(0.5); // calmer, guide-like pace
    await _tts.setPitch(1.0);
    await _tts.awaitSpeakCompletion(true);
    _tts.setStartHandler(() => setState(() => _speaking = true));
    _tts.setCompletionHandler(() => setState(() => _speaking = false));
    _tts.setCancelHandler(() => setState(() => _speaking = false));
  }

  // Speak text now, cutting off whatever is playing (seamless switch / barge-in).
  Future<void> _say(String text) async {
    if (!_voice) return;
    await _tts.stop();
    await _tts.speak(text);
  }

  void _add(String kind, String text) {
    setState(() => _log.add(Msg(kind, text)));
    // Keep the newest message in view.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
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
            setState(() => _lastPlace = m['place_id'] as String?);
            _add('guide', t);
            _say(t);
            break;
          case 'reply':
            final t = m['text'] as String;
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
      _add('meta', '· подключение ${_urlCtrl.text}');
    });
  }

  // Socket dropped: reflect it, and auto-reconnect if the user still wants to be on.
  void _onDisconnected() {
    setState(() => _connected = false);
    if (!_wantConnected) return;
    final delay = Duration(seconds: (1 << _retries).clamp(1, 16)); // 1,2,4,8,16s
    _retries++;
    _add('meta', '· связь потеряна, переподключение через ${delay.inSeconds}s…');
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
        pts.add({
          'lat': a[0] + (b[0] - a[0]) * f,
          'lon': a[1] + (b[1] - a[1]) * f,
          'dir': brg,
        });
      }
    }
    final last = kRoute.last;
    pts.add({'lat': last[0], 'lon': last[1], 'dir': 0});
    return pts;
  }

  // Start whichever source the toggle selects.
  void _start() => _useRealGps ? _startGps() : _startWalk();

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

  // Send a position and remember it for the status footer.
  void _sendPosition(double lat, double lon, double dir, String pace) {
    _send({
      'type': 'position',
      'lat': lat,
      'lon': lon,
      'direction_deg': dir,
      'gaze_confidence': 'low',
      'pace': pace,
    });
    setState(() => _lastPos = '${lat.toStringAsFixed(5)}, ${lon.toStringAsFixed(5)}');
  }

  // ---- real GPS ----------------------------------------------------------
  // Heading comes from the GPS course (movement vector), not a compass — so
  // gaze_confidence is always 'low' here, matching the documented fallback
  // (compass is unreliable when the phone is in a pocket).
  Future<void> _startGps() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        _add('meta', '⚠ Геолокация выключена в системе');
        return;
      }
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.denied ||
          perm == LocationPermission.deniedForever) {
        _add('meta', '⚠ Нет разрешения на геолокацию');
        return;
      }
    } catch (e) {
      _add('meta', '⚠ GPS недоступен на этой платформе: $e');
      return;
    }

    const settings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 5, // metres between updates
    );
    _gpsSub = Geolocator.getPositionStream(locationSettings: settings).listen(
      (pos) => _sendPosition(
        pos.latitude,
        pos.longitude,
        pos.heading >= 0 ? pos.heading : 0.0,
        pos.speed > 1.5 ? 'fast' : 'slow',
      ),
      onError: (e) => _add('meta', '⚠ GPS: $e'),
    );
    _add('meta', '· реальный GPS включён');
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
    if (!await _rec.hasPermission()) {
      _add('meta', '⚠ Нет доступа к микрофону');
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
    final path = await _rec.stop();
    setState(() => _recording = false);
    if (path == null) return;
    final bytes = await File(path).readAsBytes();
    if (bytes.isEmpty) return;
    _send({'type': 'audio', 'data_b64': base64Encode(bytes), 'format': 'wav'});
    _add('meta', '· отправлено голосом (${bytes.length} Б)');
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
    super.dispose();
  }

  Color _bg(String kind) => switch (kind) {
        'guide' => const Color(0xFFEEF2FF),
        'reply' => const Color(0xFFECFDF5),
        'you' => const Color(0xFFF3F4F6),
        _ => const Color(0xFFFFFBEB),
      };

  // Coloured chip for the agent state (or connection status).
  Widget _statusChip() {
    final (label, color, icon) = switch (true) {
      _ when !_connected && _wantConnected => ('переподключение…', Colors.orange, Icons.sync),
      _ when !_connected => ('не подключено', Colors.grey, Icons.cloud_off),
      _ when _speaking => ('говорит', Colors.indigo, Icons.graphic_eq),
      _ => switch (_state) {
          'scoring' => ('анализ', Colors.blueGrey, Icons.search),
          'narrating' => ('рассказ', Colors.indigo, Icons.record_voice_over),
          'switching' => ('переключение', Colors.indigo, Icons.swap_horiz),
          'listening' => ('слушает', Colors.teal, Icons.hearing),
          'answering' => ('отвечает', Colors.teal, Icons.question_answer),
          'expanding' => ('расширяет радиус', Colors.blueGrey, Icons.zoom_out_map),
          _ => ('готов', Colors.green, Icons.check_circle),
        },
    };
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Chip(
        visualDensity: VisualDensity.compact,
        backgroundColor: color.withValues(alpha: 0.12),
        side: BorderSide(color: color.withValues(alpha: 0.4)),
        avatar: Icon(icon, size: 16, color: color),
        label: Text(label, style: TextStyle(fontSize: 12, color: color)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final walking = _walkTimer != null || _gpsSub != null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('🎧 AI Audio Guide'),
        actions: [
          Center(child: _statusChip()),
          IconButton(
            tooltip: _log.isEmpty ? 'Лента пуста' : 'Очистить ленту',
            icon: const Icon(Icons.delete_sweep_outlined),
            onPressed: _log.isEmpty ? null : () => setState(_log.clear),
          ),
          IconButton(
            tooltip: _voice ? 'Озвучка включена' : 'Озвучка выключена',
            icon: Icon(_voice ? Icons.volume_up : Icons.volume_off),
            onPressed: _toggleVoice,
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _urlCtrl,
                  decoration: const InputDecoration(labelText: 'WebSocket URL', isDense: true),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _wantConnected ? _disconnect : _connect,
                child: Text(_wantConnected ? 'Отключиться' : 'Подключиться'),
              ),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              FilledButton.tonal(
                onPressed: _connected && !walking ? _start : null,
                child: Text(_useRealGps ? '▶ GPS' : '▶ Прогулка'),
              ),
              const SizedBox(width: 8),
              FilledButton.tonal(
                onPressed: walking ? _stopWalk : null,
                child: const Text('⏸ Стоп'),
              ),
              const Spacer(),
              const Text('GPS', style: TextStyle(fontSize: 13)),
              Switch(
                value: _useRealGps,
                // Can't switch source mid-walk.
                onChanged: walking
                    ? null
                    : (v) => setState(() => _useRealGps = v),
              ),
            ]),
            const SizedBox(height: 8),
            Expanded(
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.black12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: _log.isEmpty
                    ? const Center(
                        child: Text(
                          'Подключитесь и нажмите «Прогулка».\nГид расскажет про места вокруг.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.black38),
                        ),
                      )
                    : ListView.builder(
                        controller: _scroll,
                        itemCount: _log.length,
                        itemBuilder: (_, i) {
                          final m = _log[i];
                          return Container(
                            margin: const EdgeInsets.symmetric(vertical: 3),
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: _bg(m.kind),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(m.text),
                          );
                        },
                      ),
              ),
            ),
            // Footer: live position + current place id.
            if (_lastPos != null || _lastPlace != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(children: [
                  const Icon(Icons.place, size: 14, color: Colors.black45),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      [
                        if (_lastPos != null) _lastPos,
                        if (_lastPlace != null) '· $_lastPlace',
                      ].join(' '),
                      style: const TextStyle(fontSize: 12, color: Colors.black45),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ]),
              ),
            const SizedBox(height: 8),
            Row(children: [
              // Push to talk: tap to record, tap again to send.
              IconButton.filledTonal(
                tooltip: _recording ? 'Остановить и отправить' : 'Спросить голосом',
                isSelected: _recording,
                style: _recording
                    ? IconButton.styleFrom(backgroundColor: Colors.red.shade100)
                    : null,
                icon: Icon(_recording ? Icons.stop : Icons.mic,
                    color: _recording ? Colors.red : null),
                onPressed: _connected ? _toggleMic : null,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: _askCtrl,
                  decoration: const InputDecoration(
                    hintText: 'Спросить гида… (напр. пропускай магазины)',
                    isDense: true,
                  ),
                  onSubmitted: (_) => _ask(),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(onPressed: _connected ? _ask : null, child: const Text('Спросить')),
            ]),
          ],
        ),
      ),
    );
  }
}
