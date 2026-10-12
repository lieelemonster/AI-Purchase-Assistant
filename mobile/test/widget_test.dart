import 'package:ai_buy_assistant/api.dart';
import 'package:ai_buy_assistant/flow.dart';
import 'package:ai_buy_assistant/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Fake implements BuyApi {
  @override
  Future<bool> health() async => true;
  @override
  Future<List<CategoryInfo>> categories() async => [
        CategoryInfo(id: 'laptop', name: '笔记本电脑'),
        CategoryInfo(id: 'phone', name: '手机'),
        CategoryInfo(id: 'tablet', name: '平板电脑'),
        CategoryInfo(id: 'monitor', name: '显示器'),
        CategoryInfo(id: 'headphones', name: '耳机'),
      ];
  @override
  Future<OptionConfig> options(String categoryId) async => OptionConfig(categoryId: categoryId, version: 'v1', questions: [
        SurveyQuestion(id: 'usage', label: '你主要用它来做什么？', multiple: true, options: [OptionChoice(id: 'office', label: '写文档')]),
      ]);
  @override
  Future<RecommendationResult> recommend({
    required String requestId,
    required String inputVersion,
    required String categoryId,
    required List<Map<String, dynamic>> optionAnswers,
    required String freeText,
    required int followUpRound,
  }) async {
    return RecommendationResult(requestId: requestId, status: 'timeout', checkedAt: '2026-10-11T00:00:00Z', alternatives: [], comparison: [], sources: []);
  }
}

void main() {
  testWidgets('home lists five categories and shows connected', (tester) async {
    await tester.pumpWidget(BuyFlow(api: _Fake()));
    await tester.pumpAndSettle();
    expect(find.text('想买什么？'), findsOneWidget);
    expect(find.text('笔记本电脑'), findsOneWidget);
    expect(find.text('耳机'), findsOneWidget);
  });

  testWidgets('timeout keeps the written need and offers retry', (tester) async {
    await tester.pumpWidget(BuyFlow(api: _Fake()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('笔记本电脑'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('先跳过'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    expect(find.text('查询时间比预期长'), findsOneWidget);
    expect(find.text('重试'), findsOneWidget);
  });
}
