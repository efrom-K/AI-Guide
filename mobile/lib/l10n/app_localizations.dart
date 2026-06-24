import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_de.dart';
import 'app_localizations_en.dart';
import 'app_localizations_es.dart';
import 'app_localizations_fr.dart';
import 'app_localizations_it.dart';
import 'app_localizations_pt.dart';
import 'app_localizations_ru.dart';
import 'app_localizations_zh.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('de'),
    Locale('en'),
    Locale('es'),
    Locale('fr'),
    Locale('it'),
    Locale('pt'),
    Locale('ru'),
    Locale('zh')
  ];

  /// No description provided for @connect.
  ///
  /// In en, this message translates to:
  /// **'Connect'**
  String get connect;

  /// No description provided for @disconnect.
  ///
  /// In en, this message translates to:
  /// **'Disconnect'**
  String get disconnect;

  /// No description provided for @wsUrl.
  ///
  /// In en, this message translates to:
  /// **'WebSocket URL'**
  String get wsUrl;

  /// No description provided for @startWalk.
  ///
  /// In en, this message translates to:
  /// **'▶ Walk'**
  String get startWalk;

  /// No description provided for @startGps.
  ///
  /// In en, this message translates to:
  /// **'▶ GPS'**
  String get startGps;

  /// No description provided for @stop.
  ///
  /// In en, this message translates to:
  /// **'⏸ Stop'**
  String get stop;

  /// No description provided for @gps.
  ///
  /// In en, this message translates to:
  /// **'GPS'**
  String get gps;

  /// No description provided for @ask.
  ///
  /// In en, this message translates to:
  /// **'Ask'**
  String get ask;

  /// No description provided for @askHint.
  ///
  /// In en, this message translates to:
  /// **'Ask the guide… (e.g. skip shops)'**
  String get askHint;

  /// No description provided for @micAsk.
  ///
  /// In en, this message translates to:
  /// **'Ask by voice'**
  String get micAsk;

  /// No description provided for @micStop.
  ///
  /// In en, this message translates to:
  /// **'Stop and send'**
  String get micStop;

  /// No description provided for @clearFeed.
  ///
  /// In en, this message translates to:
  /// **'Clear feed'**
  String get clearFeed;

  /// No description provided for @feedEmpty.
  ///
  /// In en, this message translates to:
  /// **'Feed is empty'**
  String get feedEmpty;

  /// No description provided for @voiceOn.
  ///
  /// In en, this message translates to:
  /// **'Narration on'**
  String get voiceOn;

  /// No description provided for @voiceOff.
  ///
  /// In en, this message translates to:
  /// **'Narration off'**
  String get voiceOff;

  /// No description provided for @language.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get language;

  /// No description provided for @emptyHint.
  ///
  /// In en, this message translates to:
  /// **'Connect and tap “Walk”.\nThe guide will tell you about places around you.'**
  String get emptyHint;

  /// No description provided for @following.
  ///
  /// In en, this message translates to:
  /// **'Following you'**
  String get following;

  /// No description provided for @freeBrowse.
  ///
  /// In en, this message translates to:
  /// **'Free browse — tap to follow'**
  String get freeBrowse;

  /// No description provided for @chipReconnecting.
  ///
  /// In en, this message translates to:
  /// **'reconnecting…'**
  String get chipReconnecting;

  /// No description provided for @chipNotConnected.
  ///
  /// In en, this message translates to:
  /// **'not connected'**
  String get chipNotConnected;

  /// No description provided for @chipSpeaking.
  ///
  /// In en, this message translates to:
  /// **'speaking'**
  String get chipSpeaking;

  /// No description provided for @chipScoring.
  ///
  /// In en, this message translates to:
  /// **'analysing'**
  String get chipScoring;

  /// No description provided for @chipNarrating.
  ///
  /// In en, this message translates to:
  /// **'narrating'**
  String get chipNarrating;

  /// No description provided for @chipSwitching.
  ///
  /// In en, this message translates to:
  /// **'switching'**
  String get chipSwitching;

  /// No description provided for @chipListening.
  ///
  /// In en, this message translates to:
  /// **'listening'**
  String get chipListening;

  /// No description provided for @chipAnswering.
  ///
  /// In en, this message translates to:
  /// **'answering'**
  String get chipAnswering;

  /// No description provided for @chipExpanding.
  ///
  /// In en, this message translates to:
  /// **'expanding radius'**
  String get chipExpanding;

  /// No description provided for @chipReady.
  ///
  /// In en, this message translates to:
  /// **'ready'**
  String get chipReady;

  /// No description provided for @metaConnecting.
  ///
  /// In en, this message translates to:
  /// **'· connecting {url}'**
  String metaConnecting(String url);

  /// No description provided for @metaConnectionLost.
  ///
  /// In en, this message translates to:
  /// **'· connection lost, reconnecting in {seconds}s…'**
  String metaConnectionLost(int seconds);

  /// No description provided for @metaGeoDisabled.
  ///
  /// In en, this message translates to:
  /// **'⚠ Location is turned off in system settings'**
  String get metaGeoDisabled;

  /// No description provided for @metaGeoNoPermission.
  ///
  /// In en, this message translates to:
  /// **'⚠ No location permission'**
  String get metaGeoNoPermission;

  /// No description provided for @metaGpsUnavailable.
  ///
  /// In en, this message translates to:
  /// **'⚠ GPS unavailable on this platform: {error}'**
  String metaGpsUnavailable(String error);

  /// No description provided for @metaGpsError.
  ///
  /// In en, this message translates to:
  /// **'⚠ GPS: {error}'**
  String metaGpsError(String error);

  /// No description provided for @metaRealGpsOn.
  ///
  /// In en, this message translates to:
  /// **'· real GPS on'**
  String get metaRealGpsOn;

  /// No description provided for @metaMicNoPermission.
  ///
  /// In en, this message translates to:
  /// **'⚠ No microphone access'**
  String get metaMicNoPermission;

  /// No description provided for @metaSentByVoice.
  ///
  /// In en, this message translates to:
  /// **'· sent by voice ({bytes} B)'**
  String metaSentByVoice(int bytes);

  /// No description provided for @metaVoiceUnavailable.
  ///
  /// In en, this message translates to:
  /// **'· voice for {lang} is unavailable on this device'**
  String metaVoiceUnavailable(String lang);
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) => <String>[
        'de',
        'en',
        'es',
        'fr',
        'it',
        'pt',
        'ru',
        'zh'
      ].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'de':
      return AppLocalizationsDe();
    case 'en':
      return AppLocalizationsEn();
    case 'es':
      return AppLocalizationsEs();
    case 'fr':
      return AppLocalizationsFr();
    case 'it':
      return AppLocalizationsIt();
    case 'pt':
      return AppLocalizationsPt();
    case 'ru':
      return AppLocalizationsRu();
    case 'zh':
      return AppLocalizationsZh();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
