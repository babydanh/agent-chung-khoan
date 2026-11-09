import 'dart:convert';

import 'package:agent_ck/app.dart';
import 'package:agent_ck/data/demo_repository.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:agent_ck/widgets/candle_section.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _feed = '<rss><channel></channel></rss>';
final _candles = {
  'symbol': 'FPT',
  'o': [128000, 128500, 129000],
  'h': [129000, 129500, 130000],
  'l': [127500, 128000, 128500],
  'c': [128500, 129000, 129800],
  'v': [1000, 2000, 3000],
  't': ['1793588400', '1793589300', '1793590200'],
};

/// VCI gets candles, everything else (the RSS feeds) gets an empty feed; nothing reaches the network.
final _web = MockClient((r) async => r.url.host.contains('vietcap')
    ? http.Response(jsonEncode([_candles]), 200, headers: {'content-type': 'application/json'})
    : http.Response(_feed, 200, headers: {'content-type': 'application/rss+xml; charset=utf-8'}));

Future<void> _app(WidgetTester tester) async {
  SharedPreferences.setMockInitialValues({});
  final state = AppState(await SharedPreferences.getInstance(),
      repository: DemoRepository(now: DateTime(2026, 11, 5, 9, 41)), now: () => DateTime.utc(2026, 11, 5, 3, 0), httpClient: _web);
  tester.view.physicalSize = const Size(390 * 3, 844 * 3);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(AgentCkApp(state: state));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('TC-DETAIL-FR-01: a VN symbol offers 1m, 15m, 1h, 4h, 1D, 1W, 1M and switching changes the chart', (tester) async {
    await _app(tester);
    await tester.tap(find.text('FPT'));
    await tester.pumpAndSettle();

    for (final label in ['1m', '15m', '1h', '4h', '1D', '1W', '1M']) {
      expect(find.text(label), findsWidgets, reason: label);
    }
    expect(find.text('3m'), findsNothing);
    expect(find.byType(CandleSection), findsNothing, reason: 'it opens on the daily chart');
    expect(find.text('1T'), findsOneWidget);

    await tester.tap(find.text('1h'));
    await tester.pumpAndSettle();

    expect(find.byType(CandleSection), findsOneWidget);
    expect(find.textContaining('Đóng 129,80'), findsOneWidget);
    expect(find.text('1T'), findsNothing, reason: 'the 1T/1M/3M range belongs to the daily chart');

    await tester.tap(find.text('1D'));
    await tester.pumpAndSettle();

    expect(find.byType(CandleSection), findsNothing);
    expect(find.text('1T'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('TC-DETAIL-FR-02: a US symbol has no frame chips (VCI has no US candles)', (tester) async {
    await _app(tester);
    await tester.tap(find.text('US').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('NVDA'));
    await tester.pumpAndSettle();

    expect(find.text('Tổng quan'), findsOneWidget);
    expect(find.text('15m'), findsNothing);
    expect(find.text('1W'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}
