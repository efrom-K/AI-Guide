import 'package:ai_audio_guide/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('app shows brand title and language selector', (tester) async {
    await tester.pumpWidget(const GuideApp());
    await tester.pump(); // let localizations delegates load

    // Brand title is not localized — stable across languages.
    expect(find.text('🎧 AI Audio Guide'), findsOneWidget);
    // The language picker is always present (locale-independent assertion).
    expect(find.byIcon(Icons.language), findsOneWidget);
  });
}
