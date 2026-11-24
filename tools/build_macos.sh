#!/bin/bash
# 建置 macOS 版：dist-mac/資料助秘NotebookLM MCP簡報.app 與 dist-mac/ZMSNotebookLM-<版本>-mac.dmg
# 用法（在 Mac 上）：bash tools/build_macos.sh
# 需要：.venv（Python＋flet 1.1.2…）、packaging/mariadb-mac（從其他資料助秘專案複製）、Node.js 22（nvm）
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=/usr/local/bin:/opt/homebrew/bin:$PATH
PY=.venv/bin/python
VER=$($PY -c "import nb; print(nb.APP_VERSION)")
NAME="資料助秘NotebookLM MCP簡報"
BUNDLE_ID="com.achir.zmsnotebooklm"
echo "== 版本 $VER"

[ -x packaging/mariadb-mac/bin/mariadbd ] || { echo "缺少 packaging/mariadb-mac"; exit 1; }

# ---------------------------------------------------------------- NotebookLM MCP 伺服器（Node.js）
NODE_DIR=$(ls -d "$HOME"/.nvm/versions/node/v22* 2>/dev/null | sort -V | tail -1)
[ -x "$NODE_DIR/bin/node" ] || { echo "找不到 Node.js 22（~/.nvm/versions/node/v22*）"; exit 1; }
export PATH="$NODE_DIR/bin:$PATH"
echo "== NotebookLM MCP（node $(node -v)）"
( cd vendor/notebooklm-mcp && { [ -d node_modules ] || npm ci --no-audit --no-fund; } && npx tsc )
rm -rf packaging/mcp-mac && mkdir -p packaging/mcp-mac
cp vendor/notebooklm-mcp/{package.json,package-lock.json,LICENSE,README.md} packaging/mcp-mac/
rsync -a --exclude '*.map' --exclude '*.d.ts' vendor/notebooklm-mcp/dist/ packaging/mcp-mac/dist/
( cd packaging/mcp-mac && npm ci --omit=dev --ignore-scripts --no-audit --no-fund )

rm -rf build-mac dist-mac build
mkdir -p build-mac dist-mac

# 圖示 PNG → icns
SET=build-mac/icon.iconset; mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s assets/icon.png --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) assets/icon.png --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o build-mac/icon.icns

echo "== flet pack"
.venv/bin/flet pack main.py -y -n ZMSNotebookLM -i build-mac/icon.icns --distpath dist-mac \
  --add-data assets:assets --add-data nb/samples:nb/samples \
  --hidden-import edge_tts --hidden-import pymysql --hidden-import certifi --hidden-import qrcode \
  --hidden-import pptx --hidden-import docx \
  --pyinstaller-build-args=--collect-all=pptx --pyinstaller-build-args=--collect-all=docx \
  --pyinstaller-build-args=--collect-all=flet_web --pyinstaller-build-args=--collect-all=flet_audio \
  --pyinstaller-build-args=--collect-submodules=uvicorn \
  --product-name "$NAME" --product-version "$VER" --bundle-id "$BUNDLE_ID" --copyright "© 2026 吳玉柱"

APP=dist-mac/ZMSNotebookLM.app
[ -d "$APP" ] || { echo "找不到 $APP"; ls dist-mac; exit 1; }

echo "== 內附 MariaDB、Node.js、NotebookLM MCP"
cp -R packaging/mariadb-mac "$APP/Contents/Resources/mariadb"
mkdir -p "$APP/Contents/Resources/node/bin" "$APP/Contents/Resources/vendor"
cp "$NODE_DIR/bin/node" "$APP/Contents/Resources/node/bin/node"
cp -R packaging/mcp-mac "$APP/Contents/Resources/vendor/notebooklm-mcp"

PL="$APP/Contents/Info.plist"
pb() { /usr/libexec/PlistBuddy -c "$1" "$PL" 2>/dev/null || true; }
pb "Delete :CFBundleDisplayName"; pb "Add :CFBundleDisplayName string $NAME"
pb "Set :CFBundleName $NAME"
pb "Set :CFBundleShortVersionString $VER"; pb "Set :CFBundleVersion $VER"
pb "Delete :LSMinimumSystemVersion"; pb "Add :LSMinimumSystemVersion string 11.0"
pb "Delete :LSApplicationCategoryType"; pb "Add :LSApplicationCategoryType string public.app-category.education"
pb "Delete :NSHumanReadableCopyright"; pb "Add :NSHumanReadableCopyright string 系統開發：吳玉柱 先生 與 Claude AI Opus 5.5"
pb "Delete :NSLocalNetworkUsageDescription"
pb "Add :NSLocalNetworkUsageDescription string 連到公司的 MariaDB 資料庫"
pb "Delete :NSAppleEventsUsageDescription"
pb "Add :NSAppleEventsUsageDescription string 開啟 Google Chrome 讀取 NotebookLM 筆記本"

FINAL="dist-mac/$NAME.app"
rm -rf "$FINAL"; mv "$APP" "$FINAL"
SIGN_KC="$HOME/Library/Keychains/zms-signing.keychain-db"
if [ -f "$SIGN_KC" ] && [ -f "$HOME/Developer/zms-signing/kc.pass" ]; then
  security unlock-keychain -p "$(cat "$HOME/Developer/zms-signing/kc.pass")" "$SIGN_KC"
fi
IDENT=$(security find-identity -v -p codesigning | grep -o '"Developer ID Application: [^"]*"' | head -1 | tr -d '"' || true)
ENT=packaging/mac-entitlements.plist
if [ -n "$IDENT" ]; then
  echo "== 簽章（${IDENT}）"
  find "$FINAL/Contents/Resources" -type f \( -name "*.dylib" -o -name "*.so" -o -name "*.node" \) -print0 |
    xargs -0 -I{} codesign --force --timestamp --options runtime -s "$IDENT" "{}"
  find "$FINAL/Contents/Resources" -type f -perm +111 ! -name "*.dylib" ! -name "*.so" -print0 |
    while IFS= read -r -d '' f; do
      if file -b "$f" | grep -q Mach-O; then codesign --force --timestamp --options runtime -s "$IDENT" "$f"; fi
    done
  # Node.js 的 V8 需要 JIT：要帶 entitlements（allow-jit、unsigned-executable-memory）
  codesign --force --timestamp --options runtime --entitlements "$ENT" -s "$IDENT" \
    "$FINAL/Contents/Resources/node/bin/node"
  codesign --force --timestamp --options runtime --entitlements "$ENT" -s "$IDENT" "$FINAL/Contents/MacOS/ZMSNotebookLM"
  codesign --force --timestamp --options runtime --entitlements "$ENT" -s "$IDENT" "$FINAL"
else
  echo "== 簽章（ad-hoc；找不到 Developer ID 憑證）"
  codesign --force --deep -s - "$FINAL"
fi
codesign --verify --deep --strict "$FINAL" && echo "簽章 OK"

NOTARY="${NOTARY_PROFILE:-zms-notary}"
notarize() {
  xcrun notarytool submit "$1" --keychain-profile "$NOTARY" --wait --timeout 60m | tee build-mac/notary.txt
  grep -q "status: Accepted" build-mac/notary.txt || {
    ID=$(grep -m1 "  id:" build-mac/notary.txt | awk '{print $2}')
    [ -n "$ID" ] && xcrun notarytool log "$ID" --keychain-profile "$NOTARY" || true
    echo "公證失敗"; exit 1; }
}
CAN_NOTARIZE=""
if [ -n "$IDENT" ] && xcrun notarytool history --keychain-profile "$NOTARY" >/dev/null 2>&1; then CAN_NOTARIZE=1; fi
if [ -n "$CAN_NOTARIZE" ]; then
  echo "== 公證 App"
  ditto -c -k --keepParent "$FINAL" build-mac/app.zip
  notarize build-mac/app.zip
  xcrun stapler staple "$FINAL"
elif [ -n "$IDENT" ]; then
  echo "== 略過公證（沒有 notarytool 設定檔 ${NOTARY}）"
fi

echo "== DMG"
STAGE=build-mac/dmg; rm -rf "$STAGE"; mkdir -p "$STAGE"
ditto "$FINAL" "$STAGE/$NAME.app"
ln -s /Applications "$STAGE/應用程式"
SIZE_MB=$(( $(du -sm "$STAGE" | cut -f1) + 60 ))
DMG="dist-mac/ZMSNotebookLM-$VER-mac.dmg"
rm -f "$DMG"
for i in 1 2 3; do
  hdiutil create -volname "$NAME $VER" -srcfolder "$STAGE" -ov -format UDZO -size ${SIZE_MB}m "$DMG" && break
  echo "hdiutil 重試 $i"; sleep 5
done
if [ -n "$IDENT" ]; then codesign --force --timestamp -s "$IDENT" "$DMG"; fi
if [ -n "$CAN_NOTARIZE" ]; then
  echo "== 公證 DMG"
  notarize "$DMG"
  xcrun stapler staple "$DMG"
  spctl -a -vv -t install "$DMG" 2>&1 | head -3
  spctl -a -vv "$FINAL" 2>&1 | head -3
fi
shasum -a 256 "$DMG"
du -h "$DMG"
echo "BUILD_DONE"
