/// Market of a symbol; the keys match the `market` column of the database.
enum Market {
  vn('VN'),
  us('US');

  const Market(this.key);
  final String key;
}

double? _d(Object? v) => v == null ? null : (v as num).toDouble();
int _i(Object? v) => v == null ? 0 : (v as num).toInt();

/// Timestamps come from the database; a malformed one is treated as missing rather than failing the whole read.
DateTime? _t(Object? v) => v is String ? DateTime.tryParse(v)?.toLocal() : null;

class Quote {
  const Quote({
    required this.market,
    required this.symbol,
    required this.exchange,
    this.name = '',
    this.price,
    this.ref,
    this.ceil,
    this.floor,
    this.vol = 0,
    this.val = 0,
    this.fBuy,
    this.fSell,
    this.fRoom,
    this.ptVol,
    this.ptVal,
    this.asof,
  });

  final Market market;
  final String symbol, exchange, name;
  final double? price, ref, ceil, floor, fRoom;
  final double vol, val;
  final double? fBuy, fSell, ptVol, ptVal;
  final DateTime? asof;

  double? get fNet => fBuy == null || fSell == null ? null : fBuy! - fSell!;

  /// Change against the reference price in percent; null when either price is missing.
  double? get pct => price == null || ref == null || ref == 0 ? null : (price! - ref!) / ref! * 100;

  Quote withName(String n) => Quote(
        market: market, symbol: symbol, exchange: exchange, name: n, price: price, ref: ref, ceil: ceil, floor: floor,
        vol: vol, val: val, fBuy: fBuy, fSell: fSell, fRoom: fRoom, ptVol: ptVol, ptVal: ptVal, asof: asof);

  factory Quote.fromJson(Map<String, dynamic> j) => Quote(
        market: j['market'] == 'US' ? Market.us : Market.vn,
        symbol: j['symbol'] as String,
        exchange: (j['exchange'] as String?) ?? '',
        price: _d(j['price']),
        ref: _d(j['ref_price']),
        ceil: _d(j['ceil_price']),
        floor: _d(j['floor_price']),
        vol: _d(j['vol']) ?? 0,
        val: _d(j['val']) ?? 0,
        fBuy: _d(j['f_buy']),
        fSell: _d(j['f_sell']),
        fRoom: _d(j['f_room']),
        ptVol: _d(j['pt_vol']),
        ptVal: _d(j['pt_val']),
        asof: _t(j['asof']),
      );
}

/// One signal of a symbol: S1 volume, S2 foreign net flow (dir buy/sell), S3 negotiated deals, S4/S5 price moves.
class SignalItem {
  const SignalItem(this.id, [this.dir]);
  final String id;
  final String? dir;
}

class SignalRow {
  const SignalRow({required this.symbol, required this.level, required this.learning, this.items = const [], this.asof});

  final String symbol;
  final int level; // 0..3
  final bool learning;
  final List<SignalItem> items;
  final DateTime? asof;

  bool has(String id) => items.any((s) => s.id == id);

  factory SignalRow.fromJson(Map<String, dynamic> j) {
    final raw = j['items'];
    return SignalRow(
      symbol: j['symbol'] as String,
      level: _i(j['level']).clamp(0, 3),
      learning: (j['learning'] as bool?) ?? false,
      asof: _t(j['asof']),
      items: raw is List
          ? [for (final s in raw) if (s is Map && s['id'] is String) SignalItem(s['id'] as String, s['dir'] as String?)]
          : const [],
    );
  }
}

class Zone {
  const Zone({required this.symbol, required this.kind, required this.lo, required this.hi, this.asof});
  final String symbol, kind;
  final double lo, hi;
  final DateTime? asof;

  factory Zone.fromJson(Map<String, dynamic> j) => Zone(
        symbol: j['symbol'] as String,
        kind: (j['kind'] as String?) ?? '',
        lo: _d(j['price_lo']) ?? 0,
        hi: _d(j['price_hi']) ?? 0,
        asof: _t(j['asof']),
      );
}

class Digest {
  const Digest({required this.date, required this.kind, required this.body, this.createdAt});
  final String date, kind, body;
  final DateTime? createdAt;

  factory Digest.fromJson(Map<String, dynamic> j) => Digest(
        date: (j['digest_date'] as String?) ?? '',
        kind: (j['kind'] as String?) ?? '',
        body: (j['body'] as String?) ?? '',
        createdAt: _t(j['created_at']),
      );
}

class NewsItem {
  const NewsItem({required this.title, required this.url, required this.source, this.symbol, this.publishedAt});
  final String title, url, source;
  final String? symbol;
  final DateTime? publishedAt;

  factory NewsItem.fromJson(Map<String, dynamic> j) => NewsItem(
        title: (j['title'] as String?) ?? '',
        url: (j['url'] as String?) ?? '',
        source: (j['source'] as String?) ?? '',
        symbol: j['symbol'] as String?,
        publishedAt: _t(j['published_at']),
      );
}

class DailyBar {
  const DailyBar({required this.date, required this.close, this.vol = 0});
  final DateTime date;
  final double close, vol;
}

/// What the bot last reported about itself (heartbeat rows).
class BotStatus {
  const BotStatus({this.lastSnapshot, this.source, this.lateMinutes, this.missedSlots, this.heartbeatSeen});
  final DateTime? lastSnapshot, heartbeatSeen;
  final String? source;
  final int? lateMinutes, missedSlots;
}

/// Everything the screens read for one market.
class MarketData {
  const MarketData({
    this.quotes = const [],
    this.signals = const {},
    this.zones = const [],
    this.digests = const [],
    this.news = const [],
    this.status = const BotStatus(),
    this.asof,
  });

  final List<Quote> quotes;
  final Map<String, SignalRow> signals; // by symbol
  final List<Zone> zones;
  final List<Digest> digests;
  final List<NewsItem> news;
  final BotStatus status;
  final DateTime? asof;

  Quote? quote(String symbol) {
    for (final q in quotes) {
      if (q.symbol == symbol) return q;
    }
    return null;
  }

  List<Zone> zonesOf(String symbol) => [for (final z in zones) if (z.symbol == symbol) z];
}
