import 'dart:convert';
import 'dart:io';

import 'package:ai_buy_assistant/api.dart';
import 'package:ai_buy_assistant/flow.dart';
import 'package:ai_buy_assistant/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api implements BuyApi {
  _Api({this.healthOk = true, this.onRecommend});
  bool healthOk;
  final Future<RecommendationResult> Function(List<Map<String, dynamic>> options, String freeText, int round)? onRecommend;
  final payloads = <List<Map<String, dynamic>>>[];
  final texts = <String>[];

  @override
  Future<bool> health() async => healthOk;

  @override
  Future<List<CategoryInfo>> categories() async => [
        CategoryInfo(id: 'laptop', name: '笔记本电脑'),
        CategoryInfo(id: 'phone', name: '手机'),
        CategoryInfo(id: 'tablet', name: '平板电脑'),
        CategoryInfo(id: 'headphones', name: '耳机'),
      ];

  @override
  Future<OptionConfig> options(String categoryId) async {
    final file = File('../backend/app/config/options/$categoryId.json');
    return OptionConfig.fromJson(jsonDecode(file.readAsStringSync()) as Map<String, dynamic>);
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
    payloads.add(optionAnswers);
    texts.add(freeText);
    final handler = onRecommend;
    if (handler == null) throw ApiException('网络连接失败');
    return handler(optionAnswers, freeText, followUpRound);
  }
}

RecommendationResult _sample() {
  final json = jsonDecode(File('../backend/tests/fixtures/result_sample.json').readAsStringSync()) as Map<String, dynamic>;
  return RecommendationResult.fromJson(json);
}

Future<void> _openLaptop(WidgetTester tester) async {
  await tester.tap(find.text('笔记本电脑'));
  await tester.pumpAndSettle();
}

Future<void> _scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 120, scrollable: find.byType(Scrollable).first);
  await tester.pumpAndSettle();
}

Future<void> _skipRest(WidgetTester tester, int remaining) async {
  for (var i = 0; i < remaining; i++) {
    await tester.tap(find.text('先跳过'));
    await tester.pumpAndSettle();
  }
}

Future<void> _answerLaptopRequired(WidgetTester tester, {bool usage = true, String? idea}) async {
  expect(find.text('预算大概多少？'), findsOneWidget);
  expect(find.text('还没想好'), findsNothing);
  expect(find.text('指笔记本本身的官方参考价，不含配件。'), findsOneWidget);
  await tester.tap(find.text('5000–8000 元'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('下一步'));
  await tester.pumpAndSettle();
  if (!usage) return;
  expect(find.text('你的想法都可以告诉我', skipOffstage: false), findsOneWidget);
  await tester.tap(find.text('写文档、做表格、上网课、浏览网页'));
  await tester.pumpAndSettle();
  if (idea != null) {
    await _scrollTo(tester, find.byKey(const Key('free-text')));
    await tester.enterText(find.byKey(const Key('free-text')), idea);
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    return;
  }
  await tester.tap(find.text('下一步'));
  await tester.pumpAndSettle();
}

Future<void> _finishOptionalLaptop(WidgetTester tester) async {
  await _skipRest(tester, 4);
  await tester.tap(find.text('下一步'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('backend down shows retry and recovers', (tester) async {
    final api = _Api(healthOk: false);
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    expect(find.text('无法连接后端'), findsOneWidget);
    expect(find.text('重试'), findsOneWidget);
    api.healthOk = true;
    await tester.tap(find.text('重试'));
    await tester.pumpAndSettle();
    expect(find.text('想买什么？'), findsOneWidget);
    expect(find.text('无法连接后端'), findsNothing);
    expect(find.text('耳机'), findsOneWidget);
  });

  testWidgets('laptop questions match config and submit option ids', (tester) async {
    final api = _Api(onRecommend: (_, __, ___) async => _sample());
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await _openLaptop(tester);
    await _answerLaptopRequired(tester);
    expect(find.text('你会经常带着它出门吗？'), findsOneWidget);
    await _finishOptionalLaptop(tester);
    expect(find.text('开始寻找符合你的产品'), findsOneWidget);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pump();
    expect(find.textContaining('%'), findsNothing);
    await tester.pumpAndSettle();
    expect(api.payloads.single, [
      {'question_id': 'budget', 'option_ids': ['5000_8000']},
      {'question_id': 'usage', 'option_ids': ['office']},
    ]);
    await _scrollTo(tester, find.text('暂未查到价格'));
    expect(find.text('暂未查到价格'), findsOneWidget);
    expect(find.text('¥0'), findsNothing);
    expect(find.textContaining('购买'), findsNothing);
    expect(find.textContaining('去下单'), findsNothing);
  });

  testWidgets('free text alone can be submitted', (tester) async {
    final api = _Api(onRecommend: (_, __, ___) async => _sample());
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await _openLaptop(tester);
    await _answerLaptopRequired(tester, idea: '主要写文档');
    await _finishOptionalLaptop(tester);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    expect(api.texts.single, '主要写文档');
  });

  testWidgets('network failure keeps the written need and offers retry', (tester) async {
    final api = _Api();
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await _openLaptop(tester);
    await _answerLaptopRequired(tester, idea: '主要写文档');
    await _finishOptionalLaptop(tester);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    expect(find.text('网络连接失败'), findsOneWidget);
    expect(find.text('重试'), findsOneWidget);
    expect(find.text('主要写文档'), findsNothing);
    await tester.tap(find.text('修改需求'));
    await tester.pumpAndSettle();
    expect(find.text('主要写文档'), findsOneWidget);
  });

  testWidgets('search does not open a follow-up question page', (tester) async {
    final api = _Api(onRecommend: (_, __, ___) async {
      return RecommendationResult(
        requestId: 'follow',
        status: 'need_more_info',
        checkedAt: '2026-10-11T00:00:00Z',
        alternatives: [],
        comparison: [],
        sources: [],
        followUpQuestions: [FollowUpQuestion(text: '预算大概是多少？')],
      );
    });
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await _openLaptop(tester);
    await _answerLaptopRequired(tester);
    await _finishOptionalLaptop(tester);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    expect(find.text('预算大概是多少？'), findsNothing);
    expect(find.byKey(const Key('follow-text')), findsNothing);
    expect(find.text('没有找到符合条件的产品'), findsOneWidget);
  });

  testWidgets('reasons, missing price, and sources follow the result sample', (tester) async {
    final api = _Api(onRecommend: (_, __, ___) async => _sample());
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await _openLaptop(tester);
    await _answerLaptopRequired(tester, idea: '经常带出门');
    await _finishOptionalLaptop(tester);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    await _scrollTo(tester, find.text('查看详细理由'));
    await tester.tap(find.text('查看详细理由'));
    await tester.pumpAndSettle();
    expect(find.textContaining('经常带出门'), findsWidgets);
    expect(find.textContaining('写文档、做表格、上网课、浏览网页'), findsWidgets);
    expect(find.text('依据'), findsWidgets);
    expect(find.text('影响'), findsWidgets);
    expect(find.text('为什么适合你'), findsOneWidget);
    expect(find.text('需要接受的取舍'), findsNothing);
    expect(find.text('需要权衡什么'), findsNothing);
    expect(find.textContaining('续航官方数据未查到'), findsOneWidget);
    expect(find.textContaining('1.2kg'), findsWidgets);
    await _scrollTo(tester, find.text('重量'));
    expect(find.text('重量'), findsWidgets);
    expect(find.text('资料来源'), findsNothing);
    expect(find.textContaining('https://example.com/laptop-a/specs'), findsNothing);
    expect(find.textContaining('购买'), findsNothing);
    await tester.tap(find.byIcon(Icons.arrow_back));
    await tester.pumpAndSettle();
    await _scrollTo(tester, find.text('暂未查到价格'));
    expect(find.text('暂未查到价格'), findsOneWidget);
    await tester.tap(find.text('三款对比'));
    await tester.pumpAndSettle();
    expect(find.textContaining('不可直接比较'), findsOneWidget);
    expect(find.textContaining('官方价格未查到'), findsOneWidget);
    expect(find.text('重量'), findsOneWidget);
    expect(find.text('暂未查到价格'), findsOneWidget);
  });
}
