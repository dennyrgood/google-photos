#!/usr/bin/env python3
"""
Analyze Google Photos HTML dumps to find textarea elements and their properties.
Usage: python analyze_dump.py gphotos_dump_1762913731.html
"""
import sys
import os
from html.parser import HTMLParser
import json


class TextareaFinder(HTMLParser):
    """Find and analyze textarea elements in HTML."""
    
    def __init__(self):
        super().__init__()
        self.textareas = []
        self.current_textarea = None
        self.in_textarea = False
        
    def handle_starttag(self, tag, attrs):
        if tag == 'textarea':
            self.in_textarea = True
            attrs_dict = dict(attrs)
            self.current_textarea = {
                'tag': 'textarea',
                'attrs': attrs_dict,
                'aria-label': attrs_dict.get('aria-label', ''),
                'placeholder': attrs_dict.get('placeholder', ''),
                'id': attrs_dict.get('id', ''),
                'class': attrs_dict.get('class', ''),
                'value': ''
            }
    
    def handle_endtag(self, tag):
        if tag == 'textarea' and self.in_textarea:
            self.textareas.append(self.current_textarea)
            self.current_textarea = None
            self.in_textarea = False
    
    def handle_data(self, data):
        if self.in_textarea and self.current_textarea:
            self.current_textarea['value'] += data


def analyze_dump(filename):
    """Analyze an HTML dump file."""
    
    if not os.path.exists(filename):
        print(f"ERROR: File not found: {filename}")
        return
    
    print(f"\n{'='*80}")
    print(f"Analyzing: {filename}")
    print(f"{'='*80}\n")
    
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    
    # Find textareas
    parser = TextareaFinder()
    parser.feed(html)
    
    print(f"Found {len(parser.textareas)} textarea elements:\n")
    
    description_textareas = []
    
    for i, ta in enumerate(parser.textareas):
        aria_label = ta['aria-label']
        placeholder = ta['placeholder']
        value = ta['value'].strip()
        
        print(f"Textarea #{i}:")
        print(f"  aria-label: {repr(aria_label)}")
        print(f"  placeholder: {repr(placeholder)}")
        print(f"  value: {repr(value[:100])}")
        print(f"  id: {repr(ta['id'])}")
        print(f"  class: {repr(ta['class'][:80])}")
        
        if aria_label == 'Description':
            description_textareas.append({
                'index': i,
                'value': value,
                'placeholder': placeholder,
                'id': ta['id'],
                'class': ta['class']
            })
            print("  *** THIS IS A DESCRIPTION TEXTAREA ***")
        
        print()
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY:")
    print(f"{'='*80}")
    print(f"Total textareas: {len(parser.textareas)}")
    print(f"Description textareas: {len(description_textareas)}")
    
    if description_textareas:
        print("\nDescription textarea values:")
        for dt in description_textareas:
            status = "EMPTY" if not dt['value'] else f"'{dt['value'][:50]}'"
            print(f"  Index {dt['index']}: {status}")
    
    # Look for common class patterns
    if description_textareas:
        print("\nClass patterns in description textareas:")
        all_classes = set()
        for dt in description_textareas:
            classes = dt['class'].split()
            all_classes.update(classes)
        
        for cls in sorted(all_classes):
            if cls:
                print(f"  .{cls}")
    
    # Check for unique IDs
    print("\nUnique identifiers:")
    ids_found = [ta['id'] for ta in parser.textareas if ta['id']]
    if ids_found:
        for id_val in ids_found:
            print(f"  #{id_val}")
    else:
        print("  (No IDs found)")
    
    print(f"\n{'='*80}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_dump.py <html_dump_file>")
        print("\nExample:")
        print("  python analyze_dump.py gphotos_dump_1762913731.html")
        print("\nOr analyze all dumps in current directory:")
        print("  python analyze_dump.py *.html")
        sys.exit(1)
    
    # Handle wildcards by analyzing all provided files
    for filename in sys.argv[1:]:
        if os.path.isfile(filename):
            analyze_dump(filename)
        else:
            print(f"Skipping (not a file): {filename}")


if __name__ == '__main__':
    main()
