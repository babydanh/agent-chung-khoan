import 'package:flutter/material.dart';

import 'screens/board_screen.dart';
import 'screens/news_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/watch_screen.dart';
import 'screens/zone_screen.dart';
import 'state/app_state.dart';
import 'state/scope.dart';
import 'theme/theme.dart';
import 'ui/app_icon.dart';

class AgentCkApp extends StatelessWidget {
  const AgentCkApp({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: state,
      child: ListenableBuilder(
        listenable: state,
        builder: (context, _) => MaterialApp(
          title: 'Agent Chứng Khoán',
          debugShowCheckedModeBanner: false,
          theme: buildTheme(Brightness.light),
          darkTheme: buildTheme(Brightness.dark),
          themeMode: state.themeMode,
          home: const Shell(),
        ),
      ),
    );
  }
}

class Shell extends StatefulWidget {
  const Shell({super.key});

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int _tab = 0;
  bool _started = false;

  static const _tabs = [('board', 'Bảng'), ('star', 'Theo dõi'), ('news', 'Tin'), ('zone', 'Vùng'), ('settings', 'Cài đặt')];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_started) {
      _started = true;
      final s = AppScope.read(context);
      // Not during build: load() notifies listeners straight away.
      WidgetsBinding.instance.addPostFrameCallback((_) => s.refreshAll());
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return Scaffold(
      body: IndexedStack(index: _tab, children: const [BoardScreen(), WatchScreen(), NewsScreen(), ZoneScreen(), SettingsScreen()]),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(color: c.surface, border: Border(top: BorderSide(color: c.line))),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 56,
            child: Row(children: [
              for (var i = 0; i < _tabs.length; i++)
                Expanded(
                  child: Semantics(
                    button: true,
                    selected: i == _tab,
                    label: _tabs[i].$2,
                    child: InkWell(
                      onTap: () => setState(() => _tab = i),
                      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                        AppIcon(_tabs[i].$1, size: 22, color: i == _tab ? c.accent : c.text2),
                        const SizedBox(height: 2),
                        Text(_tabs[i].$2, style: AppText.base(i == _tab ? c.accent : c.text2, size: 11, weight: FontWeight.w600)),
                      ]),
                    ),
                  ),
                ),
            ]),
          ),
        ),
      ),
    );
  }
}
