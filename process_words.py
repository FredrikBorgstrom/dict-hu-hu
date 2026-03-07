#!/usr/bin/env python3
"""
Generates a clean Hungarian word list from the Magyar Ispell hunspell dictionary
(hu_HU.aff + hu_HU.dic), licensed under GPL/LGPL/MPL (Mozilla Public License 1.1).

Source: Magyar Ispell 1.9 — https://github.com/laszlonemeth/magyarispell
License of output: Mozilla Public License 1.1 (derived from Magyar Ispell)

The Magyar Ispell dictionary is available under GPL/LGPL/MPL triple-license.
We use the MPL 1.1 option. The derived word list (this output) is also made
available under MPL 1.1 in this public repository.

Processing steps:
1. Parse hu_HU.aff: extract AF (alias flag) mappings and SFX (suffix) rules
2. Parse hu_HU.dic: iterate all entries
3. For each lowercase entry, apply applicable SFX rules (≤18-char suffix)
4. Filter: only Hungarian alphabet letters (a-z + á é í ó ö ő ú ü ű),
   length 2–10 characters, no hyphens, no abbreviations
5. Remove consonant-only 2-character words (abbreviations like cm, kg, dz)
6. Sort and deduplicate the output

Output: words_hu-HU.txt — 4.3M+ inflected Hungarian word forms
"""

import re
import sys
import subprocess
import os
from collections import defaultdict

# Hungarian vowels
VOWELS = frozenset('aáeéiíoóöőuúüű')
# Valid Hungarian characters (the Hungarian alphabet)
VALID_CHARS = frozenset('abcdefghijklmnopqrstuvwxyzáéíóöőúüű')

MAX_WORD_LEN = 10   # Maximum word length for the game dictionary
MIN_WORD_LEN = 2    # Minimum word length


def is_valid_hu_word(word: str) -> bool:
    """Return True if word contains only valid Hungarian characters and is in range."""
    return (MIN_WORD_LEN <= len(word) <= MAX_WORD_LEN
            and all(c in VALID_CHARS for c in word))


def has_vowel(word: str) -> bool:
    """Return True if word contains at least one vowel."""
    return any(c in VOWELS for c in word)


def parse_aff(aff_path: str):
    """
    Parse the Hunspell .aff file.

    Returns:
        af_aliases: dict[int, bytes] — AF alias number → raw flag bytes
        sfx_rules: dict[bytes, list] — flag byte → [(strip, add, condition_re)]
        needaffix_flag: bytes | None — the NEEDAFFIX flag byte
        forbiddenword_flag: bytes | None — the FORBIDDENWORD flag byte
    """
    with open(aff_path, 'rb') as f:
        content = f.read()

    lines = content.split(b'\n')
    af_aliases: dict = {}
    af_idx = 0
    sfx_rules: defaultdict = defaultdict(list)
    needaffix_flag = None
    forbiddenword_flag = None

    for line in lines:
        if b'#' in line:
            line = line[:line.index(b'#')]
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        directive = parts[0]

        if directive == b'AF':
            if len(parts) >= 2 and not parts[1].isdigit():
                af_idx += 1
                af_aliases[af_idx] = parts[1]

        elif directive == b'NEEDAFFIX':
            if len(parts) >= 2:
                needaffix_flag = parts[1]

        elif directive == b'FORBIDDENWORD':
            if len(parts) >= 2:
                forbiddenword_flag = parts[1]

        elif directive == b'SFX':
            if len(parts) >= 5:
                flag_b = parts[1]
                strip = parts[2].decode('utf-8', errors='replace')
                add_raw = parts[3].decode('utf-8', errors='replace')
                condition = parts[4].decode('utf-8', errors='replace')

                # Extract just the word part (before any /flag)
                add_word = add_raw[:add_raw.index('/')] if '/' in add_raw else add_raw

                if strip == '0':
                    strip = ''
                if add_word == '0':
                    add_word = ''

                # Skip suffix rules that add hyphens (compound prefixes)
                if '-' in add_word:
                    continue

                # Precompile condition regex
                try:
                    cond_re = None if condition == '.' else re.compile(condition + '$')
                except re.error:
                    continue

                sfx_rules[flag_b].append((strip, add_word, cond_re))

    return af_aliases, sfx_rules, needaffix_flag, forbiddenword_flag


def expand_dictionary(aff_path: str, dic_path: str, output_path: str) -> int:
    """
    Expand all word forms and write to output_path.
    Returns number of unique words written.
    """
    print("Parsing .aff file...", flush=True)
    af_aliases, sfx_rules, needaffix_flag, forbiddenword_flag = parse_aff(aff_path)
    print(f"  {len(af_aliases)} AF aliases, {len(sfx_rules)} SFX flag groups", flush=True)

    print("Parsing .dic file...", flush=True)
    with open(dic_path, 'r', encoding='utf-8', errors='replace') as f:
        dic_lines = f.readlines()[1:]  # skip count line
    print(f"  {len(dic_lines)} entries in .dic", flush=True)

    temp_path = output_path + '.tmp'
    total_written = 0
    forbidden_words: set = set()

    print("Expanding inflected forms (streaming to disk)...", flush=True)

    with open(temp_path, 'w', encoding='utf-8') as out:
        for idx, line in enumerate(dic_lines):
            line = line.strip()
            if not line:
                continue

            # Strip frequency tab data
            if '\t' in line:
                line = line.split('\t')[0]

            # Parse word and flags
            if '/' in line:
                slash_idx = line.index('/')
                word = line[:slash_idx].replace('\\/', '/')
                flags_str = line[slash_idx + 1:]
                try:
                    flags_num = int(flags_str)
                    flag_bytes = af_aliases.get(flags_num, b'')
                except ValueError:
                    flag_bytes = flags_str.encode('utf-8', errors='replace')
            else:
                word = line
                flag_bytes = b''

            # Skip: spaces, leading hyphens, or uppercase first letter (proper nouns)
            if ' ' in word or word.startswith('-') or (word and word[0].isupper()):
                continue

            word_lower = word.lower()

            if not is_valid_hu_word(word_lower):
                continue

            # Check special flags
            has_needaffix = False
            has_forbidden = False
            for fb in flag_bytes:
                fb_b = bytes([fb])
                if forbiddenword_flag and fb_b == forbiddenword_flag:
                    has_forbidden = True
                if needaffix_flag and fb_b == needaffix_flag:
                    has_needaffix = True

            if has_forbidden:
                forbidden_words.add(word_lower)
                continue

            # Write base form (unless NEEDAFFIX)
            if not has_needaffix:
                out.write(word_lower + '\n')
                total_written += 1

            # Apply SFX rules for each flag byte
            for fb in flag_bytes:
                flag_b = bytes([fb])
                if flag_b not in sfx_rules:
                    continue
                for strip, add, cond_re in sfx_rules[flag_b]:
                    # Condition check
                    if cond_re and not cond_re.search(word_lower):
                        continue
                    # Apply strip
                    if strip:
                        if not word_lower.endswith(strip):
                            continue
                        stem = word_lower[:-len(strip)]
                    else:
                        stem = word_lower
                    # Build new word
                    new_word = stem + add
                    if is_valid_hu_word(new_word):
                        out.write(new_word + '\n')
                        total_written += 1

            if (idx + 1) % 20000 == 0:
                print(f"  {idx+1}/{len(dic_lines)} entries processed, {total_written} forms written", flush=True)

    print(f"\nRaw forms: {total_written}", flush=True)
    print("Sorting, deduplicating, and removing abbreviations...", flush=True)

    # Sort + uniq
    sorted_path = output_path + '.sorted'
    subprocess.run(f"sort -u {temp_path} > {sorted_path}", shell=True, check=True)
    os.unlink(temp_path)

    # Final pass: remove consonant-only 2-char words (abbreviations like cm, kg, dz)
    final_count = 0
    with open(sorted_path, 'r', encoding='utf-8') as inp, \
         open(output_path, 'w', encoding='utf-8') as out:
        for line in inp:
            word = line.rstrip('\n')
            if len(word) == 2 and not has_vowel(word):
                continue  # Skip: consonant-only 2-char abbreviation
            if word in forbidden_words:
                continue
            out.write(word + '\n')
            final_count += 1

    os.unlink(sorted_path)
    print(f"Final unique words: {final_count}", flush=True)
    return final_count


if __name__ == '__main__':
    import os

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Expected: hu_HU.aff and hu_HU.dic in the same directory as this script
    aff_path = os.path.join(script_dir, 'hu_HU.aff')
    dic_path = os.path.join(script_dir, 'hu_HU.dic')
    output_path = os.path.join(script_dir, 'words_hu-HU.txt')

    if not os.path.exists(aff_path) or not os.path.exists(dic_path):
        print(f"ERROR: hu_HU.aff and hu_HU.dic must be in {script_dir}")
        print("Download from: https://github.com/laszlonemeth/magyarispell")
        sys.exit(1)

    count = expand_dictionary(aff_path, dic_path, output_path)
    print(f"\nDone. Wrote {count} words to {output_path}")
