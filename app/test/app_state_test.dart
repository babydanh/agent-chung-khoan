import 'package:agent_ck/data/repository.dart';
import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
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
}
