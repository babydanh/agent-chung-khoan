import 'dart:convert';

import 'package:agent_ck/data/repository.dart';
import 'package:agent_ck/data/supabase_repository.dart';
import 'package:agent_ck/models/models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _cfg = SupabaseConfig(url: 'https://x.supabase.test', anonKey: 'anon-public', email: 'me@x.test', password: 'pw');

void _builtInConnectionTests() {
  const built = SupabaseConfig(url: 'https://built.test', anonKey: 'pk', email: '', password: '');

  group('SupabaseConfig.load with a connection built into the app', () {
    test('a device with nothing saved uses the built-in connection', () async {
      SharedPreferences.setMockInitialValues({});
      final c = SupabaseConfig.load(await SharedPreferences.getInstance(), fallback: built);
      expect(c.complete, isTrue);
      expect(c.url, 'https://built.test');
    });

    test('what the user saved wins over the built-in connection', () async {
      SharedPreferences.setMockInitialValues({'c_url': 'https://mine.test', 'c_key': 'k', 'c_mail': 'a@b.test', 'c_pass': 'p'});
      final c = SupabaseConfig.load(await SharedPreferences.getInstance(), fallback: built);
      expect((c.url, c.email), ('https://mine.test', 'a@b.test'));
    });

    test('a saved disconnect (blank values) stays in demo mode', () async {
      SharedPreferences.setMockInitialValues({'c_url': '', 'c_key': '', 'c_mail': '', 'c_pass': ''});
      expect(SupabaseConfig.load(await SharedPreferences.getInstance(), fallback: built).complete, isFalse);
    });

    test('a plain build has no built-in connection', () {
      expect(SupabaseConfig.builtIn.complete, isFalse);
    });
  });

  group('anonymous connection (URL and public key, no login)', () {
    test('TC-ANON-03: URL and key are enough to be complete; a login is optional', () {
      expect(built.complete, isTrue);
      expect(built.hasLogin, isFalse);
      expect(const SupabaseConfig(url: 'u', anonKey: '', email: '', password: '').complete, isFalse);
      expect(const SupabaseConfig(url: '', anonKey: 'k', email: '', password: '').complete, isFalse);
    });

    test('TC-ANON-04: reading signs in nowhere and sends only the public key', () async {
      final seen = <http.Request>[];
      final client = MockClient((req) async {
        seen.add(req);
        return _json([]);
      });
      final repo = SupabaseRepository(built, client: client);
      expect(await repo.signalHistory(Market.vn, 'FPT'), isEmpty);
      expect(seen, isNotEmpty);
      expect(seen.where((r) => r.url.path.startsWith('/auth/')), isEmpty, reason: 'no sign-in call');
      expect(seen.every((r) => r.headers['apikey'] == 'pk' && !r.headers.containsKey('Authorization')), isTrue);
    });

    test('TC-ANON-05: a refused read is reported as a permission error, without retrying the sign-in', () async {
      var calls = 0;
      final repo = SupabaseRepository(built, client: MockClient((_) async {
        calls++;
        return _json({}, 401);
      }));
      await expectLater(repo.signalHistory(Market.vn, 'FPT'), throwsA(isA<RepositoryException>().having((e) => e.auth, 'auth', isTrue)));
      expect(calls, 1);
    });
  });
}

http.Response _json(Object body, [int status = 200]) => http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

/// A fake server that answers the auth call and the table reads the app makes.
MockClient _server({List<http.Request>? seen, bool badLogin = false, int quoteStatus = 200, int quotePages = 1, int notesStatus = 200}) {
  var logins = 0;
  return MockClient((req) async {
    seen?.add(req);
    final path = req.url.path;
    if (path == '/auth/v1/token') {
      logins++;
      if (badLogin) return _json({'error': 'invalid_grant'}, 400);
      return _json({'access_token': 'tok$logins', 'expires_in': 3600});
    }
    if (req.headers['Authorization'] != 'Bearer tok$logins' || req.headers['apikey'] != 'anon-public') return _json({}, 401);
    final q = req.url.queryParameters;
    switch (path) {
      case '/rest/v1/quotes_latest':
        if (quoteStatus != 200) return _json({}, quoteStatus);
        final offset = int.parse(q['offset'] ?? '0');
        final rows = quotePages == 1
            ? [{'market': 'VN', 'symbol': 'FPT', 'exchange': 'HOSE', 'price': 131200, 'ref_price': 128500, 'vol': 100, 'val': 1, 'asof': '2026-11-05T02:00:00+00:00'}]
            : List.generate(offset == 0 ? 1000 : 5, (i) => {'market': 'VN', 'symbol': 'S${offset + i}', 'price': 1});
        return _json(rows);
      case '/rest/v1/signals':
        if (q.containsKey('asof')) return _json([{'symbol': 'FPT', 'level': 3, 'learning': false, 'items': [{'id': 'S1'}], 'asof': q['asof']!.substring(3)}]);
        return _json([{'asof': '2026-11-05T02:00:00+00:00'}]);
      case '/rest/v1/zones':
        return _json([{'symbol': 'FPT', 'kind': 'Pivot', 'price_lo': 1, 'price_hi': 2, 'asof': '2026-11-05T02:00:00+00:00'}, {'symbol': 'VNM', 'kind': 'Old', 'price_lo': 1, 'price_hi': 2, 'asof': '2026-11-04T02:00:00+00:00'}]);
      case '/rest/v1/digests':
        return _json([{'digest_date': '2026-11-05', 'kind': 'slot-0930', 'body': 'Mức 3: FPT', 'created_at': '2026-11-05T02:30:00+00:00'}]);
      case '/rest/v1/news':
        return _json([{'title': 'FPT ký hợp đồng', 'url': 'https://cafef.vn/x', 'source': 'CafeF', 'symbol': 'FPT', 'published_at': '2026-11-05T02:00:00+00:00'}]);
      case '/rest/v1/news_notes':
        if (notesStatus != 200) return _json({}, notesStatus);
        return _json([{'url': 'https://cafef.vn/x', 'kind': 'contract', 'aspect': 'A.', 'outlook': 'pos', 'note': 'B.'}]);
      case '/rest/v1/snapshot_meta':
        return _json([{'asof': '2026-11-05T02:00:00+00:00'}]);
      case '/rest/v1/bars_1d':
        return _json([{'trade_date': '2026-11-04', 'close': 2.0, 'vol': 1}, {'trade_date': '2026-11-03', 'close': 1.0, 'vol': 1}, {'trade_date': '2026-11-02', 'close': null, 'vol': 1}]);
    }
    return _json({}, 404);
  });
}

void main() {
  _builtInConnectionTests();
  test('load signs in once and reads every table for the market', () async {
    final seen = <http.Request>[];
    final repo = SupabaseRepository(_cfg, client: _server(seen: seen));
    final d = await repo.load(Market.vn);
    expect(d.quotes.single.symbol, 'FPT');
    expect(d.signals['FPT']!.level, 3);
    expect(d.zones.map((z) => z.symbol), ['FPT'], reason: 'only the newest batch of zones');
    expect(d.digests.single.body, 'Mức 3: FPT');
    expect(d.news.single.symbol, 'FPT');
    expect(d.status.lastSnapshot, isNotNull);
    expect(seen.where((r) => r.url.path == '/auth/v1/token').length, 1);
    expect(seen.where((r) => r.url.path.startsWith('/rest/v1/')).every((r) => r.method == 'GET'), isTrue, reason: 'the app only reads');
    expect(seen.where((r) => r.url.path == '/rest/v1/quotes_latest').single.url.queryParameters['market'], 'eq.VN');
  });

  test('TC-NNOTE-07: the notes on headlines are read by link, for the market asked', () async {
    final seen = <http.Request>[];
    final d = await SupabaseRepository(_cfg, client: _server(seen: seen)).load(Market.vn);
    expect(d.notes['https://cafef.vn/x']!.kind, 'contract');
    expect(d.notes['https://cafef.vn/x']!.outlook, 'pos');
    expect(seen.where((r) => r.url.path == '/rest/v1/news_notes').single.url.queryParameters['market'], 'eq.VN');
  });

  test('TC-NNOTE-08: the notes are optional: a missing table or a server error leaves the prices and the news intact', () async {
    for (final status in [404, 500]) {
      final d = await SupabaseRepository(_cfg, client: _server(notesStatus: status)).load(Market.vn);
      expect(d.notes, isEmpty, reason: '$status');
      expect(d.quotes.single.symbol, 'FPT');
      expect(d.news.single.symbol, 'FPT');
    }
  });

  test('a wrong password is an auth error, not a network error', () async {
    final repo = SupabaseRepository(_cfg, client: _server(badLogin: true));
    await expectLater(repo.load(Market.vn), throwsA(isA<RepositoryException>().having((e) => e.auth, 'auth', isTrue)));
  });

  test('a server error names the table', () async {
    final repo = SupabaseRepository(_cfg, client: _server(quoteStatus: 500));
    await expectLater(repo.load(Market.vn), throwsA(isA<RepositoryException>().having((e) => e.message, 'message', contains('quotes_latest'))));
  });

  test('more than one page of rows is read to the end', () async {
    final repo = SupabaseRepository(_cfg, client: _server(quotePages: 2));
    final d = await repo.load(Market.vn);
    expect(d.quotes.length, 1005);
  });

  test('daily bars skip rows without a close and come back oldest first', () async {
    final repo = SupabaseRepository(_cfg, client: _server());
    final b = await repo.bars(Market.vn, 'FPT');
    expect(b.map((x) => x.close), [1.0, 2.0]);
  });

  test('an expired token is replaced once and the read retried', () async {
    var tokens = 0;
    var first = true;
    final client = MockClient((req) async {
      if (req.url.path == '/auth/v1/token') return _json({'access_token': 't${++tokens}', 'expires_in': 3600});
      if (first) {
        first = false;
        return _json({}, 401);
      }
      return _json([]);
    });
    final repo = SupabaseRepository(_cfg, client: client);
    expect(await repo.signalHistory(Market.vn, 'FPT'), isEmpty);
    expect(tokens, 2);
  });
}
