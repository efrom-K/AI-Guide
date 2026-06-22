// AI Audio Guide — Flutter client (Stage 0 skeleton).
//
// For now this only proves the WebSocket transport end-to-end: connect to the
// backend `/ws`, send a position, and show echoed messages. Sensors, audio
// streaming and the mic (barge-in) are added in Stage 6.
//
// Build requires the Flutter SDK: `cd mobile && flutter pub get && flutter run`.

import 'dart:convert';

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

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  // Android emulator reaches host machine via 10.0.2.2; adjust for a device.
  static const String _wsUrl = 'ws://10.0.2.2:8000/ws';

  WebSocketChannel? _channel;
  final List<String> _log = [];
  bool _connected = false;

  void _connect() {
    final ch = WebSocketChannel.connect(Uri.parse(_wsUrl));
    ch.stream.listen(
      (msg) => setState(() => _log.add('← $msg')),
      onDone: () => setState(() => _connected = false),
      onError: (e) => setState(() => _log.add('! $e')),
    );
    setState(() {
      _channel = ch;
      _connected = true;
      _log.add('· connecting $_wsUrl');
    });
  }

  void _sendPosition() {
    final payload = jsonEncode({
      'type': 'position',
      'lat': 55.7558,
      'lon': 37.6173,
      'gaze_confidence': 'low',
      'pace': 'slow',
    });
    _channel?.sink.add(payload);
    setState(() => _log.add('→ $payload'));
  }

  @override
  void dispose() {
    _channel?.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('🎧 AI Audio Guide')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(Icons.circle,
                    size: 12, color: _connected ? Colors.green : Colors.red),
                const SizedBox(width: 8),
                Text(_connected ? 'connected' : 'disconnected'),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: [
                FilledButton(onPressed: _connect, child: const Text('Connect')),
                FilledButton.tonal(
                    onPressed: _connected ? _sendPosition : null,
                    child: const Text('Send position')),
              ],
            ),
            const SizedBox(height: 12),
            Expanded(
              child: Container(
                padding: const EdgeInsets.all(8),
                color: Colors.black,
                child: ListView(
                  children: _log
                      .map((l) => Text(l,
                          style: const TextStyle(
                              color: Colors.greenAccent,
                              fontFamily: 'monospace',
                              fontSize: 12)))
                      .toList(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
