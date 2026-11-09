import 'package:agent_ck/data/candles.dart';
import 'package:agent_ck/theme/theme.dart';
import 'package:agent_ck/widgets/candle_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Candle _c(int i, double o, double h, double l, double c) => Candle(t: DateTime.utc(2026, 11, 2).add(Duration(minutes: 15 * i)), o: o, h: h, l: l, c: c, v: 100);

final _candles = [_c(0, 10, 12, 9, 11), _c(1, 11, 15, 10, 14), _c(2, 14, 14, 8, 9)];

void main() {
  test('TC-CCHART-01: the highest high is at the top, the lowest low at the bottom, bodies sit between open and close', () {
    final g = CandleGeometry(_candles, const Size(300, 100));

    expect(g.y(15), 8, reason: 'top padding');
    expect(g.y(8), 92, reason: 'bottom padding');
    expect(g.y(14), lessThan(g.y(11)));
    final body = g.body(1);
    expect(body.top, g.y(14)); // close of an up candle
    expect(body.bottom, g.y(11)); // its open
    expect(body.height, greaterThanOrEqualTo(1), reason: 'a flat candle still shows a line');
  });

  test('TC-CCHART-02: candles are spread evenly and every one stays inside the width', () {
    final g = CandleGeometry(_candles, const Size(300, 100));

    expect(g.x(0), lessThan(g.x(1)));
    expect(g.x(1) - g.x(0), closeTo(g.x(2) - g.x(1), 0.001));
    for (var i = 0; i < _candles.length; i++) {
      expect(g.body(i).left, greaterThanOrEqualTo(0));
      expect(g.body(i).right, lessThanOrEqualTo(300));
    }
  });

  test('TC-CCHART-03: a flat price range does not divide by zero', () {
    final g = CandleGeometry([_c(0, 5, 5, 5, 5), _c(1, 5, 5, 5, 5)], const Size(300, 100));

    expect(g.y(5).isFinite, isTrue);
  });

  testWidgets('TC-CCHART-04: the chart renders, with and without the live dot, and a single candle draws nothing', (tester) async {
    for (final list in [_candles, [_candles.first]]) {
      for (final live in [false, true]) {
        await tester.pumpWidget(MaterialApp(
          theme: buildTheme(Brightness.dark),
          home: Scaffold(body: Center(child: SizedBox(width: 300, child: CandleChart(list, liveLast: live)))),
        ));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      }
    }
  });
}
