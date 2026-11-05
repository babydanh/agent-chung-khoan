import 'package:flutter/material.dart';
import 'package:path_drawing/path_drawing.dart';

import 'icon_paths.dart';

/// A line icon of the design set, drawn from its SVG path (24x24 grid, stroke 1.75).
class AppIcon extends StatelessWidget {
  const AppIcon(this.name, {super.key, this.size = 20, this.color});

  final String name;
  final double size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final d = iconPaths[name];
    assert(d != null, 'unknown icon $name');
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _IconPainter(d ?? '', color ?? DefaultTextStyle.of(context).style.color ?? Colors.white),
      ),
    );
  }
}

class _IconPainter extends CustomPainter {
  _IconPainter(this.data, this.color);

  final String data;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final path = parseSvgPathData(data);
    final s = size.width / 24;
    canvas.scale(s);
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.75
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(_IconPainter old) => old.data != data || old.color != color;
}
