/// Reads the public RSS feeds straight from the phone. A feed that fails is reported, not fatal; if every feed fails
/// the call fails. Headlines older than three days are dropped; the rest come newest first without duplicates.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'rank.dart';
import 'rss.dart';

const defaultFeeds = {
  'CafeF': 'https://cafef.vn/thi-truong-chung-khoan.rss',
  'Vietstock': 'https://vietstock.vn/830/chung-khoan/co-phieu.rss',
  'VnExpress Kinh doanh': 'https://vnexpress.net/rss/kinh-doanh.rss',
};

const maxAge = Duration(days: 3);
const _maxBytes = 2 * 1024 * 1024;
const _timeout = Duration(seconds: 15);

class NewsResult {
  NewsResult({List<Headline>? items, Map<String, String>? failed, List<String>? empty})
      : items = items ?? [],
        failed = failed ?? {},
        empty = empty ?? [];
  final List<Headline> items;
  final Map<String, String> failed; // source -> reason
  final List<String> empty; // parsed, but nothing usable
}

Future<String> _get(http.Client client, String url) async {
  final uri = Uri.parse(url);
  if (uri.scheme != 'https') throw NewsError('only https feeds are read');
  final res = await client.get(uri, headers: {'Accept': 'application/rss+xml, application/xml, text/xml'}).timeout(_timeout);
  if (res.statusCode != 200) throw NewsError('HTTP ${res.statusCode}');
  if (res.bodyBytes.length > _maxBytes) throw NewsError('response too large');
  return utf8.decode(res.bodyBytes, allowMalformed: true);
}

Future<NewsResult> fetchNews({
  required http.Client client,
  required Set<String> known,
  DateTime? now,
  Map<String, String> feeds = defaultFeeds,
}) async {
  final at = (now ?? DateTime.now()).toUtc();
  final oldest = at.subtract(maxAge);
  final result = NewsResult();
  final seen = <String>{};
  for (final e in feeds.entries) {
    List<Headline> parsed;
    try {
      parsed = parseRss(await _get(client, e.value), e.key, known);
    } catch (err) {
      result.failed[e.key] = '${err.runtimeType}: $err';
      continue;
    }
    var kept = 0;
    for (final h in parsed) {
      if (seen.contains(h.link) || (h.published != null && h.published!.isBefore(oldest))) continue;
      seen.add(h.link);
      result.items.add(h);
      kept++;
    }
    if (kept == 0) result.empty.add(e.key);
  }
  if (feeds.isNotEmpty && result.failed.length == feeds.length) {
    throw NewsError('no feed could be read: ${result.failed.entries.map((x) => '${x.key}: ${x.value}').join('; ')}');
  }
  result.items.sort((a, b) => (b.published ?? DateTime(1970)).compareTo(a.published ?? DateTime(1970)));
  return result;
}
