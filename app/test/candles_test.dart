import 'dart:convert';

import 'package:agent_ck/data/candles.dart';
import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

// VCI answers one symbol as parallel arrays; t is epoch seconds as a string.
Map<String, Object?> _vci({List<Object?>? c}) => {
      'symbol': 'FPT',
      'o': [52400, 50300, 50600],
      'h': [52500, 51700, 53900],
      'l': [50100, 49550, 50400],
      'c': c ?? [50200, 50400, 53900],
      'v': [12293400, 9249300, 12822500],
      't': ['1793577600', '1793664000', '1793750400'],
    };

http.Response _json(Object body, [int status = 200]) => http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

void main() {
  test('TC-CANDLE-01: VCI arrays become candles, oldest first, with the time as a UTC instant', () {
    final list = parseVciCandles([_vci()]);

    expect(list, hasLength(3));
    expect(list.first.t, DateTime.utc(2026, 11, 2));
    expect([list.first.o, list.first.h, list.first.l, list.first.c, list.first.v], [52400, 52500, 50100, 50200, 12293400]);
    expect(list.last.c, 53900);
    expect(list.first.vnTime, DateTime.utc(2026, 11, 2, 7), reason: 'VN wall clock is UTC+7');
  });

  test('TC-CANDLE-02: candles without a price are skipped; ragged arrays and other shapes give nothing', () {
    expect(parseVciCandles([_vci(c: [null, 50400, 53900])]).map((e) => e.c), [50400, 53900]);
    expect(parseVciCandles([_vci(c: [1, 2])]), isEmpty);
    expect(parseVciCandles([]), isEmpty);
    expect(parseVciCandles({'a': 1}), isEmpty);
    expect(parseVciCandles(null), isEmpty);
  });

  test('TC-CANDLE-03: the chosen frames are exactly these (no 3m), each with its VCI name', () {
    expect(Frame.values.map((f) => f.label), ['1m', '15m', '1h', '4h', '1D', '1W', '1M']);
    expect(Frame.values.where((f) => f.vci != null).map((f) => f.vci), ['ONE_MINUTE', 'FIFTEEN_MINUTES', 'ONE_HOUR', 'FOUR_HOURS', 'ONE_WEEK', 'ONE_MONTH']);
    expect(Frame.d1.vci, isNull, reason: 'daily candles come from the database, not from VCI');
  });

  test('TC-CANDLE-04: the request names one symbol, the frame and the count, with the VCI origin headers', () async {
    http.Request? seen;
    final client = MockClient((r) async {
      seen = r;
      return _json([_vci()]);
    });

    final list = await fetchCandles(client, 'FPT', Frame.m15, now: DateTime.utc(2026, 11, 9, 3));

    expect(list, hasLength(3));
    final body = jsonDecode(seen!.body) as Map<String, dynamic>;
    expect(body['symbols'], ['FPT']);
    expect(body['timeFrame'], 'FIFTEEN_MINUTES');
    expect(body['countBack'], Frame.m15.count);
    expect(body['to'], DateTime.utc(2026, 11, 9, 3).millisecondsSinceEpoch ~/ 1000);
    expect(seen!.headers['Origin'], 'https://trading.vietcap.com.vn');
    expect(seen!.url.scheme, 'https');
  });

  test('TC-CANDLE-05: an HTTP error or a broken body is a CandleError, an empty answer is just no candles', () async {
    expect(fetchCandles(MockClient((_) async => _json({'x': 1}, 500)), 'FPT', Frame.h1), throwsA(isA<CandleError>()));
    expect(fetchCandles(MockClient((_) async => http.Response('<html>', 200)), 'FPT', Frame.h1), throwsA(isA<CandleError>()));
    expect(await fetchCandles(MockClient((_) async => _json([])), 'FPT', Frame.h1), isEmpty);
  });

  test('TC-CANDLE-06: the daily frame has no VCI request', () {
    expect(fetchCandles(MockClient((_) async => _json([])), 'FPT', Frame.d1), throwsArgumentError);
  });

  test('TC-CANDLE-07: the VN session runs weekdays 09:00 to 15:05 Ho Chi Minh time', () {
    DateTime vn(int d, int h, int m) => DateTime.utc(2026, 11, d, h, m).subtract(const Duration(hours: 7)); // Mon 9 Nov 2026
    expect(vnSessionOpen(vn(9, 8, 59)), isFalse);
    expect(vnSessionOpen(vn(9, 9, 0)), isTrue);
    expect(vnSessionOpen(vn(9, 12, 0)), isTrue, reason: 'lunch is still inside the window, the board just does not move');
    expect(vnSessionOpen(vn(9, 15, 5)), isTrue);
    expect(vnSessionOpen(vn(9, 15, 6)), isFalse);
    expect(vnSessionOpen(vn(14, 10, 0)), isFalse, reason: 'Saturday');
    expect(vnSessionOpen(vn(15, 10, 0)), isFalse, reason: 'Sunday');
  });

  test('TC-CANDLE-08: the app state refuses a US frame without calling out, and passes VN through the shared client', () async {
    SharedPreferences.setMockInitialValues({});
    var calls = 0;
    final s = AppState(await SharedPreferences.getInstance(), httpClient: MockClient((_) async {
      calls++;
      return _json([_vci()]);
    }));

    await expectLater(s.candles(Market.us, 'NVDA', Frame.m1), throwsA(isA<CandleError>()));
    expect(calls, 0);
    expect(await s.candles(Market.vn, 'FPT', Frame.m1), hasLength(3));
    expect(calls, 1);
  });
}
