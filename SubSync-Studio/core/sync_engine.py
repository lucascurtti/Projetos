from __future__ import annotations

from pathlib import Path
from typing import Callable

import ffsubsync
from ffsubsync.ffsubsync import make_parser


class SyncError(RuntimeError):
    pass


def make_output_path(srt_path: str | Path, suffix: str = ".sincronizada") -> Path:
    p = Path(srt_path)
    candidate = p.with_name(f"{p.stem}{suffix}{p.suffix}")
    counter = 2
    while candidate.exists():
        candidate = p.with_name(f"{p.stem}{suffix}-{counter}{p.suffix}")
        counter += 1
    return candidate


def sync_subtitle(
    reference: str | Path,
    subtitle: str | Path,
    output: str | Path | None = None,
    mode: str = "standard",
    safe: bool = True,
    progress_callback: Callable[[float], None] | None = None,
) -> tuple[Path, dict]:
    reference = Path(reference)
    subtitle = Path(subtitle)
    if not reference.exists():
        raise FileNotFoundError(reference)
    if not subtitle.exists():
        raise FileNotFoundError(subtitle)
    output_path = Path(output) if output else make_output_path(subtitle)

    cli = [str(reference), "-i", str(subtitle), "-o", str(output_path)]
    if safe:
        cli.append("--skip-sync-on-low-quality")
    if mode == "multi":
        cli += ["--multi-segment-sync", "--segment-count", "8", "--skip-intro-outro"]
    elif mode == "cuts":
        # Deixa o algoritmo considerar divisões internas com penalidade menor.
        cli += ["--split-penalty", "2.0"]

    args = make_parser().parse_args(cli)

    def on_progress(info) -> None:
        if progress_callback and getattr(info, "fraction", None) is not None:
            progress_callback(float(info.fraction))

    result = ffsubsync.run(args, progress_handler=on_progress)
    if result.get("retval", 1) != 0 or not output_path.exists():
        raise SyncError(f"Falha ao sincronizar legenda: {result}")
    if progress_callback:
        progress_callback(1.0)
    return output_path, result
