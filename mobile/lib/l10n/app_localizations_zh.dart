// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Chinese (`zh`).
class AppLocalizationsZh extends AppLocalizations {
  AppLocalizationsZh([String locale = 'zh']) : super(locale);

  @override
  String get bgNotifTitle => 'AI Audio Guide';

  @override
  String get bgNotifText => '正在为您讲述周围的地点';

  @override
  String get bgNotifPaused => '导览已暂停';

  @override
  String get bgPause => '暂停';

  @override
  String get bgResume => '继续';

  @override
  String get connect => '连接';

  @override
  String get disconnect => '断开';

  @override
  String get startWalk => '漫步';

  @override
  String get startGps => 'GPS';

  @override
  String get stop => '停止';

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
  String get emptyHint => '点击“漫步”。\n导游会为你讲解周围的地点。';

  @override
  String get following => '正在跟随你';

  @override
  String get freeBrowse => '自由浏览——点击以跟随';

  @override
  String get appearance => '外观';

  @override
  String get themeSystem => '跟随系统';

  @override
  String get themeLight => '浅色';

  @override
  String get themeDark => '深色';

  @override
  String get themeTopic => '导览主题';

  @override
  String get themeAuto => '自动';

  @override
  String get themeHistory => '历史';

  @override
  String get themeArchitecture => '建筑';

  @override
  String get themePeople => '人物';

  @override
  String get themeCulture => '文化';

  @override
  String get themeLegends => '传说';

  @override
  String get route => '路线';

  @override
  String get walkHistory => '漫步记录';

  @override
  String get walkHistoryEmptyTitle => '还没有漫步记录';

  @override
  String get walkHistoryEmptySubtitle => '账号功能上线后，你过去的漫步会显示在这里。';

  @override
  String get nearbyHint => '走近一些，导游就会为你讲解。';

  @override
  String get zoomIn => '放大';

  @override
  String get zoomOut => '缩小';

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
  String get chipError => '数据源不可用';

  @override
  String get chipOffline => '离线';

  @override
  String metaConnectionLost(int seconds) {
    return '连接断开，$seconds 秒后重连……';
  }

  @override
  String get metaGeoDisabled => '系统中已关闭定位';

  @override
  String get metaGeoNoPermission => '没有定位权限';

  @override
  String metaGpsUnavailable(String error) {
    return '此平台不支持 GPS：$error';
  }

  @override
  String metaGpsError(String error) {
    return 'GPS：$error';
  }

  @override
  String get metaRealGpsOn => '已开启真实 GPS';

  @override
  String get metaMicNoPermission => '没有麦克风权限';

  @override
  String metaVoiceUnavailable(String lang) {
    return '此设备不支持 $lang 语音';
  }
}
