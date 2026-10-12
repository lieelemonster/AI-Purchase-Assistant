import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'models.dart';

const _bg = Color(0xFFF4F4F2);
const _bg2 = Color(0xFFEAEAE6);
const _surface = Color(0xFFFFFFFF);
const _surface2 = Color(0xFFF9F9F8);
const _ink = Color(0xFF15171C);
const _ink2 = Color(0xFF4A4D55);
const _ink3 = Color(0xFF7E818A);
const _line = Color(0xFFE4E4DF);
const _line2 = Color(0xFFD2D2CC);
const _primary = Color(0xFF1F2B48);
const _primaryInk = Color(0xFF131C33);
const _primarySoft = Color(0xFFECEEF3);
const _ok = Color(0xFF2E7356);
const _okSoft = Color(0xFFE9F1EC);
const _warn = Color(0xFF946020);
const _warnSoft = Color(0xFFF6EFE3);
const _err = Color(0xFFA8403B);
const _errSoft = Color(0xFFF6EAEA);
const _mint = Color(0xFFE8EFEC);
const _lilac = Color(0xFFEEECF2);
const _disabledBg = Color(0xFFE2E2DE);
const _disabledInk = Color(0xFF9A9CA2);

const _shadowCard = [
  BoxShadow(color: Color(0x0A14161C), blurRadius: 2, offset: Offset(0, 1)),
  BoxShadow(color: Color(0x0A14161C), blurRadius: 8, offset: Offset(0, 2)),
];
const _shadowRaise = [
  BoxShadow(color: Color(0x0D14161C), blurRadius: 4, offset: Offset(0, 2)),
  BoxShadow(color: Color(0x1414161C), blurRadius: 24, offset: Offset(0, 8)),
];

const _compareFields = <String, List<(String, String)>>{
  'laptop': [('processor', '处理器'), ('memory', '内存'), ('storage', '硬盘'), ('screen_size', '屏幕'), ('gpu', '显卡'), ('weight', '重量')],
  'phone': [('processor', '处理器'), ('memory', '内存'), ('storage', '存储'), ('screen_size', '屏幕'), ('rear_camera', '拍照'), ('battery_capacity', '电池')],
  'tablet': [('processor', '处理器'), ('memory', '内存'), ('storage', '存储'), ('screen_size', '屏幕'), ('stylus_support', '手写笔'), ('weight', '重量')],
  'headphones': [('earbud_type', '佩戴方式'), ('anc', '降噪'), ('single_battery_life', '续航'), ('weight', '重量')],
};

class BuyFlow extends StatefulWidget {
  const BuyFlow({super.key, required this.api});
  final BuyApi api;

  @override
  State<BuyFlow> createState() => _BuyFlowState();
}

enum _Page { home, ask, confirm, search, result, detail, compare }

class _BuyFlowState extends State<BuyFlow> {
  _Page page = _Page.home;
  bool connected = false;
  String? homeError;
  List<CategoryInfo> categories = [];
  CategoryInfo? category;
  OptionConfig? config;
  int step = 0;
  final answers = <String, List<String>>{};
  final textInputs = <String, TextEditingController>{};
  static const _ideaKey = 'idea';
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
    for (final controller in textInputs.values) {
      controller.dispose();
    }
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
        for (final controller in textInputs.values) {
          controller.clear();
        }
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
    setState(_pruneHidden);
  }

  List<SurveyQuestion> get shownQuestions {
    final questions = config?.questions ?? const <SurveyQuestion>[];
    return questions.where(_isShown).toList();
  }

  bool _isShown(SurveyQuestion question) {
    final when = question.showWhen;
    if (when == null) return true;
    bool hit(ShowClause clause) {
      final selected = answers[clause.questionId] ?? const <String>[];
      return clause.optionIds.any(selected.contains);
    }

    final allOk = when.allOf.every(hit);
    final anyOk = when.anyOf.isEmpty || when.anyOf.any(hit);
    return allOk && anyOk;
  }

  void _pruneHidden() {
    final visible = shownQuestions.map((question) => question.id).toSet();
    answers.removeWhere((id, _) => !visible.contains(id));
    for (final entry in textInputs.entries) {
      if (!visible.contains(entry.key)) entry.value.clear();
    }
    final count = shownQuestions.length;
    if (count > 0 && step >= count) step = count - 1;
  }

  TextEditingController _inputFor(String id) {
    return textInputs.putIfAbsent(id, TextEditingController.new);
  }

  void nextStep() {
    final last = step >= shownQuestions.length - 1;
    if (last) {
      setState(() => page = _Page.confirm);
    } else {
      setState(() => step += 1);
    }
  }

  List<Map<String, dynamic>> get optionPayload {
    final visible = shownQuestions.where((question) => question.isChoice).map((question) => question.id).toSet();
    return answers.entries
        .where((entry) => entry.value.isNotEmpty && visible.contains(entry.key))
        .map((entry) => {'question_id': entry.key, 'option_ids': entry.value})
        .toList();
  }

  String get composedText {
    final parts = <String>[];
    for (final question in shownQuestions) {
      final raw = textInputs[question.id]?.text.trim() ?? '';
      if (raw.isEmpty) continue;
      if (question.kind == 'number') {
        parts.add('预算上限：$raw元');
      } else if (question.kind == 'text') {
        parts.add('${question.label}：$raw');
      }
    }
    final idea = textInputs[_ideaKey]?.text.trim() ?? '';
    if (idea.isNotEmpty) parts.insert(0, idea);
    return parts.join('\n');
  }

  bool _showsIdea(SurveyQuestion question) => question.id == 'usage' || question.id == 'scenarios';

  String _ideaHint() {
    return switch (category?.id) {
      'phone' => '比如：只要小米、拍照要好、不要曲面屏',
      'tablet' => '比如：要能手写记笔记、只要苹果、不要太重',
      'headphones' => '比如：通勤要降噪、不要入耳、主要连手机',
      _ => '比如：要能剪视频、经常出差、不要游戏本外观',
    };
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
        followUpRound: 0,
      );
      if (!mounted || generation != requestGen) return;
      stageTimer?.cancel();
      setState(() {
        result = response;
        if (response.status == 'timeout') {
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
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: _bg,
        fontFamily: 'PingFang SC',
        splashFactory: NoSplash.splashFactory,
        colorScheme: const ColorScheme.light(primary: _primary, onPrimary: Colors.white, surface: _surface),
      ),
      home: LayoutBuilder(builder: (context, constraints) {
        final screen = _screen();
        if (constraints.maxWidth < 700) return screen;
        final height = constraints.maxHeight > 900 ? 844.0 : constraints.maxHeight;
        return ColoredBox(
          color: _bg2,
          child: Center(
            child: Container(
              width: 390,
              height: height.clamp(0, 844),
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                color: _bg,
                borderRadius: BorderRadius.circular(36),
                border: Border.all(color: _line2),
                boxShadow: _shadowRaise,
              ),
              child: screen,
            ),
          ),
        );
      }),
    );
  }

  Widget _screen() {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 280),
      switchInCurve: const Cubic(0.2, 0.7, 0.2, 1),
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: SlideTransition(
          position: Tween<Offset>(begin: const Offset(0.04, 0), end: Offset.zero).animate(animation),
          child: child,
        ),
      ),
      child: KeyedSubtree(
        key: ValueKey(page),
        child: switch (page) {
          _Page.home => _home(),
          _Page.ask => _ask(),
          _Page.confirm => _confirm(),
          _Page.search => _search(),
          _Page.result => _result(),
          _Page.detail => _detail(),
          _Page.compare => _compare(),
        },
      ),
    );
  }

  Widget _home() {
    const hints = {
      'laptop': ('办公、学习、创作', _primarySoft, Icons.laptop_mac_outlined),
      'phone': ('拍照、续航、日常', _mint, Icons.smartphone_outlined),
      'tablet': ('看剧、记笔记、绘画', _lilac, Icons.tablet_mac_outlined),
      'headphones': ('通勤、运动、降噪', _errSoft, Icons.headphones_outlined),
    };
    return Scaffold(
      backgroundColor: _bg,
      body: ListView(
        padding: const EdgeInsets.fromLTRB(24, 56, 24, 40),
        children: [
          const Text('想买什么？', style: TextStyle(fontSize: 30, height: 40 / 30, fontWeight: FontWeight.w700, letterSpacing: -0.4, color: _ink)),
          const Text('我们一起理清楚。', style: TextStyle(fontSize: 30, height: 40 / 30, fontWeight: FontWeight.w700, letterSpacing: -0.4, color: _ink)),
          const SizedBox(height: 12),
          const Text('还没想清楚需求也没关系。', style: TextStyle(fontSize: 16, height: 24 / 16, color: _ink2)),
          if (homeError != null) ...[
            const SizedBox(height: 16),
            Text(homeError!, style: const TextStyle(fontSize: 14, color: _warn)),
            const SizedBox(height: 8),
            Align(alignment: Alignment.centerLeft, child: _button('重试', true, loadHome)),
          ],
          const SizedBox(height: 40),
          for (final item in categories)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: DecoratedBox(
                decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line), boxShadow: _shadowCard),
                child: Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () => openCategory(item),
                  borderRadius: BorderRadius.circular(18),
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
            ),
        ],
      ),
    );
  }

  Widget _ask() {
    final question = shownQuestions[step];
    final selected = answers[question.id] ?? [];
    final hasChoice = selected.isNotEmpty;
    final written = textInputs[question.id]?.text.trim() ?? '';
    final numberReady = RegExp(r'^\d+$').hasMatch(written) && int.parse(written) > 0;
    final canProceed = question.kind == 'number' ? numberReady : (!question.required || hasChoice || question.kind == 'text');
    final nextLabel = question.isChoice && !hasChoice && !question.required ? '先跳过' : '下一步';
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
          if (question.note != null) ...[
            const SizedBox(height: 8),
            Text(question.note!, style: const TextStyle(fontSize: 14, height: 1.5, color: _ink2)),
          ],
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            _tag(question.kind == 'text' ? '选填' : (question.kind == 'number' ? '填写数字' : (question.multiple ? '可多选' : '单选')), question.multiple),
          ]),
          const SizedBox(height: 20),
          if (question.isChoice)
            for (final option in question.options)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _option(option, selected.contains(option.id), question.multiple, () => toggle(question, option)),
              )
          else
            _textBox(question),
          if (_showsIdea(question)) ...[
            const SizedBox(height: 14),
            const Text('你的想法都可以告诉我', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: _ink)),
            const SizedBox(height: 8),
            _textBox(question, idea: true, hint: _ideaHint()),
          ],
        ],
      ),
      bottom: Row(children: [
        if (step > 0) SizedBox(width: 112, child: _button('上一题', false, () => setState(() => step -= 1))),
        if (step > 0) const SizedBox(width: 12),
        Expanded(child: _button(nextLabel, true, canProceed ? nextStep : null)),
      ]),
    );
  }

  Widget _textBox(SurveyQuestion question, {bool idea = false, String? hint}) {
    final controller = _inputFor(idea ? _ideaKey : question.id);
    final number = question.kind == 'number';
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: _surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: freeFocused ? _primary : _line),
        boxShadow: freeFocused ? const [BoxShadow(color: Color(0x241F2B48), spreadRadius: 3)] : _shadowCard,
      ),
      child: Column(children: [
        TextField(
          key: Key(idea ? 'free-text' : 'text-${question.id}'),
          controller: controller,
          maxLength: number ? 7 : 200,
          maxLines: number ? 1 : (freeFocused ? 3 : 2),
          keyboardType: number ? TextInputType.number : TextInputType.text,
          inputFormatters: number && !idea ? [FilteringTextInputFormatter.digitsOnly] : null,
          onChanged: (_) => setState(() {}),
          onTap: () => setState(() => freeFocused = true),
          onTapOutside: (_) => setState(() => freeFocused = false),
          style: const TextStyle(fontSize: 15, height: 1.5, color: _ink),
          decoration: InputDecoration(
            counterText: '',
            isCollapsed: true,
            hintText: hint ?? (number ? '例如 6000' : '选填，没有就直接下一步'),
            hintStyle: const TextStyle(color: _ink3, fontSize: 15),
            border: InputBorder.none,
          ),
        ),
        if (idea) ...[
          const SizedBox(height: 8),
          Row(children: [
            Text(freeFocused ? '输入中…' : '选填', style: const TextStyle(fontSize: 12, color: _ink3)),
            const Spacer(),
            Text('${controller.text.characters.length}/200', style: const TextStyle(fontSize: 12, color: _ink3)),
          ]),
        ],
      ]),
    );
  }

  Widget _confirm() {
    final rows = <Widget>[];
    final shown = shownQuestions;
    for (var i = 0; i < shown.length; i++) {
      final question = shown[i];
      final written = textInputs[question.id]?.text.trim() ?? '';
      final ids = answers[question.id] ?? [];
      final labels = <String>[];
      if (question.kind == 'number' && written.isNotEmpty) {
        labels.add('$written 元');
      } else if (question.kind == 'text' && written.isNotEmpty) {
        labels.add(written);
      } else if (question.isChoice) {
        labels.addAll(question.options.where((option) => ids.contains(option.id) && !option.unsure).map((option) => option.label));
      }
      if (labels.isEmpty) continue;
      rows.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(question.label, style: const TextStyle(fontSize: 12, color: _ink3)),
            const SizedBox(height: 6),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final label in labels)
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
        if ((textInputs[_ideaKey]?.text.trim() ?? '').isNotEmpty) ...[
          const SizedBox(height: 12),
          _section('你的想法', Icons.edit_outlined, _ink2, [
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 14),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(child: Text(textInputs[_ideaKey]!.text.trim(), style: const TextStyle(fontSize: 15, height: 1.5, color: _ink))),
                TextButton(
                  onPressed: () => setState(() {
                    step = shown.indexWhere((question) => _showsIdea(question));
                    if (step < 0) step = 0;
                    page = _Page.ask;
                  }),
                  child: const Text('修改', style: TextStyle(color: _primary, fontWeight: FontWeight.w500)),
                ),
              ]),
            ),
          ]),
        ],
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
          decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line), boxShadow: _shadowCard),
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
                      color: i < searchStage ? _okSoft : (i == searchStage && !failed ? _primarySoft : _bg2),
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
            decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line), boxShadow: _shadowCard),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Container(height: 16, width: 180, decoration: BoxDecoration(color: _bg2, borderRadius: BorderRadius.circular(6))),
              const SizedBox(height: 12),
              Container(height: 12, decoration: BoxDecoration(color: _bg2, borderRadius: BorderRadius.circular(6))),
              const SizedBox(height: 12),
              Container(height: 12, width: 240, decoration: BoxDecoration(color: _bg2, borderRadius: BorderRadius.circular(6))),
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
            style: const TextStyle(fontSize: 24, height: 32 / 24, fontWeight: FontWeight.w700, letterSpacing: -0.3, color: _ink)),
        const SizedBox(height: 16),
        if (data.primary != null) _productTile(data.primary!, primary: true),
        if (data.alternatives.isNotEmpty) ...[
          const SizedBox(height: 32),
          Text(data.alternatives.length == 1 ? '备选（核实到 1 款）' : '备选', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: _ink)),
          const SizedBox(height: 12),
          for (final item in data.alternatives) Padding(padding: const EdgeInsets.only(bottom: 12), child: _productTile(item, primary: false)),
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
    final idea = textInputs[_ideaKey]?.text.trim() ?? '';
    if (idea.isNotEmpty) bits.add(idea);
    for (final question in shownQuestions.where((item) => item.kind == 'text' || item.kind == 'number')) {
      final written = textInputs[question.id]?.text.trim() ?? '';
      if (written.isNotEmpty) bits.add(question.kind == 'number' ? '预算上限：$written元' : written);
    }
    for (final question in config?.questions ?? <SurveyQuestion>[]) {
      final ids = answers[question.id] ?? [];
      final labels = question.options.where((option) => ids.contains(option.id) && !option.unsure).map((option) => option.label);
      if (labels.isNotEmpty) bits.add(labels.join('、'));
    }
    return bits.isEmpty ? '未补充具体需求' : bits.join('；');
  }

  List<String> _summaryChips() {
    final chips = <String>[];
    final idea = textInputs[_ideaKey]?.text.trim() ?? '';
    if (idea.isNotEmpty) chips.add(idea);
    for (final question in shownQuestions.where((item) => item.kind == 'text' || item.kind == 'number')) {
      final written = textInputs[question.id]?.text.trim() ?? '';
      if (written.isNotEmpty) chips.add(written);
    }
    for (final question in config!.questions.where((item) => item.isChoice)) {
      final ids = answers[question.id] ?? [];
      final labels = question.options.where((option) => ids.contains(option.id) && !option.unsure).map((option) => option.label);
      if (labels.isNotEmpty) chips.add(labels.join('、'));
    }
    if (!chips.any((item) => item.contains('元') || item.contains('预算'))) chips.add('预算未定');
    return chips.take(5).toList();
  }

  void _openDetail(ProductCard item) => setState(() { detail = item; page = _Page.detail; });

  (String, String) _nameParts(String name) {
    final split = name.indexOf(' ');
    if (split <= 0) return ('', name);
    return (name.substring(0, split), name.substring(split + 1));
  }

  Widget _productTile(ProductCard item, {required bool primary}) {
    final configLine = item.facts.where((fact) => fact.status == FactStatus.supported).take(3).map((fact) => fact.display).join(' · ');
    final parts = _nameParts(item.name);
    final body = Padding(
      padding: EdgeInsets.fromLTRB(20, primary ? 16 : 16, 16, 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (primary)
          Container(
            margin: const EdgeInsets.only(bottom: 16),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(color: _primary, borderRadius: BorderRadius.circular(6)),
            child: const Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.check, size: 13, color: Colors.white),
              SizedBox(width: 4),
              Text('首选', style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
            ]),
          ),
        if (parts.$1.isNotEmpty) Text(parts.$1, style: const TextStyle(fontSize: 13, color: _ink3)),
        Text(parts.$2, style: TextStyle(fontSize: primary ? 21 : 17, height: primary ? 28 / 21 : 24 / 17, fontWeight: FontWeight.w700, letterSpacing: -0.2, color: _ink)),
        if (configLine.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: Text(configLine, style: const TextStyle(fontSize: 14, height: 20 / 14, color: _ink2))),
        Padding(
          padding: const EdgeInsets.only(top: 16, bottom: 16),
          child: DecoratedBox(
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: _line))),
            child: Padding(padding: const EdgeInsets.only(bottom: 16), child: _priceLine(item, large: primary)),
          ),
        ),
        if (item.reasons.isNotEmpty) Text(item.reasons.first.text, style: const TextStyle(fontSize: 16, height: 26 / 16, fontWeight: FontWeight.w500, color: _ink)),
        if (primary && item.reasons.isNotEmpty) ...[
          const SizedBox(height: 20),
          const Row(children: [
            Icon(Icons.check, size: 16, color: _ok),
            SizedBox(width: 6),
            Text('符合你的需求', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: _ok)),
          ]),
          const SizedBox(height: 10),
          for (final reason in item.reasons.take(2)) Padding(padding: const EdgeInsets.only(bottom: 8), child: _reasonCard(item, reason, compact: true)),
          const SizedBox(height: 12),
          _button('查看详细理由', false, () => _openDetail(item), icon: Icons.chevron_right),
        ],
      ]),
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: primary ? _primary.withValues(alpha: 0.3) : _line),
        boxShadow: _shadowCard,
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(18),
        child: primary
            ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Container(height: 4, color: _primary),
                body,
              ])
            : Material(
                color: Colors.transparent,
                child: InkWell(onTap: () => _openDetail(item), child: body),
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
          decoration: BoxDecoration(color: _bg2, borderRadius: BorderRadius.circular(6)),
          child: Text(item.price.basisLabel, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: _ink2)),
        ),
      ],
    ]);
  }

  Widget _detail() {
    final item = detail!;
    final parts = _nameParts(item.name);
    final configLine = item.facts.where((fact) => fact.status == FactStatus.supported).take(3).map((fact) => fact.display).join(' · ');
    final primary = result?.primary?.candidateId == item.candidateId;
    return _frame(
      bar: _bar(const Text('推荐依据', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: _ink)), onBack: () => setState(() => page = _Page.result)),
      body: ListView(padding: const EdgeInsets.fromLTRB(20, 8, 20, 32), children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(color: primary ? _primarySoft : _bg2, borderRadius: BorderRadius.circular(6)),
            child: Text(primary ? '首选' : '备选', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: primary ? _primaryInk : _ink2)),
          ),
          if (parts.$1.isNotEmpty) ...[
            const SizedBox(width: 8),
            Text(parts.$1, style: const TextStyle(fontSize: 13, color: _ink3)),
          ],
        ]),
        const SizedBox(height: 8),
        Text(parts.$2, style: const TextStyle(fontSize: 24, height: 32 / 24, fontWeight: FontWeight.w700, letterSpacing: -0.3, color: _ink)),
        if (configLine.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: Text(configLine, style: const TextStyle(fontSize: 15, height: 24 / 15, color: _ink2))),
        const SizedBox(height: 16),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line), boxShadow: _shadowCard),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _priceLine(item, large: true),
            if (!item.price.missing) const Padding(padding: EdgeInsets.only(top: 8), child: Text('价格为参考，不同口径的价格不能直接比较。', style: TextStyle(fontSize: 13, color: _ink3))),
          ]),
        ),
        const SizedBox(height: 20),
        _section('为什么适合你', Icons.check, _ok, [
          for (final reason in item.reasons) Padding(padding: const EdgeInsets.only(bottom: 8), child: _reasonCard(item, reason)),
        ]),
        const SizedBox(height: 16),
        _section('关键参数', Icons.info_outline, _primary, [
          Container(
            margin: const EdgeInsets.only(top: 8),
            decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(14), border: Border.all(color: _line)),
            child: Column(children: [
              for (var i = 0; i < item.facts.length; i++)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(border: i == 0 ? null : const Border(top: BorderSide(color: _line))),
                  child: Row(children: [
                    Expanded(child: Text(_fieldLabel(category?.id, item.facts[i].field), style: const TextStyle(fontSize: 14, color: _ink2))),
                    const SizedBox(width: 12),
                    Flexible(child: Text(item.facts[i].status == FactStatus.conflicting ? '资料存在冲突' : item.facts[i].display, textAlign: TextAlign.right, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: _ink))),
                  ]),
                ),
            ]),
          ),
        ]),
      ]),
    );
  }

  Widget _reasonCard(ProductCard item, Reason reason, {bool compact = false}) {
    final facts = item.facts.where((fact) => reason.factRefs.contains(fact.factId)).map((fact) => fact.display).join('；');
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(color: _surface2, borderRadius: BorderRadius.circular(14), border: Border.all(color: _line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(compact ? reason.text : '你的需求：${_needLine()}', style: const TextStyle(fontSize: 14, height: 22 / 14, fontWeight: FontWeight.w600, color: _ink)),
        const SizedBox(height: 6),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SizedBox(width: 36, child: Text('依据', style: TextStyle(fontSize: 14, height: 22 / 14, color: _ink3))),
          Expanded(child: Text(facts.isEmpty ? '见关键参数' : facts, style: const TextStyle(fontSize: 14, height: 22 / 14, color: _ink2))),
        ]),
        if (!compact) ...[
          const SizedBox(height: 4),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const SizedBox(width: 36, child: Text('影响', style: TextStyle(fontSize: 14, height: 22 / 14, color: _ink3))),
            Expanded(child: Text(reason.text, style: const TextStyle(fontSize: 14, height: 22 / 14, fontWeight: FontWeight.w500, color: _ok))),
          ]),
          if (reason.limitations.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: Text(reason.limitations.join('；'), style: const TextStyle(fontSize: 13, height: 20 / 13, color: _warn))),
        ],
      ]),
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
            Expanded(child: Card(color: i == 0 ? _primarySoft : _surface, elevation: 0, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14), side: const BorderSide(color: _line)), child: Padding(padding: const EdgeInsets.all(8), child: Column(children: [
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
        'release_date': '上市时间', 'os': '操作系统', 'cpu': '处理器', 'processor': '处理器', 'memory': '内存容量', 'storage': '硬盘容量',
        'storage_type': '硬盘类型', 'screen_size': '屏幕尺寸', 'screen_resolution': '屏幕分辨率', 'resolution': '屏幕分辨率',
        'refresh_rate': '屏幕刷新率', 'screen_type': '屏幕类型', 'panel_type': '屏幕类型', 'battery_capacity': '电池容量',
        'charging_power': '充电功率', 'ports': '接口', 'bluetooth': '蓝牙',
        'brightness': '屏幕亮度', 'gpu_type': '显卡类型', 'gpu': '显卡芯片', 'battery': '电池容量', 'battery_life': '续航时间',
        'weight': '重量', 'thickness': '厚度', 'usb': 'USB 接口', 'other_ports': '其它接口', 'wifi': '无线网卡',
        'camera': '摄像头', 'biometrics': '生物识别',
      },
      'phone': {
        'release_date': '发布时间', 'os': '操作系统', 'cpu': '处理器', 'processor': '处理器', 'memory': '运行内存', 'storage': '机身容量',
        'screen_size': '屏幕大小', 'screen_resolution': '屏幕分辨率', 'resolution': '屏幕分辨率', 'refresh_rate': '屏幕刷新率', 'screen_material': '屏幕材质',
        'battery_capacity': '电池容量', 'wired_charging_power': '有线充电', 'wireless_charging_power': '无线充电',
        'pwm': 'PWM 调光频率', 'battery': '电池容量', 'charging': '充电', 'camera_layout': '摄像头组合',
        'rear_camera': '后置主摄', 'zoom': '变焦', 'front_camera': '前置摄像头', 'network': '网络制式',
        'satellite': '卫星通信', 'nfc': 'NFC', 'biometrics': '生物识别', 'durability': '防水防尘',
        'dimensions': '尺寸', 'weight': '重量',
      },
      'tablet': {
        'release_date': '发布时间', 'os': '操作系统', 'cpu': '处理器', 'processor': '处理器', 'memory': '运行内存', 'storage': '存储容量',
        'screen_size': '屏幕尺寸', 'screen_resolution': '分辨率', 'resolution': '分辨率', 'refresh_rate': '屏幕刷新率', 'brightness': '屏幕亮度',
        'panel_type': '屏幕类型', 'battery_capacity': '电池容量', 'charging_power': '充电功率', 'stylus_support': '手写笔',
        'keyboard_support': '键盘', 'rear_camera': '后置摄像头', 'front_camera': '前置摄像头',
        'screen_material': '屏幕材质', 'features': '特性', 'wifi': 'WiFi', 'battery': '电池容量',
        'battery_life': '续航时间', 'ports': '接口', 'speakers': '扬声器', 'dimensions': '尺寸',         'weight': '重量',
      },
      'headphones': {
        'form': '佩戴方式', 'earbud_type': '佩戴方式', 'usage': '主要用途', 'anc': '降噪功能', 'driver': '驱动单元', 'battery_life': '电池续航',
        'bluetooth_version': '蓝牙版本', 'audio_codecs': '音频编码', 'transparency_mode': '通透模式',
        'call_noise_reduction': '通话降噪', 'single_battery_life': '单次续航', 'total_battery_life': '总续航',
        'charging_method': '充电方式', 'ip_rating': '防护等级',
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
            decoration: const BoxDecoration(color: _surface, border: Border(top: BorderSide(color: _line))),
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
          child: onBack == null ? null : IconButton(onPressed: onBack, style: IconButton.styleFrom(hoverColor: const Color(0x0D000000), highlightColor: const Color(0x14000000), shape: const CircleBorder()), icon: const Icon(Icons.arrow_back, color: _ink, size: 22), tooltip: '返回'),
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
      decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line), boxShadow: _shadowCard),
      child: Wrap(spacing: 6, runSpacing: 6, children: [
        for (final label in chips)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(color: _bg2, borderRadius: BorderRadius.circular(20)),
            child: Text(label, style: const TextStyle(fontSize: 13, color: _ink2)),
          ),
      ]),
    );
  }

  Widget _section(String title, IconData icon, Color color, List<Widget> children) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line), boxShadow: _shadowCard),
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
      'headphones' => Icons.headphones_outlined,
      _ => Icons.laptop_mac_outlined,
    };
  }

  Widget _button(String label, bool primary, VoidCallback? onPressed, {IconData? icon}) {
    final enabled = onPressed != null;
    final style = FilledButton.styleFrom(
      backgroundColor: !enabled ? (primary ? _disabledBg : _surface2) : (primary ? _primary : _surface),
      disabledBackgroundColor: primary ? _disabledBg : _surface2,
      foregroundColor: !enabled ? _disabledInk : (primary ? Colors.white : _ink),
      disabledForegroundColor: _disabledInk,
      side: primary ? null : const BorderSide(color: _line),
      elevation: 0,
      shadowColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
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
      decoration: BoxDecoration(color: primary ? _primarySoft : _bg2, borderRadius: BorderRadius.circular(6)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (primary) const Icon(Icons.check, size: 13, color: _primaryInk),
        if (primary) const SizedBox(width: 4),
        Text(text, style: TextStyle(color: primary ? _primaryInk : _ink2, fontSize: 12, fontWeight: FontWeight.w500)),
      ]),
    );
  }

  Widget _option(OptionChoice option, bool selected, bool multiple, VoidCallback onTap) {
    final unsure = option.unsure && !selected;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: selected ? _primarySoft : (unsure ? _surface2 : _surface),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: selected ? _primary : (unsure ? _line2 : _line), style: unsure ? BorderStyle.solid : BorderStyle.solid),
        boxShadow: selected ? const [BoxShadow(color: Color(0x331F2B48), spreadRadius: 0.5)] : _shadowCard,
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 56),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(children: [
                Container(
                  width: 22,
                  height: 22,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: selected ? _primary : _surface,
                    borderRadius: BorderRadius.circular(multiple ? 7 : 11),
                    border: Border.all(color: selected ? _primary : _line2, width: 1.5),
                  ),
                  child: selected
                      ? (multiple
                          ? const Icon(Icons.check, size: 14, color: Colors.white)
                          : Container(width: 8, height: 8, decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle)))
                      : null,
                ),
                const SizedBox(width: 12),
                Expanded(child: Text(option.label, style: TextStyle(fontSize: 16, height: 24 / 16, fontWeight: selected ? FontWeight.w600 : FontWeight.w500, color: selected ? _primaryInk : (unsure ? _ink2 : _ink)))),
                if (selected) const Text('已选', style: TextStyle(color: _primaryInk, fontSize: 12, fontWeight: FontWeight.w500)),
              ]),
            ),
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
