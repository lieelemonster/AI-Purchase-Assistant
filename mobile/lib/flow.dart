import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'models.dart';

const _bg = Color(0xFFF5F7FA);
const _ink = Color(0xFF1F2937);
const _ink2 = Color(0xFF4B5563);
const _ink3 = Color(0xFF8A94A3);
const _line = Color(0xFFE5E8EE);
const _primary = Color(0xFF2563EB);
const _primaryInk = Color(0xFF1D4ED8);
const _primarySoft = Color(0xFFEAF1FE);
const _ok = Color(0xFF15803D);
const _okSoft = Color(0xFFE8F6EE);
const _warn = Color(0xFFB45309);
const _warnSoft = Color(0xFFFDF3E2);
const _errSoft = Color(0xFFFDEEE6);
const _mint = Color(0xFFE6F5F2);
const _lilac = Color(0xFFF0EDFB);

const _compareFields = <String, List<(String, String)>>{
  'laptop': [('weight', '重量'), ('screen_size', '屏幕'), ('battery_life', '续航'), ('memory', '内存'), ('usb', '接口'), ('gpu', '显卡')],
  'phone': [('rear_camera', '拍照'), ('battery', '续航'), ('screen_size', '屏幕尺寸'), ('weight', '重量'), ('storage', '存储')],
  'tablet': [('screen_size', '屏幕'), ('features', '手写笔支持'), ('storage', '存储'), ('weight', '重量')],
  'monitor': [('size', '尺寸'), ('resolution', '清晰度'), ('refresh_rate', '刷新率'), ('ports', '接口'), ('wall_mount', '支架')],
  'headphones': [('form', '佩戴方式'), ('anc', '降噪'), ('battery_life', '续航'), ('mic', '通话')],
};

class BuyFlow extends StatefulWidget {
  const BuyFlow({super.key, required this.api});
  final BuyApi api;

  @override
  State<BuyFlow> createState() => _BuyFlowState();
}

enum _Page { home, ask, confirm, search, follow, result, detail, compare }

class _BuyFlowState extends State<BuyFlow> {
  _Page page = _Page.home;
  bool connected = false;
  String? homeError;
  List<CategoryInfo> categories = [];
  CategoryInfo? category;
  OptionConfig? config;
  int step = 0;
  final answers = <String, List<String>>{};
  final freeText = TextEditingController();
  final followReply = TextEditingController();
  int followUpRound = 0;
  String followExtra = '';
  RecommendationResult? result;
  ProductCard? detail;
  String? searchError;
  bool searchTimeout = false;
  int requestGen = 0;
  int searchStage = 0;
  Timer? stageTimer;

  @override
  void initState() {
    super.initState();
    loadHome();
  }

  @override
  void dispose() {
    stageTimer?.cancel();
    freeText.dispose();
    followReply.dispose();
    super.dispose();
  }

  Future<void> loadHome() async {
    setState(() => homeError = null);
    try {
      final ok = await widget.api.health();
      final list = ok ? await widget.api.categories() : <CategoryInfo>[];
      if (!mounted) return;
      setState(() {
        connected = ok;
        categories = list;
        homeError = ok ? null : '无法连接后端';
      });
    } on ApiException {
      if (!mounted) return;
      setState(() {
        connected = false;
        homeError = '无法连接后端';
      });
    }
  }

  Future<void> openCategory(CategoryInfo item) async {
    try {
      final options = await widget.api.options(item.id);
      if (!mounted) return;
      setState(() {
        category = item;
        config = options;
        step = 0;
        answers.clear();
        freeText.clear();
        followUpRound = 0;
        followExtra = '';
        result = null;
        page = _Page.ask;
      });
    } on ApiException {
      setState(() => homeError = '无法读取问题');
    }
  }

  void toggle(SurveyQuestion question, OptionChoice choice) {
    final current = List<String>.from(answers[question.id] ?? []);
    if (choice.unsure) {
      answers[question.id] = current.contains(choice.id) ? [] : [choice.id];
    } else if (question.multiple) {
      current.removeWhere((id) => question.options.any((option) => option.id == id && option.unsure));
      if (current.contains(choice.id)) {
        current.remove(choice.id);
      } else {
        current.add(choice.id);
      }
      answers[question.id] = current;
    } else {
      answers[question.id] = [choice.id];
    }
    setState(() {});
  }

  void nextStep() {
    final last = step >= (config!.questions.length - 1);
    if (last) {
      setState(() => page = _Page.confirm);
    } else {
      setState(() => step += 1);
    }
  }

  List<Map<String, dynamic>> get optionPayload {
    return answers.entries
        .where((entry) => entry.value.isNotEmpty)
        .map((entry) => {'question_id': entry.key, 'option_ids': entry.value})
        .toList();
  }

  String get composedText {
    final parts = [freeText.text.trim(), followExtra.trim()].where((item) => item.isNotEmpty);
    return parts.join('\n');
  }

  Future<void> startSearch() async {
    final generation = ++requestGen;
    setState(() {
      page = _Page.search;
      searchError = null;
      searchTimeout = false;
      searchStage = 0;
    });
    stageTimer?.cancel();
    stageTimer = Timer.periodic(const Duration(milliseconds: 1100), (timer) {
      if (!mounted || page != _Page.search || searchStage >= 3) return;
      setState(() => searchStage += 1);
    });
    try {
      final response = await widget.api.recommend(
        requestId: 'app-$generation',
        inputVersion: config?.version ?? 'v1',
        categoryId: category!.id,
        optionAnswers: optionPayload,
        freeText: composedText,
        followUpRound: followUpRound,
      );
      if (!mounted || generation != requestGen) return;
      stageTimer?.cancel();
      setState(() {
        result = response;
        if (response.status == 'need_more_info') {
          page = _Page.follow;
        } else if (response.status == 'timeout') {
          searchTimeout = true;
          searchError = '资料来源响应较慢，你填写的需求都已保留。';
        } else {
          page = _Page.result;
        }
      });
    } on ApiException catch (error) {
      if (!mounted || generation != requestGen) return;
      stageTimer?.cancel();
      setState(() {
        searchTimeout = error.timeout;
        searchError = error.timeout ? '资料来源响应较慢，你填写的需求都已保留。' : '请检查网络后重试，你填写的需求都已保留。';
      });
    }
  }

  void resetHome() {
    stageTimer?.cancel();
    requestGen++;
    setState(() {
      page = _Page.home;
      result = null;
      detail = null;
    });
    loadHome();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(useMaterial3: true, scaffoldBackgroundColor: _bg, fontFamily: 'PingFang SC'),
      home: switch (page) {
        _Page.home => _home(),
        _Page.ask => _ask(),
        _Page.confirm => _confirm(),
        _Page.search => _search(),
        _Page.follow => _follow(),
        _Page.result => _result(),
        _Page.detail => _detail(),
        _Page.compare => _compare(),
      },
    );
  }

  Widget _home() {
    const hints = {
      'laptop': ('办公、学习、创作', _primarySoft),
      'phone': ('拍照、续航、日常', _mint),
      'tablet': ('看剧、记笔记、绘画', _lilac),
      'monitor': ('办公、游戏、设计', _warnSoft),
      'headphones': ('通勤、运动、降噪', _errSoft),
    };
    return Scaffold(
      body: ListView(
        padding: const EdgeInsets.fromLTRB(24, 56, 24, 32),
        children: [
          const Text('想买什么？\n我们一起理清楚。', style: TextStyle(fontSize: 28, height: 40 / 28, fontWeight: FontWeight.w700, color: _ink)),
          const SizedBox(height: 12),
          const Text('还没想清楚需求也没关系。', style: TextStyle(fontSize: 16, color: _ink2)),
          const SizedBox(height: 8),
          Text(connected ? '已连接' : (homeError ?? '无法连接后端'), style: TextStyle(fontSize: 12, color: connected ? _ok : _warn)),
          if (!connected)
            TextButton(onPressed: loadHome, child: const Text('重试')),
          const SizedBox(height: 32),
          for (final item in categories)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Material(
                color: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: const BorderSide(color: _line)),
                child: InkWell(
                  onTap: () => openCategory(item),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(children: [
                      Container(
                        width: 48,
                        height: 48,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(color: hints[item.id]?.$2 ?? _primarySoft, borderRadius: BorderRadius.circular(12)),
                        child: Text(item.name.characters.first, style: const TextStyle(fontWeight: FontWeight.w700, color: _primaryInk)),
                      ),
                      const SizedBox(width: 12),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(item.name, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: _ink)),
                        Text(hints[item.id]?.$1 ?? '', style: const TextStyle(fontSize: 13, color: _ink3)),
                      ])),
                      const Icon(Icons.chevron_right, color: _ink3),
                    ]),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _ask() {
    final question = config!.questions[step];
    final selected = answers[question.id] ?? [];
    final hasChoice = selected.isNotEmpty;
    return Scaffold(
      appBar: _bar(category!.name, onBack: () {
        if (step == 0) {
          setState(() => page = _Page.home);
        } else {
          setState(() => step -= 1);
        }
      }),
      body: Column(children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Text(question.label, style: const TextStyle(fontSize: 22, height: 30 / 22, fontWeight: FontWeight.w700, color: _ink)),
              const SizedBox(height: 12),
              _tag(question.multiple ? '可多选' : '单选', question.multiple),
              const SizedBox(height: 16),
              for (final option in question.options)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _option(option, selected.contains(option.id), question.multiple, () => toggle(question, option)),
                ),
              if (step == 0) ...[
                const SizedBox(height: 8),
                const Text('你的想法都可以告诉我', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                const SizedBox(height: 8),
                TextField(
                  key: const Key('free-text'),
                  controller: freeText,
                  maxLength: 200,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    hintText: '比如：想学 AI 产品经理、宿舍没有桌子、喜欢银色…',
                    filled: true,
                    fillColor: Colors.white,
                    border: OutlineInputBorder(),
                  ),
                ),
              ],
            ],
          ),
        ),
        _bottom(Row(children: [
          if (step > 0)
            SizedBox(width: 112, child: _button('上一题', false, () => setState(() => step -= 1))),
          if (step > 0) const SizedBox(width: 12),
          Expanded(child: _button(hasChoice ? '下一步' : '先跳过', true, nextStep)),
        ])),
      ]),
    );
  }

  Widget _confirm() {
    final rows = <Widget>[];
    for (var i = 0; i < config!.questions.length; i++) {
      final question = config!.questions[i];
      final ids = answers[question.id] ?? [];
      if (ids.isEmpty || ids.every((id) => question.options.any((option) => option.id == id && option.unsure))) continue;
      final labels = question.options.where((option) => ids.contains(option.id) && !option.unsure).map((option) => option.label).join('、');
      rows.add(ListTile(
        title: Text(question.label, style: const TextStyle(fontSize: 12, color: _ink3)),
        subtitle: Text(labels, style: const TextStyle(color: _primaryInk)),
        trailing: TextButton(onPressed: () => setState(() { step = i; page = _Page.ask; }), child: const Text('修改')),
      ));
    }
    return Scaffold(
      appBar: _bar('确认需求', onBack: () => setState(() => page = _Page.ask)),
      body: Column(children: [
        Expanded(child: ListView(padding: const EdgeInsets.all(20), children: [
          const Text('这是我目前理解的需求', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          const Text('有不对的地方，点修改就能调整。', style: TextStyle(color: _ink2)),
          const SizedBox(height: 16),
          const Text('已明确', style: TextStyle(color: _ok, fontWeight: FontWeight.w700)),
          Card(child: Column(children: rows)),
          const SizedBox(height: 16),
          const Text('你的想法', style: TextStyle(fontWeight: FontWeight.w700)),
          ListTile(
            title: Text(freeText.text.trim().isEmpty ? '未填写' : freeText.text.trim(), style: TextStyle(color: freeText.text.trim().isEmpty ? _ink3 : _ink)),
            trailing: TextButton(onPressed: () => setState(() { step = 0; page = _Page.ask; }), child: const Text('修改')),
          ),
        ])),
        _bottom(_button('开始寻找符合你的产品', true, startSearch)),
      ]),
    );
  }

  Widget _search() {
    const names = ['整理需求', '查找候选产品', '核对配置与价格', '整理推荐理由'];
    return Scaffold(
      appBar: _bar('正在查找', onBack: _leaveSearch),
      body: Column(children: [
        Expanded(child: ListView(padding: const EdgeInsets.all(20), children: [
          Text(searchError == null ? '正在查找适合你的产品' : (searchTimeout ? '查询时间比预期长' : '网络连接失败'),
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
          if (searchError != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(searchError!, style: const TextStyle(color: _warn))),
          const SizedBox(height: 16),
          for (var i = 0; i < names.length; i++)
            ListTile(
              leading: Icon(i < searchStage ? Icons.check_circle : (i == searchStage ? Icons.autorenew : Icons.circle_outlined),
                  color: i < searchStage ? _ok : (i == searchStage ? _primary : _ink3)),
              title: Text(names[i]),
              trailing: Text(i < searchStage ? '已完成' : (i == searchStage ? '进行中' : '等待中'), style: const TextStyle(fontSize: 12, color: _ink3)),
            ),
          const Text('会尽量核对具体配置，避免把不同版本混在一起。', style: TextStyle(color: _ink2)),
        ])),
        _bottom(searchError == null
            ? _button('返回修改需求', false, _leaveSearch)
            : Row(children: [
                Expanded(child: _button('修改需求', false, _leaveSearch)),
                const SizedBox(width: 12),
                Expanded(child: _button('重试', true, startSearch)),
              ])),
      ]),
    );
  }

  Widget _follow() {
    final questions = result?.followUpQuestions ?? [];
    return Scaffold(
      appBar: _bar('再补充一点', onBack: () => setState(() => page = _Page.confirm)),
      body: Column(children: [
        Expanded(child: ListView(padding: const EdgeInsets.all(20), children: [
          for (final question in questions) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(question.text, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600))),
          TextField(key: const Key('follow-text'), controller: followReply, maxLines: 3, decoration: const InputDecoration(filled: true, fillColor: Colors.white, hintText: '用自己的话补充')),
        ])),
        _bottom(_button('继续', true, () {
          followExtra = [followExtra, followReply.text.trim()].where((item) => item.isNotEmpty).join('\n');
          followReply.clear();
          followUpRound += 1;
          startSearch();
        })),
      ]),
    );
  }

  Widget _result() {
    final data = result!;
    final products = [if (data.primary != null) data.primary!, ...data.alternatives];
    if (products.isEmpty) {
      return Scaffold(
        appBar: _bar('推荐结果', right: TextButton(onPressed: resetHome, child: const Text('首页'))),
        body: Column(children: [
          const Expanded(child: Center(child: Text('没有找到符合条件的产品', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)))),
          _bottom(_button('重新开始', true, resetHome)),
        ]),
      );
    }
    return Scaffold(
      appBar: _bar('推荐结果', right: TextButton(onPressed: resetHome, child: const Text('首页'))),
      body: Column(children: [
        Expanded(child: ListView(padding: const EdgeInsets.all(20), children: [
          Wrap(spacing: 8, children: [
            for (final label in _summaryChips()) Chip(label: Text(label, style: const TextStyle(fontSize: 12))),
          ]),
          const SizedBox(height: 16),
          Text(data.status == 'success' ? '根据你的需求，优先考虑这款' : '只展示资料核实过的产品（核实到 ${data.shownCount} 款）',
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          if (data.primary != null) _productTile(data.primary!, primary: true),
          const SizedBox(height: 16),
          if (data.alternatives.isNotEmpty) const Text('备选', style: TextStyle(fontWeight: FontWeight.w700)),
          for (final item in data.alternatives) _productTile(item, primary: false),
        ])),
        _bottom(_button(products.length >= 3 ? '三款对比' : '${products.length} 款对比', true, () => setState(() => page = _Page.compare))),
      ]),
    );
  }

  void _leaveSearch() {
    requestGen++;
    stageTimer?.cancel();
    setState(() => page = _Page.confirm);
  }

  String _needLine() {
    final bits = <String>[];
    final written = freeText.text.trim();
    if (written.isNotEmpty) bits.add(written);
    for (final question in config?.questions ?? <SurveyQuestion>[]) {
      final ids = answers[question.id] ?? [];
      final labels = question.options.where((option) => ids.contains(option.id) && !option.unsure).map((option) => option.label);
      if (labels.isNotEmpty) bits.add(labels.join('、'));
    }
    return bits.isEmpty ? '未补充具体需求' : bits.join('；');
  }

  List<String> _summaryChips() {
    final chips = <String>[];
    if (freeText.text.trim().isNotEmpty) chips.add(freeText.text.trim());
    for (final question in config!.questions) {
      final ids = answers[question.id] ?? [];
      final labels = question.options.where((option) => ids.contains(option.id) && !option.unsure).map((option) => option.label);
      if (labels.isNotEmpty) chips.add(labels.join('、'));
    }
    if (!chips.any((item) => item.contains('元') || item.contains('预算'))) chips.add('预算未定');
    return chips.take(5).toList();
  }

  Widget _productTile(ProductCard item, {required bool primary}) {
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: primary ? _primary : _line, width: primary ? 2 : 1)),
      child: InkWell(
        onTap: () => setState(() { detail = item; page = _Page.detail; }),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (primary) const Text('首选', style: TextStyle(color: _primaryInk, fontWeight: FontWeight.w700)),
            Text(item.name, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text(item.price.label, key: Key('price-${item.candidateId}'), style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
            if (!item.price.missing) Text(item.price.basisLabel, style: const TextStyle(fontSize: 12, color: _ink3)),
            if (item.reasons.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(item.reasons.first.text)),
            const SizedBox(height: 8),
            const Text('查看详细理由'),
          ]),
        ),
      ),
    );
  }

  Widget _detail() {
    final item = detail!;
    return Scaffold(
      appBar: _bar('推荐依据', onBack: () => setState(() => page = _Page.result)),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        Text(item.name, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Text(item.price.label, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        if (!item.price.missing) Text('${item.price.basisLabel}\n价格为参考，不同口径的价格不能直接比较。', style: const TextStyle(color: _ink2)),
        const SizedBox(height: 16),
        const Text('为什么适合你', style: TextStyle(color: _ok, fontWeight: FontWeight.w700)),
        for (final reason in item.reasons) _reasonCard(item, reason),
        const SizedBox(height: 16),
        const Text('关键参数', style: TextStyle(fontWeight: FontWeight.w700)),
        for (final fact in item.facts)
          ListTile(
            title: Text(fact.field),
            subtitle: Text(fact.status == FactStatus.conflicting ? '资料存在冲突' : fact.display),
          ),
        const SizedBox(height: 8),
        const Text('资料来源', style: TextStyle(fontWeight: FontWeight.w700)),
        const Text('链接仅用于查看资料证据。', style: TextStyle(fontSize: 12, color: _ink3)),
        for (final source in result!.sources.where((source) => item.facts.any((fact) => fact.evidenceId == source.evidenceId) || item.price.evidenceId == source.evidenceId))
          ListTile(
            title: Text('来源：${source.sourceName ?? '太平洋电脑网'}'),
            subtitle: Text('${source.title ?? '未标注标题'}\n${source.url}\n查询时间 ${source.fetchedAt}\n来源更新时间 未标注'),
            trailing: IconButton(onPressed: () => Clipboard.setData(ClipboardData(text: source.url)), icon: const Icon(Icons.copy)),
          ),
      ]),
    );
  }

  Widget _reasonCard(ProductCard item, Reason reason) {
    final facts = item.facts.where((fact) => reason.factRefs.contains(fact.factId)).map((fact) => fact.display).join('；');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('你的需求：${_needLine()}', style: const TextStyle(fontSize: 14)),
          Text('依据：${facts.isEmpty ? '见关键参数' : facts}'),
          Text('对你的影响：${reason.text}'),
          Text(reason.isFact ? '官方资料事实' : '适合性判断', style: TextStyle(color: reason.isFact ? _ok : _primaryInk, fontSize: 12)),
          if (reason.limitations.isNotEmpty) Text('局限：${reason.limitations.join('；')}', style: const TextStyle(color: _warn)),
        ]),
      ),
    );
  }

  Widget _compare() {
    final data = result!;
    final products = [if (data.primary != null) data.primary!, ...data.alternatives];
    final fields = _compareFields[category?.id] ?? _compareFields['laptop']!;
    return Scaffold(
      appBar: _bar(products.length >= 3 ? '三款对比' : '${products.length} 款对比', onBack: () => setState(() => page = _Page.result)),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        Row(children: [
          for (var i = 0; i < products.length; i++)
            Expanded(child: Card(color: i == 0 ? _primarySoft : Colors.white, child: Padding(padding: const EdgeInsets.all(8), child: Column(children: [
              Text(i == 0 ? '首选' : '备选'),
              Text(products[i].name, style: const TextStyle(fontWeight: FontWeight.w700)),
              Text(products[i].price.label),
              if (!products[i].price.missing) Text(products[i].price.basisLabel, style: const TextStyle(fontSize: 12)),
            ])))),
        ]),
        const SizedBox(height: 12),
        for (final entry in data.comparison)
          if (!entry.comparable)
            Text('不可直接比较${entry.reason == null ? '' : '：${entry.reason}'}', style: const TextStyle(color: _warn)),
        const SizedBox(height: 12),
        for (final field in fields)
          _compareRow(field.$1, field.$2, products),
      ]),
    );
  }

  Widget _compareRow(String field, String label, List<ProductCard> products) {
    String valueOf(ProductCard item) {
      final found = item.facts.where((fact) => fact.field == field);
      if (found.isEmpty) return '暂无资料';
      return found.first.display;
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
        Row(children: [for (final item in products) Expanded(child: Text(valueOf(item)))]),
      ]),
    );
  }

  PreferredSizeWidget _bar(String title, {VoidCallback? onBack, Widget? right}) {
    return AppBar(
      backgroundColor: _bg,
      elevation: 0,
      leading: onBack == null ? const SizedBox.shrink() : IconButton(onPressed: onBack, icon: const Icon(Icons.arrow_back)),
      title: Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: _ink)),
      actions: [?right],
    );
  }

  Widget _bottom(Widget child) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
      decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: _line))),
      child: child,
    );
  }

  Widget _button(String label, bool primary, VoidCallback onPressed) {
    return SizedBox(
      height: 48,
      child: FilledButton(
        style: FilledButton.styleFrom(
          backgroundColor: primary ? _primary : Colors.white,
          foregroundColor: primary ? Colors.white : _ink,
          side: primary ? null : const BorderSide(color: _line),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        onPressed: onPressed,
        child: Text(label),
      ),
    );
  }

  Widget _tag(String text, bool primary) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(color: primary ? _primarySoft : const Color(0xFFF3F4F6), borderRadius: BorderRadius.circular(8)),
        child: Text(text, style: TextStyle(color: primary ? _primaryInk : _ink2, fontSize: 12)),
      ),
    );
  }

  Widget _option(OptionChoice option, bool selected, bool multiple, VoidCallback onTap) {
    return Material(
      color: selected ? _primarySoft : Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: selected ? _primary : (option.unsure ? _ink3 : _line), style: option.unsure && !selected ? BorderStyle.solid : BorderStyle.solid),
      ),
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 56),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(children: [
              Icon(selected ? Icons.check_circle : (multiple ? Icons.check_box_outline_blank : Icons.circle_outlined), color: selected ? _primary : _ink3),
              const SizedBox(width: 8),
              Expanded(child: Text(option.label, style: const TextStyle(fontSize: 16, color: _ink))),
              if (selected) const Text('已选', style: TextStyle(color: _primaryInk, fontSize: 12)),
            ]),
          ),
        ),
      ),
    );
  }
}
