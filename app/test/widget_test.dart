import 'package:agent_ck/app.dart';
import 'package:agent_ck/data/demo_repository.dart';
import 'package:agent_ck/state/app_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<AppState> _app(WidgetTester tester) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final state = AppState(prefs, repository: DemoRepository(now: DateTime(2026, 11, 5, 9, 41)), now: () => DateTime(2026, 11, 5, 9, 41));
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

  testWidgets('the level-3 chip hides everything below level 3', (tester) async {
    await _app(tester);
    await tester.tap(find.text('Mức 3'));
    await tester.pumpAndSettle();
    expect(find.text('VNM'), findsOneWidget);
    expect(find.text('VCB'), findsNothing);
  });
}
