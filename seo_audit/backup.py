"""Backup originals before anything is repaired.

The repair engine already writes its output to a separate folder and never
overwrites your source files - but this makes the safety net explicit: before
a repair (or on demand), copy EVERY original file verbatim into a dated,
sequenced backup folder so you always have a pristine copy to fall back on.

The copy is byte-for-byte and non-parsing: files the auditor can't read
(gitignored config, password-protected archives, binaries) are copied too,
because a backup that skips the files you most want preserved isn't a backup.

Folder naming (as requested):
    Backup_ORIGINAL_MM-DD-YYYY     <- the very first backup of a location
    Backup_2_MM-DD-YYYY            <- second, third, ... thereafter
    Backup_3_MM-DD-YYYY
"""

import os
import re
import shutil
from datetime import date

BACKUP_RE = re.compile(r"^Backup_([^_]+)_\d{2}-\d{2}-\d{4}$")


def existing_backups(dest_root):
    """Return the list of existing Backup_* folder names under dest_root."""
    if not os.path.isdir(dest_root):
        return []
    return sorted(name for name in os.listdir(dest_root)
                  if BACKUP_RE.match(name)
                  and os.path.isdir(os.path.join(dest_root, name)))


def next_label(dest_root):
    """'ORIGINAL' for the first backup here, then '2', '3', ... after that."""
    count = len(existing_backups(dest_root))
    return "ORIGINAL" if count == 0 else str(count + 1)


def _iter_source_files(sources):
    """Yield (absolute_path, relative_path) for every file to back up.

    `sources` is a directory path, a single file, or a list of those. For a
    directory the relative path is rooted at the directory itself; for loose
    files the relative path is just the file name (deduped if names collide).
    """
    if isinstance(sources, (str, os.PathLike)):
        sources = [sources]
    seen_names = {}
    for src in sources:
        src = os.path.abspath(src)
        if os.path.isdir(src):
            root_name = os.path.basename(src.rstrip(os.sep)) or "site"
            for dirpath, _dirs, files in os.walk(src):
                for fn in files:
                    ap = os.path.join(dirpath, fn)
                    rel = os.path.join(root_name, os.path.relpath(ap, src))
                    yield ap, rel
        elif os.path.isfile(src):
            base = os.path.basename(src)
            # de-dupe loose file names that collide
            n = seen_names.get(base, 0)
            seen_names[base] = n + 1
            rel = base if n == 0 else f"{n}_{base}"
            yield src, rel


def make_backup(sources, dest_root, log=None):
    """Copy every file in `sources` into a new Backup folder under dest_root.

    Returns {"folder", "label", "files_copied", "skipped": [(path, reason)],
             "bytes"}.  Never raises for an individual unreadable file - it is
    recorded in `skipped` and the rest continue.
    """
    log = log or (lambda m: None)
    os.makedirs(dest_root, exist_ok=True)
    label = next_label(dest_root)
    folder_name = f"Backup_{label}_{date.today():%m-%d-%Y}"
    folder = os.path.join(dest_root, folder_name)
    # If the same label+date somehow exists, add a numeric suffix rather than
    # clobbering an existing backup.
    if os.path.exists(folder):
        i = 2
        while os.path.exists(f"{folder}_{i}"):
            i += 1
        folder = f"{folder}_{i}"
    os.makedirs(folder, exist_ok=True)

    log(f"Backing up originals -> {os.path.basename(folder)}")
    copied, skipped, total_bytes = 0, [], 0
    for abspath, rel in _iter_source_files(sources):
        dest = os.path.join(folder, rel)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # copy2 preserves timestamps; shutil reads bytes, never parses.
            shutil.copy2(abspath, dest)
            copied += 1
            try:
                total_bytes += os.path.getsize(dest)
            except OSError:
                pass
        except (OSError, shutil.Error) as exc:
            # Unreadable (permissions, locked, password-protected container the
            # OS won't open, etc.) - record it and keep going.
            skipped.append((abspath, str(exc)))
    if skipped:
        # Leave a note in the backup so the user knows what couldn't be copied.
        try:
            with open(os.path.join(folder, "_BACKUP-NOTES.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write("These files could not be copied (permissions / locked "
                         "/ unreadable) and are NOT in this backup:\n\n")
                for path, reason in skipped:
                    fh.write(f"  {path}\n    -> {reason}\n")
        except OSError:
            pass
    log(f"  Backed up {copied} file(s)"
        + (f", {len(skipped)} unreadable and skipped" if skipped else ""))
    return {"folder": folder, "label": label, "files_copied": copied,
            "skipped": skipped, "bytes": total_bytes}
