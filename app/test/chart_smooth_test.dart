import 'dart:math' as math;

import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/theme/theme.dart';
import 'package:agent_ck/widgets/line_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

final _bars = [
  for (var i = 0; i < 30; i++) DailyBar(date: DateTime(2026, 10, 1).add(Duration(days: i)), close: 100 + 10 * math.sin(i / 3)),
];

void main() {
  test('TC-SMOOTH-01: the curve ends on every point and never leaves the range of its two neighbours', () {
    const pts = [Offset(0, 100), Offset(10, 40), Offset(20, 60), Offset(30, 10), Offset(40, 10)];
    final segs = smoothSegments(pts);

    expect(segs, hasLength(4));
    for (var i = 0; i < segs.length; i++) {
      final a = pts[i], b = pts[i + 1], s = segs[i];
      expect(s.end, b);
      final lo = math.min(a.dy, b.dy), hi = math.max(a.dy, b.dy);
      for (final c in [s.c1, s.c2]) {
        expect(c.dy, inInclusiveRange(lo, hi), reason: 'segment $i overshoots');
        expect(c.dx, inInclusiveRange(a.dx, b.dx), reason: 'segment $i goes backwards');
      }
    }
  });

  test('TC-SMOOTH-02: a flat stretch stays flat and fewer than two points give no segments', () {
    final flat = smoothSegments(const [Offset(0, 5), Offset(10, 5), Offset(20, 5)]);
    expect(flat.every((s) => s.c1.dy == 5 && s.c2.dy == 5), isTrue);
    expect(smoothSegments(const [Offset(0, 1)]), isEmpty);
    expect(smoothSegments(const []), isEmpty);
  });

  testWidgets('TC-SMOOTH-03: the chart draws in and then stays still (live dot included)', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(Brightness.dark),
      home: Scaffold(body: Center(child: SizedBox(width: 300, child: LineChart(_bars, color: Colors.teal, liveLast: true)))),
    ));
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.hasRunningAnimations, isTrue);

    await tester.pumpAndSettle();

    expect(tester.hasRunningAnimations, isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('TC-SMOOTH-04: another range draws in again, a refreshed last price does not', (tester) async {
    Widget chart(List<DailyBar> bars) => MaterialApp(
          theme: buildTheme(Brightness.dark),
          home: Scaffold(body: Center(child: SizedBox(width: 300, child: LineChart(bars, color: Colors.teal)))),
        );
    await tester.pumpWidget(chart(_bars));
    await tester.pumpAndSettle();

    final refreshed = [..._bars.sublist(0, _bars.length - 1), DailyBar(date: _bars.last.date, close: 99)];
    await tester.pumpWidget(chart(refreshed));
    expect(tester.hasRunningAnimations, isFalse, reason: 'a live refresh must not replay the intro');

    await tester.pumpWidget(chart(_bars.sublist(10)));
    expect(tester.hasRunningAnimations, isTrue, reason: 'a different range draws in again');
    await tester.pumpAndSettle();
  });
}
