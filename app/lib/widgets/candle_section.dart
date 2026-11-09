import 'dart:async';

import 'package:flutter/material.dart';

import '../data/candles.dart';
import '../models/models.dart';
import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../util/format.dart' as f;
import 'candle_chart.dart';
import 'common.dart';
import 'line_chart.dart';

const _refreshEvery = Duration(seconds: 20);

/// The chart of one VN symbol for a minute, hour, week or month frame. The candles come straight from VCI and are
/// asked for again every 20 seconds while the session is open, so the last candle moves with the market. Create it
/// with a key per frame: it loads once in `initState`.
class CandleSection extends StatefulWidget {
  const CandleSection({super.key, required this.market, required this.symbol, required this.frame, this.clock = DateTime.now});
  final Market market;
  final String symbol;
  final Frame frame;

  /// Where "now" comes from (the session check); a test passes its own.
  final DateTime Function() clock;

  @override
  State<CandleSection> createState() => _CandleSectionState();
}

class _CandleSectionState extends State<CandleSection> {
  List<Candle>? _candles;
  String? _error;
  bool _asCandles = false; // false = the smooth line, true = candlesticks
  bool _loading = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(_refreshEvery, (_) {
      if (vnSessionOpen(widget.clock())) _load(quiet: true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  /// A refresh that fails keeps what is on screen; only a first load shows the error. One request at a time.
  Future<void> _load({bool quiet = false}) async {
    if (_loading) return;
    _loading = true;
    final state = AppScope.read(context);
    try {
      final list = await state.candles(widget.market, widget.symbol, widget.frame);
      if (mounted) {
        setState(() {
          _candles = list;
          _error = null;
        });
      }
    } on CandleError catch (e) {
      if (mounted && (!quiet || _candles == null)) setState(() => _error = e.message);
    } finally {
      _loading = false;
    }
  }

  String _stamp(Candle k) {
    final t = k.vnTime;
    String two(int n) => n.toString().padLeft(2, '0');
    final date = '${two(t.day)}/${two(t.month)}';
    return widget.frame == Frame.w1 || widget.frame == Frame.mo1 ? '$date/${t.year}' : '$date ${two(t.hour)}:${two(t.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final list = _candles;
    final open = vnSessionOpen(widget.clock());
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Sp.s4),
        child: Segmented<bool>(value: _asCandles, options: const [(false, 'Đường'), (true, 'Nến')], onChanged: (v) => setState(() => _asCandles = v)),
      ),
      Padding(
        padding: const EdgeInsets.all(Sp.s4),
        child: _chart(c, list, open),
      ),
      if (list != null && list.length >= 2) ..._details(c, list, open),
    ]);
  }

  Widget _chart(AppColors c, List<Candle>? list, bool open) {
    Widget note(String text, {VoidCallback? onTap}) => GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: SizedBox(height: 100, child: Center(child: Text(text, textAlign: TextAlign.center, style: AppText.base(c.text3, size: Ts.s)))),
        );
    if (list == null && _error != null) {
      return note('Không tải được dữ liệu khung này. Bấm để thử lại.', onTap: () {
        setState(() => _error = null);
        _load();
      });
    }
    if (list == null) return note('…');
    if (list.length < 2) return note('Chưa có dữ liệu khung này');
    if (_asCandles) return CandleChart(list, liveLast: open);
    return LineChart(
      [for (final k in list) DailyBar(date: k.vnTime, close: k.c, vol: k.v)],
      color: c.accent,
      liveLast: open,
      replayOnRange: false,
    );
  }

  List<Widget> _details(AppColors c, List<Candle> list, bool open) {
    final last = list.last;
    final small = AppText.base(c.text3, size: Ts.xs);
    String p(double v) => f.price(v, vn: true);
    return [
      Padding(
        padding: const EdgeInsets.fromLTRB(Sp.s4, 0, Sp.s4, Sp.s1),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(_stamp(list.first), style: small), Text(_stamp(last), style: small)]),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(Sp.s4, 0, Sp.s4, Sp.s1),
        child: Text('${_stamp(last)}  Mở ${p(last.o)}  Cao ${p(last.h)}  Thấp ${p(last.l)}  Đóng ${p(last.c)}  KL ${f.volume(last.v)}', style: AppText.base(c.text2, size: Ts.xs)),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(Sp.s4, 0, Sp.s4, Sp.s2),
        child: Text(open ? 'Làm mới mỗi 20 giây trong phiên (09:00–15:05).' : 'Ngoài phiên giao dịch: hiện nến gần nhất đã có.', style: small),
      ),
    ];
  }
}
