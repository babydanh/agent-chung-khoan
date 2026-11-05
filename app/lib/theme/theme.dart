import 'package:flutter/material.dart';

import 'tokens.dart';

/// Semantic colours of the design, switched with the theme mode.
@immutable
class AppColors extends ThemeExtension<AppColors> {
  const AppColors({
    required this.bg,
    required this.surface,
    required this.surface2,
    required this.line,
    required this.text,
    required this.text2,
    required this.text3,
    required this.accent,
    required this.onAccent,
    required this.accentSoft,
    required this.levels,
    required this.up,
    required this.down,
    required this.ref,
    required this.ceil,
    required this.floor,
    required this.danger,
  });

  final Color bg, surface, surface2, line, text, text2, text3, accent, onAccent, accentSoft;
  final List<Color> levels; // level 0..3
  final Color up, down, ref, ceil, floor, danger;

  static const dark = AppColors(
    bg: DarkColors.bg,
    surface: DarkColors.surface,
    surface2: DarkColors.surface2,
    line: DarkColors.line,
    text: DarkColors.text,
    text2: DarkColors.text2,
    text3: DarkColors.text3,
    accent: DarkColors.accent,
    onAccent: DarkColors.onAccent,
    accentSoft: DarkColors.accentSoft,
    levels: [DarkColors.l0, DarkColors.l1, DarkColors.l2, DarkColors.l3],
    up: DarkColors.up,
    down: DarkColors.dn,
    ref: DarkColors.rf,
    ceil: DarkColors.ce,
    floor: DarkColors.fl,
    danger: DarkColors.danger,
  );

  static const light = AppColors(
    bg: LightColors.bg,
    surface: LightColors.surface,
    surface2: LightColors.surface2,
    line: LightColors.line,
    text: LightColors.text,
    text2: LightColors.text2,
    text3: LightColors.text3,
    accent: LightColors.accent,
    onAccent: LightColors.onAccent,
    accentSoft: LightColors.accentSoft,
    levels: [LightColors.l0, LightColors.l1, LightColors.l2, LightColors.l3],
    up: LightColors.up,
    down: LightColors.dn,
    ref: LightColors.rf,
    ceil: LightColors.ce,
    floor: LightColors.fl,
    danger: LightColors.danger,
  );

  @override
  AppColors copyWith() => this;

  @override
  AppColors lerp(ThemeExtension<AppColors>? other, double t) => t < 0.5 ? this : (other as AppColors? ?? this);
}

extension AppColorsX on BuildContext {
  AppColors get c => Theme.of(this).extension<AppColors>()!;
}

const _numFeatures = [FontFeature.tabularFigures()];

/// Text styles: numbers use tabular figures so columns line up.
abstract final class AppText {
  static TextStyle base(Color color, {double size = Ts.m, FontWeight weight = FontWeight.w400}) =>
      TextStyle(color: color, fontSize: size, fontWeight: weight, height: 1.3);
  static TextStyle num(Color color, {double size = Ts.m, FontWeight weight = FontWeight.w600}) =>
      TextStyle(color: color, fontSize: size, fontWeight: weight, height: 1.3, fontFeatures: _numFeatures);
}

ThemeData buildTheme(Brightness brightness) {
  final c = brightness == Brightness.dark ? AppColors.dark : AppColors.light;
  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    scaffoldBackgroundColor: c.bg,
    canvasColor: c.bg,
    colorScheme: ColorScheme.fromSeed(seedColor: c.accent, brightness: brightness).copyWith(
      surface: c.surface,
      primary: c.accent,
      onPrimary: c.onAccent,
      error: c.danger,
    ),
    dividerColor: c.line,
    splashFactory: InkRipple.splashFactory,
    textTheme: Typography.material2021().black.apply(bodyColor: c.text, displayColor: c.text),
    extensions: [c],
  );
}
