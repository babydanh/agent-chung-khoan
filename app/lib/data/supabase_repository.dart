import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/models.dart';
import 'repository.dart';

class SupabaseConfig {
  const SupabaseConfig({required this.url, required this.anonKey, required this.email, required this.password});
  final String url, anonKey, email, password;

  /// Baked in at build time with --dart-define (see the apk job in app.yml); empty in a plain build.
  /// Only the URL and the public key: the app reads VN data without a login (see 0003_anon_reads_vn.sql).
  static const builtIn = SupabaseConfig(
    url: String.fromEnvironment('SUPABASE_URL'),
    anonKey: String.fromEnvironment('SUPABASE_ANON_KEY'),
    email: '',
    password: '',
  );

  /// The connection saved on this device (the same keys the settings screen writes). A value never saved falls back
  /// to the built-in one; a saved blank (the settings "disconnect") stays blank, so demo mode is still reachable.
  factory SupabaseConfig.load(SharedPreferences p, {SupabaseConfig fallback = builtIn}) => SupabaseConfig(
        url: p.getString('c_url') ?? fallback.url,
        anonKey: p.getString('c_key') ?? fallback.anonKey,
        email: p.getString('c_mail') ?? fallback.email,
        password: p.getString('c_pass') ?? fallback.password,
      );

  /// URL and public key are enough; a login is optional (the owner adds one to also read US data).
  bool get complete => url.isNotEmpty && anonKey.isNotEmpty;
  bool get hasLogin => email.isNotEmpty && password.isNotEmpty;
}

/// Reads the bot's tables through the Supabase REST API with the owner's fixed account.
/// Row-level security decides what is visible; this class never writes.
class SupabaseRepository implements Repository {
  SupabaseRepository(this.config, {http.Client? client, DateTime Function()? now})
      : _http = client ?? http.Client(),
        _now = now ?? DateTime.now;

  final SupabaseConfig config;
  final http.Client _http;
  final DateTime Function() _now;
  String? _token;
  DateTime? _tokenUntil;

  static const _page = 1000;
  Uri _uri(String path, [Map<String, String>? q]) {
    final base = config.url.endsWith('/') ? config.url.substring(0, config.url.length - 1) : config.url;
    return Uri.parse('$base$path').replace(queryParameters: q);
  }

  Future<String> _login() async {
    if (_token != null && _tokenUntil != null && _now().isBefore(_tokenUntil!)) return _token!;
    final res = await _http.post(
      _uri('/auth/v1/token', {'grant_type': 'password'}),
      headers: {'apikey': config.anonKey, 'Content-Type': 'application/json'},
      body: jsonEncode({'email': config.email, 'password': config.password}),
    );
    if (res.statusCode == 400 || res.statusCode == 401 || res.statusCode == 422) {
      throw RepositoryException('Sai email hoặc mật khẩu', auth: true);
    }
    if (res.statusCode != 200) throw RepositoryException('Đăng nhập lỗi ${res.statusCode}');
    final body = jsonDecode(res.body) as Map<String, dynamic>;
    _token = body['access_token'] as String?;
    final secs = (body['expires_in'] as num?)?.toInt() ?? 3600;
    _tokenUntil = _now().add(Duration(seconds: secs > 120 ? secs - 60 : secs));
    if (_token == null) throw RepositoryException('Phản hồi đăng nhập thiếu khoá', auth: true);
    return _token!;
  }

  Future<List<Map<String, dynamic>>> _select(String table, Map<String, String> q, {bool retried = false}) async {
    final token = config.hasLogin ? await _login() : null; // no login: the public key alone reads the VN rows
    final res = await _http.get(_uri('/rest/v1/$table', q), headers: {
      'apikey': config.anonKey,
      if (token != null) 'Authorization': 'Bearer $token',
      'Accept': 'application/json',
    });
    if (res.statusCode == 401 && !retried && token != null) {
      _token = null;
      return _select(table, q, retried: true);
    }
    if (res.statusCode == 401 || res.statusCode == 403) throw RepositoryException('Không có quyền đọc $table', auth: true);
    if (res.statusCode != 200) throw RepositoryException('Đọc $table lỗi ${res.statusCode}');
    final data = jsonDecode(res.body);
    if (data is! List) throw RepositoryException('Phản hồi $table không phải danh sách');
    return [for (final r in data) if (r is Map<String, dynamic>) r];
  }

  Future<List<Map<String, dynamic>>> _selectAll(String table, Map<String, String> q) async {
    final out = <Map<String, dynamic>>[];
    for (var offset = 0;; offset += _page) {
      final rows = await _select(table, {...q, 'limit': '$_page', 'offset': '$offset'});
      out.addAll(rows);
      if (rows.length < _page) return out;
    }
  }

  /// The bot's notes on headlines, by link. Optional: a missing table (an older database) or a failed read leaves the
  /// notes empty instead of hiding the prices.
  Future<Map<String, NewsNote>> _notes(String market) async {
    try {
      final rows = await _select('news_notes', {
        'market': market, 'select': 'url,kind,aspect,outlook,note', 'order': 'created_at.desc', 'limit': '300',
      });
      return {for (final r in rows) if (r['url'] is String) r['url'] as String: NewsNote.fromJson(r)};
    } on Exception {
      return const {};
    }
  }

  @override
  Future<MarketData> load(Market market) async {
    final m = 'eq.${market.key}';
    final quotes = await _selectAll('quotes_latest', {'market': m, 'select': '*', 'order': 'symbol.asc'});
    final last = await _select('signals', {'market': m, 'select': 'asof', 'order': 'asof.desc', 'limit': '1'});
    final signals = <String, SignalRow>{};
    if (last.isNotEmpty) {
      final rows = await _selectAll('signals', {
        'market': m, 'asof': 'eq.${last.first['asof']}', 'select': 'symbol,level,learning,items,asof', 'order': 'symbol.asc',
      });
      for (final r in rows) {
        final s = SignalRow.fromJson(r);
        signals[s.symbol] = s;
      }
    }
    final zoneRows = await _select('zones', {
      'market': m, 'select': 'symbol,kind,price_lo,price_hi,asof', 'order': 'asof.desc', 'limit': '500',
    });
    final newest = zoneRows.isEmpty ? null : zoneRows.first['asof'];
    final digests = await _select('digests', {
      'market': m, 'select': 'digest_date,kind,body,created_at', 'order': 'created_at.desc', 'limit': '40',
    });
    final news = await _select('news', {
      'market': m, 'select': 'title,url,source,symbol,published_at', 'order': 'published_at.desc', 'limit': '100',
    });
    final notes = await _notes(m);
    final meta = await _select('snapshot_meta', {
      'market': m, 'select': 'asof,slot_start,symbols,signals', 'order': 'asof.desc', 'limit': '1',
    });
    final asof = quotes.map((q) => q['asof']).whereType<String>().fold<String?>(null, (a, b) => a == null || b.compareTo(a) > 0 ? b : a);
    return MarketData(
      quotes: [for (final r in quotes) Quote.fromJson(r)],
      signals: signals,
      zones: [for (final r in zoneRows) if (r['asof'] == newest) Zone.fromJson(r)],
      digests: [for (final r in digests) Digest.fromJson(r)],
      news: [for (final r in news) NewsItem.fromJson(r)],
      notes: notes,
      status: BotStatus(lastSnapshot: meta.isEmpty ? null : DateTime.tryParse('${meta.first['asof']}')?.toLocal()),
      asof: asof == null ? null : DateTime.tryParse(asof)?.toLocal(),
    );
  }

  @override
  Future<List<DailyBar>> bars(Market market, String symbol, {int days = 60}) async {
    final rows = await _select('bars_1d', {
      'market': 'eq.${market.key}', 'symbol': 'eq.$symbol', 'select': 'trade_date,close,vol',
      'order': 'trade_date.desc', 'limit': '$days',
    });
    return [
      for (final r in rows.reversed)
        if (r['close'] is num)
          DailyBar(date: DateTime.tryParse('${r['trade_date']}') ?? DateTime.fromMillisecondsSinceEpoch(0), close: (r['close'] as num).toDouble(), vol: (r['vol'] as num?)?.toDouble() ?? 0)
    ];
  }

  @override
  Future<List<SignalRow>> signalHistory(Market market, String symbol, {int limit = 60}) async {
    final rows = await _select('signals', {
      'market': 'eq.${market.key}', 'symbol': 'eq.$symbol', 'select': 'symbol,level,learning,items,asof',
      'order': 'asof.desc', 'limit': '$limit',
    });
    return [for (final r in rows) SignalRow.fromJson(r)];
  }
}
