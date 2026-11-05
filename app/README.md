# Agent Chứng Khoán (app)

Flutter app for one person: reads the bot's tables from Supabase and shows the board, symbol detail, watchlist,
news and bulletins, zones and an inbox. It never writes and never places orders.

- Design: `design/` — the approved prototype imported into FigCraft (`chungkhoan.figcraft`, 37 screens), design
  tokens exported as Dart (`tokens.dart`, copied to `lib/theme/tokens.dart`), per-screen and per-component Flutter
  code from FigCraft (`generated/`, `components/`: reference only, absolute-positioned) and the extractor
  (`tools/`, HTML prototype -> FigCraft script).
- Data: `lib/data/`. With no connection saved the app runs on built-in sample data. Set the Supabase URL, the
  public (anon) key and the owner's login in Cài đặt > Nguồn. They stay on the device; never use the secret key.
- Run: `flutter run` (Android). Tests: `flutter test`. Analyze: `flutter analyze`.

News and notifications (all inside the app, no Telegram, no server of its own):
- `lib/news/`: the app reads the public RSS feeds (CafeF, Vietstock, VnExpress) from the phone, groups the same story
  across sources, classifies the event by keywords and scores how hot it is (freshness 30, sources 20, event 20,
  watched symbol 15, match with a money-flow signal 15). No model is used.
- `lib/notify/planner.dart`: decides what to show now (level-3 symbols, hot headlines, new bulletins), with quiet hours
  22:00-07:00, an hourly limit and no repeats. Every text is built from templates and scanned with `lib/util/banned.dart`
  (the Dart port of `pipeline/banned.py`); a test also scans every string literal of the app.
- `lib/notify/background.dart`: on Android a periodic task (15 minutes, the system minimum) runs the same planner and shows
  system notifications. The system may delay it on battery saver. Not available on iOS (not configured).
- Settings > Thông báo: switches per market, bulletin and hot headlines, minimum level, hot threshold, hourly limit,
  the permission request and a test notice.

What the app cannot show yet, because the bot does not write it: zones (`zones` is empty until the engine is wired),
daily charts (`bars_1d` has no source) and the bot's heartbeat (not readable by the app by design).
