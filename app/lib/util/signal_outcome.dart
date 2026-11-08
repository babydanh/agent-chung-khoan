/// What the price did after a past signal, read from the daily bars the app already has. Only measures the past:
/// the change from the close of the signal day to the close some sessions later. Nothing here predicts anything.
library;

import '../models/models.dart';

int _key(DateTime t) => t.year * 10000 + t.month * 100 + t.day;

/// Change in percent after [sessions] bars, counted from the bar of [day]. Null when that day has no bar (weekend), the later
/// bar does not exist yet, the count is not positive or the base close is not positive.
double? changeAfter(List<DailyBar> bars, DateTime day, int sessions) {
  if (sessions <= 0) return null;
  final k = _key(day.toLocal());
  final i = bars.indexWhere((b) => _key(b.date) == k);
  if (i < 0 || i + sessions >= bars.length || bars[i].close <= 0) return null;
  return (bars[i + sessions].close - bars[i].close) / bars[i].close * 100;
}

class Outcomes {
  const Outcomes({required this.up, required this.down, required this.flat});
  final int up, down, flat;
  int get total => up + down + flat;
}

/// One count per signal day (several signals on one day are one day), for the change after one session. A change below
/// 0,005% reads as 0,00% on screen, so it counts as flat.
Outcomes outcomes(List<DailyBar> bars, List<SignalRow> history) {
  var up = 0, down = 0, flat = 0;
  final seen = <int>{};
  for (final r in history) {
    if (r.asof == null || r.items.isEmpty || !seen.add(_key(r.asof!.toLocal()))) continue;
    final v = changeAfter(bars, r.asof!, 1);
    if (v == null) continue;
    if (v.abs() < 0.005) {
      flat++;
    } else if (v > 0) {
      up++;
    } else {
      down++;
    }
  }
  return Outcomes(up: up, down: down, flat: flat);
}

String? outcomeLine(Outcomes o) => o.total == 0
    ? null
    : 'Sau 1 phiên (${o.total} ngày có tín hiệu): giá tăng ${o.up}, giảm ${o.down}, đi ngang ${o.flat}. Chỉ là quá khứ.';
