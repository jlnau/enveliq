#!/usr/bin/env bash
# Makes the key that signs the Enveliq Android app, once.
#
#   bash android/make-signing-key.sh
#
# It needs "keytool" (it comes with Java) and "openssl". It writes enveliq-release.jks next to where you run it and prints
# the four values to add in GitHub (Settings, Secrets and variables, Actions, New repository secret), or the ready-made
# "gh secret set" lines.
#
# KEEP enveliq-release.jks AND THE PASSWORD SOMEWHERE SAFE (a password manager). If the key is lost, every phone has to
# uninstall the app before a new version can be installed. Never put the file in the repository.
set -euo pipefail

OUT="${1:-enveliq-release.jks}"
ALIAS="enveliq"
command -v keytool >/dev/null || { echo "keytool was not found. Install Java (a JDK) first."; exit 1; }
command -v openssl >/dev/null || { echo "openssl was not found."; exit 1; }
[ -e "$OUT" ] && { echo "$OUT already exists. Move it away first, so a key is never overwritten."; exit 1; }

PASS="$(openssl rand -base64 24 | tr -d '/+=\n' | cut -c1-24)"
keytool -genkeypair -keystore "$OUT" -storetype PKCS12 -alias "$ALIAS" -keyalg RSA -keysize 4096 -validity 36500 \
  -storepass "$PASS" -keypass "$PASS" -dname "CN=Enveliq, O=Enveliq" >/dev/null

B64="$(base64 < "$OUT" | tr -d '\n')"
echo
echo "Made $OUT. Keep it, and this password, safe:  $PASS"
echo
echo "Add these four repository secrets in GitHub:"
echo "  ANDROID_KEYSTORE_BASE64    = (the long text below)"
echo "  ANDROID_KEYSTORE_PASSWORD  = $PASS"
echo "  ANDROID_KEY_ALIAS          = $ALIAS"
echo "  ANDROID_KEY_PASSWORD       = $PASS"
echo
echo "Or, with the GitHub command line tool (gh) signed in:"
echo "  base64 < $OUT | tr -d '\\n' | gh secret set ANDROID_KEYSTORE_BASE64"
echo "  gh secret set ANDROID_KEYSTORE_PASSWORD --body '$PASS'"
echo "  gh secret set ANDROID_KEY_ALIAS --body '$ALIAS'"
echo "  gh secret set ANDROID_KEY_PASSWORD --body '$PASS'"
echo
echo "ANDROID_KEYSTORE_BASE64:"
echo "$B64"
