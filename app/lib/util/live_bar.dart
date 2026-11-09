/// The chart's last bar from the live quote, so today's move shows without waiting for the daily candle.
/// Pure code: it works on the list the screen already has and never edits the stored bars.
library;

import '../models/models.dart';

/// [bars] (oldest first) with today's point taken from [q]. `live` is true when the last bar now comes from the quote.
/// Left unchanged (and not live) when the quote has no price or time, is older than the last bar, or would only
/// repeat the last close: a weekend or holiday refresh, a quote with no trade yet, the same volume as the last bar.
({List<DailyBar> bars, bool live}) withLiveBar(List<DailyBar> bars, Quote q) {
  final unchanged = (bars: bars, live: false);
  final price = q.price, asof = q.asof;
  if (bars.isEmpty || price == null || asof == null) return unchanged;
  final t = asof.toUtc().add(Duration(hours: q.market == Market.vn ? 7 : -5)); // the market's own calendar day
  final today = DateTime(t.year, t.month, t.day);
  final last = bars.last;
  final lastDay = DateTime(last.date.year, last.date.month, last.date.day);
  if (today.isBefore(lastDay)) return unchanged;
  if (today == lastDay) {
    final updated = DailyBar(date: last.date, close: price, vol: q.vol > 0 ? q.vol : last.vol);
    return (bars: [...bars.sublist(0, bars.length - 1), updated], live: true);
  }
  if (today.weekday > DateTime.friday || q.vol <= 0 || q.vol == last.vol) return unchanged;
  return (bars: [...bars, DailyBar(date: today, close: price, vol: q.vol)], live: true);
}
