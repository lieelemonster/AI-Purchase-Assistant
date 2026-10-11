import 'package:flutter/material.dart';

import 'api.dart';
import 'flow.dart';

void main() {
  runApp(BuyFlow(api: HttpBuyApi()));
}
