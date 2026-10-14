#!/usr/bin/env bash
# Build iOS Release (.app / unsigned .ipa) pointing at the Aliyun API.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$(cd "$ROOT/.." && pwd)/outputs"
API_BASE="${API_BASE:-http://47.111.129.166/buy-api}"
XCODE_APP="${XCODE_APP:-/Users/a1-6/Downloads/Xcode.app}"

if [[ -d "$XCODE_APP/Contents/Developer" ]]; then
  export DEVELOPER_DIR="$XCODE_APP/Contents/Developer"
  export PATH="$DEVELOPER_DIR/usr/bin:$PATH"
fi

cd "$ROOT"
flutter build ios --release --no-codesign --dart-define="API_BASE=$API_BASE"

APP="$ROOT/build/ios/iphoneos/Runner.app"
mkdir -p "$OUT_DIR"
rm -rf /tmp/Payload
mkdir -p /tmp/Payload
cp -R "$APP" /tmp/Payload/Runner.app
IPA="$OUT_DIR/购买选择助手-unsigned.ipa"
rm -f "$IPA"
(cd /tmp && zip -qry "$IPA" Payload)

echo "APP: $APP"
echo "IPA: $IPA"
echo "Install on a real iPhone: open ios/Runner.xcworkspace in Xcode → Signing & Capabilities → select Team → Product → Archive."
