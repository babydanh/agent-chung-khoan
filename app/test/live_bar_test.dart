import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/util/live_bar.dart';
import 'package:flutter_test/flutter_test.dart';

DailyBar _bar(int day, double close, [double vol = 0]) => DailyBar(date: DateTime(2026, 11, day), close: close, vol: vol);

Quote _quote({double? price = 52, double vol = 900, DateTime? asof, Market market = Market.vn}) =>
    Quote(market: market, symbol: 'FPT', exchange: 'HOSE', price: price, vol: vol, asof: asof);

// Thursday 5 and Friday 6 November 2026; the next session is Monday 9 November.
final _bars = [_bar(5, 50, 100), _bar(6, 51, 200)];
final _monday10am = DateTime.utc(2026, 11, 9, 3, 0); // 10:00 in Ho Chi Minh City
final _friday2pm = DateTime.utc(2026, 11, 6, 7, 0);

void main() {
  test('TC-LIVEBAR-01: a new session adds today as the last bar from the live quote', () {
    final r = withLiveBar(_bars, _quote(asof: _monday10am));

    expect(r.live, isTrue);
    expect(r.bars, hasLength(3));
    expect(r.bars.last.date, DateTime(2026, 11, 9));
    expect(r.bars.last.close, 52);
    expect(r.bars.last.vol, 900);
    expect(r.bars.first.close, 50, reason: 'earlier bars are never touched');
  });

  test('TC-LIVEBAR-02: the same session replaces the last bar instead of adding one', () {
    final r = withLiveBar(_bars, _quote(price: 53, vol: 250, asof: _friday2pm));

    expect(r.live, isTrue);
    expect(r.bars, hasLength(2));
    expect(r.bars.last.close, 53);
    expect(r.bars.last.vol, 250);
  });

  test('TC-LIVEBAR-03: a quote older than the last bar changes nothing', () {
    final r = withLiveBar(_bars, _quote(asof: DateTime.utc(2026, 11, 4, 7, 0)));

    expect(r.live, isFalse);
    expect(identical(r.bars, _bars), isTrue);
  });

  test('TC-LIVEBAR-04: no price, no time or no bars changes nothing', () {
    for (final r in [
      withLiveBar(_bars, _quote(price: null, asof: _monday10am)),
      withLiveBar(_bars, _quote()),
      withLiveBar(const [], _quote(asof: _monday10am)),
    ]) {
      expect(r.live, isFalse);
    }
  });

  test('TC-LIVEBAR-05: the day is the market day, not the UTC day (VN is UTC+7)', () {
    final r = withLiveBar(_bars, _quote(asof: DateTime.utc(2026, 11, 8, 18, 0))); // Monday 01:00 in VN

    expect(r.live, isTrue);
    expect(r.bars.last.date, DateTime(2026, 11, 9));
  });

  test('TC-LIVEBAR-06: a weekend refresh of the last close does not add a flat Saturday bar', () {
    final r = withLiveBar(_bars, _quote(vol: 700, asof: DateTime.utc(2026, 11, 7, 9, 0)));

    expect(r.live, isFalse);
    expect(r.bars, hasLength(2));
  });

  test('TC-LIVEBAR-07: a holiday refresh (same volume as the last bar) does not add a flat bar', () {
    final r = withLiveBar(_bars, _quote(vol: 200, asof: _monday10am));

    expect(r.live, isFalse);
  });

  test('TC-LIVEBAR-08: before the first trade (volume 0) there is no bar for today yet', () {
    final r = withLiveBar(_bars, _quote(vol: 0, asof: _monday10am));

    expect(r.live, isFalse);
  });

  test('TC-LIVEBAR-09: a same-day quote without volume keeps the bar volume', () {
    final r = withLiveBar(_bars, _quote(price: 53, vol: 0, asof: _friday2pm));

    expect(r.bars.last.close, 53);
    expect(r.bars.last.vol, 200);
  });
}
