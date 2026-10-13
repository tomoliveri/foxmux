# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Download a version addons.mozilla.org has already signed.

Usage: python3 scripts/amo_download.py <version> <output.xpi>

The release workflow uses this when signing reports that the version already
exists, which happens when an earlier run got the file signed but failed
before publishing it. Credentials come from AMO_JWT_ISSUER and AMO_JWT_SECRET.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.request
import zipfile

ADDON = "foxmux@foxmux"
API = "https://addons.mozilla.org/api/v5"


def jwt():
    """A short-lived token, as AMO's API expects (HS256, at most 5 minutes)."""

    def b64(data):
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    now = int(time.time())
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(
        json.dumps(
            {
                "iss": os.environ["AMO_JWT_ISSUER"],
                "jti": secrets.token_hex(16),
                "iat": now,
                "exp": now + 60,
            }
        ).encode()
    )
    signature = hmac.new(
        os.environ["AMO_JWT_SECRET"].encode(),
        f"{header}.{payload}".encode(),
        hashlib.sha256,
    ).digest()
    return f"{header}.{payload}.{b64(signature)}"


def fetch(url):
    request = urllib.request.Request(  # noqa: S310 - https only
        url, headers={"Authorization": f"JWT {jwt()}", "User-Agent": "foxmux"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return response.read()


def main(version, output):
    # A "v" prefix makes AMO look the version up by number rather than id.
    detail = json.loads(fetch(f"{API}/addons/addon/{ADDON}/versions/v{version}/"))
    if detail.get("version") != version:
        sys.exit(f"amo_download.py: AMO returned version {detail.get('version')!r}")
    data = fetch(detail["file"]["url"])
    with open(output, "wb") as file:
        file.write(data)

    with zipfile.ZipFile(output) as xpi:
        manifest = json.loads(xpi.read("manifest.json"))
        signed = any(name.startswith("META-INF/") for name in xpi.namelist())
    if manifest.get("version") != version or not signed:
        os.remove(output)
        sys.exit(f"amo_download.py: {output} is not a signed {version}")
    print(output)


if __name__ == "__main__":
    main(*sys.argv[1:])
