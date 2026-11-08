/// Dots on the price chart: what a signal or a headline said on a given day. Pure code, so it is tested without a screen.
/// The wording comes from fixed templates and headlines pass the advice scanner; a dot only reports what happened.
library;

import '../models/models.dart';
import '../util/banned.dart';

enum MarkKind { signal, news }

class ChartMark {
  const ChartMark({required this.at, required this.kind, required this.title, this.level = 0, this.detail, this.url});
  final DateTime at;
  final MarkKind kind;
  final int level; // signals only: 1..3
  final String title;
  final String? detail, url; // news: the source and the link
}

/// Everything that happened on one bar's day, earliest first.
class DayMarks {
  const DayMarks(this.index, this.date, this.marks);
  final int index; // position of the bar in the chart
  final DateTime date;
  final List<ChartMark> marks;

  bool get hasSignal => marks.any((m) => m.kind == MarkKind.signal);
  bool get hasNews => marks.any((m) => m.kind == MarkKind.news);
  int get topLevel => marks.fold(0, (a, m) => m.kind == MarkKind.signal && m.level > a ? m.level : a);
}

String signalText(SignalItem i) => switch (i.id) {
      'S1' => 'Khối lượng tăng đột biến',
      'S2' => i.dir == 'sell' ? 'Khối ngoại bán ròng lớn' : 'Khối ngoại mua ròng lớn',
      'S3' => 'Giao dịch thỏa thuận lớn',
      'S4' => i.dir == 'down' ? 'Giá giảm mạnh so với biên độ trung bình' : 'Giá tăng mạnh so với biên độ trung bình',
      'S5' => i.dir == 'down' ? 'Giá mở cửa thấp hơn hẳn giá đóng cửa trước' : 'Giá mở cửa cao hơn hẳn giá đóng cửa trước',
      _ => i.id,
    };

/// Rows with no time, no level or no signal items say nothing a dot could show, so they are left out.
List<ChartMark> signalMarks(List<SignalRow> history) => [
      for (final r in history)
        if (r.asof != null && r.level > 0 && r.items.isNotEmpty)
          ChartMark(at: r.asof!, kind: MarkKind.signal, level: r.level, title: r.items.map(signalText).join(' · ')),
    ];

/// The caller passes the headlines of one symbol. A headline without a time, or one that reads as advice, is left out.
List<ChartMark> newsMarks(List<NewsItem> items) => [
      for (final n in items)
        if (n.publishedAt != null && n.title.isNotEmpty && findBanned(n.title).isEmpty)
          ChartMark(at: n.publishedAt!, kind: MarkKind.news, title: n.title, detail: n.source, url: n.url),
    ];

/// Puts every mark on the bar of its own day. A mark on a day without a bar (weekend, today before the bar exists) is dropped.
List<DayMarks> groupByBar(List<DailyBar> bars, List<ChartMark> marks) {
  if (bars.isEmpty || marks.isEmpty) return const [];
  int key(DateTime t) => t.year * 10000 + t.month * 100 + t.day;
  final byDay = {for (var i = 0; i < bars.length; i++) key(bars[i].date): i};
  final grouped = <int, List<ChartMark>>{};
  for (final m in marks) {
    final i = byDay[key(m.at.toLocal())];
    if (i != null) grouped.putIfAbsent(i, () => []).add(m);
  }
  final order = grouped.keys.toList()..sort();
  return [
    for (final i in order) DayMarks(i, bars[i].date, grouped[i]!..sort((a, b) => a.at.compareTo(b.at))),
  ];
}
