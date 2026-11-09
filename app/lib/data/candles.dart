/// Candles for the detail chart (VN only), read straight from VCI by the phone and never stored: one symbol, one
/// frame, a few hundred rows. The daily frame is not here, it comes from the database (`bars_1d`).
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

/// The chart's time frames. [vci] is the name VCI knows the frame by (null = not served by VCI), [count] how many
/// candles to ask for.
enum Frame {
  m1('1m', 'ONE_MINUTE', 240),
  m15('15m', 'FIFTEEN_MINUTES', 120),
  h1('1h', 'ONE_HOUR', 120),
  h4('4h', 'FOUR_HOURS', 90),
  d1('1D', null, 0),
  w1('1W', 'ONE_WEEK', 60),
  mo1('1M', 'ONE_MONTH', 48);

  const Frame(this.label, this.vci, this.count);
  final String label;
  final String? vci;
  final int count;
}

class Candle {
  const Candle({required this.t, required this.o, required this.h, required this.l, required this.c, this.v = 0});
  final DateTime t; // the candle's start, a UTC instant
  final double o, h, l, c, v;

  /// Wall clock in Vietnam (UTC+7, no daylight saving), for labels.
  DateTime get vnTime => t.toUtc().add(const Duration(hours: 7));
}

class CandleError implements Exception {
  CandleError(this.message);
  final String message;

  @override
  String toString() => message;
}

final _url = Uri.parse('https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart');
const _headers = {
  'Content-Type': 'application/json',
  'Origin': 'https://trading.vietcap.com.vn',
  'Referer': 'https://trading.vietcap.com.vn/',
};
const _timeout = Duration(seconds: 15);
const _maxBytes = 2 * 1024 * 1024;

double? _num(Object? v) => v is num ? v.toDouble() : null;

/// VCI answers `[ {symbol, o, h, l, c, v, t} ]` with parallel arrays (`t` = epoch seconds, as strings). Oldest first;
/// a candle without a price is skipped, arrays of different lengths or any other shape give nothing.
List<Candle> parseVciCandles(Object? json) {
  if (json is! List || json.isEmpty || json.first is! Map) return const [];
  final m = json.first as Map;
  final cols = [for (final k in ['o', 'h', 'l', 'c', 'v', 't']) m[k]];
  if (cols.any((c) => c is! List) || cols.map((c) => (c as List).length).toSet().length != 1) return const [];
  final o = cols[0] as List, h = cols[1] as List, l = cols[2] as List, c = cols[3] as List, v = cols[4] as List, t = cols[5] as List;
  final out = <Candle>[];
  for (var i = 0; i < c.length; i++) {
    final secs = int.tryParse('${t[i]}');
    final oo = _num(o[i]), hh = _num(h[i]), ll = _num(l[i]), cc = _num(c[i]);
    if (secs == null || oo == null || hh == null || ll == null || cc == null) continue;
    out.add(Candle(t: DateTime.fromMillisecondsSinceEpoch(secs * 1000, isUtc: true), o: oo, h: hh, l: ll, c: cc, v: _num(v[i]) ?? 0));
  }
  return out;
}

/// The last [frame.count] candles of one symbol. Throws [CandleError] on a network error, a bad status or a body that
/// is not JSON; an empty answer is an empty list.
Future<List<Candle>> fetchCandles(http.Client client, String symbol, Frame frame, {DateTime? now}) async {
  final name = frame.vci;
  if (name == null) throw ArgumentError.value(frame, 'frame', 'has no VCI request');
  final body = jsonEncode({'timeFrame': name, 'symbols': [symbol], 'countBack': frame.count, 'to': (now ?? DateTime.now()).millisecondsSinceEpoch ~/ 1000});
  try {
    final res = await client.post(_url, headers: _headers, body: body).timeout(_timeout);
    if (res.statusCode != 200) throw CandleError('HTTP ${res.statusCode}');
    if (res.bodyBytes.length > _maxBytes) throw CandleError('response too large');
    return parseVciCandles(jsonDecode(utf8.decode(res.bodyBytes, allowMalformed: true)));
  } on TimeoutException {
    throw CandleError('timeout');
  } on http.ClientException catch (e) {
    throw CandleError(e.message);
  } on FormatException {
    throw CandleError('bad response');
  }
}

/// True on weekdays between 09:00 and 15:05 Vietnam time, when the price board changes.
bool vnSessionOpen(DateTime now) {
  final t = now.toUtc().add(const Duration(hours: 7));
  final minutes = t.hour * 60 + t.minute;
  return t.weekday <= DateTime.friday && minutes >= 9 * 60 && minutes <= 15 * 60 + 5;
}
