"""
sync_secrets.py
---------------
Push the local .env into the Modal secret `internship-secrets`, then verify the
result actually works.

Usage:
    python sync_secrets.py            # preview, confirm, sync, verify
    python sync_secrets.py --check    # preview + verify only, write nothing
    python sync_secrets.py --yes      # skip the confirmation prompt

Why this is more careful than a one-liner:

  * **Profile is pinned.** Two Modal workspaces exist on this account —
    `dakshinjain187` (production) and `fireinthebellyftb` (a duplicate). Writing
    the secret to the wrong one fails silently: the deploy "succeeds" and the
    real cron keeps using the old value. MODAL_PROFILE is set before modal is
    imported, since the client resolves its profile at import time.

  * **Values never touch the command line.** The previous version shelled out to
    `modal secret create ... KEY=value`, which puts every credential into the
    process list and shell history. `Secret.create_deployed` sends them over the
    API instead.

  * **It verifies.** On 2026-08-23 the Modal secret and the local .env held
    DIFFERENT Apify tokens for different accounts, and the nightly cron had been
    scraping nothing against an over-limit account while local runs worked fine.
    Nothing surfaced that — the digest just got thin. So after writing, this runs
    a container against the deployed secret and reports which Apify account it
    actually resolves to and how much budget is left.

Modal secrets are replace-all: there is no partial update, and existing values
cannot be read back. So .env must be COMPLETE, not just the key you're rotating.
"""

import os
import sys

# Must precede `import modal` — the client resolves its profile at import time.
MODAL_PROFILE = os.environ.setdefault("MODAL_PROFILE", "dakshinjain187")

import modal  # noqa: E402
from dotenv import dotenv_values  # noqa: E402

SECRET_NAME = "internship-secrets"
ENV_PATH = ".env"

# Keys the pipeline cannot run without. A .env missing one of these means a
# partial sync that would break the cron, so refuse rather than half-write.
REQUIRED_KEYS = ("APIFY_API_TOKEN", "GOOGLE_SHEET_ID")


def _fingerprint(value: str) -> str:
    """Stable short hash — lets you compare two secrets without printing either."""
    import hashlib
    return hashlib.sha256((value or "").encode()).hexdigest()[:12]


def load_env() -> dict:
    if not os.path.exists(ENV_PATH):
        sys.exit(f"[FAIL] {ENV_PATH} not found (run from the repo root).")
    values = {k: v for k, v in dotenv_values(ENV_PATH).items() if v}
    if not values:
        sys.exit(f"[FAIL] {ENV_PATH} parsed to zero usable values.")
    missing = [k for k in REQUIRED_KEYS if k not in values]
    if missing:
        sys.exit(f"[FAIL] {ENV_PATH} is missing {', '.join(missing)}. "
                 "Modal secrets are replace-all, so a partial sync would break "
                 "the cron. Fill these in and re-run.")
    return values


def preview(values: dict) -> None:
    print(f"\nWorkspace : {MODAL_PROFILE}")
    print(f"Secret    : {SECRET_NAME}")
    print(f"Source    : {ENV_PATH} ({len(values)} keys)\n")
    print(f"  {'KEY':34} {'FINGERPRINT':14} LENGTH")
    print(f"  {'-' * 34} {'-' * 14} ------")
    for k in sorted(values):
        # Names and fingerprints only — never the values themselves.
        print(f"  {k:34} {_fingerprint(values[k]):14} {len(values[k])}")


def push(values: dict) -> None:
    print(f"\nPushing {len(values)} keys to '{SECRET_NAME}' in {MODAL_PROFILE}...")
    modal.Secret.create_deployed(SECRET_NAME, values, overwrite=True)
    print("[OK] Secret written.")


# ── Verification ─────────────────────────────────────────────────────────────
# Runs INSIDE Modal against the deployed secret, so it proves what the cron will
# actually see rather than what we hoped we wrote.
_verify_app = modal.App("sync-secrets-verify")
# Modal imports THIS module inside the container to find the function below, so
# the image needs every top-level import here — python-dotenv included, even
# though the remote side never reads .env. (The alternative, serialized=True,
# couples the image's Python version to whatever the operator happens to run
# locally and fails with a version-mismatch error; this doesn't.)
_verify_image = (modal.Image.debian_slim(python_version="3.11")
                 .pip_install("requests", "python-dotenv"))


@_verify_app.function(image=_verify_image,
                      secrets=[modal.Secret.from_name(SECRET_NAME)])
def _verify_remote():
    import os as _os
    import hashlib
    import requests

    # Which keys does the deployed secret actually carry? Modal injects them as
    # env vars, so subtract the container's own baseline to isolate ours. This
    # is what makes the replace-all safe: anything here but missing from .env
    # would be destroyed by a sync.
    _BASELINE = {
        "PATH", "HOSTNAME", "HOME", "LANG", "PWD", "SHLVL", "TERM", "TZ", "USER",
        "PYTHONPATH", "PYTHONUNBUFFERED", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE",
        "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256", "PYTHON_PIP_VERSION",
        "PYTHON_GET_PIP_URL", "PYTHON_GET_PIP_SHA256", "PYTHON_SETUPTOOLS_VERSION",
        "LC_ALL", "LC_CTYPE", "DEBIAN_FRONTEND", "SSL_CERT_FILE", "SSL_CERT_DIR",
    }
    # Modal also injects build/runtime tuning vars that are NOT secret keys
    # (PIP_*, UV_*, *_NUM_THREADS, CFLAGS...). Without these prefix rules the
    # check reports a dozen false positives and stops being worth reading.
    _BASELINE |= {"CFLAGS", "CXXFLAGS", "LDFLAGS", "SOURCE_DATE_EPOCH",
                  "MAKEFLAGS", "NPY_NUM_BUILD_JOBS"}
    _PREFIXES = ("MODAL_", "PIP_", "UV_", "ORT_", "OMP_", "MKL_", "BLIS_",
                 "OPENBLAS_", "NUMEXPR_", "VECLIB_", "AWS_EXECUTION_")

    def _is_secret_key(k):
        if k.upper() != k or k in _BASELINE:
            return False
        if k.startswith(_PREFIXES) or k.endswith("_NUM_THREADS"):
            return False
        return True

    out = {"secret_keys": sorted(k for k in _os.environ if _is_secret_key(k))}
    token = _os.getenv("APIFY_API_TOKEN", "")
    out["apify_fingerprint"] = hashlib.sha256(token.encode()).hexdigest()[:12]
    out["sheet_id_set"] = bool(_os.getenv("GOOGLE_SHEET_ID"))
    out["resend_set"] = bool(_os.getenv("RESEND_API_KEY"))

    if not token:
        out["error"] = "APIFY_API_TOKEN missing inside the secret"
        return out
    try:
        h = {"Authorization": "Bearer " + token}
        u = requests.get("https://api.apify.com/v2/users/me",
                         headers=h, timeout=30).json()["data"]
        d = requests.get("https://api.apify.com/v2/users/me/limits",
                         headers=h, timeout=30).json()["data"]
        used = float(d["current"]["monthlyUsageUsd"])
        cap = float(d["limits"]["maxMonthlyUsageUsd"] or 0)
        out.update(account=u.get("username"),
                   plan=(u.get("plan") or {}).get("id"),
                   used=used, cap=cap, remaining=cap - used,
                   cycle_ends=d["monthlyUsageCycle"]["endAt"])
    except Exception as e:
        out["error"] = f"Apify check failed: {e}"
    return out


def verify(local_values: dict) -> int:
    """Report what the cron will actually resolve. Returns a process exit code."""
    print("\nVerifying against the deployed secret (starting a container)...")
    try:
        with _verify_app.run():
            r = _verify_remote.remote()
    except Exception as e:
        print(f"\n[FAIL] Could not verify remotely: {type(e).__name__}: {e}")
        print("       The secret may still have been written — re-run with "
              "--check once Modal is reachable.")
        return 1

    print(f"\n  Apify token in Modal : {r['apify_fingerprint']}")
    local_fp = _fingerprint(local_values.get("APIFY_API_TOKEN", ""))
    print(f"  Apify token in .env  : {local_fp}")
    if r["apify_fingerprint"] != local_fp:
        print("  [WARN] Modal and .env hold DIFFERENT Apify tokens — this is the "
              "exact failure mode that silently emptied the nightly run.")

    print(f"  GOOGLE_SHEET_ID set  : {r['sheet_id_set']}")
    print(f"  RESEND_API_KEY set   : {r['resend_set']}")

    # A sync REPLACES the secret wholesale, so surface anything that would be
    # dropped. Best-effort (the container baseline is filtered heuristically),
    # which is why this warns rather than blocks.
    orphaned = [k for k in r.get("secret_keys", []) if k not in local_values]
    if orphaned:
        print(f"\n  [WARN] {len(orphaned)} key(s) live in Modal but NOT in .env:")
        for k in orphaned:
            print(f"           {k}")
        print("         A sync REPLACES the whole secret, so these would be "
              "lost.\n         Add them to .env first, or accept the loss "
              "deliberately.")

    if "error" in r:
        print(f"\n[FAIL] {r['error']}")
        return 1

    print(f"\n  Apify account : {r['account']} ({r['plan']})")
    print(f"  Budget        : ${r['used']:.2f} / ${r['cap']:.2f} "
          f"-> ${r['remaining']:.2f} left")
    print(f"  Cycle ends    : {r['cycle_ends']}")

    # ~$1.27 per full pipeline run, measured 2026-08-23.
    runs = int(r["remaining"] / 1.27) if r["remaining"] > 0 else 0
    if r["remaining"] <= 0:
        print("\n[FAIL] This account is OVER its cap — the nightly run will "
              "publish nothing until the cycle resets or you supply a new key.")
        return 1
    print(f"\n[OK] Roughly {runs} more full run(s) affordable "
          f"(~$1.27 each) before the cap.")
    if runs <= 1:
        print("[WARN] That is one night or less. Rotate the key soon.")
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    check_only = "--check" in args
    assume_yes = "--yes" in args or "-y" in args

    values = load_env()
    preview(values)

    if check_only:
        print("\n--check: nothing written.")
        return verify(values)

    if not assume_yes:
        print(f"\nThis REPLACES all keys in '{SECRET_NAME}' ({MODAL_PROFILE}).")
        if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted; nothing written.")
            return 1

    push(values)
    code = verify(values)
    if code == 0:
        print("\nNext: MODAL_PROFILE=dakshinjain187 modal deploy modal_app.py")
        print("(Modal snapshots secret values at container start, so a running "
              "app keeps the OLD values until it is redeployed.)")
    return code


if __name__ == "__main__":
    sys.exit(main())
