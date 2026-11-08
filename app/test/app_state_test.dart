import 'package:agent_ck/data/repository.dart';
import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/news/rank.dart';
import 'package:agent_ck/notify/notifier.dart';
import 'package:agent_ck/notify/planner.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Repository stub whose answers the test controls.
class FakeRepo implements Repository {
  FakeRepo(this.data, {this.fail});
  MarketData data;
  Object? fail;

  @override
  Future<MarketData> load(Market market) async {
    if (fail != null) throw fail!;
    return data;
  }

  @override
  Future<List<DailyBar>> bars(Market market, String symbol, {int days = 60}) async => const [];

  @override
  Future<List<SignalRow>> signalHistory(Market market, String symbol, {int limit = 60}) async => const [];
}

class FakeNotifier implements Notifier {
  final shown = <Notice>[];
  @override
  Future<void> show(Notice n) async => shown.add(n);
  @override
  Future<bool> requestPermission() async => true;
}

Quote _q(String s, {String ex = 'HOSE', double price = 110, double ref = 100, double vol = 1000, DateTime? asof}) =>
    Quote(market: Market.vn, symbol: s, exchange: ex, price: price, ref: ref, vol: vol, asof: asof);

MarketData _data({DateTime? asof}) => MarketData(
      asof: asof,
      quotes: [_q('AAA', vol: 500, price: 90), _q('BBB', ex: 'HNX', vol: 900), _q('CCC', vol: 100, price: 120)],
      signals: {
        'AAA': const SignalRow(symbol: 'AAA', level: 1, learning: false, items: [SignalItem('S1')]),
        'BBB': const SignalRow(symbol: 'BBB', level: 3, learning: false, items: [SignalItem('S2', 'buy')]),
        'CCC': const SignalRow(symbol: 'CCC', level: 3, learning: true),
      },
    );

Future<AppState> _state({FakeRepo? repo, DateTime? now}) async {
  SharedPreferences.setMockInitialValues({});
  final s = AppState(await SharedPreferences.getInstance(), repository: repo ?? FakeRepo(_data()), now: now == null ? null : () => now);
  await s.load(Market.vn);
  return s;
}

Story _story(String title, {String event = 'earnings', List<String> symbols = const ['AAA'], DateTime? at}) => Story(
      head: Headline(title: title, link: 'https://x.test/${title.hashCode}', source: 'CafeF', published: at ?? DateTime.now(), symbols: symbols),
      event: eventByKey(event),
      sources: 1,
      cluster: 'c$title',
    );

void main() {
  test('board sorts by level then volume', () async {
    final s = await _state();
    expect(s.board().map((q) => q.symbol), ['BBB', 'CCC', 'AAA']);
  });

  test('quick chips and the filter sheet narrow the board', () async {
    final s = await _state();
    s.setQuick(QuickFilter.level3);
    expect(s.board().map((q) => q.symbol), ['BBB', 'CCC']);
    s.setQuick(QuickFilter.all);
    s.setFilters(const Filters(exchanges: {'HNX'}));
    expect(s.board().map((q) => q.symbol), ['BBB']);
    s.setFilters(const Filters(signals: {'S1'}));
    expect(s.board().map((q) => q.symbol), ['AAA']);
    s.setFilters(const Filters(sort: SortKey.percent));
    expect(s.board().first.symbol, 'CCC');
  });

  test('the watchlist survives a restart and keeps its order', () async {
    final s = await _state();
    await s.toggleWatch(Market.vn, 'AAA');
    await s.toggleWatch(Market.vn, 'BBB');
    await s.reorderWatch(Market.vn, 1, 0);
    final again = AppState(await SharedPreferences.getInstance(), repository: FakeRepo(_data()));
    expect(again.watch[Market.vn], ['BBB', 'AAA']);
    s.setQuick(QuickFilter.watch);
    expect(s.board().map((q) => q.symbol).toSet(), {'AAA', 'BBB'});
    await s.toggleWatch(Market.vn, 'AAA');
    expect(s.isWatched(Market.vn, 'AAA'), isFalse);
  });

  test('adding and removing a symbol is saved on its own, before any reordering', () async {
    final s = await _state();
    await s.toggleWatch(Market.us, 'NVDA');
    expect(AppState(await SharedPreferences.getInstance(), repository: FakeRepo(_data())).watch[Market.us], ['NVDA']);
    await s.toggleWatch(Market.us, 'NVDA');
    expect(AppState(await SharedPreferences.getInstance(), repository: FakeRepo(_data())).watch[Market.us], isEmpty);
  });

  test('a network failure keeps the last data and flags offline', () async {
    final repo = FakeRepo(_data());
    final s = await _state(repo: repo);
    repo.fail = http.ClientException('no route');
    await s.load(Market.vn);
    expect(s.offline, isTrue);
    expect(s.of(Market.vn).quotes, hasLength(3));
  });

  test('an auth failure is reported as such, not as offline', () async {
    final repo = FakeRepo(_data());
    final s = await _state(repo: repo);
    repo.fail = RepositoryException('Sai email hoặc mật khẩu', auth: true);
    await s.load(Market.vn);
    expect((s.offline, s.authError, s.error), (false, true, 'Sai email hoặc mật khẩu'));
  });

  test('freshness: fresh while open, stale when old while open, closed outside hours', () async {
    // Wednesday 2026-11-04, 10:00 Vietnam time (03:00 UTC).
    final open = DateTime.utc(2026, 11, 4, 3, 0);
    var s = await _state(repo: FakeRepo(_data(asof: open.subtract(const Duration(minutes: 20)))), now: open);
    expect(s.freshness(Market.vn), 'fresh');
    s = await _state(repo: FakeRepo(_data(asof: open.subtract(const Duration(hours: 2)))), now: open);
    expect(s.freshness(Market.vn), 'stale');
    final night = DateTime.utc(2026, 11, 4, 14, 0); // 21:00 Vietnam
    s = await _state(repo: FakeRepo(_data(asof: night.subtract(const Duration(hours: 5)))), now: night);
    expect(s.freshness(Market.vn), 'closed');
  });

  test('marketOpen follows the Vietnamese sessions and skips lunch and weekends', () {
    DateTime vn(int d, int h, int m) => DateTime(2026, 11, d, h, m); // 2026-11-04 is a Wednesday
    expect(marketOpen(Market.vn, vn(4, 9, 30)), isTrue);
    expect(marketOpen(Market.vn, vn(4, 12, 0)), isFalse);
    expect(marketOpen(Market.vn, vn(4, 13, 30)), isTrue);
    expect(marketOpen(Market.vn, vn(4, 15, 0)), isFalse);
    expect(marketOpen(Market.vn, vn(7, 10, 0)), isFalse); // Saturday
  });

  test('inbox lists symbols at the chosen level and respects the per-market switch', () async {
    final s = await _state();
    expect(s.inbox().map((i) => i.symbol), unorderedEquals(['BBB', 'CCC']));
    await s.setNotify(s.notify.copyWith(vn: false));
    expect(s.inbox(), isEmpty);
    await s.setNotify(const NotifyPrefs(minLevel: 1));
    expect(s.inbox().length, 3);
  });

  test('search matches symbol and name, case-insensitively', () async {
    final s = await _state();
    expect(s.search(Market.vn, 'bb').map((q) => q.symbol), ['BBB']);
    expect(s.search(Market.vn, ''), isEmpty);
  });

  group('news and notifications in the app', () {
    test('stories are ranked hottest first and the hot ones are flagged', () async {
      final s = await _state();
      await s.toggleWatch(Market.vn, 'AAA'); // a watched symbol adds 15 points
      s.stories = [_story('Tin nhỏ', event: 'other', symbols: []), _story('AAA báo lãi quý 3', at: DateTime.now())];
      expect(s.rankedStories().map((x) => x.head.title), ['AAA báo lãi quý 3', 'Tin nhỏ']);
      expect(s.isHot(s.rankedStories().first), isTrue);
      expect(s.isHot(s.rankedStories().last), isFalse);
    });

    test('a story that matches a money-flow signal is marked as a match', () async {
      final s = await _state();
      expect(s.flowMatch(_story('AAA ký hợp đồng', symbols: ['BBB'])), isTrue); // BBB is level 3
      expect(s.flowMatch(_story('AAA ký hợp đồng', symbols: ['AAA'])), isFalse); // AAA is level 1
    });

    test('notifyNow shows what the planner says once and keeps the state', () async {
      final n = FakeNotifier();
      SharedPreferences.setMockInitialValues({});
      final s = AppState(await SharedPreferences.getInstance(), repository: FakeRepo(_data(asof: DateTime.now())), notifier: n, now: () => DateTime.utc(2026, 11, 5, 3));
      await s.load(Market.vn);
      expect(await s.notifyNow(), 2); // BBB and CCC are level 3
      expect(n.shown.map((x) => x.title), unorderedEquals(['BBB · Mức 3', 'CCC · Mức 3']));
      expect(await s.notifyNow(), 0);
      expect(n.shown, hasLength(2));
    });

    test('notifyNow without a notifier does nothing', () async {
      final s = await _state();
      expect(await s.notifyNow(), 0);
    });

    test('the test notice and the permission request go through the notifier', () async {
      final n = FakeNotifier();
      SharedPreferences.setMockInitialValues({});
      final s = AppState(await SharedPreferences.getInstance(), repository: FakeRepo(_data()), notifier: n);
      expect(await s.allowNotifications(), isTrue);
      await s.sendTestNotice();
      expect(n.shown.single.title, 'Thông báo thử');
      final bare = await _state();
      expect(await bare.allowNotifications(), isFalse);
      await bare.sendTestNotice(); // no notifier: nothing happens, nothing throws
    });

    test('refreshAll loads data and news, then notifies', () async {
      final n = FakeNotifier();
      SharedPreferences.setMockInitialValues({});
      final client = MockClient((_) async => http.Response('<rss><channel><item><title>AAA báo lãi quý 3</title><link>https://x.test/1</link><description>d</description></item></channel></rss>', 200, headers: {'content-type': 'application/rss+xml; charset=utf-8'}));
      final at = DateTime.utc(2026, 11, 5, 3); // 10:00 in Vietnam: outside the quiet hours, whatever the real clock says
      final s = AppState(await SharedPreferences.getInstance(), repository: FakeRepo(_data(asof: at)), notifier: n, httpClient: client, now: () => at);
      await s.refreshAll();
      expect(s.of(Market.vn).quotes, hasLength(3));
      expect(s.stories.single.head.title, 'AAA báo lãi quý 3');
      expect(n.shown.map((x) => x.title), containsAll(['BBB · Mức 3', 'CCC · Mức 3']));
    });

    test('a news failure is shown as a short message and keeps the old stories', () async {
      SharedPreferences.setMockInitialValues({});
      final s = AppState(await SharedPreferences.getInstance(), repository: FakeRepo(_data()), httpClient: MockClient((_) async => http.Response('x', 503)));
      s.stories = [_story('Cũ')];
      await s.loadNews();
      expect(s.newsError, isNotNull);
      expect(s.stories, hasLength(1));
    });

    test('the inbox lists hot headlines too', () async {
      final s = await _state();
      s.stories = [_story('AAA báo lãi quý 3', at: DateTime.now())];
      await s.toggleWatch(Market.vn, 'AAA');
      expect(s.inbox().where((i) => i.story != null), hasLength(1));
    });
  });
}
