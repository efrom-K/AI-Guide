// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get connect => 'Connect';

  @override
  String get disconnect => 'Disconnect';

  @override
  String get wsUrl => 'WebSocket URL';

  @override
  String get startWalk => '▶ Walk';

  @override
  String get startGps => '▶ GPS';

  @override
  String get stop => '⏸ Stop';

  @override
  String get gps => 'GPS';

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
  String get feedEmpty => 'Feed is empty';

  @override
  String get voiceOn => 'Narration on';

  @override
  String get voiceOff => 'Narration off';

  @override
  String get language => 'Language';

  @override
  String get emptyHint =>
      'Connect and tap “Walk”.\nThe guide will tell you about places around you.';

  @override
  String get following => 'Following you';

  @override
  String get freeBrowse => 'Free browse — tap to follow';

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
  String metaConnecting(String url) {
    return '· connecting $url';
  }

  @override
  String metaConnectionLost(int seconds) {
    return '· connection lost, reconnecting in ${seconds}s…';
  }

  @override
  String get metaGeoDisabled => '⚠ Location is turned off in system settings';

  @override
  String get metaGeoNoPermission => '⚠ No location permission';

  @override
  String metaGpsUnavailable(String error) {
    return '⚠ GPS unavailable on this platform: $error';
  }

  @override
  String metaGpsError(String error) {
    return '⚠ GPS: $error';
  }

  @override
  String get metaRealGpsOn => '· real GPS on';

  @override
  String get metaMicNoPermission => '⚠ No microphone access';

  @override
  String metaSentByVoice(int bytes) {
    return '· sent by voice ($bytes B)';
  }

  @override
  String metaVoiceUnavailable(String lang) {
    return '· voice for $lang is unavailable on this device';
  }
}
