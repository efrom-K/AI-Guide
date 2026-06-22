// AI Audio Guide — Flutter client (web/desktop).
//
// Thin WebSocket client: connect to the backend /ws, simulate a walk along a
// route (sends positions), and show the guide's narration/replies. On mobile
// (Stage 6b) the simulated walk is replaced by real GPS + compass + mic.
//
//   cd mobile && flutter run -d chrome      (backend must be running on :8000)

import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
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
  WebSocketChannel? _ch;
  bool _connected = false;
  String _state = '—';
  final List<Msg> _log = [];
  Timer? _walkTimer;
  List<Map<String, double>> _points = [];
  int _idx = 0;

  void _add(String kind, String text) => setState(() => _log.add(Msg(kind, text)));

  void _connect() {
    final ch = WebSocketChannel.connect(Uri.parse(_urlCtrl.text.trim()));
    ch.stream.listen(
      (data) {
        final m = jsonDecode(data as String) as Map<String, dynamic>;
        switch (m['type']) {
          case 'state':
            setState(() => _state = m['state'] as String);
            break;
          case 'narration':
            _add('guide', m['text'] as String);
            break;
          case 'reply':
            _add('reply', m['text'] as String);
            break;
          case 'transcript':
            _add('you', m['text'] as String);
            break;
          case 'error':
            _add('meta', '⚠ ${m['message']}');
            break;
        }
      },
      onDone: () => setState(() => _connected = false),
      onError: (e) => _add('meta', '⚠ $e'),
    );
    setState(() {
      _ch = ch;
      _connected = true;
      _add('meta', '· подключение ${_urlCtrl.text}');
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
      _send({
        'type': 'position',
        'lat': p['lat'],
        'lon': p['lon'],
        'direction_deg': p['dir'],
        'gaze_confidence': 'low',
        'pace': 'slow',
      });
    });
    setState(() {});
  }

  void _stopWalk() {
    _walkTimer?.cancel();
    _walkTimer = null;
    setState(() {});
  }

  void _ask() {
    final t = _askCtrl.text.trim();
    if (t.isEmpty || _ch == null) return;
    _add('you', t);
    _send({'type': 'utterance', 'text': t});
    _askCtrl.clear();
  }

  @override
  void dispose() {
    _walkTimer?.cancel();
    _ch?.sink.close();
    super.dispose();
  }

  Color _bg(String kind) => switch (kind) {
        'guide' => const Color(0xFFEEF2FF),
        'reply' => const Color(0xFFECFDF5),
        'you' => const Color(0xFFF3F4F6),
        _ => const Color(0xFFFFFBEB),
      };

  @override
  Widget build(BuildContext context) {
    final walking = _walkTimer != null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('🎧 AI Audio Guide'),
        actions: [
          Center(child: Text('  $_state  ', style: const TextStyle(fontSize: 13))),
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
                onPressed: _connected ? null : _connect,
                child: Text(_connected ? 'connected' : 'Подключиться'),
              ),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              FilledButton.tonal(
                onPressed: _connected && !walking ? _startWalk : null,
                child: const Text('▶ Прогулка'),
              ),
              const SizedBox(width: 8),
              FilledButton.tonal(
                onPressed: walking ? _stopWalk : null,
                child: const Text('⏸ Стоп'),
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
                child: ListView.builder(
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
            const SizedBox(height: 8),
            Row(children: [
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
