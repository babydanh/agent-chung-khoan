import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/theme/theme.dart';
import 'package:agent_ck/util/banned.dart';
import 'package:agent_ck/widgets/chart_marks.dart';
import 'package:agent_ck/widgets/line_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

DailyBar _bar(int day, double close) => DailyBar(date: DateTime(2026, 11, day), close: close);

final _bars = [_bar(2, 100), _bar(3, 104), _bar(4, 98), _bar(5, 110)];

SignalRow _sig(DateTime? at, int level, List<SignalItem> items) => SignalRow(symbol: 'FPT', level: level, learning: false, items: items, asof: at);

void main() {
  group('signal and news marks', () {
    test('TC-MARK-01: a signal row becomes a mark with its level, time and plain wording', () {
      final marks = signalMarks([
        _sig(DateTime(2026, 11, 3, 10, 20), 2, const [SignalItem('S2', 'buy'), SignalItem('S1')]),
        _sig(null, 3, const [SignalItem('S1')]), // no time: cannot be placed
        _sig(DateTime(2026, 11, 4, 9, 50), 0, const []), // no signal at all
        _sig(DateTime(2026, 11, 4, 11, 20), 2, const []), // a level without items says nothing
      ]);
      expect(marks, hasLength(1));
      expect(marks.single.kind, MarkKind.signal);
      expect(marks.single.level, 2);
      expect(marks.single.title, 'Khối ngoại mua ròng lớn · Khối lượng tăng đột biến');
    });

    test('TC-MARK-02: every signal wording passes the advice scanner', () {
      for (final id in ['S1', 'S2', 'S3', 'S4', 'S5']) {
        for (final dir in [null, 'buy', 'sell', 'up', 'down']) {
          final text = signalText(SignalItem(id, dir));
          expect(text, isNotEmpty);
          expect(findBanned(text), isEmpty, reason: '$id/$dir: $text');
        }
      }
    });

    test('TC-MARK-03: news marks skip headlines without a time and headlines that read as advice', () {
      final marks = newsMarks([
        NewsItem(title: 'FPT báo lãi quý 3', url: 'https://x.test/1', source: 'CafeF', publishedAt: DateTime(2026, 11, 4, 8, 0)),
        const NewsItem(title: 'FPT không rõ ngày', url: 'https://x.test/2', source: 'CafeF'),
        NewsItem(title: 'Nên mua FPT ngay', url: 'https://x.test/3', source: 'Blog', publishedAt: DateTime(2026, 11, 4, 9, 0)),
      ]);
      expect(marks.map((m) => m.title), ['FPT báo lãi quý 3']);
      expect(marks.single.kind, MarkKind.news);
      expect(marks.single.url, 'https://x.test/1');
    });

    test('TC-MARK-04: marks are grouped on the bar of their day; a day without a bar is dropped', () {
      final marks = [
        ChartMark(at: DateTime(2026, 11, 3, 14, 50), kind: MarkKind.signal, level: 1, title: 'a'),
        ChartMark(at: DateTime(2026, 11, 3, 9, 50), kind: MarkKind.signal, level: 3, title: 'b'),
        ChartMark(at: DateTime(2026, 11, 3, 8, 0), kind: MarkKind.news, title: 'c'),
        ChartMark(at: DateTime(2026, 11, 5, 10, 0), kind: MarkKind.news, title: 'd'),
        ChartMark(at: DateTime(2026, 11, 7, 10, 0), kind: MarkKind.signal, level: 2, title: 'weekend, no bar'),
      ];
      final days = groupByBar(_bars, marks);
      expect(days.map((d) => d.index), [1, 3]);
      expect(days[0].topLevel, 3);
      expect(days[0].hasSignal && days[0].hasNews, isTrue);
      expect(days[0].marks.map((m) => m.title), ['c', 'b', 'a']); // earliest first
      expect(days[1].hasSignal, isFalse);
      expect(days[1].hasNews, isTrue);
      expect(days[1].topLevel, 0);
    });

    test('TC-MARK-05: no bars or no marks gives nothing and does not throw', () {
      expect(groupByBar(const [], [ChartMark(at: DateTime(2026, 11, 3), kind: MarkKind.news, title: 'x')]), isEmpty);
      expect(groupByBar(_bars, const []), isEmpty);
    });
  });

  group('tapping a mark', () {
    final days = groupByBar(_bars, [
      ChartMark(at: DateTime(2026, 11, 3, 10), kind: MarkKind.signal, level: 2, title: 'a'),
      ChartMark(at: DateTime(2026, 11, 4, 10), kind: MarkKind.signal, level: 1, title: 'b'),
    ]);
    const size = Size(300, 140);

    test('TC-MARK-06: a tap near a mark finds its day, a tap far away finds nothing', () {
      final g = ChartGeometry(_bars, size);
      expect(hitMark(g, days, g.point(1) + const Offset(6, -4))?.index, 1);
      expect(hitMark(g, days, g.point(2))?.index, 2);
      expect(hitMark(g, days, const Offset(5, 135)), isNull);
    });

    test('TC-MARK-07: between two marks the nearer one wins', () {
      final g = ChartGeometry(_bars, size);
      final mid = Offset((g.point(1).dx * 0.7 + g.point(2).dx * 0.3), g.point(1).dy);
      expect(hitMark(g, days, mid, radius: 200)?.index, 1);
    });

    testWidgets('TC-MARK-08: the chart reports the day that was tapped', (tester) async {
      DayMarks? tapped;
      await tester.pumpWidget(MaterialApp(
        theme: buildTheme(Brightness.dark),
        home: Scaffold(body: Center(child: SizedBox(width: 300, child: LineChart(_bars, color: Colors.teal, marks: days, onMarkTap: (d) => tapped = d)))),
      ));
      final box = tester.getTopLeft(find.byType(LineChart));
      final g = ChartGeometry(_bars, const Size(300, 140));
      await tester.tapAt(box + g.point(1));
      await tester.pump();
      expect(tapped?.index, 1);
    });
  });
}
