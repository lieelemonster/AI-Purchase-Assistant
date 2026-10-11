import 'package:ai_buy_assistant/api.dart';
import 'package:ai_buy_assistant/flow.dart';
import 'package:ai_buy_assistant/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _ScriptedApi implements BuyApi {
  _ScriptedApi(this.results);
  final Map<String, RecommendationResult> results;
  final calls = <String>[];

  @override
  Future<bool> health() async => true;

  @override
  Future<List<CategoryInfo>> categories() async => [CategoryInfo(id: 'laptop', name: '笔记本电脑')];

  @override
  Future<OptionConfig> options(String categoryId) async {
    return OptionConfig(categoryId: categoryId, version: 'v1', questions: [
      SurveyQuestion(id: 'usage', label: '你主要用它来做什么？', multiple: true, options: [OptionChoice(id: 'office', label: '写文档')]),
    ]);
  }

  @override
  Future<RecommendationResult> recommend({
    required String requestId,
    required String inputVersion,
    required String categoryId,
    required List<Map<String, dynamic>> optionAnswers,
    required String freeText,
    required int followUpRound,
  }) async {
    calls.add(freeText);
    final delay = freeText == '需求A' ? const Duration(milliseconds: 400) : const Duration(milliseconds: 50);
    await Future<void>.delayed(delay);
    return results[freeText]!;
  }
}

RecommendationResult _result(String name) {
  return RecommendationResult(
    requestId: name,
    status: 'success',
    checkedAt: '2026-10-11T12:00:00Z',
    primary: ProductCard(
      candidateId: 'c1',
      name: name,
      facts: [],
      price: PriceFact(status: FactStatus.supported, amountMinor: 100, minorUnitDigits: 2, currency: 'CNY'),
      reasons: [],
    ),
    alternatives: [
      ProductCard(candidateId: 'c2', name: '$name-b', facts: [], price: PriceFact(status: FactStatus.unknown), reasons: []),
      ProductCard(candidateId: 'c3', name: '$name-c', facts: [], price: PriceFact(status: FactStatus.unknown), reasons: []),
    ],
    comparison: [],
    sources: [],
  );
}

void main() {
  testWidgets('later request is not overwritten by an older response', (tester) async {
    final api = _ScriptedApi({'需求A': _result('结果A'), '需求B': _result('结果B')});
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await tester.tap(find.text('笔记本电脑'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('free-text')), '需求A');
    await tester.tap(find.text('先跳过'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pump();
    await tester.tap(find.text('返回修改需求'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('修改').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('free-text')), '需求B');
    await tester.tap(find.text('先跳过'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 80));
    expect(find.text('结果B'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('结果B'), findsOneWidget);
    expect(find.text('结果A'), findsNothing);
  });
}
