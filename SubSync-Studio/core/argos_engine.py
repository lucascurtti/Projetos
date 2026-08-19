from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
from typing import Callable

from .subtitles import SubtitleEntry, normalize_ptbr, read_srt, write_srt


class ArgosError(RuntimeError):
    pass


def _imports():
    try:
        import argostranslate.package as package
        import argostranslate.translate as translate
        return package, translate
    except Exception as exc:
        raise ArgosError(
            "Argos Translate não está disponível. Rode setup_windows.bat novamente."
        ) from exc


def model_installed() -> bool:
    _, translate = _imports()
    try:
        from_lang = translate.get_language_from_code("en")
        to_lang = translate.get_language_from_code("pt")
        if not from_lang or not to_lang:
            return False
        from_lang.get_translation(to_lang)
        return True
    except Exception:
        return False


def install_en_pt_model(progress_callback: Callable[[str], None] | None = None) -> None:
    package, translate = _imports()
    if model_installed():
        if progress_callback:
            progress_callback("Modelo EN → PT já está instalado.")
        return
    if progress_callback:
        progress_callback("Atualizando índice de modelos do Argos...")
    package.update_package_index()
    available = package.get_available_packages()
    candidate = next((p for p in available if p.from_code == "en" and p.to_code == "pt"), None)
    if candidate is None:
        raise ArgosError("Não encontrei o modelo EN → PT no índice do Argos.")
    if progress_callback:
        progress_callback("Baixando modelo EN → PT (somente na primeira vez)...")
    path = candidate.download()
    package.install_from_path(path)
    translate.get_installed_languages.cache_clear()
    if progress_callback:
        progress_callback("Modelo EN → PT instalado.")


def _preserve_tags_translate(text: str, translator) -> str:
    tags: list[str] = []

    def stash(match: re.Match) -> str:
        tags.append(match.group(0))
        return f" __TAG{len(tags)-1}__ "

    protected = re.sub(r"<[^>]+>|\{\\[^}]+\}", stash, text)
    translated = translator.translate(protected)
    for i, tag in enumerate(tags):
        translated = translated.replace(f"__TAG{i}__", tag).replace(f"__ TAG{i} __", tag)
    return translated.strip()


def translate_entries(
    entries: list[SubtitleEntry],
    ptbr_normalization: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[SubtitleEntry]:
    _, translate = _imports()
    if not model_installed():
        raise ArgosError("O modelo EN → PT ainda não foi instalado.")
    from_lang = translate.get_language_from_code("en")
    to_lang = translate.get_language_from_code("pt")
    translator = from_lang.get_translation(to_lang)

    cache: dict[str, str] = {}
    result: list[SubtitleEntry] = []
    total = len(entries)
    for i, entry in enumerate(entries, start=1):
        source = entry.text.strip()
        if source in cache:
            text = cache[source]
        else:
            text = _preserve_tags_translate(source, translator)
            if ptbr_normalization:
                text = normalize_ptbr(text)
            cache[source] = text
        result.append(replace(entry, text=text))
        if progress_callback and (i == 1 or i == total or i % 5 == 0):
            progress_callback(i, total)
    return result


def translate_srt(
    source_path: str | Path,
    output_path: str | Path,
    ptbr_normalization: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    entries = read_srt(source_path)
    if not entries:
        raise ArgosError("Não encontrei blocos de legenda válidos no arquivo.")
    translated = translate_entries(entries, ptbr_normalization, progress_callback)
    output = Path(output_path)
    write_srt(output, translated)
    return output
