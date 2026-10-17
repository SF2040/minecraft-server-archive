#!/usr/bin/env python3
"""
upload_aip.py - OAIS "Archival Storage" step for the Minecraft Auto-Archiver.
Run it BY HAND after build_aip.py. It never touches the bot.

  1. Error Checking : re-computes every SHA-256 in every AIP and stops if anything differs
  2. Safety check   : refuses to push if the GitHub repo is public (override: --allow-public)
  3. Receive Data   : git add / commit / push to your GitHub repo
  4. Confirmation   : asks GitHub which commit it now holds and compares it with yours,
                      then writes reports/storage_confirmation_<time>.json

Needs Git for Windows (https://git-scm.com) with the repo already cloned. The first push opens a
browser window to sign in to GitHub; after that it remembers you. No tokens in any file.

  python upload_aip.py --repo "C:\\path\\to\\your\\repo"
  python upload_aip.py --repo "..." --verify-only      (just check integrity, no git needed)
  python upload_aip.py --repo "..." --dry-run          (show what would be uploaded)
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LIMIT = 95 * 1024 * 1024


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_aips(repo):
    """Fixity check. Returns (number of AIPs checked, list of problems)."""
    problems, n = [], 0
    root = repo / "aips"
    for aip in sorted(root.glob("*")) if root.exists() else []:
        if not aip.is_dir() or aip.name.endswith(".tmp"):
            continue
        n += 1
        try:
            manifest = json.loads((aip / "aip.json").read_text(encoding="utf-8"))
            fixity = json.loads((aip / "pdi" / "fixity.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            problems.append(f"{aip.name}: cannot read aip.json / fixity.json ({e})")
            continue
        listed = {f["path"] for f in manifest["files"]}
        for f in manifest["files"]:
            p = aip / f["path"]
            if not p.exists():
                problems.append(f"{aip.name}: missing {f['path']}")
            elif sha256_file(p) != f["sha256"]:
                problems.append(f"{aip.name}: CHANGED {f['path']}")
        extra = {p.relative_to(aip).as_posix() for p in aip.rglob("*") if p.is_file()} - listed - {"aip.json"}
        problems += [f"{aip.name}: unlisted file {x}" for x in sorted(extra)]
        zp = aip / fixity["content_file"]
        if zp.exists() and sha256_file(zp) != fixity["sha256"]:
            problems.append(f"{aip.name}: content zip does not match fixity.json")
    return n, problems


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def repo_is_public(url):
    """True = public, False = private/not found, None = could not tell."""
    m = re.search(r"github\.com[:/](?P<o>[^/]+)/(?P<r>[^/]+?)(?:\.git)?/?$", url)
    if not m:
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{m['o']}/{m['r']}",
                                 headers={"User-Agent": "auto-archiver"})
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Verify and upload the archive repo to GitHub.")
    ap.add_argument("--repo", required=True, help="your archive folder (a clone of the GitHub repo)")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-public", action="store_true", help="push even if the GitHub repo is public")
    a = ap.parse_args()
    repo = Path(a.repo)

    # 1. Error checking
    n, problems = verify_aips(repo)
    if problems:
        print(f"INTEGRITY PROBLEMS in {len(problems)} place(s) - nothing was uploaded:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"Integrity check passed: {n} AIP(s), every hash matches.")
    if a.verify_only:
        return 0

    # prerequisites
    if not shutil.which("git"):
        print("Git is not installed (or not on PATH). Install Git for Windows from https://git-scm.com and try again.")
        return 1
    if not (repo / ".git").exists():
        print("This folder is not a git repository. Clone your GitHub repo first (see the setup steps).")
        return 1
    remote = git(repo, "remote", "get-url", "origin", check=False)
    if not remote:
        print("No 'origin' remote. Clone the repo from GitHub instead of creating the folder by hand.")
        return 1

    # 2. Safety
    pub = repo_is_public(remote)
    if pub is True and not a.allow_public:
        print(f"{remote} is PUBLIC. These worlds contain player data and unclear rights - make the repo private "
              "(GitHub > repo > Settings > Danger Zone > Change visibility) or re-run with --allow-public.")
        return 1
    if pub is None:
        print("Warning: could not check whether the repo is private (offline, or GitHub limit). Continuing.")

    big = [p for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts and p.stat().st_size > LIMIT]
    if big:
        print("Files over GitHub's 100 MB limit:", *[str(b) for b in big], sep="\n  ")
        return 1

    # what would change
    # (a leftover storage_confirmation file alone is not a reason to push)
    changed = [ln for ln in git(repo, "status", "--porcelain", "-uall").splitlines()
               if "reports/storage_confirmation_" not in ln]
    if not changed:
        print("Nothing new to upload.")
        return 0
    if a.dry_run:
        pending = sorted({m[1] for ln in changed if (m := re.search(r"aips/([^/]+)/", ln))})
        print(f"Would upload {len(pending)} AIP(s) and {len(changed)} changed file(s):")
        print(*[f"  {x}" for x in pending], sep="\n")
        return 0

    # 3. Receive data: commit + push
    git(repo, "add", "-A")
    ids = sorted({m[1] for m in re.finditer(r"^aips/([^/]+)/", git(repo, "diff", "--cached", "--name-only"), re.M)})
    msg = (f"Ingest {len(ids)} AIP(s)\n\n" + "\n".join(ids)) if ids else "Update catalogue and reports"
    try:
        git(repo, "commit", "-m", msg)
        branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        git(repo, "push", "-u", "origin", "HEAD")
    except RuntimeError as e:
        print(e)
        print("\nIf this mentions 'user.name' or 'user.email', run:\n  git config --global user.name \"Your Name\"\n"
              "  git config --global user.email \"you@example.com\"\nIf it mentions authentication, sign in when the browser opens.")
        return 1

    # 4. Storage confirmation: ask the remote what it holds
    local = git(repo, "rev-parse", "HEAD")
    remote_line = git(repo, "ls-remote", "origin", f"refs/heads/{branch}")
    remote_sha = remote_line.split()[0] if remote_line else ""
    ok = remote_sha == local
    conf = {"verified": ok, "when_utc": datetime.now(timezone.utc).isoformat(), "remote": remote,
            "branch": branch, "commit": local, "remote_commit": remote_sha, "aips": ids}
    out = repo / "reports" / f"storage_confirmation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")
    if ok:
        print(f"Stored and confirmed: commit {local[:10]} is on GitHub ({len(ids)} AIP(s)).")
        print(f"Confirmation saved to {out.relative_to(repo)} (it is uploaded with your next batch).")
        return 0
    print("WARNING: GitHub does not report the commit you just pushed. Do not delete anything; try again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
