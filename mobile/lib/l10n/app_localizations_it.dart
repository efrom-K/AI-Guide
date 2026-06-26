// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Italian (`it`).
class AppLocalizationsIt extends AppLocalizations {
  AppLocalizationsIt([String locale = 'it']) : super(locale);

  @override
  String get connect => 'Connetti';

  @override
  String get disconnect => 'Disconnetti';

  @override
  String get wsUrl => 'URL WebSocket';

  @override
  String get startWalk => '▶ Passeggiata';

  @override
  String get startGps => '▶ GPS';

  @override
  String get stop => '⏸ Stop';

  @override
  String get gps => 'GPS';

  @override
  String get ask => 'Chiedi';

  @override
  String get askHint => 'Chiedi alla guida… (es. salta i negozi)';

  @override
  String get micAsk => 'Chiedi a voce';

  @override
  String get micStop => 'Ferma e invia';

  @override
  String get clearFeed => 'Cancella il registro';

  @override
  String get feedEmpty => 'Il registro è vuoto';

  @override
  String get voiceOn => 'Narrazione attiva';

  @override
  String get voiceOff => 'Narrazione disattivata';

  @override
  String get language => 'Lingua';

  @override
  String get settings => 'Impostazioni';

  @override
  String get history => 'Cronologia';

  @override
  String get simulatedWalk => 'Passeggiata simulata (demo)';

  @override
  String get compassNorth => 'Orienta a nord';

  @override
  String get emptyHint =>
      'Connettiti e tocca «Passeggiata».\nLa guida ti racconterà i luoghi intorno a te.';

  @override
  String get following => 'Ti sto seguendo';

  @override
  String get freeBrowse => 'Esplorazione libera — tocca per seguire';

  @override
  String get chipReconnecting => 'riconnessione…';

  @override
  String get chipNotConnected => 'non connesso';

  @override
  String get chipSpeaking => 'parla';

  @override
  String get chipScoring => 'analisi';

  @override
  String get chipNarrating => 'racconto';

  @override
  String get chipSwitching => 'cambio';

  @override
  String get chipListening => 'ascolta';

  @override
  String get chipAnswering => 'risponde';

  @override
  String get chipExpanding => 'amplia il raggio';

  @override
  String get chipReady => 'pronto';

  @override
  String get chipError => 'fonte non disponibile';

  @override
  String get chipOffline => 'offline';

  @override
  String metaConnecting(String url) {
    return '· connessione $url';
  }

  @override
  String metaConnectionLost(int seconds) {
    return '· connessione persa, riconnessione tra ${seconds}s…';
  }

  @override
  String get metaGeoDisabled =>
      '⚠ La geolocalizzazione è disattivata nel sistema';

  @override
  String get metaGeoNoPermission => '⚠ Nessun permesso di geolocalizzazione';

  @override
  String metaGpsUnavailable(String error) {
    return '⚠ GPS non disponibile su questa piattaforma: $error';
  }

  @override
  String metaGpsError(String error) {
    return '⚠ GPS: $error';
  }

  @override
  String get metaRealGpsOn => '· GPS reale attivo';

  @override
  String get metaMicNoPermission => '⚠ Nessun accesso al microfono';

  @override
  String metaSentByVoice(int bytes) {
    return '· inviato a voce ($bytes B)';
  }

  @override
  String metaVoiceUnavailable(String lang) {
    return '· la voce per $lang non è disponibile su questo dispositivo';
  }
}
