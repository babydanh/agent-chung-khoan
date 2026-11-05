import 'package:flutter/material.dart';

import '../models/models.dart';

/// Closing prices as one line; the area under it is faintly filled.
class LineChart extends StatelessWidget {
  const LineChart(this.bars, {super.key, required this.color, this.height = 140});
  final List<DailyBar> bars;
  final Color color;
  final double height;

  @override
  Widget build(BuildContext context) =>
      SizedBox(height: height, width: double.infinity, child: CustomPaint(painter: _LinePainter(bars, color)));
}

class _LinePainter extends CustomPainter {
  _LinePainter(this.bars, this.color);
  final List<DailyBar> bars;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (bars.length < 2) return;
    final lo = bars.map((b) => b.close).reduce((a, b) => a < b ? a : b);
    final hi = bars.map((b) => b.close).reduce((a, b) => a > b ? a : b);
    final span = hi - lo == 0 ? 1 : hi - lo;
    Offset pt(int i) => Offset(size.width * i / (bars.length - 1), size.height - 8 - (size.height - 16) * (bars[i].close - lo) / span);
    final line = Path()..moveTo(pt(0).dx, pt(0).dy);
    for (var i = 1; i < bars.length; i++) {
      line.lineTo(pt(i).dx, pt(i).dy);
    }
    final fill = Path.from(line)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(fill, Paint()..color = color.withValues(alpha: 0.12));
    canvas.drawPath(line, Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 2..strokeJoin = StrokeJoin.round);
  }

  @override
  bool shouldRepaint(_LinePainter old) => old.bars != bars || old.color != color;
}
