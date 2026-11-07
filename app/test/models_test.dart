import 'package:agent_ck/models/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Quote.fromJson tolerates missing numbers and computes the change', () {
    final q = Quote.fromJson({'market': 'VN', 'symbol': 'FPT', 'price': 131200, 'ref_price': 128500, 'vol': 6100000, 'val': 8e11, 'f_buy': 1280000, 'f_sell': 640000});
    expect(q.pct, closeTo(2.1012, 0.001));
    expect(q.fNet, 640000);
    expect(q.ceil, isNull);
    final empty = Quote.fromJson({'market': 'US', 'symbol': 'X'});
    expect(empty.market, Market.us);
    expect(empty.pct, isNull);
    expect(empty.vol, 0);
  });

  test('SignalRow.fromJson ignores malformed items and clamps the level', () {
    final r = SignalRow.fromJson({
      'symbol': 'FPT', 'level': 9, 'learning': true,
      'items': [{'id': 'S1', 'dir': null}, {'id': 'S2', 'dir': 'buy'}, 'junk', {'dir': 'x'}, {'id': 3}],
    });
    expect(r.level, 3);
    expect(r.items.map((i) => i.id), ['S1', 'S2']);
    expect(r.has('S2'), isTrue);
    expect(SignalRow.fromJson({'symbol': 'A', 'level': 1, 'items': null}).items, isEmpty);
  });

  test('Zone and Digest parse', () {
    final z = Zone.fromJson({'symbol': 'FPT', 'kind': 'Pivot', 'price_lo': 1, 'price_hi': 2, 'asof': '2026-11-05T02:00:00+00:00'});
    expect((z.lo, z.hi), (1, 2));
    expect(Digest.fromJson({'digest_date': '2026-11-05', 'kind': 'slot-0930', 'body': 'x'}).body, 'x');
  });

  test('a malformed timestamp becomes null instead of failing the whole read', () {
    expect(Quote.fromJson({'market': 'VN', 'symbol': 'A', 'asof': 'not a date'}).asof, isNull);
    expect(Zone.fromJson({'symbol': 'A', 'asof': ''}).asof, isNull);
    expect(SignalRow.fromJson({'symbol': 'A', 'level': 0, 'asof': 'x'}).asof, isNull);
    expect(Digest.fromJson({'created_at': 'x'}).createdAt, isNull);
    expect(NewsItem.fromJson({'published_at': 'x'}).publishedAt, isNull);
  });
}
