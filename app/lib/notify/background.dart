/// Android background task: every 15 minutes (the system minimum) read the data and the news and show what the
/// planner says. It runs in its own isolate, so it rebuilds everything from the stored settings.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';

import '../data/supabase_repository.dart';
import 'cycle.dart';
import 'notifier.dart';

const _uniqueName = 'ck-notify';
const _taskName = 'ck_notify_cycle';

@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.reload(); // the app may have changed the settings since this isolate started
    final cfg = SupabaseConfig.load(prefs);
    if (!cfg.complete) return true; // sample data: nothing real to notify about
    final client = http.Client();
    try {
      await runCycle(prefs: prefs, repo: SupabaseRepository(cfg, client: client), client: client, notifier: SystemNotifier());
    } finally {
      client.close();
    }
    return true;
  });
}

/// Registers the periodic task (replacing an older registration). Does nothing off Android.
Future<void> startBackground() async {
  if (kIsWeb || !Platform.isAndroid) return;
  await Workmanager().initialize(callbackDispatcher);
  await Workmanager().registerPeriodicTask(
    _uniqueName,
    _taskName,
    frequency: const Duration(minutes: 15),
    constraints: Constraints(networkType: NetworkType.connected),
    existingWorkPolicy: ExistingPeriodicWorkPolicy.update,
  );
}
