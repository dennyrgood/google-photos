"""Keystroke handler - extracted from inject_v3.py"""
import json
import os
import re


class KeystrokeHandler:
    """Manages keyboard shortcuts from names.json."""
    
    def __init__(self, browser_controller, names_file=None):
        """Initialize keystroke handler with browser controller and optional names file path."""
        self.browser = browser_controller
        self.names_file = names_file
        self.shortcuts = {}
        self.names_list = []  # Store original names list for UI
        self._load_shortcuts()
    
    def _load_shortcuts(self):
        """Load shortcuts from names.json and register defaults."""
        # Register default navigation shortcuts
        self.shortcuts['n'] = ('next', None)
        self.shortcuts['N'] = ('next', None)
        self.shortcuts['p'] = ('prev', None)
        self.shortcuts['P'] = ('prev', None)
        
        # Register space/add shortcuts
        self.shortcuts['a'] = ('space', None)
        self.shortcuts['A'] = ('space', None)
        self.shortcuts[' '] = ('space', None)
        
        # Load names from names.json
        names = self._load_names()
        self.names_list = names  # Store for UI
        
        for raw in names:
            label = raw
            pushed = ''.join(ch for ch in raw if ch not in '()')
            
            match = re.search(r'\((.)\)', label)
            if match:
                shortcut_key = match.group(1)
                self.shortcuts[shortcut_key.lower()] = ('name', pushed)
                self.shortcuts[shortcut_key.upper()] = ('name', pushed)
                print(f'[KEYSTROKE] Registered shortcut: {shortcut_key} -> {pushed}')
    
    def _load_names(self):
        """Load names from names.json file."""
        names = []
        
        # Try provided path first
        if self.names_file and os.path.exists(self.names_file):
            try:
                with open(self.names_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        names = data.get('names', [])
                    elif isinstance(data, list):
                        names = data
                    print(f'[KEYSTROKE] Loaded {len(names)} names from {self.names_file}')
                    return names
            except Exception as e:
                print(f'[KEYSTROKE] Failed to load {self.names_file}: {e}')
        
        # Try standard locations
        ROOT = os.path.dirname(__file__)
        paths_to_try = [
            os.path.join(ROOT, 'names.json'),
            os.path.join(ROOT, '..', 'poc', 'names.json'),
        ]
        
        for path in paths_to_try:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            names = data.get('names', [])
                        elif isinstance(data, list):
                            names = data
                        if names:
                            print(f'[KEYSTROKE] Loaded {len(names)} names from {path}')
                            return names
                except Exception as e:
                    print(f'[KEYSTROKE] Failed to load {path}: {e}')
        
        # Fallback
        print('[KEYSTROKE] Using fallback names')
        names = ['(D)ennis', '(L)aura', '(B)ekah']
        return names
    
    def on_key_press(self, key):
        """Handle key press event and return action tuple or None."""
        if key in self.shortcuts:
            return self.shortcuts[key]
        
        # Check for backspace key 'x' or 'X'
        if key.lower() == 'x':
            return ('backspace', None)
        
        return None
    
    def get_all_shortcuts(self):
        """Return dict of all registered shortcuts."""
        return self.shortcuts.copy()
    
    def get_names_list(self):
        """Return original names list for UI button creation."""
        return self.names_list.copy()
