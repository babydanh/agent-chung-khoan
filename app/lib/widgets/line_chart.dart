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

/// One cubic segment of the smoothed line: control points [c1], [c2] and the end point.
typedef CurveSegment = ({Offset c1, Offset c2, Offset end});

/// Catmull-Rom curve through [pts] as cubic segments. The control points are held inside the y-range of their own
/// two points, so the line is smooth but never overshoots a high or a low (a price that was not traded stays off the chart).
List<CurveSegment> smoothSegments(List<Offset> pts) {
  double clampY(double y, Offset a, Offset b) => y.clamp(math.min(a.dy, b.dy), math.max(a.dy, b.dy));
  return [
    for (var i = 0; i < pts.length - 1; i++)
      () {
        final p0 = pts[math.max(i - 1, 0)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[math.min(i + 2, pts.length - 1)];
        final c1 = p1 + (p2 - p0) / 6, c2 = p2 - (p3 - p1) / 6;
        return (c1: Offset(c1.dx, clampY(c1.dy, p1, p2)), c2: Offset(c2.dx, clampY(c2.dy, p1, p2)), end: p2);
      }(),
  ];
}

/// Closing prices as one smooth line; the area under it is faintly filled. [marks] draw a dot per day with signals or
/// headlines. [liveLast] puts a dot on the last point (it comes from the live quote). The line draws in once and again
/// when another range is shown, unless the system asks for no animation.
class LineChart extends StatefulWidget {
  const LineChart(this.bars, {super.key, required this.color, this.height = 140, this.marks = const [], this.onMarkTap, this.liveLast = false});
  final List<DailyBar> bars;
  final Color color;
  final double height;
  final List<DayMarks> marks;
  final void Function(DayMarks day)? onMarkTap;
  final bool liveLast;

  @override
  State<LineChart> createState() => _LineChartState();
}

class _LineChartState extends State<LineChart> with SingleTickerProviderStateMixin {
  late final AnimationController _draw = AnimationController(vsync: this, duration: const Duration(milliseconds: 450));
  bool _started = false;

  void _play() => MediaQuery.disableAnimationsOf(context) ? _draw.value = 1 : _draw.forward(from: 0);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    _play();
  }

  @override
  void didUpdateWidget(LineChart old) {
    super.didUpdateWidget(old);
    // A new first day means another range (or a new session pushed the window); a refreshed last price keeps the line still.
    final other = old.bars.isEmpty || widget.bars.isEmpty || old.bars.first.date != widget.bars.first.date;
    if (other) _play();
  }

  @override
  void dispose() {
    _draw.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return SizedBox(
      height: widget.height,
      width: double.infinity,
      child: LayoutBuilder(builder: (context, box) {
        final size = Size(box.maxWidth, widget.height);
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapUp: widget.onMarkTap == null
              ? null
              : (d) {
                  final day = hitMark(ChartGeometry(widget.bars, size), widget.marks, d.localPosition);
                  if (day != null) widget.onMarkTap!(day);
                },
          child: AnimatedBuilder(
            animation: _draw,
            builder: (context, _) => CustomPaint(
              size: size,
              painter: _LinePainter(widget.bars, widget.color, widget.marks, c, Curves.easeOutCubic.transform(_draw.value), widget.liveLast),
            ),
          ),
        );
      }),
    );
  }
}

class _LinePainter extends CustomPainter {
  _LinePainter(this.bars, this.color, this.marks, this.colors, this.progress, this.liveLast);
  final List<DailyBar> bars;
  final Color color;
  final List<DayMarks> marks;
  final AppColors colors;
  final double progress; // 0..1, how much of the width is drawn
  final bool liveLast;

  @override
  void paint(Canvas canvas, Size size) {
    if (bars.length < 2) return;
    final g = ChartGeometry(bars, size);
    final pts = [for (var i = 0; i < bars.length; i++) g.point(i)];
    final line = Path()..moveTo(pts.first.dx, pts.first.dy);
    for (final s in smoothSegments(pts)) {
      line.cubicTo(s.c1.dx, s.c1.dy, s.c2.dx, s.c2.dy, s.end.dx, s.end.dy);
    }
    final fill = Path.from(line)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    if (progress < 1) {
      canvas.save();
      canvas.clipRect(Rect.fromLTWH(0, 0, size.width * progress, size.height));
    }
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
    if (liveLast) {
      canvas.drawCircle(pts.last, 9, Paint()..color = color.withValues(alpha: 0.2));
      canvas.drawCircle(pts.last, 4.5, Paint()..color = color);
    }
    if (progress < 1) canvas.restore();
  }

  @override
  bool shouldRepaint(_LinePainter old) =>
      old.bars != bars || old.color != color || old.marks != marks || old.colors != colors || old.progress != progress || old.liveLast != liveLast;
}
