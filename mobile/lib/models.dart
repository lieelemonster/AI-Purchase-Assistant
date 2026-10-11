class CategoryInfo {
  CategoryInfo({required this.id, required this.name});
  final String id;
  final String name;

  factory CategoryInfo.fromJson(Map<String, dynamic> json) {
    return CategoryInfo(id: json['id'] as String, name: json['name'] as String);
  }
}

class OptionChoice {
  OptionChoice({required this.id, required this.label});
  final String id;
  final String label;

  bool get unsure => id == 'not_sure' || id == 'unfamiliar';

  factory OptionChoice.fromJson(Map<String, dynamic> json) {
    return OptionChoice(id: json['id'] as String, label: json['label'] as String);
  }
}

class SurveyQuestion {
  SurveyQuestion({required this.id, required this.label, required this.multiple, required this.options});
  final String id;
  final String label;
  final bool multiple;
  final List<OptionChoice> options;

  factory SurveyQuestion.fromJson(Map<String, dynamic> json) {
    return SurveyQuestion(
      id: json['id'] as String,
      label: json['label'] as String,
      multiple: json['multiple'] as bool,
      options: (json['options'] as List).map((item) => OptionChoice.fromJson(item as Map<String, dynamic>)).toList(),
    );
  }
}

class OptionConfig {
  OptionConfig({required this.categoryId, required this.version, required this.questions});
  final String categoryId;
  final String version;
  final List<SurveyQuestion> questions;

  factory OptionConfig.fromJson(Map<String, dynamic> json) {
    return OptionConfig(
      categoryId: json['category_id'] as String,
      version: json['version'] as String,
      questions: (json['questions'] as List).map((item) => SurveyQuestion.fromJson(item as Map<String, dynamic>)).toList(),
    );
  }
}

enum FactStatus { supported, unknown, conflicting, unavailable }

FactStatus parseStatus(String raw) {
  switch (raw) {
    case 'supported':
      return FactStatus.supported;
    case 'unknown':
      return FactStatus.unknown;
    case 'conflicting':
      return FactStatus.conflicting;
    case 'unavailable':
      return FactStatus.unavailable;
    default:
      throw FormatException('不认识的状态：$raw');
  }
}

class PriceFact {
  PriceFact({required this.status, this.amountMinor, this.minorUnitDigits, this.currency, this.priceBasis, this.evidenceId});
  final FactStatus status;
  final int? amountMinor;
  final int? minorUnitDigits;
  final String? currency;
  final String? priceBasis;
  final String? evidenceId;

  factory PriceFact.fromJson(Map<String, dynamic> json) {
    final amount = json['amount_minor'];
    return PriceFact(
      status: parseStatus(json['status'] as String),
      amountMinor: amount == null ? null : amount as int,
      minorUnitDigits: json['minor_unit_digits'] as int?,
      currency: json['currency'] as String?,
      priceBasis: json['price_basis'] as String?,
      evidenceId: json['evidence_id'] as String?,
    );
  }

  String get label {
    if (status != FactStatus.supported || amountMinor == null) return '暂未查到价格';
    final digits = minorUnitDigits ?? 2;
    final scale = _pow10(digits);
    final whole = amountMinor! ~/ scale;
    final fraction = amountMinor! % scale;
    final body = fraction == 0 ? _group(whole) : '${_group(whole)}.${fraction.toString().padLeft(digits, '0')}';
    final symbol = currency == 'CNY' || currency == null ? '¥' : '$currency ';
    final starting = priceBasis == 'pconline_reference_starting' || priceBasis == 'starting_price' ? '起' : '';
    return '$symbol$body$starting';
  }

  bool get missing => status != FactStatus.supported || amountMinor == null;

  String get basisLabel {
    if (missing) return '';
    if (priceBasis == 'pconline_reference' || priceBasis == 'pconline_reference_starting') {
      return '参考价（行货价格）';
    }
    return '参考价';
  }
}

int _pow10(int digits) {
  var value = 1;
  for (var i = 0; i < digits; i++) {
    value *= 10;
  }
  return value;
}

String _group(int value) {
  final text = value.toString();
  final buffer = StringBuffer();
  for (var i = 0; i < text.length; i++) {
    if (i > 0 && (text.length - i) % 3 == 0) buffer.write(',');
    buffer.write(text[i]);
  }
  return buffer.toString();
}

class VerifiedFact {
  VerifiedFact({required this.factId, required this.field, required this.status, this.value, this.unit, this.excerpt, this.evidenceId});
  final String factId;
  final String field;
  final FactStatus status;
  final String? value;
  final String? unit;
  final String? excerpt;
  final String? evidenceId;

  factory VerifiedFact.fromJson(Map<String, dynamic> json) {
    return VerifiedFact(
      factId: json['fact_id'] as String,
      field: json['field'] as String,
      status: parseStatus(json['status'] as String),
      value: json['value'] as String?,
      unit: json['unit'] as String?,
      excerpt: json['excerpt'] as String?,
      evidenceId: json['evidence_id'] as String?,
    );
  }

  String get display {
    if (status == FactStatus.unknown || value == null || value!.isEmpty) return '暂无核实资料';
    if (unit != null && unit!.isNotEmpty && !value!.contains(unit!)) return '$value$unit';
    return value!;
  }
}

class Reason {
  Reason({required this.needRefs, required this.factRefs, required this.conclusionType, required this.text, required this.limitations});
  final List<String> needRefs;
  final List<String> factRefs;
  final String conclusionType;
  final String text;
  final List<String> limitations;

  bool get isFact => conclusionType == 'fact';

  factory Reason.fromJson(Map<String, dynamic> json) {
    return Reason(
      needRefs: (json['need_refs'] as List).map((item) => item as String).toList(),
      factRefs: (json['fact_refs'] as List?)?.map((item) => item as String).toList() ?? [],
      conclusionType: json['conclusion_type'] as String,
      text: json['text'] as String,
      limitations: (json['limitations'] as List?)?.map((item) => item as String).toList() ?? [],
    );
  }
}

class ProductCard {
  ProductCard({required this.candidateId, required this.name, required this.facts, required this.price, required this.reasons});
  final String candidateId;
  final String name;
  final List<VerifiedFact> facts;
  final PriceFact price;
  final List<Reason> reasons;

  factory ProductCard.fromJson(Map<String, dynamic> json) {
    return ProductCard(
      candidateId: json['candidate_id'] as String,
      name: json['name'] as String,
      facts: (json['facts'] as List?)?.map((item) => VerifiedFact.fromJson(item as Map<String, dynamic>)).toList() ?? [],
      price: PriceFact.fromJson(json['price'] as Map<String, dynamic>),
      reasons: (json['reasons'] as List?)?.map((item) => Reason.fromJson(item as Map<String, dynamic>)).toList() ?? [],
    );
  }
}

class ComparisonEntry {
  ComparisonEntry({required this.candidateId, required this.comparable, this.differenceMinor, this.reason});
  final String candidateId;
  final bool comparable;
  final int? differenceMinor;
  final String? reason;

  factory ComparisonEntry.fromJson(Map<String, dynamic> json) {
    return ComparisonEntry(
      candidateId: json['candidate_id'] as String,
      comparable: json['comparable'] as bool,
      differenceMinor: json['difference_minor_vs_primary'] as int?,
      reason: json['not_comparable_reason'] as String?,
    );
  }
}

class EvidenceSource {
  EvidenceSource({required this.evidenceId, required this.url, required this.fetchedAt, this.title, this.sourceName});
  final String evidenceId;
  final String url;
  final String fetchedAt;
  final String? title;
  final String? sourceName;

  factory EvidenceSource.fromJson(Map<String, dynamic> json) {
    return EvidenceSource(
      evidenceId: json['evidence_id'] as String,
      url: json['url'] as String,
      fetchedAt: json['fetched_at'] as String,
      title: json['title'] as String?,
      sourceName: json['source_name'] as String?,
    );
  }
}

class FollowUpQuestion {
  FollowUpQuestion({required this.text, this.questionId});
  final String text;
  final String? questionId;

  factory FollowUpQuestion.fromJson(Map<String, dynamic> json) {
    return FollowUpQuestion(text: json['text'] as String, questionId: json['question_id'] as String?);
  }
}

class RecommendationResult {
  RecommendationResult({
    required this.requestId,
    required this.status,
    required this.alternatives,
    required this.comparison,
    required this.sources,
    required this.checkedAt,
    this.primary,
    this.followUpQuestions = const [],
  });

  final String requestId;
  final String status;
  final ProductCard? primary;
  final List<ProductCard> alternatives;
  final List<ComparisonEntry> comparison;
  final List<EvidenceSource> sources;
  final String checkedAt;
  final List<FollowUpQuestion> followUpQuestions;

  int get shownCount => (primary == null ? 0 : 1) + alternatives.length;

  factory RecommendationResult.fromJson(Map<String, dynamic> json) {
    final follow = json['follow_up'] as Map<String, dynamic>?;
    return RecommendationResult(
      requestId: json['request_id'] as String,
      status: json['status'] as String,
      primary: json['primary'] == null ? null : ProductCard.fromJson(json['primary'] as Map<String, dynamic>),
      alternatives: (json['alternatives'] as List?)?.map((item) => ProductCard.fromJson(item as Map<String, dynamic>)).toList() ?? [],
      comparison: (json['comparison'] as List?)?.map((item) => ComparisonEntry.fromJson(item as Map<String, dynamic>)).toList() ?? [],
      sources: (json['evidence_sources'] as List?)?.map((item) => EvidenceSource.fromJson(item as Map<String, dynamic>)).toList() ?? [],
      checkedAt: json['checked_at'] as String,
      followUpQuestions: follow == null
          ? []
          : ((follow['questions'] as List?) ?? []).map((item) => FollowUpQuestion.fromJson(item as Map<String, dynamic>)).toList(),
    );
  }
}
