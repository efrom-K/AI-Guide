// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get bgNotifTitle => 'AI Audio Guide';

  @override
  String get bgNotifText => 'Telling you about places around you';

  @override
  String get connect => 'Connect';

  @override
  String get disconnect => 'Disconnect';

  @override
  String get startWalk => 'Walk';

  @override
  String get startGps => 'GPS';

  @override
  String get stop => 'Stop';

  @override
  String get ask => 'Ask';

  @override
  String get askHint => 'Ask the guide… (e.g. skip shops)';

  @override
  String get micAsk => 'Ask by voice';

  @override
  String get micStop => 'Stop and send';

  @override
  String get clearFeed => 'Clear feed';

  @override
  String get voiceOn => 'Narration on';

  @override
  String get voiceOff => 'Narration off';

  @override
  String get language => 'Language';

  @override
  String get settings => 'Settings';

  @override
  String get history => 'History';

  @override
  String get simulatedWalk => 'Simulated walk (demo)';

  @override
  String get compassNorth => 'Orient north';

  @override
  String get emptyHint =>
      'Tap “Walk”.\nThe guide will tell you about places around you.';

  @override
  String get following => 'Following you';

  @override
  String get freeBrowse => 'Free browse — tap to follow';

  @override
  String get appearance => 'Appearance';

  @override
  String get themeSystem => 'System';

  @override
  String get themeLight => 'Light';

  @override
  String get themeDark => 'Dark';

  @override
  String get themeTopic => 'Tour theme';

  @override
  String get themeAuto => 'Auto';

  @override
  String get themeHistory => 'History';

  @override
  String get themeArchitecture => 'Architecture';

  @override
  String get themePeople => 'People';

  @override
  String get themeCulture => 'Culture';

  @override
  String get themeLegends => 'Legends';

  @override
  String get route => 'Route';

  @override
  String get walkHistory => 'Walk history';

  @override
  String get walkHistoryEmptyTitle => 'No walks yet';

  @override
  String get walkHistoryEmptySubtitle =>
      'Your past walks will appear here once accounts arrive.';

  @override
  String get nearbyHint => 'Walk closer and the guide will tell you about it.';

  @override
  String get zoomIn => 'Zoom in';

  @override
  String get zoomOut => 'Zoom out';

  @override
  String get chipReconnecting => 'reconnecting…';

  @override
  String get chipNotConnected => 'not connected';

  @override
  String get chipSpeaking => 'speaking';

  @override
  String get chipScoring => 'analysing';

  @override
  String get chipNarrating => 'narrating';

  @override
  String get chipSwitching => 'switching';

  @override
  String get chipListening => 'listening';

  @override
  String get chipAnswering => 'answering';

  @override
  String get chipExpanding => 'expanding radius';

  @override
  String get chipReady => 'ready';

  @override
  String get chipError => 'source unavailable';

  @override
  String get chipOffline => 'offline';

  @override
  String metaConnectionLost(int seconds) {
    return 'Connection lost, reconnecting in ${seconds}s…';
  }

  @override
  String get metaGeoDisabled => 'Location is turned off in system settings';

  @override
  String get metaGeoNoPermission => 'No location permission';

  @override
  String metaGpsUnavailable(String error) {
    return 'GPS unavailable on this platform: $error';
  }

  @override
  String metaGpsError(String error) {
    return 'GPS: $error';
  }

  @override
  String get metaRealGpsOn => 'Real GPS on';

  @override
  String get metaMicNoPermission => 'No microphone access';

  @override
  String metaVoiceUnavailable(String lang) {
    return 'Voice for $lang is unavailable on this device';
  }
}
