import '../models/models.dart';

/// Where the screens get their data from: the live database or the built-in demo set.
abstract class Repository {
  Future<MarketData> load(Market market);
  Future<List<DailyBar>> bars(Market market, String symbol, {int days = 60});

  /// Recent signal rows of one symbol, newest first (one row per bot run that stored the symbol).
  Future<List<SignalRow>> signalHistory(Market market, String symbol, {int limit = 60});
}

class RepositoryException implements Exception {
  RepositoryException(this.message, {this.auth = false});
  final String message;

  /// True when the failure is about credentials (wrong login, expired session), not the network.
  final bool auth;

  @override
  String toString() => message;
}
