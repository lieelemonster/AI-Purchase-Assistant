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
        CategoryInfo(id: 'monitor', name: '显示器'),
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
    expect(find.text('你主要用它来做什么？'), findsOneWidget);
    expect(find.text('写文档、做表格、上网课、浏览网页'), findsOneWidget);
    await tester.tap(find.text('写文档、做表格、上网课、浏览网页'));
    await tester.pumpAndSettle();
    await _scrollTo(tester, find.text('你的想法都可以告诉我'));
    expect(find.text('你的想法都可以告诉我'), findsOneWidget);
    await tester.pumpAndSettle();
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    expect(find.text('你会经常带着它出门吗？'), findsOneWidget);
    await _skipRest(tester, 5);
    expect(find.text('开始寻找符合你的产品'), findsOneWidget);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pump();
    expect(find.textContaining('%'), findsNothing);
    await tester.pumpAndSettle();
    expect(api.payloads.single, [
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
    await _scrollTo(tester, find.byKey(const Key('free-text')));
    await tester.enterText(find.byKey(const Key('free-text')), '主要写文档');
    await _skipRest(tester, 6);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    expect(api.payloads.single, isEmpty);
    expect(api.texts.single, '主要写文档');
  });

  testWidgets('network failure keeps the written need and offers retry', (tester) async {
    final api = _Api();
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await _openLaptop(tester);
    await _scrollTo(tester, find.byKey(const Key('free-text')));
    await tester.enterText(find.byKey(const Key('free-text')), '主要写文档');
    await _skipRest(tester, 6);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    expect(find.text('网络连接失败'), findsOneWidget);
    expect(find.text('重试'), findsOneWidget);
    expect(find.text('主要写文档'), findsNothing);
    await tester.tap(find.text('修改需求'));
    await tester.pumpAndSettle();
    expect(find.text('主要写文档'), findsOneWidget);
  });

  testWidgets('follow-up answer is sent and then shows the result', (tester) async {
    var round = 0;
    final api = _Api(onRecommend: (_, text, followUpRound) async {
      round = followUpRound;
      if (followUpRound == 0) {
        return RecommendationResult(
          requestId: 'follow',
          status: 'need_more_info',
          checkedAt: '2026-10-11T00:00:00Z',
          alternatives: [],
          comparison: [],
          sources: [],
          followUpQuestions: [FollowUpQuestion(text: '预算大概是多少？')],
        );
      }
      return _sample();
    });
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await _openLaptop(tester);
    await _skipRest(tester, 6);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    expect(find.text('预算大概是多少？'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('follow-text')), '五千左右');
    await tester.tap(find.text('继续'));
    await tester.pumpAndSettle();
    expect(round, 1);
    expect(api.texts.last, contains('五千左右'));
    expect(find.text('根据你的需求，优先考虑这款'), findsOneWidget);
  });

  testWidgets('reasons, missing price, and sources follow the result sample', (tester) async {
    final api = _Api(onRecommend: (_, __, ___) async => _sample());
    await tester.pumpWidget(BuyFlow(api: api));
    await tester.pumpAndSettle();
    await _openLaptop(tester);
    await tester.tap(find.text('写文档、做表格、上网课、浏览网页'));
    await tester.pumpAndSettle();
    await _scrollTo(tester, find.byKey(const Key('free-text')));
    await tester.enterText(find.byKey(const Key('free-text')), '经常带出门');
    await tester.tap(find.text('下一步'));
    await tester.pumpAndSettle();
    await _skipRest(tester, 5);
    await tester.tap(find.text('开始寻找符合你的产品'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('查看详细理由').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('经常带出门'), findsWidgets);
    expect(find.textContaining('写文档、做表格、上网课、浏览网页'), findsWidgets);
    expect(find.text('官方资料事实'), findsOneWidget);
    expect(find.text('适合性判断'), findsOneWidget);
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
