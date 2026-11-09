import 'dart:convert';

import 'package:agent_ck/data/candles.dart';
import 'package:agent_ck/models/models.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:agent_ck/state/scope.dart';
import 'package:agent_ck/theme/theme.dart';
import 'package:agent_ck/widgets/candle_chart.dart';
import 'package:agent_ck/widgets/candle_section.dart';
import 'package:agent_ck/widgets/line_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Three 15-minute candles of 2 Nov 2026 (03:00, 03:15, 03:30 UTC = 10:00, 10:15, 10:30 in Ho Chi Minh City).
Map<String, Object?> _vci(List<num> closes) => {
      'symbol': 'FPT',
      'o': [for (final c in closes) c - 100],
      'h': [for (final c in closes) c + 200],
      'l': [for (final c in closes) c - 300],
      'c': closes,
      'v': [1000, 2000, 3000],
      't': ['1793588400', '1793589300', '1793590200'],
    };

http.Response _ok(List<num> closes) => http.Response(jsonEncode([_vci(closes)]), 200, headers: {'content-type': 'application/json'});

final _monday10am = DateTime.utc(2026, 11, 9, 3, 0);
final _saturday = DateTime.utc(2026, 11, 7, 3, 0);

Future<void> _pump(WidgetTester tester, Future<http.Response> Function(http.Request) handler, {DateTime? clock, Frame frame = Frame.m15}) async {
  SharedPreferences.setMockInitialValues({});
  final state = AppState(await SharedPreferences.getInstance(), httpClient: MockClient(handler));
  await tester.pumpWidget(AppScope(
    state: state,
    child: MaterialApp(
      theme: buildTheme(Brightness.dark),
      home: Scaffold(
        body: SingleChildScrollView(child: CandleSection(key: ValueKey(frame), market: Market.vn, symbol: 'FPT', frame: frame, clock: () => clock ?? _monday10am)),
      ),
    ),
  ));
}

Future<void> _dispose(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox()); // cancels the refresh timer
}

void main() {
  testWidgets('TC-CSEC-01: it shows a loading mark, then the smooth line and the last candle in plain numbers', (tester) async {
    await _pump(tester, (_) async => _ok([50200, 50400, 50800]));
    expect(find.text('…'), findsOneWidget);

    await tester.pumpAndSettle();

    expect(find.byType(LineChart), findsOneWidget);
    expect(find.byType(CandleChart), findsNothing);
    expect(find.textContaining('Đóng 50,80'), findsOneWidget);
    expect(find.textContaining('10:30'), findsWidgets, reason: 'the last candle is stamped in Vietnam time');
    await _dispose(tester);
  });

  testWidgets('TC-CSEC-02: the switch shows candlesticks instead of the line', (tester) async {
    await _pump(tester, (_) async => _ok([50200, 50400, 50800]));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nến'));
    await tester.pumpAndSettle();

    expect(find.byType(CandleChart), findsOneWidget);
    expect(find.byType(LineChart), findsNothing);
    await _dispose(tester);
  });

  testWidgets('TC-CSEC-03: a failed load says so and a tap tries again', (tester) async {
    var calls = 0;
    await _pump(tester, (_) async => ++calls == 1 ? http.Response('x', 500) : _ok([50200, 50400, 50800]));
    await tester.pumpAndSettle();

    expect(find.textContaining('Không tải được'), findsOneWidget);
    await tester.tap(find.textContaining('Không tải được'));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.byType(LineChart), findsOneWidget);
    await _dispose(tester);
  });

  testWidgets('TC-CSEC-04: no candles says there is nothing for this frame', (tester) async {
    await _pump(tester, (_) async => http.Response('[]', 200));
    await tester.pumpAndSettle();

    expect(find.text('Chưa có dữ liệu khung này'), findsOneWidget);
    await _dispose(tester);
  });

  testWidgets('TC-CSEC-05: in the session it asks again every 20 seconds and moves the last candle', (tester) async {
    var calls = 0;
    await _pump(tester, (_) async => _ok(++calls == 1 ? [50200, 50400, 50800] : [50200, 50400, 51300]));
    await tester.pumpAndSettle();
    expect(find.textContaining('Đóng 50,80'), findsOneWidget);

    await tester.pump(const Duration(seconds: 21));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.textContaining('Đóng 51,30'), findsOneWidget);
    expect(find.textContaining('20 giây'), findsOneWidget);
    await _dispose(tester);
  });

  testWidgets('TC-CSEC-06: outside the session it does not poll', (tester) async {
    var calls = 0;
    await _pump(tester, (_) async {
      calls++;
      return _ok([50200, 50400, 50800]);
    }, clock: _saturday);
    await tester.pumpAndSettle();

    await tester.pump(const Duration(seconds: 61));

    expect(calls, 1);
    expect(find.textContaining('Ngoài phiên'), findsOneWidget);
    await _dispose(tester);
  });

  testWidgets('TC-CSEC-07: a failed refresh keeps the candles already shown', (tester) async {
    var calls = 0;
    await _pump(tester, (_) async => ++calls == 1 ? _ok([50200, 50400, 50800]) : http.Response('x', 503));
    await tester.pumpAndSettle();

    await tester.pump(const Duration(seconds: 21));
    await tester.pumpAndSettle();

    expect(calls, 2);
    expect(find.byType(LineChart), findsOneWidget);
    expect(find.textContaining('Không tải được'), findsNothing);
    await _dispose(tester);
  });

  testWidgets('TC-CSEC-08: weekly and monthly frames are stamped with the date, not the time', (tester) async {
    await _pump(tester, (_) async => _ok([50200, 50400, 50800]), frame: Frame.w1);
    await tester.pumpAndSettle();

    expect(find.textContaining('02/11/2026'), findsWidgets);
    expect(find.textContaining('10:30'), findsNothing);
    await _dispose(tester);
  });
}
