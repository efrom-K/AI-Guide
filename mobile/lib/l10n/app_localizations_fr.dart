// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class AppLocalizationsFr extends AppLocalizations {
  AppLocalizationsFr([String locale = 'fr']) : super(locale);

  @override
  String get connect => 'Connecter';

  @override
  String get disconnect => 'Déconnecter';

  @override
  String get startWalk => 'Balade';

  @override
  String get startGps => 'GPS';

  @override
  String get stop => 'Arrêter';

  @override
  String get ask => 'Demander';

  @override
  String get askHint => 'Demandez au guide… (p. ex. ignore les boutiques)';

  @override
  String get micAsk => 'Demander à la voix';

  @override
  String get micStop => 'Arrêter et envoyer';

  @override
  String get clearFeed => 'Effacer le journal';

  @override
  String get voiceOn => 'Narration activée';

  @override
  String get voiceOff => 'Narration désactivée';

  @override
  String get language => 'Langue';

  @override
  String get settings => 'Réglages';

  @override
  String get history => 'Historique';

  @override
  String get simulatedWalk => 'Balade simulée (démo)';

  @override
  String get compassNorth => 'Orienter au nord';

  @override
  String get emptyHint =>
      'Appuyez sur « Balade ».\nLe guide vous parlera des lieux autour de vous.';

  @override
  String get following => 'Je vous suis';

  @override
  String get freeBrowse => 'Navigation libre — appuyez pour suivre';

  @override
  String get appearance => 'Apparence';

  @override
  String get themeSystem => 'Système';

  @override
  String get themeLight => 'Clair';

  @override
  String get themeDark => 'Sombre';

  @override
  String get themeTopic => 'Thème de la visite';

  @override
  String get themeAuto => 'Auto';

  @override
  String get themeHistory => 'Histoire';

  @override
  String get themeArchitecture => 'Architecture';

  @override
  String get themePeople => 'Personnages';

  @override
  String get themeCulture => 'Culture';

  @override
  String get themeLegends => 'Légendes';

  @override
  String get route => 'Itinéraire';

  @override
  String get walkHistory => 'Historique des balades';

  @override
  String get walkHistoryEmptyTitle => 'Aucune balade pour l\'instant';

  @override
  String get walkHistoryEmptySubtitle =>
      'Vos balades passées apparaîtront ici une fois les comptes disponibles.';

  @override
  String get nearbyHint => 'Approchez-vous et le guide vous en parlera.';

  @override
  String get zoomIn => 'Zoom avant';

  @override
  String get zoomOut => 'Zoom arrière';

  @override
  String get chipReconnecting => 'reconnexion…';

  @override
  String get chipNotConnected => 'non connecté';

  @override
  String get chipSpeaking => 'parle';

  @override
  String get chipScoring => 'analyse';

  @override
  String get chipNarrating => 'récit';

  @override
  String get chipSwitching => 'changement';

  @override
  String get chipListening => 'écoute';

  @override
  String get chipAnswering => 'réponse';

  @override
  String get chipExpanding => 'élargit le rayon';

  @override
  String get chipReady => 'prêt';

  @override
  String get chipError => 'source indisponible';

  @override
  String get chipOffline => 'hors ligne';

  @override
  String metaConnectionLost(int seconds) {
    return 'connexion perdue, reconnexion dans ${seconds}s…';
  }

  @override
  String get metaGeoDisabled =>
      'La localisation est désactivée dans le système';

  @override
  String get metaGeoNoPermission => 'Pas d\'autorisation de localisation';

  @override
  String metaGpsUnavailable(String error) {
    return 'GPS indisponible sur cette plateforme : $error';
  }

  @override
  String metaGpsError(String error) {
    return 'GPS : $error';
  }

  @override
  String get metaRealGpsOn => 'GPS réel activé';

  @override
  String get metaMicNoPermission => 'Pas d\'accès au microphone';

  @override
  String metaVoiceUnavailable(String lang) {
    return 'la voix pour $lang n\'est pas disponible sur cet appareil';
  }
}
