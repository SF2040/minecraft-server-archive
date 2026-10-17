#!/usr/bin/env python3
"""
build_aip.py - OAIS "Ingest" step for the Minecraft Auto-Archiver.
Run it BY HAND after an archival session. It never touches the bot.

It reads three things the pipeline already produces:
  * the saves folder       (the SIP: one world per <ip>_<port>)
  * Minecraft's logs       (latest.log + dated .log.gz)
  * archival_log.txt       (written by your Python script)
and turns every world into an Archival Information Package (AIP):

  <repo>/aips/<ip>_<port>_<timestamp>/
      content/<ip>_<port>.zip        Content Information  (the world)
      pdi/reference.json             PDI - Reference
      pdi/provenance.json            PDI - Provenance
      pdi/context.json               PDI - Context
      pdi/fixity.json                PDI - Fixity (SHA-256 of the zip and of every file inside)
      pdi/access_rights.json         PDI - Access Rights
      pdi/session_log_excerpt.txt    the Minecraft log lines for that server visit
      aip.json                       Packaging Information (every file above + its hash)
  <repo>/catalogue.csv               Descriptive Information (one row per AIP)
  <repo>/reports/ingest_<time>.json  receipt + QA results for this run

Only the Python standard library is used (Python 3.9+).
If you capture the same server twice, the most recent capture in the logs is used.
"""
import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "autoarchiver-aip/1"
GITHUB_LIMIT = 95 * 1024 * 1024  # GitHub rejects files over 100 MB

IP = r"(?:\d{1,3}\.){3}\d{1,3}|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
NAME_RE = re.compile(rf"^(?P<ip>{IP})_(?P<port>\d{{1,5}})(?:-(?P<epoch>\d{{10,13}}))?$")
ARCH_TS = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] ?(.*)$")
MC_LINE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\] \[(.+?)/(INFO|WARN|ERROR|FATAL|DEBUG|TRACE)\]: (.*)$")
SAVED_RE = re.compile(r"\[WorldTools\] Saved (?P<what>.+?) in dimension (?P<dim>\S+) to saves directory (?P<name>\S+)")
ZIPPED_RE = re.compile(r"Finished zipping .+? with size (?P<src>[\d.]+ \w+) to (?P<zip>.+?\.zip) with size (?P<dst>[\d.]+ \w+)")
GZ_LOG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d+\.log\.gz$")


# --------------------------------------------------------------------------- helpers
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def redact(text, extra):
    """Hide the Windows account name in paths (and anything passed with --redact)."""
    text = re.sub(r"(?i)([A-Z]:\\Users\\)[^\\\s]+", r"\1<redacted>", text)
    for s in extra:
        if s:
            text = text.replace(s, "<redacted>")
    return text


def scrub(obj, extra):
    if isinstance(obj, str):
        return redact(obj, extra)
    if isinstance(obj, list):
        return [scrub(x, extra) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v, extra) for k, v in obj.items()}
    return obj


def write_json(path, obj, extra):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scrub(obj, extra), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def epoch_to_utc(epoch):
    n = int(epoch)
    return datetime.fromtimestamp(n / 1000 if len(str(epoch)) >= 13 else n, timezone.utc)


# --------------------------------------------------------------------------- parse archival_log.txt
def parse_archival_log(path):
    blocks, cur = [], None
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = ARCH_TS.match(raw)
        if not m:
            continue
        ts, msg = datetime.strptime(m[1], "%Y-%m-%d %H:%M:%S"), m[2].strip()
        if msg.startswith("Processing:"):
            ip, _, port = msg.split(":", 1)[1].strip().rpartition(":")
            cur = {"ip": ip, "port": port, "started": ts, "lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append((ts, msg))
    return blocks


def summarise_block(b):
    s = {"processing_started": b["started"].isoformat(sep=" "), "version": None, "country": None,
         "connected": False, "build_detected_line": None, "coordinates": None, "goto_command": None,
         "download_triggered": False, "python_log_download_timeout": False, "disconnected_at": None}
    for ts, msg in b["lines"]:
        if msg.startswith("Version:"):
            s["version"] = msg.split(":", 1)[1].strip()
        elif msg.startswith("Country:"):
            s["country"] = msg.split(":", 1)[1].strip()
        elif "Server connected successfully" in msg:
            s["connected"] = True
        elif msg.startswith("BUILD DETECTED:"):
            s["build_detected_line"] = msg.split(":", 1)[1].strip()
        elif msg.startswith("Extracted coordinates:"):
            m = re.search(r"X=(-?\d+), Y=(-?\d+), Z=(-?\d+)", msg)
            if m:
                s["coordinates"] = {"x": int(m[1]), "y": int(m[2]), "z": int(m[3])}
        elif msg.startswith("Sending goto command:"):
            s["goto_command"] = msg.split(":", 1)[1].strip()
        elif "Triggering world download" in msg:
            s["download_triggered"] = True
        elif "Download timeout" in msg:
            s["python_log_download_timeout"] = True
        elif msg.startswith("Disconnecting"):
            s["disconnected_at"] = ts.isoformat(sep=" ")
    return s


def pick_block(blocks, ip, port, cap_tod):
    cands = [b for b in blocks if b["ip"] == ip and b["port"] == port]
    if not cands:
        return None, "no_entry_in_archival_log"
    if cap_tod is None:
        return cands[-1], "matched_by_ip_port_only"
    best, best_d = None, None
    for b in cands:
        tod = b["started"].hour * 3600 + b["started"].minute * 60 + b["started"].second
        d = (cap_tod - tod) % 86400
        if best_d is None or d < best_d:
            best, best_d = b, d
    return (best, "matched_by_time") if best_d <= 1800 else (None, "time_mismatch")


# --------------------------------------------------------------------------- parse Minecraft logs
def load_minecraft_logs(logs_dir):
    d = Path(logs_dir)
    files = sorted(p for p in d.glob("*.log.gz") if GZ_LOG_RE.match(p.name))
    if (d / "latest.log").exists():
        files.append(d / "latest.log")
    entries = []
    for f in files:
        opener = gzip.open if f.suffix == ".gz" else open
        with opener(f, "rt", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.rstrip("\r\n")
                m = MC_LINE.match(raw)
                if m:
                    h, mi, s, thread, level, msg = m.groups()
                    entries.append({"file": f.name, "tod": int(h) * 3600 + int(mi) * 60 + int(s),
                                    "clock": f"{h}:{mi}:{s}", "level": level, "msg": msg,
                                    "raw": raw, "extra": []})
                elif entries:
                    entries[-1]["extra"].append(raw)
    return [f.name for f in files], entries


def read_environment(entries):
    env = {"minecraft": None, "fabric_loader": None, "mods": {}}
    for e in entries:
        m = re.match(r"Loading Minecraft (\S+) with Fabric Loader (\S+)", e["msg"])
        if m:
            env["minecraft"], env["fabric_loader"] = m.groups()
        if re.match(r"Loading \d+ mods:", e["msg"]):
            for x in e["extra"]:
                m = re.match(r"^\t- (\S+) (\S+)\s*$", x)
                if m:
                    env["mods"][m[1]] = m[2]
    return env


def parse_counts(text):
    pats = {"chunks": r"(\d+) chunks?", "entities": r"(\d+) entit(?:y|ies)",
            "players": r"(\d+) players?", "containers": r"(\d+) containers?"}
    return {k: (int(m[1]) if (m := re.search(p, text)) else 0) for k, p in pats.items()}


def analyse_capture(entries, name, ip, port):
    """Everything Minecraft's log says about the capture of one world."""
    starts = [i for i, e in enumerate(entries) if f"[WorldTools] Started capturing {name}" in e["msg"]]
    saved = [(i, SAVED_RE.search(e["msg"])) for i, e in enumerate(entries) if "[WorldTools] Saved" in e["msg"]]
    saved = [(i, m) for i, m in saved if m and m["name"] == name]
    if not starts and not saved:
        return None
    start = starts[-1] if starts else saved[-1][0]
    saved = [(i, m) for i, m in saved if i >= start] if starts else saved

    seg_start = start
    for j in range(start, max(-1, start - 3000), -1):
        if entries[j]["msg"].startswith(f"Connecting to {ip}, {port}"):
            seg_start = j
            break
    seg_end = len(entries)
    for j in range(start + 1, len(entries)):
        if entries[j]["msg"].startswith("Connecting to ") or (entries[j]["tod"] - entries[start]["tod"]) % 86400 > 900:
            seg_end = j
            break
    seg = entries[seg_start:seg_end]
    after = entries[start:seg_end]

    errors = []
    for e in after:
        if e["level"] in ("ERROR", "FATAL"):
            errors.append(e["msg"] + (" | " + e["extra"][0].strip() if e["extra"] else ""))
    zipped = next((m for m in (ZIPPED_RE.search(e["msg"]) for e in after) if m), None)

    meteor = []
    for e in seg:
        m = re.search(r"\[Meteor\] (.*)", e["msg"])
        if m:
            meteor.append(f"[{e['clock']}] {m[1]}")

    lines = []
    for e in seg:
        lines.append(e["raw"])
        lines.extend(e["extra"][:8])
        if len(e["extra"]) > 8:
            lines.append(f"\t... ({len(e['extra']) - 8} more lines)")

    return {
        "started_tod": entries[start]["tod"], "started_clock": entries[start]["clock"],
        "saved": [{"dimension": m["dim"], "summary": m["what"], **parse_counts(m["what"])} for _, m in saved],
        "capture_metadata_saved": any("Saved capture metadata" in e["msg"] for e in after),
        "worldtools_zip": ({"size_before": zipped["src"], "size_after": zipped["dst"],
                            "file": re.split(r"[\\/]", zipped["zip"])[-1]} if zipped else None),
        "errors": errors,
        "storage_error": any("Unhandled storage flow error" in e["msg"] for e in after),
        "meteor_lines": meteor, "excerpt": lines,
    }


# --------------------------------------------------------------------------- worlds
def discover_worlds(saves):
    worlds, skipped = {}, []
    for p in sorted(Path(saves).iterdir()):
        stem = p.name[:-4] if (p.is_file() and p.suffix.lower() == ".zip") else p.name
        m = NAME_RE.match(stem)
        if not m:
            skipped.append(p.name)
            continue
        key = f"{m['ip']}_{m['port']}"
        w = worlds.setdefault(key, {"name": key, "ip": m["ip"], "port": m["port"], "folder": None, "zips": []})
        if p.is_dir():
            w["folder"] = p
        elif p.is_file() and p.suffix.lower() == ".zip":
            w["zips"].append((m["epoch"] or "0", p))
    return worlds, skipped


def make_zip(folder, dest):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(folder).as_posix())


def inventory_zip(path):
    inv = []
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        for info in z.infolist():
            if info.is_dir():
                continue
            h = hashlib.sha256()
            with z.open(info) as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            inv.append({"path": info.filename, "size": info.file_size, "sha256": h.hexdigest()})
    inv.sort(key=lambda x: x["path"])
    digest = hashlib.sha256("\n".join(f"{i['path']}\t{i['sha256']}" for i in inv).encode()).hexdigest()
    return bad, inv, digest


def run_qa(inv, zip_bad, zip_size, cap):
    names = {i["path"]: i["size"] for i in inv}

    def has(suffix):
        return any(n == suffix or n.endswith("/" + suffix) for n in names)

    region = any(re.search(r"(^|/)region/r\..+\.mca$", n) and s > 0 for n, s in names.items())
    confirmed = None if cap is None else bool(cap["saved"])
    checks = [
        {"check": "zip_integrity", "ok": zip_bad is None, "detail": zip_bad or "all members readable"},
        {"check": "level_dat_present", "ok": has("level.dat"), "detail": ""},
        {"check": "region_data_present", "ok": region, "detail": ""},
        {"check": "under_github_file_limit", "ok": zip_size <= GITHUB_LIMIT, "detail": f"{zip_size} bytes"},
        {"check": "capture_metadata_present", "ok": has("WorldTools/Capture Metadata.md"), "detail": ""},
        {"check": "worldtools_reported_saved", "ok": confirmed,
         "detail": "no Minecraft log evidence found" if confirmed is None else ""},
        {"check": "no_storage_errors_in_log", "ok": (None if cap is None else not cap["storage_error"]),
         "detail": "; ".join(cap["errors"][:2]) if cap and cap["errors"] else ""},
    ]
    by = {c["check"]: c["ok"] for c in checks}
    if not (by["zip_integrity"] and by["level_dat_present"] and by["region_data_present"] and by["under_github_file_limit"]):
        status = "rejected"
    elif by["worldtools_reported_saved"] is False or by["no_storage_errors_in_log"] is False or not by["capture_metadata_present"]:
        status = "incomplete"
    elif by["worldtools_reported_saved"] is None:
        status = "unverified"
    else:
        status = "complete"
    return status, checks, confirmed


# --------------------------------------------------------------------------- repo-level documents
README = """# Minecraft Auto-Archiver - archive repository

Archive of Minecraft Java Edition worlds captured from public servers by the Auto-Archiver
and organised after the OAIS reference model (ISO 14721 / CCSDS 650.0-M-2).
This is a personal prototype; it follows OAIS as a framework, not as a certification.

## Designated Community
People who study or preserve Minecraft servers and player-built structures (archivists,
researchers, historians) and can open a Java Edition world.

## Virtual Submission Agreement
Accepted: world captures made by WorldTools through the Auto-Archiver (folder or zip named
`<ip>_<port>`), together with Minecraft's log and the archiver's `archival_log.txt`.
Each submission (SIP) is checked at ingest and gets a status in `catalogue.csv`:

| qa_status  | meaning |
|------------|---------|
| complete   | WorldTools reported the save, metadata file present, no storage errors in the log |
| incomplete | stored, but the log shows a failed or unconfirmed save - use with care |
| unverified | files look fine but no Minecraft log evidence was available |
| rejected   | not stored (empty, corrupt, no level.dat / region data, or too large) |

## Layout
    aips/<ip>_<port>_<timestamp>/   one Archival Information Package per capture
        content/                    the world (zip)
        pdi/                        preservation description information (reference, provenance,
                                    context, fixity, access rights, log excerpt)
        aip.json                    packaging information: every file and its SHA-256
    catalogue.csv                   descriptive information: one row per AIP
    reports/                        ingest receipts and storage confirmations
    docs/representation_information.md   how to open the worlds

Times without a time zone come from the archiving PC's local clock.

## Checking integrity
    python upload_aip.py --repo . --verify-only

## Access rights - read before sharing
Worlds were captured from public servers by joining as an ordinary client. The server owners and
players were not asked for permission, rights are unknown, and worlds may contain player data
(UUIDs in `playerdata/` and `stats/`). Keep this repository private until that is reviewed.
"""

REPRESENTATION = """# Representation Information - Minecraft Java Edition world captures

Format: Minecraft Java Edition world folder, stored zipped. Captured with WorldTools (Fabric mod)
on the client. It contains **only what the client was sent** (chunks near where the bot travelled),
not the server's full world.

| Path in the zip | Format |
|---|---|
| `level.dat` | gzip-compressed NBT: world settings and version |
| `region/r.X.Z.mca`, `entities/r.X.Z.mca` | Anvil region files (blocks / entities), one file per 32x32 chunks |
| `playerdata/<uuid>.dat` | gzip-compressed NBT, one per player captured |
| `stats/<uuid>.json` | JSON player statistics |
| `data/` | NBT data files (maps, etc.) |
| `session.lock` | lock file written by Minecraft, no archival value |
| `WorldTools/Capture Metadata.md` | WorldTools' own description of the capture |

How to open: unzip into `.minecraft/saves/` and load with Minecraft Java Edition (the version in
`pdi/provenance.json`, or newer - Minecraft upgrades old worlds). To inspect without playing use an
NBT/Anvil tool such as NBTExplorer or Amulet Map Editor.

Software that produced the capture (exact versions are recorded per AIP in `pdi/provenance.json`):
Minecraft Java, Fabric Loader, WorldTools, Meteor Client (build detection), Baritone (pathing),
ViaFabricPlus (version compatibility).
"""

ACCESS_RIGHTS = {
    "repository_visibility": "private while the prototype is tested",
    "source": "public Minecraft server joined as an ordinary client; no permission requested from owner or players",
    "licence": "none granted; rights stay with the server owners and players",
    "redistribution": "not cleared - do not make this repository public before review",
    "personal_data": "world may contain player UUIDs and statistics (playerdata/, stats/)",
}


def ensure_repo_docs(repo):
    for rel, text in (("README.md", README), ("docs/representation_information.md", REPRESENTATION),
                      (".gitignore", "__pycache__/\n*.tmp\n.DS_Store\nThumbs.db\n")):
        p = repo / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")


CATALOGUE_FIELDS = ["aip_id", "server_ip", "server_port", "country", "minecraft_version", "captured_local",
                    "qa_status", "worldtools_saved", "chunks", "entities", "players", "containers",
                    "trigger", "coordinates", "zip_bytes", "files", "sha256", "content_digest", "ingested_utc"]


def read_catalogue(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_catalogue(path, row):
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CATALOGUE_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Build OAIS AIPs from the archiver's worlds and logs.")
    ap.add_argument("--saves", required=True, help=r"...\.minecraft\saves")
    ap.add_argument("--logs", required=True, help=r"...\.minecraft\logs")
    ap.add_argument("--archival-log", required=True, help="archival_log.txt written by the Python script")
    ap.add_argument("--repo", required=True, help="your archive folder (a clone of the GitHub repo)")
    ap.add_argument("--only", action="append", default=[], help="only ingest this folder, e.g. 1.2.3.4_25565")
    ap.add_argument("--redact", action="append", default=[], help="extra text to hide in copied log lines (e.g. your Minecraft username)")
    ap.add_argument("--reject-incomplete", action="store_true", help="do not store worlds whose QA status is 'incomplete'")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, write nothing")
    a = ap.parse_args()

    repo, now = Path(a.repo), datetime.now(timezone.utc)
    blocks = parse_archival_log(a.archival_log)
    log_files, entries = load_minecraft_logs(a.logs)
    env = read_environment(entries)
    worlds, skipped = discover_worlds(a.saves)
    if a.only:
        worlds = {k: v for k, v in worlds.items() if k in a.only}
    print(f"archival_log: {len(blocks)} server visits | minecraft logs: {len(log_files)} file(s), {len(entries)} lines | worlds found: {len(worlds)}")

    catalogue_path = repo / "catalogue.csv"
    known = {r["content_digest"] for r in read_catalogue(catalogue_path)}
    report = {"run_utc": now.isoformat(), "saves": str(a.saves), "log_files": log_files,
              "archival_log_visits": len(blocks), "skipped_not_server_worlds": skipped, "worlds": []}
    if not a.dry_run:
        ensure_repo_docs(repo)

    for name, w in sorted(worlds.items()):
        ip, port = w["ip"], w["port"]
        wt_epoch = max(w["zips"])[0] if w["zips"] else None
        if wt_epoch == "0":
            wt_epoch = None
        item = {"world": name}
        report["worlds"].append(item)
        with tempfile.TemporaryDirectory() as tmp:
            # ---- Receive submission: get one zip to work with
            zip_tmp = Path(tmp) / f"{name}.zip"
            if w["folder"] is not None:
                make_zip(w["folder"], zip_tmp)
                source = f"folder {w['folder'].name}"
            elif w["zips"]:
                zip_tmp.write_bytes(max(w["zips"])[1].read_bytes())
                source = f"zip {max(w['zips'])[1].name}"
            else:
                item.update(outcome="skipped", reason="no folder or zip")
                continue
            try:
                zip_bad, inv, digest = inventory_zip(zip_tmp)
            except zipfile.BadZipFile as e:
                zip_bad, inv, digest = f"unreadable zip: {e}", [], ""
            zip_size = zip_tmp.stat().st_size

            # ---- Quality assurance
            cap = analyse_capture(entries, name, ip, port) if entries else None
            block, matched = pick_block(blocks, ip, port, cap["started_tod"] if cap else None)
            status, checks, confirmed = run_qa(inv, zip_bad, zip_size, cap)
            item.update(source=source, qa_status=status, checks=checks, archival_log_match=matched)

            if status == "rejected" or (status == "incomplete" and a.reject_incomplete):
                item["outcome"] = "not stored (" + status + ")"
                print(f"  {name:28} {status.upper():10} not stored")
                continue
            if digest in known:
                item["outcome"] = "duplicate of an existing AIP, skipped"
                print(f"  {name:28} duplicate - already archived")
                continue

            # ---- Generate AIP
            py = summarise_block(block) if block else None
            cap_local = None
            if cap and block:
                cap_local = datetime.combine(block["started"].date(), datetime.min.time()) + timedelta(seconds=cap["started_tod"])
                if cap_local < block["started"] - timedelta(minutes=1):
                    cap_local += timedelta(days=1)
            elif block:
                cap_local = block["started"]
            cap_utc = epoch_to_utc(wt_epoch) if wt_epoch else None
            if cap_local:
                stamp = cap_local.strftime("%Y%m%dT%H%M%S")
                time_source = "archival_log" + ("+minecraft_log" if cap else "")
            elif cap_utc:
                stamp, time_source = cap_utc.strftime("%Y%m%dT%H%M%SZ"), "worldtools_zip_name"
            else:
                mt = datetime.fromtimestamp((w["folder"] or max(w["zips"])[1]).stat().st_mtime)
                stamp, time_source = mt.strftime("%Y%m%dT%H%M%S"), "file_modified_time"
            aip_id = f"{name}_{stamp}"
            if (repo / "aips" / aip_id).exists():
                aip_id += "-b"

            notes = []
            if matched not in ("matched_by_time", "matched_by_ip_port_only"):
                notes.append(f"no usable archival_log.txt entry ({matched}); discovery details unavailable")
            if matched == "matched_by_ip_port_only":
                notes.append("archival_log entry matched on ip:port only (no Minecraft log timing)")
            if py and py["python_log_download_timeout"]:
                notes.append("archival_log.txt printed 'Download timeout'; that message is only the script's wait "
                             "limit - worldtools_saved below is the authoritative result")
            if cap is None:
                notes.append("no WorldTools lines for this world in the supplied Minecraft logs")
            if cap and cap["storage_error"]:
                notes.append("WorldTools logged 'Unhandled storage flow error' during this capture")

            pdi = {
                "reference": {"aip_id": aip_id, "server_ip": ip, "server_port": int(port), "folder_name": name,
                              "captured_local": cap_local.isoformat() if cap_local else None,
                              "captured_utc": cap_utc.isoformat() if cap_utc else None,
                              "time_source": time_source},
                "provenance": {
                    "producer": "Auto-Archiver (Python/PyAutoGUI bot driving Minecraft)",
                    "tools": {"minecraft": env["minecraft"], "fabric_loader": env["fabric_loader"],
                              "mods": env["mods"]},
                    "discovery_and_visit": py,
                    "capture": ({"worldtools_saved": confirmed, "saved": cap["saved"],
                                 "capture_metadata_saved": cap["capture_metadata_saved"],
                                 "worldtools_zip": cap["worldtools_zip"], "errors": cap["errors"]} if cap else None),
                    "custody": [
                        {"event": "captured", "by": "Auto-Archiver", "when_local": cap_local.isoformat() if cap_local else None},
                        {"event": "ingested_into_aip", "by": "build_aip.py", "when_utc": now.isoformat(), "source": source}],
                    "notes": notes},
                "context": {
                    "why_captured": ("Meteor reported a possible player build" if py and py["build_detected_line"]
                                     else "no build trigger recorded"),
                    "trigger_line": py["build_detected_line"] if py else None,
                    "coordinates": py["coordinates"] if py else None,
                    "meteor_messages_during_visit": cap["meteor_lines"][:100] if cap else [],
                    "country": py["country"] if py else None,
                    "minecraft_version_reported": py["version"] if py else None},
                "fixity": {"algorithm": "sha256", "content_file": f"content/{name}.zip",
                           "sha256": sha256_file(zip_tmp), "size_bytes": zip_size, "file_count": len(inv),
                           "content_digest": digest, "inventory": inv},
                "access_rights": ACCESS_RIGHTS,
            }
            item.update(outcome=f"ingested as {aip_id}", aip_id=aip_id, notes=notes)
            trig = "meteor_build" if (py and py["build_detected_line"]) else "none_recorded"
            print(f"  {name:28} {status.upper():10} -> {aip_id}")
            if a.dry_run:
                continue

            final = repo / "aips" / aip_id
            build = repo / "aips" / (aip_id + ".tmp")
            build.mkdir(parents=True, exist_ok=True)
            (build / "content").mkdir(exist_ok=True)
            (build / "content" / f"{name}.zip").write_bytes(zip_tmp.read_bytes())
            for k, v in pdi.items():
                write_json(build / "pdi" / f"{k}.json", v, a.redact)
            excerpt = "\n".join(cap["excerpt"]) if cap else "(no Minecraft log lines found for this world)"
            (build / "pdi" / "session_log_excerpt.txt").write_text(redact(excerpt, a.redact) + "\n", encoding="utf-8")
            files = [{"path": p.relative_to(build).as_posix(), "size": p.stat().st_size, "sha256": sha256_file(p)}
                     for p in sorted(build.rglob("*")) if p.is_file()]
            write_json(build / "aip.json", {
                "schema": SCHEMA, "aip_id": aip_id, "created_utc": now.isoformat(), "qa_status": status,
                "qa_checks": checks, "representation_information": "../../docs/representation_information.md",
                "files": files}, a.redact)
            build.rename(final)

            sv = (cap["saved"] if cap else [])
            append_catalogue(catalogue_path, {
                "aip_id": aip_id, "server_ip": ip, "server_port": port,
                "country": (py or {}).get("country") or "", "minecraft_version": (py or {}).get("version") or env["minecraft"] or "",
                "captured_local": cap_local.isoformat() if cap_local else "", "qa_status": status,
                "worldtools_saved": "" if confirmed is None else str(confirmed).lower(),
                "chunks": sum(s["chunks"] for s in sv), "entities": sum(s["entities"] for s in sv),
                "players": sum(s["players"] for s in sv), "containers": sum(s["containers"] for s in sv),
                "trigger": trig,
                "coordinates": (lambda c: f"{c['x']} {c['y']} {c['z']}" if c else "")((py or {}).get("coordinates")),
                "zip_bytes": zip_size, "files": len(inv), "sha256": pdi["fixity"]["sha256"],
                "content_digest": digest, "ingested_utc": now.isoformat()})
            known.add(digest)

    counts = {}
    for it in report["worlds"]:
        counts[it.get("qa_status", "n/a")] = counts.get(it.get("qa_status", "n/a"), 0) + 1
    report["summary"] = counts
    if not a.dry_run and report["worlds"]:
        write_json(repo / "reports" / f"ingest_{now.strftime('%Y%m%dT%H%M%SZ')}.json", report, a.redact)
    print("done." + ("  (dry run - nothing written)" if a.dry_run else f"  Archive folder: {repo}"))
    if skipped:
        print(f"  ignored (not <ip>_<port> worlds): {', '.join(skipped)}")


if __name__ == "__main__":
    sys.exit(main())
