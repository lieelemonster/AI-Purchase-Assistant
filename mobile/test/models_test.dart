import 'dart:convert';
import 'dart:io';

import 'package:ai_buy_assistant/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('sample json keeps unknown price null and rejects unknown status', () {
    final file = File('../backend/tests/fixtures/result_sample.json');
    final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final result = RecommendationResult.fromJson(json);
    expect(result.alternatives[1].price.amountMinor, isNull);
    expect(result.alternatives[1].price.status, FactStatus.unknown);
    expect(result.alternatives[1].price.label, '暂未查到价格');
    expect(() => parseStatus('not-a-status'), throwsFormatException);
    final pconline = PriceFact(
      status: FactStatus.supported,
      amountMinor: 529900,
      minorUnitDigits: 2,
      currency: 'CNY',
      priceBasis: 'pconline_reference',
    );
    expect(pconline.label, '¥5,299');
    expect(pconline.basisLabel, '参考价（行货价格）');
    expect(PriceFact(status: FactStatus.unknown).basisLabel, '');
  });
}
