// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Russian (`ru`).
class AppLocalizationsRu extends AppLocalizations {
  AppLocalizationsRu([String locale = 'ru']) : super(locale);

  @override
  String get connect => 'Подключиться';

  @override
  String get disconnect => 'Отключиться';

  @override
  String get wsUrl => 'WebSocket URL';

  @override
  String get startWalk => '▶ Прогулка';

  @override
  String get startGps => '▶ GPS';

  @override
  String get stop => '⏸ Стоп';

  @override
  String get gps => 'GPS';

  @override
  String get ask => 'Спросить';

  @override
  String get askHint => 'Спросить гида… (напр. пропускай магазины)';

  @override
  String get micAsk => 'Спросить голосом';

  @override
  String get micStop => 'Остановить и отправить';

  @override
  String get clearFeed => 'Очистить ленту';

  @override
  String get feedEmpty => 'Лента пуста';

  @override
  String get voiceOn => 'Озвучка включена';

  @override
  String get voiceOff => 'Озвучка выключена';

  @override
  String get language => 'Язык';

  @override
  String get settings => 'Настройки';

  @override
  String get history => 'История';

  @override
  String get simulatedWalk => 'Симуляция прогулки (демо)';

  @override
  String get emptyHint =>
      'Подключитесь и нажмите «Прогулка».\nГид расскажет про места вокруг.';

  @override
  String get following => 'Следую за вами';

  @override
  String get freeBrowse => 'Свободный просмотр — нажмите, чтобы следовать';

  @override
  String get chipReconnecting => 'переподключение…';

  @override
  String get chipNotConnected => 'не подключено';

  @override
  String get chipSpeaking => 'говорит';

  @override
  String get chipScoring => 'анализ';

  @override
  String get chipNarrating => 'рассказ';

  @override
  String get chipSwitching => 'переключение';

  @override
  String get chipListening => 'слушает';

  @override
  String get chipAnswering => 'отвечает';

  @override
  String get chipExpanding => 'расширяет радиус';

  @override
  String get chipReady => 'готов';

  @override
  String metaConnecting(String url) {
    return '· подключение $url';
  }

  @override
  String metaConnectionLost(int seconds) {
    return '· связь потеряна, переподключение через ${seconds}s…';
  }

  @override
  String get metaGeoDisabled => '⚠ Геолокация выключена в системе';

  @override
  String get metaGeoNoPermission => '⚠ Нет разрешения на геолокацию';

  @override
  String metaGpsUnavailable(String error) {
    return '⚠ GPS недоступен на этой платформе: $error';
  }

  @override
  String metaGpsError(String error) {
    return '⚠ GPS: $error';
  }

  @override
  String get metaRealGpsOn => '· реальный GPS включён';

  @override
  String get metaMicNoPermission => '⚠ Нет доступа к микрофону';

  @override
  String metaSentByVoice(int bytes) {
    return '· отправлено голосом ($bytes Б)';
  }

  @override
  String metaVoiceUnavailable(String lang) {
    return '· голос $lang недоступен на устройстве';
  }
}
