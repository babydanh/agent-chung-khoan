import 'package:agent_ck/news/rss.dart';
import 'package:flutter_test/flutter_test.dart';

const known = {'HPG', 'FPT', 'VNM', 'CEO'};

String feed(List<String> items) => '<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>${items.join()}</channel></rss>';

String item({String title = 'HPG báo lãi quý 3', String? link = 'https://cafef.vn/a', String? date = 'Thu, 05 Nov 2026 03:00:00 GMT', String desc = 'Tóm tắt'}) =>
    '<item><title>$title</title>${link == null ? '' : '<link>$link</link>'}${date == null ? '' : '<pubDate>$date</pubDate>'}<description>$desc</description></item>';

void main() {
  test('reads title, https link, source, time in UTC and the known symbols', () {
    final out = parseRss(feed([item()]), 'CafeF', known);
    expect(out, hasLength(1));
    expect(out.first.title, 'HPG báo lãi quý 3');
    expect(out.first.link, 'https://cafef.vn/a');
    expect(out.first.source, 'CafeF');
    expect(out.first.published, DateTime.utc(2026, 11, 5, 3));
    expect(out.first.symbols, ['HPG']);
  });

  test('a time zone offset is converted to UTC and a bad date becomes null', () {
    expect(parseRss(feed([item(date: 'Thu, 05 Nov 2026 10:00:00 +0700')]), 's', known).first.published, DateTime.utc(2026, 11, 5, 3));
    expect(parseRss(feed([item(date: 'yesterday')]), 's', known).first.published, isNull);
    expect(parseRss(feed([item(date: null)]), 's', known).first.published, isNull);
  });

  test('items without a title or without an https link are dropped', () {
    final out = parseRss(feed([item(title: ''), item(link: null), item(link: 'http://insecure.test/a'), item(link: 'javascript:alert(1)'), item()]), 's', known);
    expect(out, hasLength(1));
  });

  test('html is removed, entities decoded (also double encoded) and long text is cut', () {
    final out = parseRss(
      feed([item(title: '&lt;b&gt;HPG&lt;/b&gt; tăng &amp;amp; giảm', desc: '<![CDATA[<p>Một <script>x()</script>đoạn&nbsp;văn</p>]]>')]), 's', known);
    expect(out.first.title, 'HPG tăng & giảm');
    expect(out.first.summary, 'Một đoạn văn');
    final long = parseRss(feed([item(title: 'a' * 500, desc: 'b' * 500)]), 's', known).first;
    expect(long.title.length, 200);
    expect(long.summary.length, 200);
    expect(long.summary.endsWith('…'), isTrue);
  });

  test('common acronyms and unknown words are not symbols, even when the ticker list has them', () {
    final out = parseRss(feed([item(title: 'CEO HPG gặp USD và XYZ', desc: '')]), 's', known);
    expect(out.first.symbols, ['HPG']);
  });

  test('a symbol glued to other letters is not a symbol', () {
    expect(parseRss(feed([item(title: 'HPGx và aFPT', desc: '')]), 's', known).first.symbols, isEmpty);
  });

  test('not valid XML is reported', () {
    expect(() => parseRss('<rss><channel><item>', 'CafeF', known), throwsA(isA<NewsError>()));
    expect(() => parseRss('', 'CafeF', known), throwsA(isA<NewsError>()));
  });
}
