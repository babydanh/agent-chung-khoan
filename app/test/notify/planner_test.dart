import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/news/rank.dart';
import 'package:agent_ck/notify/planner.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:agent_ck/util/banned.dart';
import 'package:flutter_test/flutter_test.dart';

final now = DateTime.utc(2026, 11, 5, 3); // Thursday 10:00 in Vietnam
const prefs = NotifyPrefs();

SignalRow sig(String s, int level, [List<SignalItem> items = const [SignalItem('S1')]]) => SignalRow(symbol: s, level: level, learning: false, items: items);

Map<Market, MarketData> data({List<SignalRow> vn = const [], List<SignalRow> us = const [], List<Digest> digests = const []}) => {
      Market.vn: MarketData(signals: {for (final s in vn) s.symbol: s}, digests: digests, asof: now),
      Market.us: MarketData(signals: {for (final s in us) s.symbol: s}, asof: now),
    };

Story news(String title, {String event = 'earnings', int sources = 1, int ageMin = 10, List<String> symbols = const ['HPG'], String link = 'https://x.test/1'}) => Story(
      head: Headline(title: title, link: link, source: 'CafeF', published: now.subtract(Duration(minutes: ageMin)), symbols: symbols),
      event: eventByKey(event),
      sources: sources,
      cluster: 'c$link',
    );

PlanResult run({Map<Market, MarketData>? d, List<Story> stories = const [], Set<String> watch = const {}, NotifyPrefs p = prefs, NotifyState? state, DateTime? at}) =>
    plan(now: at ?? now, data: d ?? data(), stories: stories, watch: watch, prefs: p, state: state ?? NotifyState());

void main() {
  test('a symbol at the chosen level is shown once, with its signals', () {
    final d = data(vn: [sig('HPG', 3, [const SignalItem('S1'), const SignalItem('S2', 'buy')]), sig('FPT', 2)]);
    final r = run(d: d);
    expect(r.show, hasLength(1));
    expect(r.show.single.title, 'HPG · Mức 3');
    expect(r.show.single.body, 'KL tăng đột biến · NN ròng dương');
    final again = run(d: d, state: r.state, at: now.add(const Duration(minutes: 30)));
    expect(again.show, isEmpty, reason: 'the same symbol at the same level is not shown again');
  });

  test('a higher level on the same day is a new notice', () {
    final first = run(d: data(vn: [sig('HPG', 2)]), p: prefs.copyWith(minLevel: 2));
    final second = run(d: data(vn: [sig('HPG', 3)]), p: prefs.copyWith(minLevel: 2), state: first.state);
    expect(second.show.single.title, 'HPG · Mức 3');
  });

  test('a market switched off in the settings stays silent', () {
    final d = data(vn: [sig('HPG', 3)], us: [sig('NVDA', 3)]);
    expect(run(d: d, p: prefs.copyWith(vn: false)).show.map((n) => n.title), ['NVDA · Mức 3']);
    expect(run(d: d, p: prefs.copyWith(us: false, vn: false)).show, isEmpty);
  });

  test('a hot headline is shown with its event, source and link; a cold one is not', () {
    final r = run(stories: [news('HPG báo lãi quý 3 tăng 20%'), news('Tin nhỏ', event: 'other', symbols: [], link: 'https://x.test/2')], watch: {'HPG'});
    expect(r.show, hasLength(1));
    expect(r.show.single.title, 'HPG · Kết quả kinh doanh');
    expect(r.show.single.body, contains('HPG báo lãi quý 3 tăng 20%'));
    expect(r.show.single.body, contains('CafeF · 09:50'));
    expect(r.show.single.url, 'https://x.test/1');
  });

  test('headlines can be switched off', () {
    expect(run(stories: [news('HPG báo lãi quý 3')], watch: {'HPG'}, p: prefs.copyWith(news: false)).show, isEmpty);
  });

  test('the hot threshold comes from the settings', () {
    final s = [news('FPT ký hợp đồng chuyển đổi số', event: 'contract', symbols: ['FPT'], ageMin: 400)];
    expect(run(stories: s).show, isEmpty);
    expect(run(stories: s, watch: {'FPT'}, p: prefs.copyWith(hot: 40)).show, hasLength(1));
  });

  test('a headline that matches a money-flow signal says so', () {
    final d = data(vn: [sig('HPG', 2, [const SignalItem('S1'), const SignalItem('S2', 'buy')])]);
    final r = run(d: d, stories: [news('HPG ký hợp đồng cung cấp thép', event: 'contract')]);
    final n = r.show.singleWhere((x) => x.title.contains('Hợp đồng'));
    expect(n.body, contains('Khớp dòng tiền: Mức 2 · KL tăng đột biến, NN ròng dương'));
  });

  test('a new bulletin is announced once', () {
    final d = data(digests: [Digest(date: '2026-11-05', kind: 'slot-0930', body: 'Mức 3: HPG.\nDòng hai.', createdAt: now)]);
    final r = run(d: d);
    expect(r.show.single.title, 'Bản tin VN');
    expect(r.show.single.body, 'Mức 3: HPG.');
    expect(run(d: d, state: r.state).show, isEmpty);
    expect(run(d: d, p: prefs.copyWith(digest: false)).show, isEmpty);
  });

  test('quiet hours hold everything back; the queue is shown after seven', () {
    final night = DateTime.utc(2026, 11, 5, 16); // 23:00 in Vietnam
    final held = run(d: data(vn: [sig('HPG', 3)]), at: night);
    expect(held.show, isEmpty);
    expect(held.state.queue, hasLength(1));
    final morning = DateTime.utc(2026, 11, 6, 0, 5); // 07:05
    final out = run(d: data(), state: held.state, at: morning);
    expect(out.show.single.title, 'HPG · Mức 3');
    expect(out.state.queue, isEmpty);
  });

  test('with quiet hours off the night is not special', () {
    final night = DateTime.utc(2026, 11, 5, 16);
    expect(run(d: data(vn: [sig('HPG', 3)]), at: night, p: prefs.copyWith(quiet: false)).show, hasLength(1));
  });

  test('over the hourly limit the rest becomes one summary and is not shown again', () {
    final d = data(vn: [for (final s in ['AAA', 'BBB', 'CCC', 'DDD']) sig(s, 3)]);
    final r = run(d: d, p: prefs.copyWith(maxPerHour: 2));
    expect(r.show, hasLength(2));
    expect(r.show[1].title, 'Còn 3 tin nóng chưa hiện');
    final later = run(d: d, p: prefs.copyWith(maxPerHour: 2), state: r.state, at: now.add(const Duration(minutes: 5)));
    expect(later.show, isEmpty);
  });

  test('a queued message older than a day is dropped, sent records older than three days too', () {
    final old = NotifyState(
      queue: [Notice(key: 'q', title: 'cũ', body: '', score: 100, at: now.subtract(const Duration(hours: 30)))],
      sent: {'old': now.subtract(const Duration(days: 5)), 'new': now.subtract(const Duration(hours: 1))},
    );
    final r = run(state: old);
    expect(r.show, isEmpty);
    expect(r.state.sent.keys, ['new']);
  });

  test('advice wording in a headline keeps it from being shown', () {
    final r = run(stories: [news('HPG báo lãi quý 3: nên mua ngay trước khi tăng')], watch: {'HPG'});
    expect(r.show, isEmpty);
  });

  test('everything shown passes the wording scan', () {
    final d = data(vn: [sig('HPG', 3, [const SignalItem('S2', 'sell'), const SignalItem('S3')])], digests: [Digest(date: 'd', kind: 'k', body: 'Mức 3', createdAt: now)]);
    final r = run(d: d, stories: [news('HPG báo lãi quý 3')], watch: {'HPG'});
    expect(r.show, isNotEmpty);
    for (final n in r.show) {
      expect(findBanned('${n.title} ${n.body}'), isEmpty, reason: n.title);
    }
  });

  test('the state survives a round trip through JSON', () {
    final r = run(d: data(vn: [sig('HPG', 3)]), at: DateTime.utc(2026, 11, 5, 16));
    final back = NotifyState.fromJson(r.state.toJson());
    expect(back.queue.single.title, 'HPG · Mức 3');
    expect(back.toJson(), r.state.toJson());
    expect(NotifyState.fromJson({'sent': 'junk', 'queue': 3}).queue, isEmpty);
  });

  test('a notice has a stable numeric id for the system notification', () {
    expect(Notice(key: 'a', title: '', body: '', score: 1, at: now).id, Notice(key: 'a', title: 'x', body: '', score: 1, at: now).id);
    expect(Notice(key: 'a', title: '', body: '', score: 1, at: now).id, isNonNegative);
  });
}
