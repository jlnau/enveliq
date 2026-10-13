"""Copy the pictures taken by scripts/retake_pictures.mjs into place.
Usage: python scripts/place_pictures.py <folder given to retake_pictures.mjs>
- docs/images/NAME.png (dark) and docs/images/NAME-light.png: used by the README (GitHub) and the guides.
- website/src/images/NAME.webp (dark) and NAME-light.webp: used by the front page and the tour.
The website build shows the dark or the light one to match the visitor's choice."""
import sys, os
from PIL import Image
src = sys.argv[1]
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = {  # docs picture -> taken picture
 "backup": "backup", "backup-phone": "backup-phone", "export-my-data": "export",
 "check-address": "check-address", "check-address-phone": "check-address-phone",
 "home": "ship-home", "shipping": "ship-page",
 "link-check": "links-careful", "link-check-phone": "links-phone",
 "scam-warning": "scam-list", "scam-warning-phone": "scam-phone",
 "search": "search-everywhere", "search-phone": "search-phone",
 "sender-check": "sender-not-confirmed", "sender-check-phone": "sender-phone",
 "snooze": "snooze-menu", "snooze-list": "snooze-list", "snooze-phone": "snooze-phone",
 "subscriptions": "sub-page", "subscriptions-home": "sub-home", "subscriptions-phone": "sub-page-phone",
 "trips": "trip-page", "trips-home": "trip-home", "trips-phone": "trip-page-phone",
 "writing-help": "writehelp-reply",
}
SITE = {  # website picture -> taken picture
 "check-address": "check-address", "link-check": "links-careful", "sender-check": "sender-not-confirmed",
 "scam-warning": "scam-list", "scam-warning-phone": "scam-phone", "shipping": "ship-page", "shipping-home": "ship-home",
 "snooze": "snooze-menu", "subscriptions": "sub-page", "subscriptions-home": "sub-home", "trips": "trip-page",
 "trips-home": "trip-home", "writing-help": "writehelp-reply", "search": "search-everywhere", "phone": "ship-home-phone",
 "tour-new-email": "nm-suggest", "tour-viewer": "unsub-viewer",
}
for theme in ("dark", "light"):
    suffix = "" if theme == "dark" else "-light"
    for name, shot in DOCS.items():
        Image.open(os.path.join(src, theme, shot + ".png")).convert("RGB").save(os.path.join(root, "docs/images", name + suffix + ".png"), optimize=True)
    for name, shot in SITE.items():
        Image.open(os.path.join(src, theme, shot + ".png")).convert("RGB").save(os.path.join(root, "website/src/images", name + suffix + ".webp"), quality=84, method=6)
print("placed", len(DOCS) * 2, "guide pictures and", len(SITE) * 2, "website pictures")
