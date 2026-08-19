import tempfile
import unittest
from pathlib import Path

from core.subtitles import (
    SubtitleEntry, apply_safe_fixes, normalize_ptbr, parse_timestamp,
    format_timestamp, quick_review, read_srt, write_srt,
)


class SubtitleTests(unittest.TestCase):
    def test_timestamp_roundtrip(self):
        value = "01:02:03,456"
        self.assertEqual(format_timestamp(parse_timestamp(value)), value)

    def test_read_write_roundtrip(self):
        entries = [
            SubtitleEntry(1, 1000, 2500, "Olá!"),
            SubtitleEntry(2, 3000, 4500, "Tudo bem?"),
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.srt"
            write_srt(path, entries)
            loaded = read_srt(path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[1].text, "Tudo bem?")

    def test_quick_review_finds_english(self):
        entries = [SubtitleEntry(1, 0, 2000, "What are you doing here?")]
        issues = quick_review(entries)
        self.assertTrue(any(i["category"] == "Tradução" for i in issues))

    def test_safe_fix(self):
        entries = [SubtitleEntry(1, 0, 2000, "Olá  ,como vai?")]
        fixed, count = apply_safe_fixes(entries)
        self.assertEqual(count, 1)
        self.assertEqual(fixed[0].text, "Olá, como vai?")

    def test_ptbr_normalization(self):
        text = "Abra o ficheiro no ecrã do telemóvel."
        out = normalize_ptbr(text)
        self.assertIn("arquivo", out.lower())
        self.assertIn("tela", out.lower())
        self.assertIn("celular", out.lower())


if __name__ == "__main__":
    unittest.main()
