import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'models.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.timeout = false});
  final String message;
  final bool timeout;
}

abstract class BuyApi {
  Future<bool> health();
  Future<List<CategoryInfo>> categories();
  Future<OptionConfig> options(String categoryId);
  Future<RecommendationResult> recommend({
    required String requestId,
    required String inputVersion,
    required String categoryId,
    required List<Map<String, dynamic>> optionAnswers,
    required String freeText,
    required int followUpRound,
  });
}

String defaultBaseUrl() {
  const defined = String.fromEnvironment('API_BASE');
  if (defined.isNotEmpty) return defined;
  if (Platform.isAndroid) return 'http://10.0.2.2:8000';
  return 'http://127.0.0.1:8000';
}

class HttpBuyApi implements BuyApi {
  HttpBuyApi({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ?? defaultBaseUrl();

  final http.Client _client;
  final String baseUrl;

  Future<http.Response> _get(String path) async {
    try {
      return await _client.get(Uri.parse('$baseUrl$path')).timeout(const Duration(seconds: 8));
    } on Exception {
      throw ApiException('网络连接失败');
    }
  }

  @override
  Future<bool> health() async {
    final response = await _get('/health');
    return response.statusCode == 200;
  }

  @override
  Future<List<CategoryInfo>> categories() async {
    final response = await _get('/v1/categories');
    if (response.statusCode != 200) throw ApiException('无法读取品类');
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return (body['categories'] as List).map((item) => CategoryInfo.fromJson(item as Map<String, dynamic>)).toList();
  }

  @override
  Future<OptionConfig> options(String categoryId) async {
    final response = await _get('/v1/options?category_id=$categoryId');
    if (response.statusCode != 200) throw ApiException('无法读取问题');
    return OptionConfig.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
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
    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/recommendations'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'request_id': requestId,
              'input_version': inputVersion,
              'category_id': categoryId,
              'option_answers': optionAnswers,
              'free_text': freeText,
              'follow_up_round': followUpRound,
            }),
          )
          .timeout(const Duration(seconds: 130));
      if (response.statusCode != 200) throw ApiException('推荐失败');
      return RecommendationResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw ApiException('查询时间比预期长', timeout: true);
    } on Exception {
      throw ApiException('网络连接失败');
    }
  }
}
