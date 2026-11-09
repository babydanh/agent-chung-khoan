import 'dart:async';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../data/candles.dart';
import '../data/demo_repository.dart';
import '../data/repository.dart';
import '../data/supabase_repository.dart';
import '../models/models.dart';
import '../news/news_service.dart';
import '../news/rank.dart';
import '../notify/cycle.dart' as cycle;
import '../notify/notifier.dart';
import '../notify/planner.dart';

enum SortKey { level, percent, volume, symbol }

enum QuickFilter { all, level2, level3, watch }

class Filters {
  const Filters({this.minLevel = 0, this.exchanges = const {}, this.signals = const {}, this.sort = SortKey.level});
  final int minLevel;
  final Set<String> exchanges; // empty = all
  final Set<String> signals; // S1/S2/S3, empty = any
  final SortKey sort;

  int get activeCount => (minLevel > 0 ? 1 : 0) + exchanges.length + signals.length + (sort != SortKey.level ? 1 : 0);

  Filters copyWith({int? minLevel, Set<String>? exchanges, Set<String>? signals, SortKey? sort}) => Filters(
        minLevel: minLevel ?? this.minLevel,
        exchanges: exchanges ?? this.exchanges,
        signals: signals ?? this.signals,
        sort: sort ?? this.sort,
      );
}

class NotifyPrefs {
  const NotifyPrefs({this.vn = true, this.us = true, this.minLevel = 3, this.digest = true, this.quiet = true, this.news = true, this.hot = 60, this.maxPerHour = 6});
  final bool vn, us, digest, quiet, news; // quiet = 22:00-07:00; news = hot headlines
  final int minLevel, hot, maxPerHour;

  /// Reads the stored settings; unreadable or out-of-range values fall back to the defaults.
  factory NotifyPrefs.load(SharedPreferences p) => NotifyPrefs(
        vn: p.getBool('n_vn') ?? true,
        us: p.getBool('n_us') ?? true,
        digest: p.getBool('n_dg') ?? true,
        quiet: p.getBool('n_quiet') ?? true,
        news: p.getBool('n_news') ?? true,
        minLevel: (p.getInt('n_min') ?? 3).clamp(1, 3),
        hot: (p.getInt('n_hot') ?? 60).clamp(30, 95),
        maxPerHour: (p.getInt('n_max') ?? 6).clamp(1, 20),
      );

  NotifyPrefs copyWith({bool? vn, bool? us, bool? digest, bool? quiet, bool? news, int? minLevel, int? hot, int? maxPerHour}) => NotifyPrefs(
        vn: vn ?? this.vn, us: us ?? this.us, digest: digest ?? this.digest, quiet: quiet ?? this.quiet, news: news ?? this.news,
        minLevel: minLevel ?? this.minLevel, hot: hot ?? this.hot, maxPerHour: maxPerHour ?? this.maxPerHour);
}

/// Opening hours in Vietnam time. Holidays are not known to the app; the bot's own data age tells the rest.
bool marketOpen(Market m, DateTime vnNow) {
  final t = vnNow.hour * 60 + vnNow.minute;
  final wd = vnNow.weekday; // 1 = Monday
  if (m == Market.vn) return wd <= 5 && ((t >= 9 * 60 && t < 11 * 60 + 30) || (t >= 13 * 60 && t < 15 * 60));
  // US regular session 20:30-03:00 (winter) / 21:30-04:00 (summer): use the wide window.
  return (wd <= 5 && t >= 20 * 60 + 30) || (wd >= 2 && wd <= 6 && t < 4 * 60);
}

class AppState extends ChangeNotifier {
  AppState(this._prefs, {Repository? repository, DateTime Function()? now, this.notifier, http.Client? httpClient})
      : _now = now ?? DateTime.now,
        _client = httpClient ?? http.Client() {
    _loadPrefs();
    _repo = repository ?? _buildRepo();
  }

  final SharedPreferences _prefs;
  final http.Client _client;
  final Notifier? notifier;
  final DateTime Function() _now;
  late Repository _repo;

  // --- settings -----------------------------------------------------------------------------------
  ThemeMode themeMode = ThemeMode.dark;
  Market defaultMarket = Market.vn;
  Market market = Market.vn; // board
  Filters filters = const Filters();
  QuickFilter quick = QuickFilter.all;
  NotifyPrefs notify = const NotifyPrefs();
  final Map<Market, List<String>> watch = {Market.vn: [], Market.us: []};
  List<String> recentSearches = [];
  SupabaseConfig connection = const SupabaseConfig(url: '', anonKey: '', email: '', password: '');

  bool get demo => !connection.complete;

  // --- data ---------------------------------------------------------------------------------------
  final Map<Market, MarketData> data = {};
  final Map<Market, DateTime> loadedAt = {};
  List<Story> stories = [];
  String? newsError;
  bool loading = false;
  bool offline = false;
  String? error;
  bool authError = false;

  DateTime get now => _now();
  MarketData of(Market m) => data[m] ?? const MarketData();

  void _loadPrefs() {
    themeMode = _prefs.getString('theme') == 'light' ? ThemeMode.light : ThemeMode.dark;
    defaultMarket = _prefs.getString('defMarket') == 'US' ? Market.us : Market.vn;
    market = defaultMarket;
    watch[Market.vn] = _prefs.getStringList('watch_VN') ?? [];
    watch[Market.us] = _prefs.getStringList('watch_US') ?? [];
    recentSearches = _prefs.getStringList('recent') ?? [];
    notify = NotifyPrefs.load(_prefs);
    connection = SupabaseConfig.load(_prefs);
  }

  Repository _buildRepo() => connection.complete ? SupabaseRepository(connection) : DemoRepository(now: _now());

  // --- loading ------------------------------------------------------------------------------------
  Future<void> load([Market? m]) async {
    final target = m ?? market;
    loading = true;
    notifyListeners();
    try {
      data[target] = await _repo.load(target);
      loadedAt[target] = now;
      offline = false;
      error = null;
      authError = false;
    } on RepositoryException catch (e) {
      error = e.message;
      authError = e.auth;
    } on http.ClientException {
      offline = true;
    } on TimeoutException {
      offline = true;
    } catch (e) {
      error = 'Lỗi đọc dữ liệu: $e';
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  /// Reads the public feeds from the phone. A failure keeps the stories already loaded and sets [newsError].
  Future<void> loadNews() async {
    try {
      final known = {for (final q in of(Market.vn).quotes) q.symbol};
      final r = await fetchNews(client: _client, known: known, now: now);
      stories = clusterStories(r.items);
      newsError = r.failed.isEmpty ? null : 'Một số nguồn tin lỗi: ${r.failed.keys.join(', ')}';
      notifyListeners();
    } catch (e) {
      newsError = 'Không đọc được tin';
      notifyListeners();
    }
  }

  /// Headlines that name [symbol]: the rows the bot stored plus, for VN, the stories this phone read from the feeds.
  /// One per link, newest first (a headline without a time goes last).
  List<NewsItem> headlinesOf(Market m, String symbol) {
    final out = [for (final n in of(m).news) if (n.symbol == symbol) n];
    if (m == Market.vn) {
      final seen = {for (final n in out) n.url};
      for (final st in stories) {
        final h = st.head;
        if (h.symbols.contains(symbol) && seen.add(h.link)) {
          out.add(NewsItem(title: h.title, url: h.link, source: h.source, symbol: symbol, publishedAt: h.published));
        }
      }
    }
    out.sort((a, b) => (b.publishedAt ?? DateTime(1970)).compareTo(a.publishedAt ?? DateTime(1970)));
    return out;
  }

  /// Data, headlines, then notifications: what the refresh gesture and the first start do.
  Future<void> refreshAll() async {
    await load(Market.vn);
    await Future.wait([loadNews(), if (data.containsKey(Market.us) || market == Market.us) load(Market.us)]);
    await askPermissionOnce();
    await notifyNow();
  }

  /// Android 13+ shows no notice without the permission, so the first start asks for it instead of waiting for a trip to
  /// the settings. The flag is set before asking: a second refresh or a restart never prompts again.
  Future<void> askPermissionOnce() async {
    final n = notifier;
    if (n == null || (_prefs.getBool('n_asked') ?? false)) return;
    await _prefs.setBool('n_asked', true);
    await allowNotifications();
  }

  Set<String> get _flowSymbols => {for (final r in of(Market.vn).signals.values) if (r.level >= 2) r.symbol};

  bool flowMatch(Story s) => s.head.symbols.any(_flowSymbols.contains);

  int score(Story s) => hotScore(s, now.toUtc(), watch[Market.vn]!.toSet(), _flowSymbols);

  bool isHot(Story s) => score(s) >= notify.hot;

  /// Stories hottest first (ties keep the newest first).
  List<Story> rankedStories() {
    final scored = [for (var i = 0; i < stories.length; i++) (stories[i], score(stories[i]), i)];
    scored.sort((a, b) => b.$2 != a.$2 ? b.$2.compareTo(a.$2) : a.$3.compareTo(b.$3));
    return [for (final x in scored) x.$1];
  }

  /// Shows the notices the planner picks from the data already loaded. Returns how many were shown.
  Future<int> notifyNow() async {
    final n = notifier;
    if (n == null) return 0;
    final result = plan(now: now.toUtc(), data: data, stories: stories, watch: watch[Market.vn]!.toSet(), prefs: notify, state: cycle.loadState(_prefs));
    final shown = await cycle.showAll(n, result);
    await cycle.saveState(_prefs, result.state);
    return shown;
  }

  /// Asks for the notification permission. False when it is refused or there is no notifier.
  Future<bool> allowNotifications() async => await notifier?.requestPermission() ?? false;

  Future<void> sendTestNotice() async {
    await notifier?.show(Notice(key: 'test:${now.microsecondsSinceEpoch}', title: 'Thông báo thử', body: 'Hoạt động bình thường', score: 0, at: now.toUtc()));
  }

  Future<List<DailyBar>> bars(Market m, String symbol, {int days = 60}) async {
    try {
      return await _repo.bars(m, symbol, days: days);
    } catch (_) {
      return const [];
    }
  }

  /// Candles of one VN symbol for a frame other than the daily one, straight from VCI (nothing is stored).
  /// Throws [CandleError]; the US market has no such source.
  Future<List<Candle>> candles(Market m, String symbol, Frame frame) {
    if (m != Market.vn) return Future.error(CandleError('only the VN market has this frame'));
    return fetchCandles(_client, symbol, frame, now: now);
  }

  Future<List<SignalRow>> signalHistory(Market m, String symbol) async {
    try {
      return await _repo.signalHistory(m, symbol);
    } catch (_) {
      return const [];
    }
  }

  // --- connection ---------------------------------------------------------------------------------
  Future<void> saveConnection(SupabaseConfig c) async {
    connection = c;
    await _prefs.setString('c_url', c.url);
    await _prefs.setString('c_key', c.anonKey);
    await _prefs.setString('c_mail', c.email);
    await _prefs.setString('c_pass', c.password);
    _repo = _buildRepo();
    data.clear();
    loadedAt.clear();
    notifyListeners();
    await load();
  }

  // --- derived lists ------------------------------------------------------------------------------
  /// Board rows after the quick chip, the filter sheet and the sort.
  List<Quote> board() {
    final d = of(market);
    var rows = d.quotes.toList();
    switch (quick) {
      case QuickFilter.level2:
        rows = rows.where((q) => (d.signals[q.symbol]?.level ?? 0) >= 2).toList();
      case QuickFilter.level3:
        rows = rows.where((q) => (d.signals[q.symbol]?.level ?? 0) >= 3).toList();
      case QuickFilter.watch:
        rows = rows.where((q) => isWatched(market, q.symbol)).toList();
      case QuickFilter.all:
        break;
    }
    if (filters.minLevel > 0) rows = rows.where((q) => (d.signals[q.symbol]?.level ?? 0) >= filters.minLevel).toList();
    if (filters.exchanges.isNotEmpty) rows = rows.where((q) => filters.exchanges.contains(q.exchange)).toList();
    if (filters.signals.isNotEmpty) {
      rows = rows.where((q) => filters.signals.any((s) => d.signals[q.symbol]?.has(s) ?? false)).toList();
    }
    int lvl(Quote q) => d.signals[q.symbol]?.level ?? 0;
    switch (filters.sort) {
      case SortKey.level:
        rows.sort((a, b) {
          final c = lvl(b).compareTo(lvl(a));
          return c != 0 ? c : b.vol.compareTo(a.vol);
        });
      case SortKey.percent:
        rows.sort((a, b) => (b.pct ?? -999).compareTo(a.pct ?? -999));
      case SortKey.volume:
        rows.sort((a, b) => b.vol.compareTo(a.vol));
      case SortKey.symbol:
        rows.sort((a, b) => a.symbol.compareTo(b.symbol));
    }
    return rows;
  }

  List<Quote> search(Market m, String q) {
    final s = q.trim().toLowerCase();
    if (s.isEmpty) return const [];
    return of(m).quotes.where((x) => x.symbol.toLowerCase().contains(s) || x.name.toLowerCase().contains(s)).toList();
  }

  /// Level-3 symbols and bulletins the bot produced, newest first: the in-app inbox.
  List<InboxItem> inbox() {
    final out = <InboxItem>[];
    for (final m in Market.values) {
      final on = m == Market.vn ? notify.vn : notify.us;
      if (!on) continue;
      final d = of(m);
      for (final s in d.signals.values) {
        if (s.level >= notify.minLevel) out.add(InboxItem(market: m, symbol: s.symbol, level: s.level, at: s.asof));
      }
      if (notify.digest) {
        for (final g in d.digests.take(6)) {
          out.add(InboxItem(market: m, digest: g, at: g.createdAt));
        }
      }
    }
    if (notify.news && notify.vn) {
      for (final st in rankedStories().where(isHot)) {
        out.add(InboxItem(market: Market.vn, story: st, at: st.head.published));
      }
    }
    out.sort((a, b) => (b.at ?? DateTime(2000)).compareTo(a.at ?? DateTime(2000)));
    return out;
  }

  // --- data health --------------------------------------------------------------------------------
  /// 'fresh' | 'stale' (data older than two slots while open) | 'closed' (outside trading hours).
  String freshness(Market m) {
    final at = of(m).asof;
    if (at == null) return 'none';
    final vnNow = now.toUtc().add(const Duration(hours: 7));
    final age = now.difference(at);
    if (!marketOpen(m, vnNow)) return age.inMinutes > 60 ? 'closed' : 'fresh';
    return age.inMinutes > 60 ? 'stale' : 'fresh';
  }

  // --- user actions -------------------------------------------------------------------------------
  bool isWatched(Market m, String symbol) => watch[m]!.contains(symbol);

  Future<void> toggleWatch(Market m, String symbol) async {
    final list = watch[m]!;
    list.contains(symbol) ? list.remove(symbol) : list.add(symbol);
    await _prefs.setStringList('watch_${m.key}', list);
    notifyListeners();
  }

  Future<void> reorderWatch(Market m, int from, int to) async {
    final list = watch[m]!; // `to` is already adjusted for the removed item (onReorderItem)
    list.insert(to, list.removeAt(from));
    await _prefs.setStringList('watch_${m.key}', list);
    notifyListeners();
  }

  void setMarket(Market m) {
    market = m;
    notifyListeners();
    if (!data.containsKey(m)) load(m);
  }

  void setQuick(QuickFilter q) {
    quick = q;
    notifyListeners();
  }

  void setFilters(Filters f) {
    filters = f;
    notifyListeners();
  }

  Future<void> setTheme(ThemeMode m) async {
    themeMode = m;
    await _prefs.setString('theme', m == ThemeMode.light ? 'light' : 'dark');
    notifyListeners();
  }

  Future<void> setDefaultMarket(Market m) async {
    defaultMarket = m;
    await _prefs.setString('defMarket', m.key);
    notifyListeners();
  }

  Future<void> setNotify(NotifyPrefs p) async {
    notify = p;
    await _prefs.setBool('n_vn', p.vn);
    await _prefs.setBool('n_us', p.us);
    await _prefs.setBool('n_dg', p.digest);
    await _prefs.setBool('n_quiet', p.quiet);
    await _prefs.setInt('n_min', p.minLevel);
    await _prefs.setBool('n_news', p.news);
    await _prefs.setInt('n_hot', p.hot);
    await _prefs.setInt('n_max', p.maxPerHour);
    notifyListeners();
  }

  Future<void> remember(String q) async {
    final s = q.trim();
    if (s.isEmpty) return;
    recentSearches = [s, ...recentSearches.where((x) => x != s)].take(8).toList();
    await _prefs.setStringList('recent', recentSearches);
    notifyListeners();
  }
}

/// One line of the in-app inbox: either a symbol that reached the chosen level or a bulletin.
class InboxItem {
  const InboxItem({required this.market, this.symbol, this.level = 0, this.digest, this.story, this.at});
  final Market market;
  final String? symbol;
  final int level;
  final Digest? digest;
  final Story? story;
  final DateTime? at;
}
