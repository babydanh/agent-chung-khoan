import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/util/banned.dart';
import 'package:agent_ck/util/signal_outcome.dart';
import 'package:flutter_test/flutter_test.dart';

DailyBar _bar(int day, double close) => DailyBar(date: DateTime(2026, 11, day), close: close);

// Mon 2 .. Fri 6, then Mon 9 (the 7th and 8th are the weekend).
final _bars = [_bar(2, 100), _bar(3, 104), _bar(4, 98), _bar(5, 110), _bar(6, 110), _bar(9, 121)];

SignalRow _sig(DateTime at, {int level = 1}) => SignalRow(symbol: 'FPT', level: level, learning: false, items: const [SignalItem('S2', 'buy')], asof: at);

void main() {
  test('TC-OUT-01: the change is measured from the close of the signal day to the close some sessions later', () {
    final d = DateTime(2026, 11, 3, 10, 20);
    expect(changeAfter(_bars, d, 1), closeTo((98 - 104) / 104 * 100, 1e-9));
    expect(changeAfter(_bars, d, 2), closeTo((110 - 104) / 104 * 100, 1e-9));
    expect(changeAfter(_bars, DateTime(2026, 11, 6, 14, 50), 1), closeTo(10.0, 1e-9)); // over the weekend: next bar is Monday
  });

  test('TC-OUT-02: nothing is said when the day has no bar, the later bar does not exist yet, or the count is not positive', () {
    expect(changeAfter(_bars, DateTime(2026, 11, 7, 10), 1), isNull); // Saturday: no bar
    expect(changeAfter(_bars, DateTime(2026, 11, 9, 10), 1), isNull); // last bar: no later bar yet
    expect(changeAfter(_bars, DateTime(2026, 11, 6, 10), 3), isNull); // would need a bar past the end
    expect(changeAfter(_bars, DateTime(2026, 11, 3, 10), 0), isNull);
    expect(changeAfter(const [], DateTime(2026, 11, 3), 1), isNull);
    expect(changeAfter([_bar(2, 0), _bar(3, 5)], DateTime(2026, 11, 2), 1), isNull); // a zero close cannot be a base
  });

  test('TC-OUT-03: the summary counts each signal day once and only days that can be measured', () {
    final history = [
      _sig(DateTime(2026, 11, 3, 10, 20)), // Tue: 104 -> 98, down
      _sig(DateTime(2026, 11, 3, 14, 50)), // same day: not counted twice
      _sig(DateTime(2026, 11, 2, 9, 50)), // Mon: 100 -> 104, up
      _sig(DateTime(2026, 11, 5, 9, 50)), // Thu: 110 -> 110, flat
      _sig(DateTime(2026, 11, 9, 9, 50)), // last bar: cannot be measured yet
      _sig(DateTime(2026, 11, 7, 9, 50)), // weekend: no bar
    ];
    final o = outcomes(_bars, history);
    expect((o.up, o.down, o.flat), (1, 1, 1));
    expect(o.total, 3);
  });

  test('TC-OUT-04: the summary line is plain, passes the advice scanner and is empty when nothing can be measured', () {
    final line = outcomeLine(const Outcomes(up: 3, down: 2, flat: 1));
    expect(line, 'Sau 1 phiên (6 ngày có tín hiệu): giá tăng 3, giảm 2, đi ngang 1. Chỉ là quá khứ.');
    expect(findBanned(line!), isEmpty);
    expect(outcomeLine(const Outcomes(up: 0, down: 0, flat: 0)), isNull);
  });
}
