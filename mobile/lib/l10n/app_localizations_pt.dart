// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Portuguese (`pt`).
class AppLocalizationsPt extends AppLocalizations {
  AppLocalizationsPt([String locale = 'pt']) : super(locale);

  @override
  String get bgNotifTitle => 'AI Audio Guide';

  @override
  String get bgNotifText => 'Contando sobre os lugares ao seu redor';

  @override
  String get bgNotifPaused => 'Passeio em pausa';

  @override
  String get bgPause => 'Pausar';

  @override
  String get bgResume => 'Retomar';

  @override
  String get connect => 'Conectar';

  @override
  String get disconnect => 'Desconectar';

  @override
  String get startWalk => 'Passeio';

  @override
  String get startGps => 'GPS';

  @override
  String get stop => 'Parar';

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
  String get compassNorth => 'Orientar ao norte';

  @override
  String get emptyHint =>
      'Toque em «Passeio».\nO guia vai falar sobre os lugares ao seu redor.';

  @override
  String get following => 'Seguindo você';

  @override
  String get freeBrowse => 'Navegação livre — toque para seguir';

  @override
  String get appearance => 'Aparência';

  @override
  String get themeSystem => 'Sistema';

  @override
  String get themeLight => 'Claro';

  @override
  String get themeDark => 'Escuro';

  @override
  String get themeTopic => 'Tema do passeio';

  @override
  String get themeAuto => 'Auto';

  @override
  String get themeHistory => 'História';

  @override
  String get themeArchitecture => 'Arquitetura';

  @override
  String get themePeople => 'Pessoas';

  @override
  String get themeCulture => 'Cultura';

  @override
  String get themeLegends => 'Lendas';

  @override
  String get route => 'Rota';

  @override
  String get walkHistory => 'Histórico de passeios';

  @override
  String get walkHistoryEmptyTitle => 'Ainda sem passeios';

  @override
  String get walkHistoryEmptySubtitle =>
      'Seus passeios anteriores aparecerão aqui quando as contas chegarem.';

  @override
  String get nearbyHint => 'Chegue mais perto e o guia vai falar sobre ele.';

  @override
  String get zoomIn => 'Aproximar';

  @override
  String get zoomOut => 'Afastar';

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
  String get chipError => 'fonte indisponível';

  @override
  String get chipOffline => 'offline';

  @override
  String metaConnectionLost(int seconds) {
    return 'conexão perdida, reconectando em ${seconds}s…';
  }

  @override
  String get metaGeoDisabled => 'A localização está desativada no sistema';

  @override
  String get metaGeoNoPermission => 'Sem permissão de localização';

  @override
  String metaGpsUnavailable(String error) {
    return 'GPS indisponível nesta plataforma: $error';
  }

  @override
  String metaGpsError(String error) {
    return 'GPS: $error';
  }

  @override
  String get metaRealGpsOn => 'GPS real ativado';

  @override
  String get metaMicNoPermission => 'Sem acesso ao microfone';

  @override
  String metaVoiceUnavailable(String lang) {
    return 'a voz para $lang não está disponível neste dispositivo';
  }
}
