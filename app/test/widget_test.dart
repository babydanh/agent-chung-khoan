import 'package:agent_ck/app.dart';
import 'package:agent_ck/data/demo_repository.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _feed = '<rss><channel><item><title>VNM báo lãi quý 3 tăng 20% so với cùng kỳ</title><link>https://example.com/a</link>'
    '<pubDate>Thu, 05 Nov 2026 02:50:00 GMT</pubDate><description>d</description></item></channel></rss>';

/// No test reaches the network: every feed request gets this one headline.
final _web = MockClient((_) async => http.Response(_feed, 200, headers: {'content-type': 'application/rss+xml; charset=utf-8'}));

Future<AppState> _app(WidgetTester tester, {Map<String, Object> stored = const {}}) async {
  SharedPreferences.setMockInitialValues(stored);
  final prefs = await SharedPreferences.getInstance();
  final state = AppState(prefs, repository: DemoRepository(now: DateTime(2026, 11, 5, 9, 41)), now: () => DateTime.utc(2026, 11, 5, 3, 0), httpClient: _web);
  tester.view.physicalSize = const Size(390 * 3, 844 * 3);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(AgentCkApp(state: state));
  await tester.pumpAndSettle();
  return state;
}

void main() {
  testWidgets('opens on the board with the demo symbols, highest level first', (tester) async {
    await _app(tester);
    expect(find.text('FPT'), findsOneWidget);
    expect(find.text('VNM'), findsOneWidget);
    expect(find.text('cập nhật 09:41'), findsOneWidget);
    expect(tester.getTopLeft(find.text('VNM')).dy, lessThan(tester.getTopLeft(find.text('VCB')).dy));
  });

  testWidgets('tapping a row opens the detail and the star adds it to the watchlist', (tester) async {
    final s = await _app(tester);
    await tester.tap(find.text('FPT'));
    await tester.pumpAndSettle();
    expect(find.text('Tổng quan'), findsOneWidget);
    expect(find.text('NN ròng'), findsWidgets);
    await tester.tap(find.bySemanticsLabel('Theo dõi'));
    await tester.pumpAndSettle();
    expect(s.watch.values.expand((e) => e), contains('FPT'));
  });

  testWidgets('switching to US shows the US symbols', (tester) async {
    await _app(tester);
    await tester.tap(find.text('US').first);
    await tester.pumpAndSettle();
    expect(find.text('NVDA'), findsOneWidget);
    expect(find.text('FPT'), findsNothing);
  });

  testWidgets('every bottom tab opens without an error', (tester) async {
    await _app(tester);
    for (final t in ['Theo dõi', 'Tin', 'Vùng', 'Cài đặt', 'Bảng']) {
      await tester.tap(find.text(t).last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull, reason: t);
    }
  });

  testWidgets('TC-PIN-06: a device with a login but no password opens on the PIN screen, not the board', (tester) async {
    await _app(tester, stored: {'c_url': 'http://127.0.0.1:1', 'c_key': 'pk', 'c_mail': 'reader@x.test'});
    expect(find.text('Nhập mã PIN'), findsOneWidget);
    expect(find.text('Bảng'), findsNothing);
  });

  testWidgets('the level-3 chip hides everything below level 3', (tester) async {
    await _app(tester);
    await tester.tap(find.text('Mức 3'));
    await tester.pumpAndSettle();
    expect(find.text('VNM'), findsOneWidget);
    expect(find.text('VCB'), findsNothing);
  });

  testWidgets('the news tab shows the ranked headline with its event, a hot flag and a money-flow match', (tester) async {
    await _app(tester, stored: {'watch_VN': ['VNM']});
    await tester.tap(find.text('Tin').last);
    await tester.pumpAndSettle();
    expect(find.text('VNM báo lãi quý 3 tăng 20% so với cùng kỳ'), findsOneWidget);
    expect(find.text('Kết quả kinh doanh'), findsOneWidget);
    expect(find.text('Nóng'), findsOneWidget);
    expect(find.text('Khớp'), findsOneWidget, reason: 'VNM is level 3 in the demo data');
  });

  testWidgets('the notification settings offer the permission and a test message', (tester) async {
    await _app(tester);
    await tester.tap(find.text('Cài đặt').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hộp thư và lọc'));
    await tester.pumpAndSettle();
    expect(find.text('Tin nóng'), findsOneWidget);
    expect(find.text('Cho phép thông báo'), findsOneWidget);
    expect(find.text('Gửi thử'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
