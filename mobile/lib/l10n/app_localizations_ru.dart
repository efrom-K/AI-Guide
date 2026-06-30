// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Russian (`ru`).
class AppLocalizationsRu extends AppLocalizations {
  AppLocalizationsRu([String locale = 'ru']) : super(locale);

  @override
  String get bgNotifTitle => 'AI Audio Guide';

  @override
  String get bgNotifText => 'Рассказываю о местах вокруг вас';

  @override
  String get connect => 'Подключиться';

  @override
  String get disconnect => 'Отключиться';

  @override
  String get startWalk => 'Прогулка';

  @override
  String get startGps => 'GPS';

  @override
  String get stop => 'Стоп';

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
  String get compassNorth => 'На север';

  @override
  String get emptyHint =>
      'Нажмите «Прогулка».\nГид расскажет про места вокруг.';

  @override
  String get following => 'Следую за вами';

  @override
  String get freeBrowse => 'Свободный просмотр — нажмите, чтобы следовать';

  @override
  String get appearance => 'Оформление';

  @override
  String get themeSystem => 'Система';

  @override
  String get themeLight => 'Светлая';

  @override
  String get themeDark => 'Тёмная';

  @override
  String get themeTopic => 'Тема рассказа';

  @override
  String get themeAuto => 'Авто';

  @override
  String get themeHistory => 'История';

  @override
  String get themeArchitecture => 'Архитектура';

  @override
  String get themePeople => 'Люди';

  @override
  String get themeCulture => 'Культура';

  @override
  String get themeLegends => 'Легенды';

  @override
  String get route => 'Маршрут';

  @override
  String get walkHistory => 'Истории прогулок';

  @override
  String get walkHistoryEmptyTitle => 'Пока нет прогулок';

  @override
  String get walkHistoryEmptySubtitle =>
      'Ваши прошлые прогулки появятся здесь, когда добавим аккаунты.';

  @override
  String get nearbyHint => 'Подойдите ближе — гид расскажет о нём.';

  @override
  String get zoomIn => 'Приблизить';

  @override
  String get zoomOut => 'Отдалить';

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
  String get chipError => 'источник недоступен';

  @override
  String get chipOffline => 'оффлайн';

  @override
  String metaConnectionLost(int seconds) {
    return 'Связь потеряна, переподключение через ${seconds}s…';
  }

  @override
  String get metaGeoDisabled => 'Геолокация выключена в системе';

  @override
  String get metaGeoNoPermission => 'Нет разрешения на геолокацию';

  @override
  String metaGpsUnavailable(String error) {
    return 'GPS недоступен на этой платформе: $error';
  }

  @override
  String metaGpsError(String error) {
    return 'GPS: $error';
  }

  @override
  String get metaRealGpsOn => 'Реальный GPS включён';

  @override
  String get metaMicNoPermission => 'Нет доступа к микрофону';

  @override
  String metaVoiceUnavailable(String lang) {
    return 'Голос $lang недоступен на устройстве';
  }
}
