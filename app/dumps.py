"""The output folders of dumping tools: finished dumps, offered with the tools' logs, and staged when the core asks.

Disc rippers leave a folder per disc, often deep in their output tree, holding the image, the tool's logs and
intermediate files that are no use once the image is made: a folder with a cue sheet or gdi is one dump. Cartridge
dumpers often write every dump into one folder: there, each image is a dump, with the notes that share its name. Only
images and notes are staged; the rest stays where the tool left it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import Candidate, Job

# What a finished dump is made of, as a DAT lists it, or as an archive or compressed image of it.
IMAGES = {
    ".cue", ".bin", ".iso", ".gdi", ".raw", ".gcm", ".chd", ".rvz", ".zip", ".7z",
    ".nes", ".fds", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".n64", ".z64", ".v64", ".nds", ".vb", ".md", ".gen", ".32x",
    ".sms", ".gg", ".sg", ".pce", ".a26", ".a52", ".a78", ".lnx", ".jag", ".ws", ".wsc", ".ngp", ".ngc", ".col", ".int",
}
# What a tool writes about the dump: its log, its own checksums, its own DAT entry.
NOTES = {".log", ".txt", ".dat", ".md5", ".sha1", ".sfv"}
NOTES_LIMIT = 4000
# Tools whose output this knows, by a word in their logs' names or text, to say where a dump came from.
TOOLS = ["redumper", "DiscImageCreator", "Aaru", "dumpos", "Cartridge Reader", "GB Operator", "Retrode", "Dolphin"]
_TRACK = re.compile(r'^\s*FILE\s+"([^"]+)"', re.IGNORECASE | re.MULTILINE)


# A disc's image is described by these; a folder with one is one dump.
SHEETS = {".cue", ".gdi"}


@dataclass(frozen=True)
class Dump:
    path: str  # the disc's folder or the cartridge's file, relative to the root
    name: str
    images: tuple[Path, ...]
    notes: tuple[Path, ...]
    size: int
    changed: float

    @property
    def candidate_id(self) -> str:
        return json.dumps({"p": self.path, "s": self.size, "m": int(self.changed)}, separators=(",", ":"))


class Dumps:
    def __init__(self, root: str):
        self.root = Path(root)

    def finished(self, settle_seconds: float) -> list[Dump]:
        """The dumps that are finished: nothing in them changed for settle_seconds, and for a disc, every track its cue
        sheets name is there. Oldest first."""
        found = []
        now = time.time()
        for folder, names in self._folders():
            files = [folder / n for n in names if not n.startswith(".")]
            images = sorted(f for f in files if f.suffix.lower() in IMAGES)
            notes = sorted(f for f in files if f.suffix.lower() in NOTES)
            if any(i.suffix.lower() in SHEETS for i in images):
                # Everything the ripper writes counts, intermediate files too: it isn't done until they stop changing.
                if self._whole(images):
                    found.append(self._dump(folder, folder.name if folder != self.root else images[0].stem, images, notes, files))
            else:
                for image in images:
                    own = [n for n in notes if n.stem == image.stem]
                    found.append(self._dump(image, image.stem, [image], own, [image, *own]))
        return sorted((d for d in found if now - d.changed >= settle_seconds), key=lambda d: d.changed)

    def _dump(self, path: Path, name: str, images: list[Path], notes: list[Path], files: list[Path]) -> Dump:
        return Dump(path.relative_to(self.root).as_posix(), name, tuple(images), tuple(notes),
                    sum(i.stat().st_size for i in images), max(f.stat().st_mtime for f in files))

    def _folders(self):
        for folder, dirs, names in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            yield Path(folder), names

    @staticmethod
    def _whole(images: list[Path]) -> bool:
        """Whether every track the folder's cue sheets name is there, so a disc still being ripped isn't taken."""
        present = {i.name for i in images}
        for cue in (i for i in images if i.suffix.lower() == ".cue"):
            if any(Path(track).name not in present for track in _TRACK.findall(cue.read_text(errors="replace"))):
                return False
        return True

    def candidate(self, dump: Dump) -> Candidate:
        notes = self.notes(dump)
        tool = next((t for t in TOOLS if notes and t.lower() in notes.lower()), None)
        where = dump.path
        formats = sorted({i.suffix.lower().lstrip(".") for i in dump.images})
        return Candidate(candidate_id=dump.candidate_id, name=dump.name, source=f"{tool}: {where}" if tool else where,
                         size=dump.size, format=",".join(formats), notes=notes)

    def notes(self, dump: Dump) -> str | None:
        texts = []
        for file in dump.notes:
            if file.stat().st_size <= 1 << 20:
                text = file.read_text(errors="replace").strip()
                if text:
                    texts.append(f"{file.name}:\n{text}")
        joined = "\n\n".join(texts)
        return joined[:NOTES_LIMIT] + ("\n…" if len(joined) > NOTES_LIMIT else "") if joined else None

    def fetch(self, job: Job, candidate_id: str, directory: Path, settings: dict[str, Any]) -> list[dict[str, Any]]:
        data = json.loads(candidate_id)
        path = (self.root / data["p"]).resolve()
        if path != self.root.resolve() and self.root.resolve() not in path.parents:
            raise ValueError("The candidate points outside the dumps folder.")
        dump = next((d for d in self.finished(0) if d.path == data["p"]), None)
        if dump is None:
            raise FileNotFoundError(f"{data['p']} isn't a finished dump any more.")
        keep = settings.get("keepOriginals", True)
        written = []
        for file in [*dump.images, *dump.notes]:
            job.check()
            target = directory / file.name
            shutil.copy2(file, target) if keep else shutil.move(file, target)
            # The core and the igir worker run as other users, and need to read and move these.
            os.chmod(target, 0o666)
            written.append({"path": target.name, "size": target.stat().st_size})
        # A disc's folder holds what the ripper left behind; once its image is gone, it can go too.
        if not keep and settings.get("removeLeftovers", False) and path.is_dir() and path != self.root.resolve():
            shutil.rmtree(path, ignore_errors=True)
        return written
