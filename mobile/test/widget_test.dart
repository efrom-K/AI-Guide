import 'package:ai_audio_guide/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('app shows title and connect button', (tester) async {
    await tester.pumpWidget(const GuideApp());
    expect(find.text('🎧 AI Audio Guide'), findsOneWidget);
    expect(find.text('Подключиться'), findsOneWidget);
  });
}
