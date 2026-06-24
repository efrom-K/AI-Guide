// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Portuguese (`pt`).
class AppLocalizationsPt extends AppLocalizations {
  AppLocalizationsPt([String locale = 'pt']) : super(locale);

  @override
  String get connect => 'Conectar';

  @override
  String get disconnect => 'Desconectar';

  @override
  String get wsUrl => 'URL do WebSocket';

  @override
  String get startWalk => '▶ Passeio';

  @override
  String get startGps => '▶ GPS';

  @override
  String get stop => '⏸ Parar';

  @override
  String get gps => 'GPS';

  @override
  String get ask => 'Perguntar';

  @override
  String get askHint => 'Pergunte ao guia… (ex.: pule as lojas)';

  @override
  String get micAsk => 'Perguntar por voz';

  @override
  String get micStop => 'Parar e enviar';

  @override
  String get clearFeed => 'Limpar o histórico';

  @override
  String get feedEmpty => 'O histórico está vazio';

  @override
  String get voiceOn => 'Narração ativada';

  @override
  String get voiceOff => 'Narração desativada';

  @override
  String get language => 'Idioma';

  @override
  String get settings => 'Configurações';

  @override
  String get history => 'Histórico';

  @override
  String get simulatedWalk => 'Passeio simulado (demo)';

  @override
  String get emptyHint =>
      'Conecte-se e toque em «Passeio».\nO guia vai falar sobre os lugares ao seu redor.';

  @override
  String get following => 'Seguindo você';

  @override
  String get freeBrowse => 'Navegação livre — toque para seguir';

  @override
  String get chipReconnecting => 'reconectando…';

  @override
  String get chipNotConnected => 'sem conexão';

  @override
  String get chipSpeaking => 'falando';

  @override
  String get chipScoring => 'analisando';

  @override
  String get chipNarrating => 'narrando';

  @override
  String get chipSwitching => 'alternando';

  @override
  String get chipListening => 'ouvindo';

  @override
  String get chipAnswering => 'respondendo';

  @override
  String get chipExpanding => 'ampliando o raio';

  @override
  String get chipReady => 'pronto';

  @override
  String metaConnecting(String url) {
    return '· conectando $url';
  }

  @override
  String metaConnectionLost(int seconds) {
    return '· conexão perdida, reconectando em ${seconds}s…';
  }

  @override
  String get metaGeoDisabled => '⚠ A localização está desativada no sistema';

  @override
  String get metaGeoNoPermission => '⚠ Sem permissão de localização';

  @override
  String metaGpsUnavailable(String error) {
    return '⚠ GPS indisponível nesta plataforma: $error';
  }

  @override
  String metaGpsError(String error) {
    return '⚠ GPS: $error';
  }

  @override
  String get metaRealGpsOn => '· GPS real ativado';

  @override
  String get metaMicNoPermission => '⚠ Sem acesso ao microfone';

  @override
  String metaSentByVoice(int bytes) {
    return '· enviado por voz ($bytes B)';
  }

  @override
  String metaVoiceUnavailable(String lang) {
    return '· a voz para $lang não está disponível neste dispositivo';
  }
}
