/// Shows a notice as a system notification. The interface keeps the planner and the cycle testable; only
/// [SystemNotifier] touches the platform.
library;

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'planner.dart';

abstract class Notifier {
  Future<void> show(Notice n);

  /// Asks the user for the notification permission (Android 13+). True when granted.
  Future<bool> requestPermission();
}

class SystemNotifier implements Notifier {
  final _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  Future<void> _init() async {
    if (_ready) return;
    await _plugin.initialize(settings: const InitializationSettings(android: AndroidInitializationSettings('@mipmap/ic_launcher')));
    _ready = true;
  }

  @override
  Future<void> show(Notice n) async {
    await _init();
    await _plugin.show(
      id: n.id,
      title: n.title,
      body: n.body.isEmpty ? null : n.body,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails('hot', 'Tin nóng và mức tín hiệu', channelDescription: 'Mã lên mức cao, tin nóng, bản tin', importance: Importance.high, priority: Priority.high),
      ),
      payload: n.url,
    );
  }

  @override
  Future<bool> requestPermission() async {
    await _init();
    return await _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()?.requestNotificationsPermission() ?? false;
  }
}
