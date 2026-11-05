import 'package:agent_ck/news/news_service.dart';
import 'package:agent_ck/news/rss.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

final now = DateTime.utc(2026, 11, 5, 3);
const known = {'HPG', 'FPT'};

String rss(List<(String, String, int)> items) => '<rss><channel>${[
      for (final (t, l, ageMin) in items)
        '<item><title>$t</title><link>$l</link><pubDate>${_gmt(now.subtract(Duration(minutes: ageMin)))}</pubDate><description>d</description></item>'
    ].join()}</channel></rss>';

String _gmt(DateTime t) {
  const d = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  String two(int n) => n.toString().padLeft(2, '0');
  return '${d[t.weekday - 1]}, ${two(t.day)} ${m[t.month - 1]} ${t.year} ${two(t.hour)}:${two(t.minute)}:00 GMT';
}

http.Response ok(String body, [int status = 200]) =>
    http.Response(body, status, headers: {'content-type': 'application/rss+xml; charset=utf-8'});

MockClient server(Map<String, http.Response Function()> byHost) => MockClient((req) async {
      final h = byHost[req.url.host];
      if (h == null) throw http.ClientException('no route to ${req.url.host}');
      return h();
    });

const urls = {'A': 'https://a.test/rss', 'B': 'https://b.test/rss', 'C': 'https://c.test/rss'};

void main() {
  test('merges the feeds, drops duplicates, keeps newest first', () async {
    final c = server({
      'a.test': () => ok(rss([('HPG báo lãi', 'https://x.test/1', 30), ('FPT ký hợp đồng', 'https://x.test/2', 90)]), 200),
      'b.test': () => ok(rss([('HPG báo lãi quý 3', 'https://x.test/1', 30), ('Tin mới nhất', 'https://x.test/3', 5)]), 200),
      'c.test': () => ok(rss([]), 200),
    });
    final r = await fetchNews(client: c, known: known, now: now, feeds: urls);
    expect(r.items.map((i) => i.link), ['https://x.test/3', 'https://x.test/1', 'https://x.test/2']);
    expect(r.empty, ['C']);
    expect(r.failed, isEmpty);
  });

  test('one broken feed is reported and the others still count', () async {
    final c = server({
      'a.test': () => ok(rss([('HPG báo lãi', 'https://x.test/1', 30)]), 200),
      'b.test': () => ok('<rss', 200),
      'c.test': () => ok('oops', 503),
    });
    final r = await fetchNews(client: c, known: known, now: now, feeds: urls);
    expect(r.items, hasLength(1));
    expect(r.failed.keys, unorderedEquals(['B', 'C']));
  });

  test('when every feed fails the call fails with all the reasons', () async {
    final c = server({});
    await expectLater(fetchNews(client: c, known: known, now: now, feeds: urls),
        throwsA(isA<NewsError>().having((e) => e.message, 'message', allOf(contains('A:'), contains('B:'), contains('C:')))));
  });

  test('headlines older than three days are dropped', () async {
    final c = server({
      'a.test': () => ok(rss([('Cũ', 'https://x.test/old', 60 * 24 * 4), ('Mới', 'https://x.test/new', 60)]), 200),
      'b.test': () => ok(rss([]), 200),
      'c.test': () => ok(rss([]), 200),
    });
    final r = await fetchNews(client: c, known: known, now: now, feeds: urls);
    expect(r.items.map((i) => i.link), ['https://x.test/new']);
  });

  test('a feed that only had old headlines is listed as empty', () async {
    final c = server({
      'a.test': () => ok(rss([('Cũ', 'https://x.test/old', 60 * 24 * 4)]), 200),
      'b.test': () => ok(rss([('Mới', 'https://x.test/new', 60)]), 200),
      'c.test': () => ok(rss([]), 200),
    });
    final r = await fetchNews(client: c, known: known, now: now, feeds: urls);
    expect(r.empty, unorderedEquals(['A', 'C']));
  });

  test('a huge response is refused', () async {
    final c = server({
      'a.test': () => ok('<rss><channel><item><title>HPG</title><link>https://x.test/big</link><description>${'x' * (3 * 1024 * 1024)}</description></item></channel></rss>', 200),
      'b.test': () => ok(rss([('Mới', 'https://x.test/new', 60)]), 200),
      'c.test': () => ok(rss([]), 200),
    });
    final r = await fetchNews(client: c, known: known, now: now, feeds: urls);
    expect(r.failed.keys, ['A']);
    expect(r.failed['A'], contains('too large'));
    expect(r.items.map((i) => i.link), isNot(contains('https://x.test/big')));
  });

  test('only https feed addresses are requested', () async {
    final seen = <Uri>[];
    final c = MockClient((req) async {
      seen.add(req.url);
      return ok(rss([]), 200);
    });
    await fetchNews(client: c, known: known, now: now, feeds: {'A': 'http://a.test/rss', 'B': 'https://b.test/rss'}).catchError((_) => NewsResult());
    expect(seen.map((u) => u.scheme).toSet(), {'https'});
  });
}
