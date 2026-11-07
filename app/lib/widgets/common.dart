import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';
import '../ui/app_icon.dart';
import '../util/format.dart' as f;

/// Colour of a price against the reference, ceiling and floor of the day (Vietnamese convention).
Color priceColor(AppColors c, Quote q) {
  final p = q.price, r = q.ref;
  if (p == null || r == null) return c.text2;
  if (q.ceil != null && p >= q.ceil!) return c.ceil;
  if (q.floor != null && p <= q.floor!) return c.floor;
  if (p > r) return c.up;
  if (p < r) return c.down;
  return c.ref;
}

class LevelChip extends StatelessWidget {
  const LevelChip(this.level, {super.key});
  final int level;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final color = c.levels[level.clamp(0, 3)];
    return Semantics(
      label: 'Mức $level',
      child: Container(
        height: 24,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        decoration: BoxDecoration(color: c.surface2, borderRadius: BorderRadius.circular(Rd.pill)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          for (var i = 0; i < 3; i++)
            Container(
              width: 8,
              height: 8,
              margin: EdgeInsets.only(left: i == 0 ? 0 : 4),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: i < level ? color : Colors.transparent,
                border: i < level ? null : Border.all(color: c.text3, width: 1.5),
              ),
            ),
        ]),
      ),
    );
  }
}

class Pill extends StatelessWidget {
  const Pill(this.label, {super.key, this.selected = false, this.onTap, this.icon});
  final String label;
  final bool selected;
  final VoidCallback? onTap;
  final String? icon;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return Semantics(
      button: onTap != null,
      selected: selected,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: Sp.touch),
          child: Center(
            widthFactor: 1,
            child: Container(
              height: 36,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                color: selected ? c.accent : c.surface2,
                borderRadius: BorderRadius.circular(Rd.pill),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                if (icon != null) ...[AppIcon(icon!, size: 16, color: selected ? c.onAccent : c.text2), const SizedBox(width: 6)],
                Text(label, style: AppText.base(selected ? c.onAccent : c.text2, size: Ts.s, weight: FontWeight.w600)),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

/// Two-way switch such as VN | US.
class Segmented<T> extends StatelessWidget {
  const Segmented({super.key, required this.value, required this.options, required this.onChanged});
  final T value;
  final List<(T, String)> options;
  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(Rd.m), border: Border.all(color: c.line)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        for (final (v, label) in options)
          Semantics(
            button: true,
            selected: v == value,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onChanged(v),
              child: Container(
                constraints: const BoxConstraints(minWidth: 56, minHeight: 36),
                alignment: Alignment.center,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                decoration: BoxDecoration(color: v == value ? c.surface2 : Colors.transparent, borderRadius: BorderRadius.circular(Rd.s)),
                child: Text(label, style: AppText.base(v == value ? c.text : c.text2, size: Ts.s, weight: FontWeight.w600)),
              ),
            ),
          ),
      ]),
    );
  }
}

class IconBtn extends StatelessWidget {
  const IconBtn(this.icon, {super.key, this.onTap, this.dot = false, this.label});
  final String icon;
  final VoidCallback? onTap;
  final bool dot;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return Semantics(
      button: true,
      label: label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: SizedBox(
          width: Sp.touch,
          height: Sp.touch,
          child: Stack(alignment: Alignment.center, children: [
            AppIcon(icon, size: 22, color: c.text),
            if (dot)
              Positioned(
                right: 10,
                top: 10,
                child: Container(width: 8, height: 8, decoration: BoxDecoration(color: c.levels[3], shape: BoxShape.circle)),
              ),
          ]),
        ),
      ),
    );
  }
}

/// Small text badge with an optional icon ("đang học").
class Tag extends StatelessWidget {
  const Tag(this.label, {super.key, this.icon, this.color});
  final String label;
  final String? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final col = color ?? c.text2;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(color: c.surface2, borderRadius: BorderRadius.circular(Rd.s)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (icon != null) ...[AppIcon(icon!, size: 12, color: col), const SizedBox(width: 4)],
        Flexible(child: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: AppText.base(col, size: 11, weight: FontWeight.w600))),
      ]),
    );
  }
}

/// Number tile: label on top, value below (detail screen).
class Tile extends StatelessWidget {
  const Tile(this.label, this.value, {super.key, this.color});
  final String label, value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return Container(
      padding: const EdgeInsets.all(Sp.s3),
      decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(Rd.m)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: AppText.base(c.text2, size: Ts.xs)),
        const SizedBox(height: 4),
        Text(value, style: AppText.num(color ?? c.text, size: Ts.l, weight: FontWeight.w700)),
      ]),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing});
  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Sp.s4, Sp.s5, Sp.s4, Sp.s2),
      child: Row(children: [
        Expanded(child: Text(text, style: AppText.base(c.text2, size: Ts.s, weight: FontWeight.w600))),
        ?trailing,
      ]),
    );
  }
}

/// One-line status strip under the top bar: offline, stale data, closed market, retry on error.
class StatusBanner extends StatelessWidget {
  const StatusBanner({super.key, required this.icon, required this.text, this.trailing, this.color, this.onTap});
  final String icon, text;
  final String? trailing;
  final Color? color;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    final col = color ?? c.text2;
    return Semantics(
      button: onTap != null,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.fromLTRB(Sp.s4, Sp.s2, Sp.s4, 0),
          padding: const EdgeInsets.symmetric(horizontal: Sp.s3, vertical: Sp.s3),
          decoration: BoxDecoration(color: c.surface, borderRadius: BorderRadius.circular(Rd.m), border: Border.all(color: c.line)),
          child: Row(children: [
            AppIcon(icon, size: 20, color: col),
            const SizedBox(width: Sp.s3),
            Expanded(child: Text(text, style: AppText.base(c.text, size: Ts.s, weight: FontWeight.w600))),
            if (trailing case final t?) Text(t, style: AppText.num(c.text2, size: Ts.s, weight: FontWeight.w500)),
          ]),
        ),
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState(this.icon, this.text, {super.key, this.action, this.onAction});
  final String icon, text;
  final String? action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(Sp.s5),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          AppIcon(icon, size: 40, color: c.text3),
          const SizedBox(height: Sp.s3),
          Text(text, textAlign: TextAlign.center, style: AppText.base(c.text2, size: Ts.s)),
          if (action != null) ...[const SizedBox(height: Sp.s4), Pill(action!, selected: true, onTap: onAction)],
        ]),
      ),
    );
  }
}

class SkeletonRows extends StatelessWidget {
  const SkeletonRows({super.key, this.count = 8});
  final int count;

  @override
  Widget build(BuildContext context) {
    final c = context.c;
    Widget bar(double w) => Container(width: w, height: 14, decoration: BoxDecoration(color: c.surface2, borderRadius: BorderRadius.circular(4)));
    return Column(children: [
      for (var i = 0; i < count; i++)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Sp.s4, vertical: 14),
          child: Row(children: [bar(70), const Spacer(), bar(56), const SizedBox(width: Sp.s4), bar(48), const SizedBox(width: Sp.s4), bar(40)]),
        ),
    ]);
  }
}

String levelWord(int l) => 'Mức $l';

String shortAgo(DateTime? t, DateTime now) => f.ago(t, now);
