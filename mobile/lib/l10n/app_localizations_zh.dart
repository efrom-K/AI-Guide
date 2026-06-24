// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Chinese (`zh`).
class AppLocalizationsZh extends AppLocalizations {
  AppLocalizationsZh([String locale = 'zh']) : super(locale);

  @override
  String get connect => '连接';

  @override
  String get disconnect => '断开';

  @override
  String get wsUrl => 'WebSocket 地址';

  @override
  String get startWalk => '▶ 漫步';

  @override
  String get startGps => '▶ GPS';

  @override
  String get stop => '⏸ 停止';

  @override
  String get gps => 'GPS';

  @override
  String get ask => '提问';

  @override
  String get askHint => '向导游提问……（例如：跳过商店）';

  @override
  String get micAsk => '语音提问';

  @override
  String get micStop => '停止并发送';

  @override
  String get clearFeed => '清空记录';

  @override
  String get feedEmpty => '记录为空';

  @override
  String get voiceOn => '已开启朗读';

  @override
  String get voiceOff => '已关闭朗读';

  @override
  String get language => '语言';

  @override
  String get settings => '设置';

  @override
  String get history => '历史';

  @override
  String get simulatedWalk => '模拟漫步（演示）';

  @override
  String get compassNorth => '朝向正北';

  @override
  String get emptyHint => '连接后点击“漫步”。\n导游会为你讲解周围的地点。';

  @override
  String get following => '正在跟随你';

  @override
  String get freeBrowse => '自由浏览——点击以跟随';

  @override
  String get chipReconnecting => '正在重连……';

  @override
  String get chipNotConnected => '未连接';

  @override
  String get chipSpeaking => '正在朗读';

  @override
  String get chipScoring => '分析中';

  @override
  String get chipNarrating => '讲解中';

  @override
  String get chipSwitching => '切换中';

  @override
  String get chipListening => '聆听中';

  @override
  String get chipAnswering => '回答中';

  @override
  String get chipExpanding => '扩大范围';

  @override
  String get chipReady => '就绪';

  @override
  String metaConnecting(String url) {
    return '· 正在连接 $url';
  }

  @override
  String metaConnectionLost(int seconds) {
    return '· 连接断开，$seconds 秒后重连……';
  }

  @override
  String get metaGeoDisabled => '⚠ 系统中已关闭定位';

  @override
  String get metaGeoNoPermission => '⚠ 没有定位权限';

  @override
  String metaGpsUnavailable(String error) {
    return '⚠ 此平台不支持 GPS：$error';
  }

  @override
  String metaGpsError(String error) {
    return '⚠ GPS：$error';
  }

  @override
  String get metaRealGpsOn => '· 已开启真实 GPS';

  @override
  String get metaMicNoPermission => '⚠ 没有麦克风权限';

  @override
  String metaSentByVoice(int bytes) {
    return '· 已通过语音发送（$bytes 字节）';
  }

  @override
  String metaVoiceUnavailable(String lang) {
    return '· 此设备不支持 $lang 语音';
  }
}
