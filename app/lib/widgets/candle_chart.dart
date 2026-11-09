import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../data/candles.dart';
import '../theme/theme.dart';

/// Where each candle sits; the painter and the tests share it.
class CandleGeometry {
  CandleGeometry(this.candles, this.size)
      : lo = candles.isEmpty ? 0 : candles.map((c) => c.l).reduce(math.min),
        hi = candles.isEmpty ? 0 : candles.map((c) => c.h).reduce(math.max);
  final List<Candle> candles;
  final Size size;
  final double lo, hi;

  static const pad = 8.0;

  double get _span => hi - lo == 0 ? 1 : hi - lo;

  double y(double price) => size.height - pad - (size.height - 2 * pad) * (price - lo) / _span;

  double x(int i) => size.width * (i + 0.5) / candles.length;

  /// The candle's body: open to close, at least one pixel tall so a flat candle still shows.
  Rect body(int i) {
    final c = candles[i];
    final w = (size.width / candles.length * 0.7).clamp(1.0, 14.0);
    final top = math.min(y(c.o), y(c.c)), bottom = math.max(y(c.o), y(c.c));
    return Rect.fromLTRB(x(i) - w / 2, top, x(i) + w / 2, math.max(bottom, top + 1));
  }
}

/// Candlesticks (open, high, low, close). [liveLast] marks the last close with a dot and a faint line across.
class CandleChart extends StatelessWidget {
  const CandleChart(this.candles, {super.key, this.height = 180, this.liveLast = false});
  final List<Candle> candles;
  final double height;
  final bool liveLast;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return SizedBox(
      height: height,
      width: double.infinity,
      child: LayoutBuilder(builder: (context, box) => CustomPaint(size: Size(box.maxWidth, height), painter: _CandlePainter(candles, c, liveLast))),
    );
  }
}

class _CandlePainter extends CustomPainter {
  _CandlePainter(this.candles, this.colors, this.liveLast);
  final List<Candle> candles;
  final AppColors colors;
  final bool liveLast;

  @override
  void paint(Canvas canvas, Size size) {
    if (candles.length < 2) return;
    final g = CandleGeometry(candles, size);
    for (var i = 0; i < candles.length; i++) {
      final k = candles[i];
      final color = k.c >= k.o ? colors.up : colors.down;
      canvas.drawLine(Offset(g.x(i), g.y(k.h)), Offset(g.x(i), g.y(k.l)), Paint()..color = color..strokeWidth = 1);
      canvas.drawRect(g.body(i), Paint()..color = color);
    }
    if (liveLast) {
      final y = g.y(candles.last.c);
      canvas.drawLine(Offset(0, y), Offset(size.width, y), Paint()..color = colors.accent.withValues(alpha: 0.35)..strokeWidth = 1);
      canvas.drawCircle(Offset(g.x(candles.length - 1), y), 9, Paint()..color = colors.accent.withValues(alpha: 0.2));
      canvas.drawCircle(Offset(g.x(candles.length - 1), y), 4.5, Paint()..color = colors.accent);
    }
  }

  @override
  bool shouldRepaint(_CandlePainter old) => old.candles != candles || old.colors != colors || old.liveLast != liveLast;
}
