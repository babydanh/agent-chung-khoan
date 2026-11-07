import 'package:agent_ck/util/format.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('price uses comma decimals and shows thousands of dong', () {
    expect(price(131200), '131,20');
    expect(price(26.85, vn: false), '26,85');
    expect(price(null), '—');
  });

  test('percent keeps the sign and a true minus', () {
    expect(percent(2.1), '+2,10%');
    expect(percent(-6.99), '−6,99%');
    expect(percent(0.001), '0,00%');
    expect(percent(null), '—');
  });

  test('volume compacts to k, tr and tỷ', () {
    expect(volume(410000), '410k');
    expect(volume(6100000), '6,10tr');
    expect(volume(2100000000), '2,10 tỷ');
    expect(volume(950), '950');
  });

  test('signed volume', () {
    expect(signed(640000), '+640k');
    expect(signed(-1280000), '−1,28tr');
    expect(signed(0), '0');
  });

  test('fixed groups thousands with dots', () {
    expect(fixed(1234567.891, 2), '1.234.567,89');
    expect(fixed(-1234.5, 1), '−1.234,5');
  });

  test('valueBillions', () => expect(valueBillions(800300000000), '800,3 tỷ'));

  test('ago words', () {
    final now = DateTime(2026, 11, 5, 12);
    expect(ago(now.subtract(const Duration(minutes: 5)), now), '5 phút');
    expect(ago(now.subtract(const Duration(hours: 3)), now), '3 giờ');
    expect(ago(null, now), '—');
  });
}
