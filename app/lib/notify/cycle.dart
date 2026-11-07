/// One notification cycle: read the data, read the news, decide with the planner, show, remember. Used by the
/// background task; the foreground refresh uses the same planner on data it already has.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../data/repository.dart';
import '../models/models.dart';
import '../news/news_service.dart';
import '../news/rank.dart';
import '../state/app_state.dart' show NotifyPrefs;
import 'notifier.dart';
import 'planner.dart';

const stateKey = 'notify_state';

NotifyState loadState(SharedPreferences prefs) {
  final raw = prefs.getString(stateKey);
  if (raw == null) return NotifyState();
  try {
    return NotifyState.fromJson(jsonDecode(raw));
  } catch (_) {
    return NotifyState(); // a damaged state must not stop the notices
  }
}

Future<void> saveState(SharedPreferences prefs, NotifyState s) => prefs.setString(stateKey, jsonEncode(s.toJson()));

/// Shows what [plan] says and stores the new state. A notice the platform refuses is skipped, not retried.
Future<int> showAll(Notifier notifier, PlanResult r) async {
  var shown = 0;
  for (final n in r.show) {
    try {
      await notifier.show(n);
      shown++;
    } catch (_) {}
  }
  return shown;
}

/// Returns how many notifications were shown. Nothing is shown and nothing stored when the data cannot be read.
Future<int> runCycle({
  required SharedPreferences prefs,
  required Repository repo,
  required http.Client client,
  required Notifier notifier,
  DateTime? now,
}) async {
  final at = (now ?? DateTime.now()).toUtc();
  final np = NotifyPrefs.load(prefs);
  final data = <Market, MarketData>{};
  try {
    for (final m in Market.values) {
      if (m == Market.vn ? np.vn : np.us) data[m] = await repo.load(m);
    }
  } catch (_) {
    return 0;
  }
  if (data.isEmpty) return 0;
  var stories = const <Story>[];
  if (np.news && np.vn) {
    try {
      final known = {for (final q in data[Market.vn]?.quotes ?? const <Quote>[]) q.symbol};
      stories = clusterStories((await fetchNews(client: client, known: known, now: at)).items);
    } catch (_) {} // the headlines are optional
  }
  final result = plan(now: at, data: data, stories: stories, watch: (prefs.getStringList('watch_VN') ?? const []).toSet(), prefs: np, state: loadState(prefs));
  final shown = await showAll(notifier, result);
  await saveState(prefs, result.state);
  return shown;
}
