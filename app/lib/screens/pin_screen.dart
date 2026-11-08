import 'package:flutter/material.dart';

import '../state/scope.dart';
import '../theme/theme.dart';
import '../theme/tokens.dart';

/// Asked on first start (and again if the server refuses the PIN). The PIN is the password of the app's login.
class PinScreen extends StatefulWidget {
  const PinScreen({super.key});

  @override
  State<PinScreen> createState() => _PinScreenState();
}

class _PinScreenState extends State<PinScreen> {
  final _pin = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _pin.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || _pin.text.trim().isEmpty) return; // a double tap must not send two sign-ins
    setState(() => _busy = true);
    await AppScope.read(context).submitPin(_pin.text);
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final c = context.c;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Sp.s4),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 360),
              child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Text('Nhập mã PIN', style: AppText.base(c.text, size: Ts.l, weight: FontWeight.w700)),
                const SizedBox(height: Sp.s3),
                TextField(
                  controller: _pin,
                  obscureText: true,
                  autofocus: true,
                  autocorrect: false,
                  enableSuggestions: false,
                  onSubmitted: (_) => _submit(),
                  style: AppText.base(c.text),
                  decoration: InputDecoration(labelText: 'PIN', labelStyle: AppText.base(c.text2), filled: true, fillColor: c.surface, border: OutlineInputBorder(borderRadius: BorderRadius.circular(Rd.m), borderSide: BorderSide.none)),
                ),
                if (s.authError && s.error != null) Padding(padding: const EdgeInsets.only(top: Sp.s3), child: Text('PIN không đúng', style: AppText.base(c.danger, size: Ts.s))),
                const SizedBox(height: Sp.s4),
                FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: c.accent, foregroundColor: c.onAccent, minimumSize: const Size.fromHeight(48)),
                  onPressed: _busy ? null : _submit,
                  child: Text(_busy ? '…' : 'Mở'),
                ),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}
