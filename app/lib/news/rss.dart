/// RSS headlines: title, link, source, time and a short plain-text summary. Nothing else is kept.
/// Feed text is untrusted: markup is stripped, only https links survive, lengths are capped.
library;

import 'package:xml/xml.dart';

import 'rank.dart';

class NewsError implements Exception {
  NewsError(this.message);
  final String message;
  @override
  String toString() => message;
}

const titleMax = 200, summaryMax = 200;

// Three-letter words that read like tickers but are not.
const _notSymbols = {
  'USD', 'GDP', 'CEO', 'CFO', 'CPI', 'PMI', 'IPO', 'ETF', 'VND', 'EUR', 'FED', 'OPEC', 'EPS', 'ROE', 'ROA', 'FDI', 'WTO', 'IMF',
  'NHNN', 'TTCK', 'UBCK', 'AI', 'OTC', 'ESG',
};

final _script = RegExp(r'<(script|style)\b.*?</\1\s*>', caseSensitive: false, dotAll: true);
final _block = RegExp(r'</?(br|p|div|li|ul|ol|h\d|tr|td|table)\b[^>]*>', caseSensitive: false);
final _tag = RegExp(r'<[^>]*>');
final _entity = RegExp(r'&(#x[0-9a-fA-F]+|#[0-9]+|[a-zA-Z]+);');
const _named = {'amp': '&', 'lt': '<', 'gt': '>', 'quot': '"', 'apos': "'", 'nbsp': ' '};

String _unescape(String s) => s.replaceAllMapped(_entity, (m) {
      final g = m.group(1)!;
      if (g.startsWith('#x')) return _code(int.tryParse(g.substring(2), radix: 16), m.group(0)!);
      if (g.startsWith('#')) return _code(int.tryParse(g.substring(1)), m.group(0)!);
      return _named[g] ?? m.group(0)!;
    });

String _code(int? c, String raw) => c == null || c <= 0 || c > 0x10ffff ? raw : String.fromCharCode(c);

String _stripTags(String t) => t.replaceAll(_script, ' ').replaceAll(_block, ' ').replaceAll(_tag, '');

/// Plain text: entities are decoded first (so escaped tags are seen), tags removed, then once more in case the
/// removal itself joined a new tag together.
String stripHtml(String? text) {
  var t = text ?? '';
  for (var i = 0; i < 3; i++) {
    final d = _unescape(t);
    if (d == t) break;
    t = d;
  }
  t = _stripTags(_stripTags(t));
  return t.replaceAll(RegExp(r'\s+'), ' ').trim();
}

String summarize(String text, [int limit = summaryMax]) => text.length <= limit ? text : '${text.substring(0, limit - 1).trimRight()}…';

final _ticker = RegExp(r'(?<![\p{L}\p{N}_])[A-Z]{3}(?![\p{L}\p{N}_])', unicode: true);

List<String> extractSymbols(String text, Set<String> known) =>
    ({for (final m in _ticker.allMatches(text)) m.group(0)!}.where((t) => known.contains(t) && !_notSymbols.contains(t)).toList()..sort());

const _months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12};
final _date = RegExp(r'(?:[A-Za-z]{3},\s*)?(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?\s*(GMT|UTC|UT|Z|[+-]\d{4})?');

/// RFC 822 dates as RSS uses them, in UTC; null when unreadable.
DateTime? parseRfc822(String? raw) {
  final m = raw == null ? null : _date.firstMatch(raw);
  final month = m == null ? null : _months[m.group(2)!.toLowerCase()];
  if (m == null || month == null) return null;
  var t = DateTime.utc(int.parse(m.group(3)!), month, int.parse(m.group(1)!), int.parse(m.group(4)!), int.parse(m.group(5)!), int.parse(m.group(6) ?? '0'));
  final z = m.group(7);
  if (z != null && (z.startsWith('+') || z.startsWith('-'))) {
    final off = Duration(hours: int.parse(z.substring(1, 3)), minutes: int.parse(z.substring(3, 5)));
    t = z.startsWith('+') ? t.subtract(off) : t.add(off);
  }
  return t;
}

List<Headline> parseRss(String body, String source, Set<String> known) {
  final XmlDocument doc;
  try {
    doc = XmlDocument.parse(body);
  } on XmlException catch (e) {
    throw NewsError('$source: not valid XML (${e.message})');
  }
  final out = <Headline>[];
  for (final item in doc.findAllElements('item')) {
    String text(String name) => item.getElement(name)?.innerText ?? '';
    var title = stripHtml(text('title'));
    if (title.length > titleMax) title = title.substring(0, titleMax);
    final link = text('link').trim();
    if (title.isEmpty || !link.startsWith('https://')) continue; // no http:, javascript: or other schemes
    final summary = summarize(stripHtml(text('description')));
    out.add(Headline(
      title: title,
      link: link,
      source: source,
      published: parseRfc822(text('pubDate')),
      summary: summary,
      symbols: extractSymbols('$title $summary', known),
    ));
  }
  return out;
}
