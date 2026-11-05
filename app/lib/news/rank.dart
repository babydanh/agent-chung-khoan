/// Rank headlines without a model: classify the event by keywords, group the same story across sources and
/// score how hot it is. Pure functions; every figure a notification shows comes from here or from the signals.
library;

import '../util/banned.dart' show normalize;

class Headline {
  const Headline({
    required this.title,
    required this.link,
    required this.source,
    this.published,
    this.summary = '',
    this.symbols = const [],
  });
  final String title, link, source, summary;
  final DateTime? published;
  final List<String> symbols;
}

class EventInfo {
  const EventInfo(this.key, this.label, this.weight);
  final String key, label;
  final double weight;
}

// Keywords per event (accent-folded, whole words or phrases). Order matters: the first event with a matching
// keyword wins, so "lai suat" (macro) is checked before the earnings words.
const _rules = <(String, String, double, List<String>)>[
  ('macro', 'Vĩ mô', 0.5, ['lai suat', 'ty gia', 'gdp', 'cpi', 'nhnn', 'ngan hang nha nuoc', 'fed', 'trai phieu chinh phu']),
  ('legal', 'Pháp lý', 1.0, ['thanh tra', 'khoi to', 'xu phat', 'vi pham', 'dinh chi', 'dieu tra', 'bat tam giam', 'huy niem yet']),
  ('deal', 'Thâu tóm, sáp nhập', 1.0, ['thau tom', 'sap nhap', 'mua lai doanh nghiep', 'm&a', 'chuyen nhuong von', 'chao mua cong khai']),
  ('earnings', 'Kết quả kinh doanh', 1.0, ['loi nhuan', 'lai quy', 'bao lai', 'bao lo', 'doanh thu', 'ket qua kinh doanh']),
  ('dividend', 'Cổ tức', 0.8, ['co tuc', 'chia thuong', 'co phieu thuong', 'ngay giao dich khong huong quyen']),
  ('issuance', 'Phát hành', 0.8, ['phat hanh them', 'tang von', 'chao ban', 'phat hanh co phieu', 'phat hanh trai phieu']),
  ('insider', 'Giao dịch cổ đông lớn', 0.6, ['co dong lon', 'giao dich noi bo', 'nguoi noi bo', 'dang ky giao dich', 'lanh dao dang ky']),
  ('contract', 'Hợp đồng, dự án', 0.6, ['hop dong', 'du an', 'ky ket', 'trung thau']),
  ('liquidity', 'Thanh khoản', 0.5, ['margin', 'von ngoai', 'etf', 'thanh khoan', 'khoi ngoai']),
  ('other', 'Tin khác', 0.2, []),
];

final events = [for (final r in _rules) EventInfo(r.$1, r.$2, r.$3)];

EventInfo eventByKey(String key) => events.firstWhere((e) => e.key == key, orElse: () => events.last);

final _word = RegExp(r'[a-z0-9&]+');

String _padded(String text) => ' ${_word.allMatches(normalize(text)).map((m) => m.group(0)).join(' ')} ';

EventInfo classify(String text) {
  final t = _padded(text);
  for (final r in _rules) {
    if (r.$4.any((k) => t.contains(' $k '))) return eventByKey(r.$1);
  }
  return eventByKey('other');
}

/// One story: the newest headline that tells it, how many distinct sources tell it, a stable id and its event.
class Story {
  const Story({required this.head, required this.event, required this.sources, required this.cluster});
  final Headline head;
  final EventInfo event;
  final int sources;
  final String cluster;
}

const _sameStory = 0.6;

Set<String> _tokens(String title) => {for (final m in _word.allMatches(normalize(title))) m.group(0)!};

bool _similar(Headline a, Headline b) {
  final ta = _tokens(a.title), tb = _tokens(b.title);
  if (ta.isEmpty || tb.isEmpty) return false;
  if (a.symbols.isNotEmpty && b.symbols.isNotEmpty && a.symbols.toSet().difference(b.symbols.toSet()).isNotEmpty) return false;
  if (a.symbols.isNotEmpty && b.symbols.isNotEmpty && b.symbols.toSet().difference(a.symbols.toSet()).isNotEmpty) return false;
  return ta.intersection(tb).length / ta.union(tb).length >= _sameStory;
}

/// FNV-1a, 32 bit, as 8 hex digits: a stable id that does not depend on the platform.
String _hash(String s) {
  var h = 0x811c9dc5;
  for (final c in s.codeUnits) {
    h = ((h ^ c) * 0x01000193) & 0xffffffff;
  }
  return h.toRadixString(16).padLeft(8, '0');
}

List<Story> clusterStories(List<Headline> items) {
  final newestFirst = [...items]..sort((a, b) => (b.published ?? DateTime(1970)).compareTo(a.published ?? DateTime(1970)));
  final groups = <List<Headline>>[];
  for (final it in newestFirst) {
    final g = groups.where((g) => _similar(g.first, it));
    g.isEmpty ? groups.add([it]) : g.first.add(it);
  }
  return [
    for (final g in groups)
      Story(
        head: g.first,
        event: classify('${g.first.title} ${g.first.summary}'),
        sources: {for (final m in g) m.source}.length,
        cluster: _hash(g.map((m) => m.link).reduce((a, b) => a.compareTo(b) <= 0 ? a : b)),
      ),
  ];
}

const _freshFull = 60, _freshZero = 12 * 60;
const _unknownFresh = 0.3;

double _freshness(DateTime? published, DateTime now) {
  if (published == null) return _unknownFresh;
  final age = now.difference(published).inSeconds / 60;
  if (age <= _freshFull) return 1;
  if (age >= _freshZero) return 0;
  return 1 - (age - _freshFull) / (_freshZero - _freshFull);
}

/// 0..100: 30 freshness + 20 sources (three or more is full) + 20 event weight + 15 watched + 15 money-flow match.
int hotScore(Story s, DateTime now, Set<String> watch, Set<String> flows) {
  final syms = s.head.symbols.toSet();
  final score = 30 * _freshness(s.head.published, now) +
      20 * (s.sources > 3 ? 3 : s.sources) / 3 +
      20 * s.event.weight +
      (syms.intersection(watch).isNotEmpty ? 15 : 0) +
      (syms.intersection(flows).isNotEmpty ? 15 : 0);
  return score.round();
}
