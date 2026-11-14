"""The version shown in reports and the status page. Keep it in step with the README."""
VERSION = "0.104"


import os as _os
import re as _re

# Preview images are built with a build number (the number of the "Build UI Preview" run) so a tester can tell which build is running.
# A release image has none and shows only VERSION. Anything that is not a short plain number is ignored.
def clean_build(raw: object) -> str:
    text = str(raw or "").strip()
    return text if _re.fullmatch(r"[0-9]{1,9}", text) else ""


BUILD = clean_build(_os.environ.get("ENVELIQ_BUILD", ""))
