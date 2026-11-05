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

What the app cannot show yet, because the bot does not write it: zones (`zones` is empty until the engine is wired),
daily charts (`bars_1d` has no source) and the bot's heartbeat (not readable by the app by design).
