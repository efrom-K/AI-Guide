// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AppLocalizationsEs extends AppLocalizations {
  AppLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get connect => 'Conectar';

  @override
  String get disconnect => 'Desconectar';

  @override
  String get wsUrl => 'URL de WebSocket';

  @override
  String get startWalk => '▶ Paseo';

  @override
  String get startGps => '▶ GPS';

  @override
  String get stop => '⏸ Parar';

  @override
  String get gps => 'GPS';

  @override
  String get ask => 'Preguntar';

  @override
  String get askHint => 'Pregunta al guía… (p. ej. omite las tiendas)';

  @override
  String get micAsk => 'Preguntar por voz';

  @override
  String get micStop => 'Detener y enviar';

  @override
  String get clearFeed => 'Borrar el registro';

  @override
  String get feedEmpty => 'El registro está vacío';

  @override
  String get voiceOn => 'Narración activada';

  @override
  String get voiceOff => 'Narración desactivada';

  @override
  String get language => 'Idioma';

  @override
  String get settings => 'Ajustes';

  @override
  String get history => 'Historial';

  @override
  String get simulatedWalk => 'Paseo simulado (demo)';

  @override
  String get compassNorth => 'Orientar al norte';

  @override
  String get emptyHint =>
      'Conéctate y pulsa «Paseo».\nEl guía te hablará de los lugares a tu alrededor.';

  @override
  String get following => 'Siguiéndote';

  @override
  String get freeBrowse => 'Exploración libre: toca para seguir';

  @override
  String get chipReconnecting => 'reconectando…';

  @override
  String get chipNotConnected => 'sin conexión';

  @override
  String get chipSpeaking => 'hablando';

  @override
  String get chipScoring => 'analizando';

  @override
  String get chipNarrating => 'narrando';

  @override
  String get chipSwitching => 'cambiando';

  @override
  String get chipListening => 'escuchando';

  @override
  String get chipAnswering => 'respondiendo';

  @override
  String get chipExpanding => 'ampliando radio';

  @override
  String get chipReady => 'listo';

  @override
  String metaConnecting(String url) {
    return '· conectando $url';
  }

  @override
  String metaConnectionLost(int seconds) {
    return '· conexión perdida, reconectando en ${seconds}s…';
  }

  @override
  String get metaGeoDisabled => '⚠ La ubicación está desactivada en el sistema';

  @override
  String get metaGeoNoPermission => '⚠ Sin permiso de ubicación';

  @override
  String metaGpsUnavailable(String error) {
    return '⚠ GPS no disponible en esta plataforma: $error';
  }

  @override
  String metaGpsError(String error) {
    return '⚠ GPS: $error';
  }

  @override
  String get metaRealGpsOn => '· GPS real activado';

  @override
  String get metaMicNoPermission => '⚠ Sin acceso al micrófono';

  @override
  String metaSentByVoice(int bytes) {
    return '· enviado por voz ($bytes B)';
  }

  @override
  String metaVoiceUnavailable(String lang) {
    return '· la voz para $lang no está disponible en este dispositivo';
  }
}
