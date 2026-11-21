"""
keywords.py – Loading and matching PHI keywords via plain text, EXACT, or REGEX rules.
"""

import os
import re


class KeywordMatcher:
    def __init__(self, filepath: str = ""):
        self.matchers = []
        if filepath:
            self.load(filepath)

    def load(self, filepath: str):
        if not os.path.exists(filepath):
            print(f"[INFO] No keywords file found at {filepath} — matching disabled.")
            self.matchers = []
            return

        matchers = []
        with open(filepath, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue

                if line.upper().startswith("REGEX:"):
                    pattern = line[6:].strip()
                    try:
                        compiled = re.compile(pattern, re.IGNORECASE)
                        matchers.append(
                            ("regex", pattern, lambda w, c=compiled: bool(c.search(w)))
                        )
                    except re.error as e:
                        print(f"  [WARN] Bad regex in keywords file: {pattern!r} → {e}")

                elif line.upper().startswith("EXACT:"):
                    token = line[6:].strip()
                    compiled = re.compile(
                        r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
                        re.IGNORECASE,
                    )
                    matchers.append(
                        ("exact", token, lambda w, c=compiled: bool(c.search(w)))
                    )

                else:
                    needle = line.lower()
                    matchers.append(
                        ("contains", needle, lambda w, n=needle: n in w.lower())
                    )

        self.matchers = matchers
        print(f"[INFO] Loaded {len(self.matchers)} PHI keyword matcher(s) from {filepath}")

    def matches(self, word_str: str) -> bool:
        w = word_str.strip()
        if not w or not self.matchers:
            return False
        return any(fn(w) for _, _, fn in self.matchers)