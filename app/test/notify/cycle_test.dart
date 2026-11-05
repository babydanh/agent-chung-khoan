import 'dart:convert';

import 'package:agent_ck/data/repository.dart';
import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/notify/cycle.dart';
import 'package:agent_ck/notify/notifier.dart';
import 'package:agent_ck/notify/planner.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

final now = DateTime.utc(2026, 11, 5, 3); // 10:00 in Vietnam

class FakeRepo implements Repository {
  FakeRepo(this.vn, {this.us = const MarketData(), this.fail = false});
  MarketData vn, us;
  bool fail;

  @override
  Future<MarketData> load(Market m) async {
    if (fail) throw RepositoryException('down');
    return m == Market.vn ? vn : us;
  }

  @override
  Future<List<DailyBar>> bars(Market m, String s, {int days = 60}) async => const [];
  @override
  Future<List<SignalRow>> signalHistory(Market m, String s, {int limit = 60}) async => const [];
}

class FakeNotifier implements Notifier {
  final shown = <Notice>[];
  @override
  Future<void> show(Notice n) async => shown.add(n);
  @override
  Future<bool> requestPermission() async => true;
}

MarketData vnData({int level = 3}) => MarketData(
      asof: now,
      quotes: [Quote(market: Market.vn, symbol: 'HPG', exchange: 'HOSE', price: 1, ref: 1)],
      signals: {'HPG': SignalRow(symbol: 'HPG', level: level, learning: false, items: const [SignalItem('S1')], asof: now)},
    );

String feed(String title, {int ageMin = 10}) {
  final t = now.subtract(Duration(minutes: ageMin));
  const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  String two(int n) => n.toString().padLeft(2, '0');
  return '<rss><channel><item><title>$title</title><link>https://x.test/1</link><pubDate>Thu, ${two(t.day)} ${m[t.month - 1]} ${t.year} ${two(t.hour)}:${two(t.minute)}:00 GMT</pubDate><description>d</description></item></channel></rss>';
}

MockClient web(String body, {int status = 200}) =>
    MockClient((_) async => http.Response(body, status, headers: {'content-type': 'application/rss+xml; charset=utf-8'}));

Future<SharedPreferences> prefs([Map<String, Object> v = const {}]) async {
  SharedPreferences.setMockInitialValues(v);
  return SharedPreferences.getInstance();
}

void main() {
  test('shows the notices of the moment and remembers them', () async {
    final p = await prefs({'watch_VN': ['HPG']});
    final n = FakeNotifier();
    final shown = await runCycle(prefs: p, repo: FakeRepo(vnData()), client: web(feed('HPG báo lãi quý 3 tăng 20%')), notifier: n, now: now);
    expect(shown, 2);
    expect(n.shown.map((x) => x.title), containsAll(['HPG · Mức 3', 'HPG · Kết quả kinh doanh']));
    final again = await runCycle(prefs: p, repo: FakeRepo(vnData()), client: web(feed('HPG báo lãi quý 3 tăng 20%')), notifier: n, now: now.add(const Duration(minutes: 30)));
    expect(again, 0);
    expect(n.shown, hasLength(2));
    expect((jsonDecode(p.getString('notify_state')!) as Map).keys, containsAll(['sent', 'queue', 'recent']));
  });

  test('the watchlist stored on the phone decides whether a modest headline is hot', () async {
    final story = feed('HPG ký hợp đồng cung cấp thép cho dự án mới'); // fresh contract: 49 points, 64 when watched
    final plain = FakeNotifier();
    await runCycle(prefs: await prefs(), repo: FakeRepo(vnData(level: 1)), client: web(story), notifier: plain, now: now);
    expect(plain.shown, isEmpty);
    final watched = FakeNotifier();
    await runCycle(prefs: await prefs({'watch_VN': ['HPG']}), repo: FakeRepo(vnData(level: 1)), client: web(story), notifier: watched, now: now);
    expect(watched.shown.single.title, 'HPG · Hợp đồng, dự án');
  });

  test('broken feeds do not stop the signal notices', () async {
    final n = FakeNotifier();
    final shown = await runCycle(prefs: await prefs(), repo: FakeRepo(vnData()), client: web('oops', status: 503), notifier: n, now: now);
    expect(shown, 1);
    expect(n.shown.single.title, 'HPG · Mức 3');
  });

  test('when the data cannot be read nothing is shown and the state is untouched', () async {
    final p = await prefs();
    final n = FakeNotifier();
    final shown = await runCycle(prefs: p, repo: FakeRepo(vnData(), fail: true), client: web(feed('x')), notifier: n, now: now);
    expect(shown, 0);
    expect(n.shown, isEmpty);
    expect(p.getString('notify_state'), isNull);
  });

  test('settings are read from the stored preferences', () async {
    final p = await prefs({'n_vn': false, 'n_us': false});
    final n = FakeNotifier();
    expect(await runCycle(prefs: p, repo: FakeRepo(vnData()), client: web(feed('x')), notifier: n, now: now), 0);
  });

  test('a stored state that is garbage is replaced, not fatal', () async {
    final p = await prefs({'notify_state': '{not json'});
    final n = FakeNotifier();
    expect(await runCycle(prefs: p, repo: FakeRepo(vnData()), client: web(feed('x')), notifier: n, now: now), 1);
  });

  test('a notifier that throws does not lose the other notices', () async {
    final p = await prefs();
    final n = _Flaky();
    final shown = await runCycle(prefs: p, repo: FakeRepo(vnData()), client: web(feed('HPG báo lãi quý 3'), status: 200), notifier: n, now: now);
    expect(shown, greaterThanOrEqualTo(1));
  });

  test('NotifyPrefs.load reads and clamps stored values', () async {
    final p = await prefs({'n_min': 9, 'n_hot': 5, 'n_max': 99, 'n_news': false});
    final l = NotifyPrefs.load(p);
    expect((l.minLevel, l.hot, l.maxPerHour, l.news), (3, 30, 20, false));
    expect(NotifyPrefs.load(await prefs()).hot, 60);
  });
}

class _Flaky implements Notifier {
  int calls = 0;
  @override
  Future<void> show(Notice n) async {
    if (calls++ == 0) throw StateError('platform error');
  }

  @override
  Future<bool> requestPermission() async => true;
}
