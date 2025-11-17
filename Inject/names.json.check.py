#!/usr/bin/env python3
"""
check_names.py

Checks the "names" section of a JSON-like file for:
 - JSON parse errors (often caused by missing commas)
 - Missing commas between array entries (line-based heuristic)
 - Duplicate letters used inside parentheses (e.g. "(D)ennis")
 - Duplicate numbers used inside parentheses (e.g. "(1) Dennis")

Usage:
    python check_names.py path/to/file.json
or
    cat file.json | python check_names.py -

If the JSON is invalid (for example because of missing commas), the script will
attempt to locate the "names" array in the raw text and run line-based checks
to help you find the problem lines.
"""

from __future__ import annotations
import argparse
import json
import sys
import re
from collections import defaultdict, Counter
from typing import List, Tuple, Optional


def load_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def try_parse_json(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Try to parse JSON. On success return (obj, None).
    On failure return (None, error_message).
    """
    try:
        obj = json.loads(text)
        return obj, None
    except json.JSONDecodeError as e:
        return None, str(e)


def find_bracket_block(text: str, key: str) -> Optional[Tuple[int, int, str]]:
    """
    Find the bracketed block for a top-level key like "names": [ ... ].
    Returns (start_index_of_block, end_index_exclusive, block_text) or None.
    This function attempts to handle quotes/escapes so it can find the closing
    bracket even when the JSON is syntactically incorrect (e.g. missing commas).
    """
    # find the key
    m = re.search(r'"' + re.escape(key) + r'"\s*:\s*\[', text)
    if not m:
        return None
    start = text.find('[', m.end() - 1)
    if start == -1:
        return None

    i = start
    depth = 0
    in_string = False
    escape = False
    while i < len(text):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    # include the closing bracket
                    end = i + 1
                    return start, end, text[start:end]
        i += 1
    return None


def extract_array_string_entries(block_text: str) -> List[Tuple[str, int, int, str]]:
    """
    From the raw block text (starting with '[' and ending with ']'),
    return a list of tuples (string_value, match_start, match_end, trailing_chars)
    representing each double-quoted string literal found inside the block and the
    characters that follow it on the same line (for comma detection).
    This is a heuristic that works for the typical layout:
        "something",   (maybe trailing spaces)
    Each entry is expected to be on a single line in most cases.
    """
    entries = []
    # Find double-quoted JSON string literals
    # This regex matches the closing quote as well; it doesn't validate escapes fully,
    # but it's good enough for the typical cases here.
    pattern = re.compile(r'"((?:\\.|[^"\\])*)"', re.DOTALL)
    for m in pattern.finditer(block_text):
        s = m.group(1)
        # Determine what characters follow the closing quote on the same line (up to newline)
        after_start = m.end()
        # Find end of line
        nl = block_text.find('\n', after_start)
        if nl == -1:
            nl = len(block_text)
        trailing = block_text[after_start:nl]
        entries.append((s, m.start(), m.end(), trailing))
    return entries


def check_missing_commas_in_block(block_text: str) -> List[Tuple[int, str]]:
    """
    Heuristic: inspect the block line-by-line and report lines that contain a quoted
    string literal but do not have a trailing comma (and are not the last item).
    Returns a list of tuples (line_number, line_text) for suspect lines.
    """
    lines = block_text.splitlines()
    suspects = []
    # We'll detect lines that contain a double-quoted string and determine whether it ends with a comma.
    # Find all lines that look like they have an entry string.
    entry_line_indices = []
    for idx, line in enumerate(lines):
        if '"' in line:
            # crude check to see if it contains a JSON-like quoted string
            # ignore lines that are only brackets
            if re.search(r'"\s*[:\]]', line):  # skip keys or awkward things
                pass
            else:
                # only consider lines with at least one double-quoted string not followed immediately by :
                if re.search(r'"((?:\\.|[^"\\])*)"', line):
                    entry_line_indices.append(idx)
    # For each entry line except the last, check for trailing comma
    for i, idx in enumerate(entry_line_indices):
        if i == len(entry_line_indices) - 1:
            # last entry in the block: it should NOT have a trailing comma (JSON forbids trailing commas)
            # but we won't flag missing comma here; we will flag an unexpected trailing comma later below
            continue
        line = lines[idx]
        # Determine if there is a comma after the closing quote on this line
        # Find the last closing quote on the line
        last_quote = line.rfind('"')
        after = line[last_quote + 1:].strip()
        if not after.startswith(','):
            suspects.append((idx + 1, line))  # human-friendly 1-based line number
    # Also check for unexpected comma on the last entry line (trailing comma)
    if entry_line_indices:
        last_idx = entry_line_indices[-1]
        last_line = lines[last_idx]
        last_quote = last_line.rfind('"')
        after = last_line[last_quote + 1:].strip()
        if after.startswith(','):
            suspects.append((last_idx + 1, last_line))
    return suspects


def analyze_parsed_names(names: List[str]) -> Tuple[dict, dict, List[int]]:
    """
    Given a parsed list of name strings, extract the first parenthesized token
    (if any) from each name and tally letter and numeric tokens. Returns:
      letter_counts: mapping letter -> list of indices (0-based) where it appears
      number_counts: mapping num -> list of indices where it appears
      no_paren_indices: list of indices that had no parenthesized token found
    """
    letter_map = defaultdict(list)
    number_map = defaultdict(list)
    no_paren = []
    paren_pattern = re.compile(r'\(([^)]*)\)')
    for idx, entry in enumerate(names):
        if not isinstance(entry, str):
            no_paren.append(idx)
            continue
        m = paren_pattern.search(entry)
        if not m:
            no_paren.append(idx)
            continue
        token = m.group(1).strip()
        if token == "":
            no_paren.append(idx)
            continue
        # If token is single digit or multi-digit number, treat as number
        if token.isdigit():
            number_map[token].append(idx)
        else:
            # single letter or more: reduce to single letter if length>1? We'll treat the whole token,
            # but commonly it's one letter like "D" or "d".
            # Use lowercase for case-insensitive comparison.
            key = token.lower()
            letter_map[key].append(idx)
    return letter_map, number_map, no_paren


def format_entries_for_report(names: List[str], indices: List[int]) -> List[str]:
    return [f"{i+1}: {names[i]!r}" for i in indices]


def main():
    parser = argparse.ArgumentParser(description="Check the 'names' section for commas and duplicate initials/numbers.")
    parser.add_argument("file", help="JSON file to check, or - to read stdin")
    args = parser.parse_args()

    text = load_text(args.file)
    parsed, err = try_parse_json(text)
    if parsed is None:
        print("JSON parse error:")
        print(err)
        print()
        print("Attempting heuristic analysis on the raw text...")

        block = find_bracket_block(text, "names")
        if not block:
            print("Couldn't locate a 'names' array in the file. Make sure the key is spelled exactly \"names\".")
            sys.exit(2)
        start, end, block_text = block
        print(f"'names' array located at text indices {start}:{end}. Inspecting block lines for missing/extra commas...\n")
        suspects = check_missing_commas_in_block(block_text)
        if suspects:
            print("Suspect lines (line numbers are relative to the 'names' block):")
            for ln, line in suspects:
                print(f"  line {ln}: {line.rstrip()!s}")
            print("\nNotes:")
            print(" - Lines that contain a string entry but do not end with a comma (except the last entry) are flagged.")
            print(" - The last entry in the array should NOT have a trailing comma; if it does, it's flagged.")
        else:
            print("No obvious missing/extra-commas found by the line heuristic.")
        # Also try to extract string entries and analyze duplicated parenthesized tokens from the raw block
        raw_entries = extract_array_string_entries(block_text)
        names_list = [e[0] for e in raw_entries]
        if not names_list:
            print("\nNo string entries were found inside the names block.")
            sys.exit(2)
        print(f"\nFound {len(names_list)} entries inside the 'names' block (heuristic). Checking duplicates...")
        letter_map, number_map, no_paren = analyze_parsed_names(names_list)
        has_any = False
        # letter duplicates
        dup_letters = {k: v for k, v in letter_map.items() if len(v) > 1}
        if dup_letters:
            has_any = True
            print("\nDuplicate letters found (case-insensitive):")
            for k, idxs in sorted(dup_letters.items()):
                entries_text = format_entries_for_report(names_list, idxs)
                print(f"  '{k}' appears {len(idxs)} times in entries:")
                for t in entries_text:
                    print(f"    {t}")
        else:
            print("\nNo duplicate letters found by heuristic.")
        # number duplicates
        dup_numbers = {k: v for k, v in number_map.items() if len(v) > 1}
        if dup_numbers:
            has_any = True
            print("\nDuplicate numbers found:")
            for k, idxs in sorted(dup_numbers.items(), key=lambda iv: iv[0]):
                entries_text = format_entries_for_report(names_list, idxs)
                print(f"  '{k}' appears {len(idxs)} times in entries:")
                for t in entries_text:
                    print(f"    {t}")
        else:
            print("\nNo duplicate numbers found by heuristic.")
        if no_paren:
            print("\nEntries with no parenthesized token detected (indices shown):")
            for i in no_paren:
                print(f"  {i+1}: {names_list[i]!r}")
        if not has_any:
            print("\nNo duplicate initials or numbers detected by the heuristic.")
        print("\nBecause the input JSON failed to parse, please inspect the flagged lines for missing commas or other syntax issues.")
        sys.exit(1)

    # If we reach here, JSON parsed successfully.
    if "names" not in parsed:
        print("The JSON parsed successfully but does not contain a top-level 'names' key.")
        sys.exit(2)

    names = parsed["names"]
    if not isinstance(names, list):
        print("The 'names' key exists but is not an array.")
        sys.exit(2)

    print(f"Parsed JSON successfully. Found {len(names)} 'names' entries.\n")

    # Analyze duplicates
    letter_map, number_map, no_paren = analyze_parsed_names(names)

    dup_letters = {k: v for k, v in letter_map.items() if len(v) > 1}
    dup_numbers = {k: v for k, v in number_map.items() if len(v) > 1}

    if dup_letters:
        print("Duplicate letters (case-insensitive) detected:")
        for k, idxs in sorted(dup_letters.items()):
            print(f"  '{k}' used {len(idxs)} times:")
            for i in idxs:
                print(f"    {i+1}: {names[i]!r}")
    else:
        print("No duplicate letters detected.")

    print()

    if dup_numbers:
        print("Duplicate numbers detected:")
        for k, idxs in sorted(dup_numbers.items(), key=lambda kv: kv[0]):
            print(f"  '{k}' used {len(idxs)} times:")
            for i in idxs:
                print(f"    {i+1}: {names[i]!r}")
    else:
        print("No duplicate numbers detected.")

    print()

    if no_paren:
        print("Entries with no parenthesized token (these may be missing initials/markers):")
        for i in no_paren:
            print(f"  {i+1}: {names[i]!r}")
    else:
        print("All entries contain at least one parenthesized token.")

    # Additional line-based check for missing commas even if JSON parsed (useful for style / trailing comma issues)
    block = find_bracket_block(text, "names")
    if block:
        _, _, block_text = block
        suspects = check_missing_commas_in_block(block_text)
        if suspects:
            print("\nLine-based comma/style issues found in the 'names' block (line numbers relative to block):")
            for ln, line in suspects:
                print(f"  line {ln}: {line.rstrip()!s}")
            print("Note: When JSON parsed successfully, these are usually style issues (like an unexpected trailing comma).")
        else:
            print("\nNo line-based comma/style issues detected in the raw 'names' block.")

    print("\nDone.")


if __name__ == "__main__":
    main()
