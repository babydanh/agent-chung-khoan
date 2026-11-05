import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app.dart';
import 'notify/background.dart';
import 'notify/notifier.dart';
import 'state/app_state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final state = AppState(prefs, notifier: SystemNotifier());
  runApp(AgentCkApp(state: state));
  // Not awaited: the app must open even if the system refuses the background task.
  startBackground().catchError((Object e) => debugPrint('background task not started: $e'));
}
