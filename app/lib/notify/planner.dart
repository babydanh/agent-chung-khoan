/// Decides which notifications to show now. Pure: the same inputs give the same output, so the background task, the
/// foreground refresh and the tests all use it. Texts are built from templates here and scanned with the wording
/// rules; headline titles from the feeds are untrusted and dropped when they read as advice.
library;

import '../models/models.dart';
import '../news/rank.dart';
import '../state/app_state.dart' show NotifyPrefs;
import '../util/banned.dart';
import '../util/format.dart' as f;

const _keepSent = Duration(days: 3);
const _queueMax = 30;
const _queueMaxAge = Duration(hours: 24);
const _maxSignalAge = Duration(hours: 3);
const _flowLevel = 2;
const _signalRank = 100; // signal notices rank above headlines
const _digestRank = 50;
const _quietStart = 22, _quietEnd = 7; // Vietnam time

class Notice {
  const Notice({required this.key, required this.title, required this.body, required this.score, required this.at, this.url});
  final String key, title, body;
  final int score;
  final DateTime at;
  final String? url;

  /// Stable id for the system notification (FNV-1a over the key).
  int get id {
    var h = 0x811c9dc5;
    for (final c in key.codeUnits) {
      h = ((h ^ c) * 0x01000193) & 0xffffffff;
    }
    return h & 0x7fffffff;
  }

  Map<String, Object?> toJson() => {'key': key, 'title': title, 'body': body, 'score': score, 'at': at.toIso8601String(), if (url != null) 'url': url};

  static Notice? tryFrom(Object? j) {
    if (j is! Map) return null;
    final at = DateTime.tryParse('${j['at']}');
    if (j['key'] is! String || j['title'] is! String || j['body'] is! String || j['score'] is! int || at == null) return null;
    return Notice(key: j['key'] as String, title: j['title'] as String, body: j['body'] as String, score: j['score'] as int, at: at.toUtc(), url: j['url'] as String?);
  }
}

class NotifyState {
  NotifyState({Map<String, DateTime>? sent, List<Notice>? queue, List<DateTime>? recent})
      : sent = sent ?? {},
        queue = queue ?? [],
        recent = recent ?? [];
  final Map<String, DateTime> sent; // key -> when it was shown
  final List<Notice> queue; // held back (quiet hours, hourly limit)
  final List<DateTime> recent; // show times of the last hour

  Map<String, Object?> toJson() => {
        'sent': {for (final e in sent.entries) e.key: e.value.toIso8601String()},
        'queue': [for (final n in queue) n.toJson()],
        'recent': [for (final t in recent) t.toIso8601String()],
      };

  /// Tolerant: anything unreadable is dropped, never thrown.
  factory NotifyState.fromJson(Object? j) {
    if (j is! Map) return NotifyState();
    final sent = <String, DateTime>{};
    if (j['sent'] is Map) {
      (j['sent'] as Map).forEach((k, v) {
        final t = DateTime.tryParse('$v');
        if (k is String && t != null) sent[k] = t.toUtc();
      });
    }
    return NotifyState(
      sent: sent,
      queue: [if (j['queue'] is List) for (final n in j['queue'] as List) ?Notice.tryFrom(n)],
      recent: [if (j['recent'] is List) for (final t in j['recent'] as List) ?DateTime.tryParse('$t')?.toUtc()],
    );
  }
}

class PlanResult {
  PlanResult(this.show, this.state);
  final List<Notice> show;
  final NotifyState state;
}

String _signalLabel(SignalItem s) => switch (s.id) {
      'S1' => 'KL tăng đột biến',
      'S2' => s.dir == 'sell' ? 'NN ròng âm' : 'NN ròng dương',
      'S3' => 'Thoả thuận lớn',
      'S4' => 'Biến động giá',
      'S5' => 'Gap mở cửa',
      _ => s.id,
    };

DateTime _vn(DateTime t) => t.toUtc().add(const Duration(hours: 7));

List<Notice> _signalNotices(DateTime now, Map<Market, MarketData> data, NotifyPrefs prefs) {
  final out = <Notice>[];
  final date = _vn(now).toIso8601String().substring(0, 10);
  for (final m in Market.values) {
    if (!(m == Market.vn ? prefs.vn : prefs.us)) continue;
    for (final r in (data[m]?.signals.values ?? const <SignalRow>[])) {
      if (r.level < prefs.minLevel) continue;
      if (r.asof != null && now.difference(r.asof!.toUtc()) > _maxSignalAge) continue;
      out.add(Notice(
        key: 'lv:${m.key}:${r.symbol}:$date:${r.level}',
        title: '${r.symbol} · Mức ${r.level}',
        body: r.items.map(_signalLabel).where((x) => x.isNotEmpty).join(' · '),
        score: _signalRank + r.level,
        at: now,
      ));
    }
  }
  return out;
}

List<Notice> _digestNotices(DateTime now, Map<Market, MarketData> data, NotifyPrefs prefs) {
  if (!prefs.digest) return const [];
  final out = <Notice>[];
  for (final m in Market.values) {
    if (!(m == Market.vn ? prefs.vn : prefs.us)) continue;
    final ds = data[m]?.digests ?? const <Digest>[];
    if (ds.isEmpty) continue;
    final d = ds.first;
    if (d.createdAt != null && now.difference(d.createdAt!.toUtc()) > _maxSignalAge) continue;
    final first = d.body.split('\n').firstWhere((l) => l.trim().isNotEmpty, orElse: () => '');
    out.add(Notice(key: 'digest:${m.key}:${d.date}:${d.kind}', title: 'Bản tin ${m.key}', body: first, score: _digestRank, at: now));
  }
  return out;
}

String? _flowNote(List<String> symbols, Map<String, SignalRow> signals) {
  for (final s in symbols) {
    final r = signals[s];
    if (r != null && r.level >= _flowLevel) {
      final labels = r.items.map(_signalLabel).where((x) => x.isNotEmpty).join(', ');
      return 'Khớp dòng tiền: Mức ${r.level}${labels.isEmpty ? '' : ' · $labels'}';
    }
  }
  return null;
}

List<Notice> _newsNotices(DateTime now, MarketData vn, List<Story> stories, Set<String> watch, NotifyPrefs prefs) {
  if (!prefs.news || !prefs.vn) return const [];
  final flows = {for (final r in vn.signals.values) if (r.level >= _flowLevel) r.symbol};
  final out = <Notice>[];
  for (final st in stories) {
    final score = hotScore(st, now, watch, flows);
    if (score < prefs.hot) continue;
    final h = st.head;
    final lines = [h.title, h.published == null ? h.source : '${h.source} · ${f.hhmm(_vn(h.published!))}', ?_flowNote(h.symbols, vn.signals)];
    out.add(Notice(
      key: 'n:${st.cluster}',
      title: '${h.symbols.isEmpty ? 'Thị trường' : h.symbols.first} · ${st.event.label}',
      body: lines.join('\n'),
      score: score,
      at: now,
      url: h.link,
    ));
  }
  return out;
}

/// What to show now, and the new state to store. `now` may be any time zone; quiet hours use Vietnam time.
PlanResult plan({
  required DateTime now,
  required Map<Market, MarketData> data,
  required List<Story> stories,
  required Set<String> watch,
  required NotifyPrefs prefs,
  required NotifyState state,
}) {
  final at = now.toUtc();
  final sent = {for (final e in state.sent.entries) if (at.difference(e.value) < _keepSent) e.key: e.value};
  final queue = [for (final n in state.queue) if (at.difference(n.at) < _queueMaxAge) n];
  final recent = [for (final t in state.recent) if (at.difference(t) < const Duration(hours: 1)) t];

  final known = {...queue.map((n) => n.key), ...sent.keys};
  final fresh = [
    ..._signalNotices(at, data, prefs),
    ..._digestNotices(at, data, prefs),
    ..._newsNotices(at, data[Market.vn] ?? const MarketData(), stories, watch, prefs),
  ].where((n) => !known.contains(n.key) && findBanned('${n.title} ${n.body}').isEmpty).toList();

  final all = [...queue, ...fresh];
  final order = {for (var i = 0; i < all.length; i++) all[i]: i};
  all.sort((a, b) => b.score != a.score ? b.score.compareTo(a.score) : order[a]!.compareTo(order[b]!)); // stable

  final hour = _vn(at).hour;
  final quiet = prefs.quiet && (hour >= _quietStart || hour < _quietEnd);
  final budget = prefs.maxPerHour - recent.length;
  if (quiet || all.isEmpty || budget <= 0) {
    return PlanResult(const [], NotifyState(sent: sent, queue: all.take(_queueMax).toList(), recent: recent));
  }

  var show = all;
  var covered = const <Notice>[];
  if (all.length > budget) {
    final full = budget > 1 ? budget - 1 : 0;
    show = all.take(full).toList();
    covered = all.skip(full).toList();
    show.add(Notice(key: 'sum:${at.toIso8601String()}', title: 'Còn ${covered.length} tin nóng chưa hiện', body: '', score: 0, at: at));
  }
  for (final n in [...show, ...covered]) {
    sent[n.key] = at;
  }
  recent.addAll(List.filled(show.length, at));
  return PlanResult(show, NotifyState(sent: sent, queue: const [], recent: recent));
}
