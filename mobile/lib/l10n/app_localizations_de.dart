// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for German (`de`).
class AppLocalizationsDe extends AppLocalizations {
  AppLocalizationsDe([String locale = 'de']) : super(locale);

  @override
  String get bgNotifTitle => 'AI Audio Guide';

  @override
  String get bgNotifText => 'Ich erzähle dir von Orten in deiner Nähe';

  @override
  String get connect => 'Verbinden';

  @override
  String get disconnect => 'Trennen';

  @override
  String get startWalk => 'Spaziergang';

  @override
  String get startGps => 'GPS';

  @override
  String get stop => 'Stopp';

  @override
  String get ask => 'Fragen';

  @override
  String get askHint => 'Frag den Guide… (z. B. Läden überspringen)';

  @override
  String get micAsk => 'Per Sprache fragen';

  @override
  String get micStop => 'Stoppen und senden';

  @override
  String get clearFeed => 'Verlauf löschen';

  @override
  String get voiceOn => 'Sprachausgabe an';

  @override
  String get voiceOff => 'Sprachausgabe aus';

  @override
  String get language => 'Sprache';

  @override
  String get settings => 'Einstellungen';

  @override
  String get history => 'Verlauf';

  @override
  String get simulatedWalk => 'Simulierter Spaziergang (Demo)';

  @override
  String get compassNorth => 'Nach Norden ausrichten';

  @override
  String get emptyHint =>
      'Tippe auf „Spaziergang“.\nDer Guide erzählt dir von Orten in deiner Nähe.';

  @override
  String get following => 'Folge dir';

  @override
  String get freeBrowse => 'Freie Ansicht – tippen zum Folgen';

  @override
  String get appearance => 'Darstellung';

  @override
  String get themeSystem => 'System';

  @override
  String get themeLight => 'Hell';

  @override
  String get themeDark => 'Dunkel';

  @override
  String get themeTopic => 'Tour-Thema';

  @override
  String get themeAuto => 'Auto';

  @override
  String get themeHistory => 'Geschichte';

  @override
  String get themeArchitecture => 'Architektur';

  @override
  String get themePeople => 'Menschen';

  @override
  String get themeCulture => 'Kultur';

  @override
  String get themeLegends => 'Legenden';

  @override
  String get route => 'Route';

  @override
  String get walkHistory => 'Spaziergangsverlauf';

  @override
  String get walkHistoryEmptyTitle => 'Noch keine Spaziergänge';

  @override
  String get walkHistoryEmptySubtitle =>
      'Deine bisherigen Spaziergänge erscheinen hier, sobald es Konten gibt.';

  @override
  String get nearbyHint => 'Geh näher heran, und der Guide erzählt dir davon.';

  @override
  String get zoomIn => 'Vergrößern';

  @override
  String get zoomOut => 'Verkleinern';

  @override
  String get chipReconnecting => 'Wiederverbindung…';

  @override
  String get chipNotConnected => 'nicht verbunden';

  @override
  String get chipSpeaking => 'spricht';

  @override
  String get chipScoring => 'analysiert';

  @override
  String get chipNarrating => 'erzählt';

  @override
  String get chipSwitching => 'wechselt';

  @override
  String get chipListening => 'hört zu';

  @override
  String get chipAnswering => 'antwortet';

  @override
  String get chipExpanding => 'erweitert Radius';

  @override
  String get chipReady => 'bereit';

  @override
  String get chipError => 'Quelle nicht verfügbar';

  @override
  String get chipOffline => 'offline';

  @override
  String metaConnectionLost(int seconds) {
    return 'Verbindung verloren, Wiederverbindung in ${seconds}s…';
  }

  @override
  String get metaGeoDisabled => 'Standort ist im System deaktiviert';

  @override
  String get metaGeoNoPermission => 'Keine Standortberechtigung';

  @override
  String metaGpsUnavailable(String error) {
    return 'GPS auf dieser Plattform nicht verfügbar: $error';
  }

  @override
  String metaGpsError(String error) {
    return 'GPS: $error';
  }

  @override
  String get metaRealGpsOn => 'Echtes GPS an';

  @override
  String get metaMicNoPermission => 'Kein Mikrofonzugriff';

  @override
  String metaVoiceUnavailable(String lang) {
    return 'Stimme für $lang ist auf diesem Gerät nicht verfügbar';
  }
}
