import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme/theme.dart';
import 'chart_marks.dart';

/// Where each bar sits on the chart; the painter and the tap test share it so a dot is where its tap area is.
class ChartGeometry {
  ChartGeometry(this.bars, this.size)
      : lo = bars.isEmpty ? 0 : bars.map((b) => b.close).reduce(math.min),
        hi = bars.isEmpty ? 0 : bars.map((b) => b.close).reduce(math.max);
  final List<DailyBar> bars;
  final Size size;
  final double lo, hi;

  double get _span => hi - lo == 0 ? 1 : hi - lo;

  Offset point(int i) => Offset(size.width * i / (bars.length - 1), size.height - 8 - (size.height - 16) * (bars[i].close - lo) / _span);
}

/// The day whose dot is nearest to [tap] within [radius], or null.
DayMarks? hitMark(ChartGeometry g, List<DayMarks> days, Offset tap, {double radius = 24}) {
  if (g.bars.length < 2) return null;
  DayMarks? best;
  var bestDistance = radius;
  for (final d in days) {
    final distance = (g.point(d.index) - tap).distance;
    if (distance <= bestDistance) {
      best = d;
      bestDistance = distance;
    }
  }
  return best;
}

/// Closing prices as one line; the area under it is faintly filled. [marks] draw a dot per day with signals or headlines.
class LineChart extends StatelessWidget {
  const LineChart(this.bars, {super.key, required this.color, this.height = 140, this.marks = const [], this.onMarkTap});
  final List<DailyBar> bars;
  final Color color;
  final double height;
  final List<DayMarks> marks;
  final void Function(DayMarks day)? onMarkTap;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return SizedBox(
      height: height,
      width: double.infinity,
      child: LayoutBuilder(builder: (context, box) {
        final size = Size(box.maxWidth, height);
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapUp: onMarkTap == null
              ? null
              : (d) {
                  final day = hitMark(ChartGeometry(bars, size), marks, d.localPosition);
                  if (day != null) onMarkTap!(day);
                },
          child: CustomPaint(size: size, painter: _LinePainter(bars, color, marks, c)),
        );
      }),
    );
  }
}

class _LinePainter extends CustomPainter {
  _LinePainter(this.bars, this.color, this.marks, this.colors);
  final List<DailyBar> bars;
  final Color color;
  final List<DayMarks> marks;
  final AppColors colors;

  @override
  void paint(Canvas canvas, Size size) {
    if (bars.length < 2) return;
    final g = ChartGeometry(bars, size);
    final line = Path()..moveTo(g.point(0).dx, g.point(0).dy);
    for (var i = 1; i < bars.length; i++) {
      line.lineTo(g.point(i).dx, g.point(i).dy);
    }
    final fill = Path.from(line)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(fill, Paint()..color = color.withValues(alpha: 0.12));
    canvas.drawPath(line, Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 2..strokeJoin = StrokeJoin.round);
    for (final d in marks) {
      final p = g.point(d.index);
      if (d.hasSignal) {
        canvas.drawCircle(p, 7, Paint()..color = colors.bg); // a ring of the background keeps the dot readable on the line
        canvas.drawCircle(p, 5, Paint()..color = colors.levels[d.topLevel.clamp(0, 3)]);
      }
      if (d.hasNews) {
        final q = d.hasSignal ? p.translate(0, -14) : p;
        canvas.drawCircle(q, 4, Paint()..color = colors.bg);
        canvas.drawCircle(q, 3.5, Paint()..color = colors.text2..style = PaintingStyle.stroke..strokeWidth = 1.5);
      }
    }
  }

  @override
  bool shouldRepaint(_LinePainter old) => old.bars != bars || old.color != color || old.marks != marks || old.colors != colors;
}
