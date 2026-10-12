import 'dart:async';

import 'package:flutter/material.dart';

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
  bool freeFocused = false;
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
      theme: ThemeData(useMaterial3: true, scaffoldBackgroundColor: _bg, fontFamily: 'PingFang SC', splashFactory: NoSplash.splashFactory),
      home: LayoutBuilder(builder: (context, constraints) {
        final screen = _screen();
        if (constraints.maxWidth < 700) return screen;
        final height = constraints.maxHeight > 900 ? 844.0 : constraints.maxHeight;
        return ColoredBox(
          color: const Color(0xFFE7EBF2),
          child: Center(
            child: Container(
              width: 390,
              height: height.clamp(0, 844),
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                color: _bg,
                borderRadius: BorderRadius.circular(36),
                border: Border.all(color: const Color(0xFFD7DDE6)),
                boxShadow: const [BoxShadow(color: Color(0x1A1F2937), blurRadius: 40, offset: Offset(0, 16))],
              ),
              child: screen,
            ),
          ),
        );
      }),
    );
  }

  Widget _screen() {
    return switch (page) {
      _Page.home => _home(),
      _Page.ask => _ask(),
      _Page.confirm => _confirm(),
      _Page.search => _search(),
      _Page.follow => _follow(),
      _Page.result => _result(),
      _Page.detail => _detail(),
      _Page.compare => _compare(),
    };
  }

  Widget _home() {
    const hints = {
      'laptop': ('办公、学习、创作', _primarySoft, Icons.laptop_mac_outlined),
      'phone': ('拍照、续航、日常', _mint, Icons.smartphone_outlined),
      'tablet': ('看剧、记笔记、绘画', _lilac, Icons.tablet_mac_outlined),
      'monitor': ('办公、游戏、设计', _warnSoft, Icons.monitor_outlined),
      'headphones': ('通勤、运动、降噪', _errSoft, Icons.headphones_outlined),
    };
    return Scaffold(
      backgroundColor: _bg,
      body: ListView(
        padding: const EdgeInsets.fromLTRB(24, 56, 24, 40),
        children: [
          const Text('想买什么？', style: TextStyle(fontSize: 28, height: 40 / 28, fontWeight: FontWeight.w700, letterSpacing: -0.4, color: _ink)),
          const Text('我们一起理清楚。', style: TextStyle(fontSize: 28, height: 40 / 28, fontWeight: FontWeight.w700, letterSpacing: -0.4, color: _ink)),
          const SizedBox(height: 12),
          const Text('还没想清楚需求也没关系。', style: TextStyle(fontSize: 16, color: _ink2)),
          if (homeError != null) ...[
            const SizedBox(height: 16),
            Text(homeError!, style: const TextStyle(fontSize: 14, color: _warn)),
            const SizedBox(height: 8),
            Align(alignment: Alignment.centerLeft, child: _button('重试', true, loadHome)),
          ],
          const SizedBox(height: 48),
          for (final item in categories)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Material(
                color: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: const BorderSide(color: _line)),
                child: InkWell(
                  onTap: () => openCategory(item),
                  borderRadius: BorderRadius.circular(16),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(children: [
                      Container(
                        width: 48,
                        height: 48,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(color: hints[item.id]?.$2 ?? _primarySoft, borderRadius: BorderRadius.circular(12)),
                        child: Icon(hints[item.id]?.$3 ?? Icons.laptop_mac_outlined, color: _ink, size: 24),
                      ),
                      const SizedBox(width: 16),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(item.name, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: _ink)),
                        const SizedBox(height: 2),
                        Text(hints[item.id]?.$1 ?? '', style: const TextStyle(fontSize: 13, color: _ink3)),
                      ])),
                      const Icon(Icons.chevron_right, color: _ink3, size: 18),
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
    return _frame(
      bar: _bar(
        Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(_categoryIcon(category!.id), size: 18, color: _ink),
          const SizedBox(width: 6),
          Flexible(child: Text(category!.name, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink))),
        ]),
        onBack: () {
          if (step == 0) {
            setState(() => page = _Page.home);
          } else {
            setState(() => step -= 1);
          }
        },
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
        children: [
          Text(question.label, style: const TextStyle(fontSize: 22, height: 30 / 22, fontWeight: FontWeight.w700, color: _ink)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            _tag(question.multiple ? '可多选' : '单选', question.multiple),
          ]),
          const SizedBox(height: 20),
          for (final option in question.options)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _option(option, selected.contains(option.id), question.multiple, () => toggle(question, option)),
            ),
          if (step == 0) ...[
            const SizedBox(height: 14),
            const Text('你的想法都可以告诉我', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: _ink)),
            const SizedBox(height: 8),
            AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: freeFocused ? _primary : _line, width: freeFocused ? 1.5 : 1),
              ),
              child: Column(children: [
                TextField(
                  key: const Key('free-text'),
                  controller: freeText,
                  maxLength: 200,
                  maxLines: freeFocused ? 3 : 2,
                  onChanged: (_) => setState(() {}),
                  onTap: () => setState(() => freeFocused = true),
                  onTapOutside: (_) => setState(() => freeFocused = false),
                  style: const TextStyle(fontSize: 15, height: 1.5, color: _ink),
                  decoration: const InputDecoration(
                    counterText: '',
                    isCollapsed: true,
                    hintText: '比如：想学 AI 产品经理、宿舍没有桌子、喜欢银色…',
                    hintStyle: TextStyle(color: _ink3, fontSize: 15),
                    border: InputBorder.none,
                  ),
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Text(freeFocused ? '输入中…' : '选填', style: const TextStyle(fontSize: 12, color: _ink3)),
                  const Spacer(),
                  Text('${freeText.text.characters.length}/200', style: const TextStyle(fontSize: 12, color: _ink3)),
                ]),
              ]),
            ),
          ],
        ],
      ),
      bottom: Row(children: [
        if (step > 0) SizedBox(width: 112, child: _button('上一题', false, () => setState(() => step -= 1))),
        if (step > 0) const SizedBox(width: 12),
        Expanded(child: _button(hasChoice ? '下一步' : '先跳过', true, nextStep)),
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
      rows.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(question.label, style: const TextStyle(fontSize: 12, color: _ink3)),
            const SizedBox(height: 6),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final label in labels.split('、'))
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(color: _primarySoft, borderRadius: BorderRadius.circular(8)),
                  child: Text(label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500, color: _primaryInk)),
                ),
            ]),
          ])),
          TextButton(onPressed: () => setState(() { step = i; page = _Page.ask; }), child: const Text('修改', style: TextStyle(color: _primary, fontWeight: FontWeight.w500))),
        ]),
      ));
    }
    return _frame(
      bar: _bar(const Text('确认需求', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink)), onBack: () => setState(() => page = _Page.ask)),
      body: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 24), children: [
        const Text('这是我目前理解的需求', style: TextStyle(fontSize: 22, height: 30 / 22, fontWeight: FontWeight.w700, color: _ink)),
        const SizedBox(height: 6),
        const Text('有不对的地方，点修改就能调整。', style: TextStyle(fontSize: 14, color: _ink2)),
        const SizedBox(height: 16),
        _section('已明确', Icons.check_rounded, _ok, rows.isEmpty ? [const Padding(padding: EdgeInsets.symmetric(vertical: 14), child: Text('还没有明确的选项', style: TextStyle(color: _ink3)))] : rows),
        const SizedBox(height: 12),
        _section('你的想法', Icons.edit_outlined, _ink2, [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(child: Text(freeText.text.trim().isEmpty ? '未填写' : freeText.text.trim(), style: TextStyle(fontSize: 15, height: 1.5, color: freeText.text.trim().isEmpty ? _ink3 : _ink))),
              TextButton(onPressed: () => setState(() { step = 0; page = _Page.ask; }), child: const Text('修改', style: TextStyle(color: _primary, fontWeight: FontWeight.w500))),
            ]),
          ),
        ]),
      ]),
      bottom: _button('开始寻找符合你的产品', true, startSearch, icon: Icons.search),
    );
  }

  Widget _search() {
    const names = ['整理需求', '查找候选产品', '核对配置与价格', '整理推荐理由'];
    final failed = searchError != null;
    return _frame(
      bar: _bar(const Text('正在查找', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink)), onBack: _leaveSearch),
      body: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 24), children: [
        if (!failed)
          const Text('正在查找适合你的产品', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: _ink))
        else
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 36,
              height: 36,
              alignment: Alignment.center,
              decoration: const BoxDecoration(color: _warnSoft, shape: BoxShape.circle),
              child: const Icon(Icons.error_outline, color: _warn, size: 18),
            ),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(searchTimeout ? '查询时间比预期长' : '网络连接失败', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: _ink)),
              const SizedBox(height: 4),
              Text(searchError!, style: const TextStyle(fontSize: 14, height: 1.5, color: _ink2)),
            ])),
          ]),
        const SizedBox(height: 24),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: _line)),
          child: Column(children: [
            for (var i = 0; i < names.length; i++)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Row(children: [
                  Container(
                    width: 28,
                    height: 28,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: i < searchStage ? _okSoft : (i == searchStage && !failed ? _primarySoft : const Color(0xFFF3F5F8)),
                      shape: BoxShape.circle,
                    ),
                    child: i < searchStage
                        ? const Icon(Icons.check, size: 15, color: _ok)
                        : (!failed && i == searchStage
                            ? const _SpinningIcon(icon: Icons.autorenew, color: _primary)
                            : (!failed
                                ? const _PulsingDot()
                                : Container(width: 6, height: 6, decoration: const BoxDecoration(color: _ink3, shape: BoxShape.circle)))),
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: Text(names[i], style: TextStyle(fontSize: 16, fontWeight: i <= searchStage && !failed ? FontWeight.w500 : FontWeight.w400, color: i <= searchStage && !failed ? _ink : _ink3))),
                  Text(i < searchStage ? '已完成' : (i == searchStage && !failed ? '进行中' : '等待中'),
                      style: TextStyle(fontSize: 13, color: i < searchStage ? _ok : (i == searchStage && !failed ? _primary : _ink3))),
                ]),
              ),
          ]),
        ),
        if (!failed) ...[
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: _line)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Container(height: 16, width: 180, decoration: BoxDecoration(color: const Color(0xFFEEF0F3), borderRadius: BorderRadius.circular(6))),
              const SizedBox(height: 12),
              Container(height: 12, decoration: BoxDecoration(color: const Color(0xFFEEF0F3), borderRadius: BorderRadius.circular(6))),
              const SizedBox(height: 12),
              Container(height: 12, width: 240, decoration: BoxDecoration(color: const Color(0xFFEEF0F3), borderRadius: BorderRadius.circular(6))),
            ]),
          ),
          const SizedBox(height: 20),
          const Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(Icons.info_outline, size: 18, color: _primary),
            SizedBox(width: 8),
            Expanded(child: Text('会尽量核对具体配置，避免把不同版本混在一起。', style: TextStyle(fontSize: 14, color: _ink2))),
          ]),
        ],
      ]),
      bottom: failed
          ? Row(children: [
              Expanded(child: _button('修改需求', false, _leaveSearch)),
              const SizedBox(width: 12),
              Expanded(child: _button('重试', true, startSearch)),
            ])
          : _button('返回修改需求', false, _leaveSearch, icon: Icons.edit_outlined),
    );
  }

  Widget _follow() {
    final questions = result?.followUpQuestions ?? [];
    return _frame(
      bar: _bar(const Text('再补充一点', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink)), onBack: () => setState(() => page = _Page.confirm)),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        for (final question in questions) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(question.text, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: _ink))),
        TextField(key: const Key('follow-text'), controller: followReply, maxLines: 3, decoration: InputDecoration(filled: true, fillColor: Colors.white, hintText: '用自己的话补充', border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: _line)))),
      ]),
      bottom: _button('继续', true, () {
        followExtra = [followExtra, followReply.text.trim()].where((item) => item.isNotEmpty).join('\n');
        followReply.clear();
        followUpRound += 1;
        startSearch();
      }),
    );
  }

  Widget _result() {
    final data = result!;
    final products = [if (data.primary != null) data.primary!, ...data.alternatives];
    if (products.isEmpty) {
      return _frame(
        bar: _bar(const Text('推荐结果', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink)), right: _homeButton()),
        body: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 24), children: [
          _needSummary(),
          const SizedBox(height: 56),
          const Center(child: Text('没有找到符合条件的产品', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: _ink))),
        ]),
        bottom: _button('重新开始', true, resetHome),
      );
    }
    return _frame(
      bar: _bar(const Text('推荐结果', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink)), right: _homeButton()),
      body: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
        _needSummary(),
        const SizedBox(height: 20),
        Text(data.status == 'success' ? '根据你的需求，优先考虑这款' : '只展示资料核实过的产品（核实到 ${data.shownCount} 款）',
            style: const TextStyle(fontSize: 22, height: 30 / 22, fontWeight: FontWeight.w700, color: _ink)),
        const SizedBox(height: 12),
        if (data.primary != null) _productTile(data.primary!, primary: true),
        if (data.alternatives.isNotEmpty) ...[
          const SizedBox(height: 20),
          const Text('备选', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: _ink)),
          const SizedBox(height: 8),
          for (final item in data.alternatives) Padding(padding: const EdgeInsets.only(bottom: 10), child: _productTile(item, primary: false)),
        ],
      ]),
      bottom: _button(products.length >= 3 ? '三款对比' : '${products.length} 款对比', true, () => setState(() => page = _Page.compare), icon: Icons.compare_arrows),
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
    final configLine = item.facts.where((fact) => fact.status == FactStatus.supported).take(3).map((fact) => fact.display).join(' · ');
    return Material(
      color: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: primary ? _primary : _line, width: primary ? 2 : 1)),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => setState(() { detail = item; page = _Page.detail; }),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (primary)
              Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(color: _primarySoft, borderRadius: BorderRadius.circular(6)),
                child: const Text('首选', style: TextStyle(color: _primaryInk, fontSize: 12, fontWeight: FontWeight.w600)),
              ),
            Text(item.name, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700, color: _ink)),
            if (configLine.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: Text(configLine, style: const TextStyle(fontSize: 14, color: _ink2))),
            const SizedBox(height: 10),
            _priceLine(item, large: true),
            if (item.reasons.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(item.reasons.first.text, style: const TextStyle(fontSize: 15, height: 1.45, color: _ink))),
            const SizedBox(height: 10),
            const Text('查看详细理由', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: _primary)),
          ]),
        ),
      ),
    );
  }

  Widget _priceLine(ProductCard item, {required bool large}) {
    return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
      Flexible(child: Text(item.price.label, key: Key('price-${item.candidateId}'), style: TextStyle(fontSize: item.price.missing ? 15 : (large ? 24 : 18), fontWeight: item.price.missing ? FontWeight.w500 : FontWeight.w700, color: item.price.missing ? _ink2 : _ink))),
      if (!item.price.missing) ...[
        const SizedBox(width: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(color: const Color(0xFFEEF0F3), borderRadius: BorderRadius.circular(6)),
          child: Text(item.price.basisLabel, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: _ink2)),
        ),
      ],
    ]);
  }

  Widget _detail() {
    final item = detail!;
    return _frame(
      bar: _bar(const Text('推荐依据', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink)), onBack: () => setState(() => page = _Page.result)),
      body: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
        Text(item.name, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: _line)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _priceLine(item, large: true),
            if (!item.price.missing) const Padding(padding: EdgeInsets.only(top: 8), child: Text('价格为参考，不同口径的价格不能直接比较。', style: TextStyle(fontSize: 13, color: _ink3))),
          ]),
        ),
        const SizedBox(height: 16),
        const Text('为什么适合你', style: TextStyle(color: _ok, fontWeight: FontWeight.w700)),
        for (final reason in item.reasons) _reasonCard(item, reason),
        const SizedBox(height: 16),
        const Text('关键参数', style: TextStyle(fontWeight: FontWeight.w700)),
        for (final fact in item.facts)
          ListTile(
            title: Text(_fieldLabel(category?.id, fact.field)),
            subtitle: Text(fact.status == FactStatus.conflicting ? '资料存在冲突' : fact.display),
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
    return _frame(
      bar: _bar(Text(products.length >= 3 ? '三款对比' : '${products.length} 款对比', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink)), onBack: () => setState(() => page = _Page.result)),
      body: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
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

  String _fieldLabel(String? categoryId, String field) {
    const names = <String, Map<String, String>>{
      'laptop': {
        'release_date': '上市时间', 'os': '操作系统', 'cpu': '处理器', 'memory': '内存容量', 'storage': '硬盘容量',
        'screen_size': '屏幕尺寸', 'resolution': '屏幕分辨率', 'refresh_rate': '屏幕刷新率', 'screen_type': '屏幕类型',
        'brightness': '屏幕亮度', 'gpu_type': '显卡类型', 'gpu': '显卡芯片', 'battery': '电池容量', 'battery_life': '续航时间',
        'weight': '重量', 'thickness': '厚度', 'usb': 'USB 接口', 'other_ports': '其它接口', 'wifi': '无线网卡',
        'camera': '摄像头', 'biometrics': '生物识别',
      },
      'phone': {
        'release_date': '发布时间', 'os': '操作系统', 'cpu': '处理器', 'memory': '运行内存', 'storage': '机身容量',
        'screen_size': '屏幕大小', 'resolution': '屏幕分辨率', 'refresh_rate': '屏幕刷新率', 'screen_material': '屏幕材质',
        'pwm': 'PWM 调光频率', 'battery': '电池容量', 'charging': '充电', 'camera_layout': '摄像头组合',
        'rear_camera': '后置主摄', 'zoom': '变焦', 'front_camera': '前置摄像头', 'network': '网络制式',
        'satellite': '卫星通信', 'nfc': 'NFC', 'biometrics': '生物识别', 'durability': '防水防尘',
        'dimensions': '尺寸', 'weight': '重量',
      },
      'tablet': {
        'release_date': '发布时间', 'os': '操作系统', 'cpu': '处理器', 'memory': '运行内存', 'storage': '存储容量',
        'screen_size': '屏幕尺寸', 'resolution': '分辨率', 'refresh_rate': '屏幕刷新率', 'brightness': '屏幕亮度',
        'screen_material': '屏幕材质', 'features': '特性', 'wifi': 'WiFi', 'battery': '电池容量',
        'battery_life': '续航时间', 'ports': '接口', 'speakers': '扬声器', 'dimensions': '尺寸', 'weight': '重量',
      },
      'monitor': {
        'size': '尺寸', 'aspect_ratio': '屏幕比例', 'resolution': '分辨率', 'refresh_rate': '刷新率', 'panel': '面板类型',
        'brightness': '亮度', 'contrast': '典型对比度', 'response_time': '响应时间', 'colors': '色数', 'ports': '接口类型',
        'wall_mount': '支持壁挂', 'dimensions': '外观尺寸', 'weight': '重量',
      },
      'headphones': {
        'form': '佩戴方式', 'usage': '主要用途', 'anc': '降噪功能', 'driver': '驱动单元', 'battery_life': '电池续航',
        'fast_charge': '快速充电', 'mic': '麦克风', 'material': '外观材质', 'other': '其它功能',
      },
    };
    return names[categoryId]?[field] ?? names['laptop']?[field] ?? field;
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

  Widget _frame({Widget? bar, required Widget body, Widget? bottom}) {
    return Scaffold(
      backgroundColor: _bg,
      body: Column(children: [
        if (bar != null) bar,
        Expanded(child: body),
        if (bottom != null)
          Container(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
            decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: _line))),
            child: bottom,
          ),
      ]),
    );
  }

  Widget _bar(Widget title, {VoidCallback? onBack, Widget? right}) {
    return SizedBox(
      height: 48,
      child: Row(children: [
        SizedBox(
          width: 44,
          height: 44,
          child: onBack == null ? null : IconButton(onPressed: onBack, icon: const Icon(Icons.arrow_back, color: _ink, size: 22), tooltip: '返回'),
        ),
        Expanded(child: Center(child: title)),
        SizedBox(width: right == null ? 44 : null, child: right),
        if (right != null) const SizedBox(width: 8),
      ]),
    );
  }

  Widget _homeButton() {
    return TextButton.icon(
      onPressed: resetHome,
      icon: const Icon(Icons.home_outlined, size: 18, color: _ink2),
      label: const Text('首页', style: TextStyle(fontSize: 14, color: _ink2)),
    );
  }

  Widget _needSummary() {
    final chips = _summaryChips();
    if (chips.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: _line)),
      child: Wrap(spacing: 6, runSpacing: 6, children: [
        for (final label in chips)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(color: _bg, borderRadius: BorderRadius.circular(20)),
            child: Text(label, style: const TextStyle(fontSize: 13, color: _ink2)),
          ),
      ]),
    );
  }

  Widget _section(String title, IconData icon, Color color, List<Widget> children) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: _line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 6),
          Text(title, style: TextStyle(fontWeight: FontWeight.w700, color: color)),
        ]),
        ...children,
      ]),
    );
  }

  IconData _categoryIcon(String id) {
    return switch (id) {
      'phone' => Icons.smartphone_outlined,
      'tablet' => Icons.tablet_mac_outlined,
      'monitor' => Icons.monitor_outlined,
      'headphones' => Icons.headphones_outlined,
      _ => Icons.laptop_mac_outlined,
    };
  }

  Widget _button(String label, bool primary, VoidCallback onPressed, {IconData? icon}) {
    final style = FilledButton.styleFrom(
      backgroundColor: primary ? _primary : Colors.white,
      foregroundColor: primary ? Colors.white : _ink,
      side: primary ? null : const BorderSide(color: _line),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
    );
    return SizedBox(
      height: 48,
      width: double.infinity,
      child: icon == null
          ? FilledButton(style: style, onPressed: onPressed, child: Text(label))
          : FilledButton.icon(style: style, onPressed: onPressed, icon: Icon(icon, size: 18), label: Text(label)),
    );
  }

  Widget _tag(String text, bool primary) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: primary ? _primarySoft : const Color(0xFFEEF0F3), borderRadius: BorderRadius.circular(6)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (primary) const Icon(Icons.check, size: 13, color: _primaryInk),
        if (primary) const SizedBox(width: 4),
        Text(text, style: TextStyle(color: primary ? _primaryInk : _ink2, fontSize: 12, fontWeight: FontWeight.w500)),
      ]),
    );
  }

  Widget _option(OptionChoice option, bool selected, bool multiple, VoidCallback onTap) {
    final unsure = option.unsure && !selected;
    return Material(
      color: selected ? _primarySoft : Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: selected ? _primary : (unsure ? const Color(0xFFCFD5DE) : _line), width: selected ? 1.5 : 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 56),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(children: [
              Container(
                width: 20,
                height: 20,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: selected ? _primary : Colors.white,
                  borderRadius: BorderRadius.circular(multiple ? 4 : 10),
                  border: Border.all(color: selected ? _primary : const Color(0xFFB9C1CD), width: 1.5),
                ),
                child: selected ? const Icon(Icons.check, size: 13, color: Colors.white) : null,
              ),
              const SizedBox(width: 12),
              Expanded(child: Text(option.label, style: TextStyle(fontSize: 16, fontWeight: selected ? FontWeight.w600 : FontWeight.w400, color: selected ? _primaryInk : _ink))),
              if (selected) const Text('已选', style: TextStyle(color: _primaryInk, fontSize: 12, fontWeight: FontWeight.w500)),
            ]),
          ),
        ),
      ),
    );
  }
}

class _SpinningIcon extends StatefulWidget {
  const _SpinningIcon({required this.icon, required this.color});
  final IconData icon;
  final Color color;

  @override
  State<_SpinningIcon> createState() => _SpinningIconState();
}

class _SpinningIconState extends State<_SpinningIcon> with SingleTickerProviderStateMixin {
  late final AnimationController _turns;

  @override
  void initState() {
    super.initState();
    _turns = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat();
  }

  @override
  void dispose() {
    _turns.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RotationTransition(turns: _turns, child: Icon(widget.icon, size: 15, color: widget.color));
  }
}

class _PulsingDot extends StatefulWidget {
  const _PulsingDot();

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: Tween<double>(begin: 0.35, end: 1).animate(_pulse),
      child: Container(width: 6, height: 6, decoration: const BoxDecoration(color: _ink3, shape: BoxShape.circle)),
    );
  }
}
