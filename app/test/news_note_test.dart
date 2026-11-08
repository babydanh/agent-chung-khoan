import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/util/banned.dart';
import 'package:agent_ck/util/news_note.dart';
import 'package:flutter_test/flutter_test.dart';

NewsNote _n({String kind = 'earnings', String aspect = 'Tin kết quả kinh doanh thường liên quan tới doanh thu.', String outlook = 'pos', String note = 'Kết quả tốt hơn kỳ trước.'}) =>
    NewsNote(kind: kind, aspect: aspect, outlook: outlook, note: note);

void main() {
  test('TC-NNOTE-01: a row from the table is read field by field and missing fields get plain defaults', () {
    final n = NewsNote.fromJson({'url': 'https://x.test/1', 'kind': 'legal', 'aspect': 'A.', 'outlook': 'neg', 'note': 'B.'});
    expect((n.kind, n.aspect, n.outlook, n.note), ('legal', 'A.', 'neg', 'B.'));
    final empty = NewsNote.fromJson({});
    expect((empty.kind, empty.aspect, empty.outlook, empty.note), ('other', '', 'unclear', ''));
  });

  test('TC-NNOTE-02: no note means nothing to show', () {
    expect(shownNote(null), isNull);
  });

  test('TC-NNOTE-03: a leaning with a reason is shown as a guess, with the kind label from the rank list', () {
    final s = shownNote(_n())!;
    expect((s.kind, s.lean, s.guess), ('Kết quả kinh doanh', leanPositive, true));
    expect(s.reason, 'Kết quả tốt hơn kỳ trước.');
    expect(shownNote(_n(outlook: 'neg'))!.lean, leanNegative);
  });

  test('TC-NNOTE-04: a leaning without a reason, an unclear one and an unknown one are all shown as unclear', () {
    for (final n in [_n(note: ''), _n(outlook: 'unclear'), _n(outlook: 'moon')]) {
      final s = shownNote(n)!;
      expect((s.lean, s.guess), (leanUnclear, false), reason: '${n.outlook}/${n.note}');
    }
    expect(shownNote(_n(kind: 'nonsense'))!.kind, 'Tin khác');
  });

  test('TC-NNOTE-05: text that reads as advice or a price forecast is dropped, and a leaning built on it falls back to unclear', () {
    final s = shownNote(_n(note: 'Nhà đầu tư nên mua vào ngay.', aspect: 'Giá có thể tăng mạnh.'))!;
    expect((s.reason, s.aspect, s.lean, s.guess), ('', '', leanUnclear, false));
  });

  test('TC-NNOTE-06: every fixed string the app adds passes the advice scanner', () {
    for (final t in [leanPositive, leanNegative, leanUnclear, noteDisclaimer]) {
      expect(findBanned(t), isEmpty, reason: t);
    }
    expect(noteDisclaimer, contains('có thể sai'));
  });
}
