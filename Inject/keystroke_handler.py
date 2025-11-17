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
    
    def reload_shortcuts(self):
        """Reload shortcuts from names.json file."""
        self.shortcuts = {}
        self.names_list = []
        self._load_shortcuts()
        print(f'[KEYSTROKE] Reloaded {len(self.names_list)} names from file')
        return self.names_list
    
    def _load_shortcuts(self):
        """Load shortcuts from names.json and register defaults."""
        # Arrow keys for navigation
        self.shortcuts['Left'] = ('prev', None)
        self.shortcuts['Right'] = ('next', None)
        
        # Delete all shortcut
        self.shortcuts['='] = ('delete_all', None)

        # Cursor to end DHM
        self.shortcuts['-'] = ('cursor_to_end', None)
        
        # Tab to add "Dennis " and go next
        self.shortcuts['Tab'] = ('tab_dennis', None)
        
        # Note: n, N, p, P are NOT registered - they pass through as natural keystrokes
        
        # Load names from names.json
        names = self._load_names()
        self.names_list = names  # Store for UI

        # Map shifted number keys to their unshifted counterparts
        SHIFTED_NUMBER_MAP = {
            '!': '1',
            '@': '2',
            '#': '3',
            '$': '4',
            '%': '5',
            '^': '6',
            '&': '7',
            '*': '8',
            '(': '9',
            ')': '0'
        }
        
        for raw in names:
            label = raw
            pushed = ''.join(ch for ch in raw if ch not in '()')
            
            match = re.search(r'\((.)\)', label)
            if match:
                shortcut_key = match.group(1)
                # Register Ctrl+lowercase -> just add name
                self.shortcuts[(shortcut_key.lower(), 'ctrl')] = ('name', pushed)
                # Register Ctrl+UPPERCASE -> add name and advance
                self.shortcuts[(shortcut_key.upper(), 'ctrl')] = ('name_and_next', pushed)
                print(f'[KEYSTROKE] Registered Ctrl+{shortcut_key.lower()} -> {pushed}')
                print(f'[KEYSTROKE] Registered Ctrl+{shortcut_key.upper()} -> {pushed} + NEXT')
            
            # Extract numbered groups like "(1) Dennis Laura " and strip numeric prefix
            num_match = re.search(r'\((\d+)\)', label)
            if num_match:
                group_num = num_match.group(1)
                # Strip the numeric prefix from the label first, then remove parentheses
                stripped_label = re.sub(r'^\(\d+\)\s*', '', label).strip()
                if stripped_label:  # Only register if there's content after stripping
                    # Register Ctrl+number and just number -> just add name
                    self.shortcuts[(group_num, 'ctrl')] = ('name', stripped_label + ' ')
                    self.shortcuts[group_num] = ('name', stripped_label + ' ')
                    print(f'[KEYSTROKE] Registered {group_num} -> {stripped_label} (stripped)')
                    
                    # Register shifted version -> add name and advance
                    shifted_symbol = [k for k, v in SHIFTED_NUMBER_MAP.items() if v == group_num]
                    if shifted_symbol:
                        self.shortcuts[shifted_symbol[0]] = ('name_and_next', stripped_label + ' ')
                        print(f'[KEYSTROKE] Registered {shifted_symbol[0]} -> {stripped_label} + NEXT')
                else:
                    # Empty group, register as-is
                    self.shortcuts[(group_num, 'ctrl')] = ('name', pushed)
                    self.shortcuts[group_num] = ('name', pushed)
                    print(f'[KEYSTROKE] Registered {group_num} -> (empty)')
    
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
    
    def on_key_press(self, key, ctrl=False, state=0, keycode=None, keysym=None):
        """Handle key press event and return action tuple or None.
        
        Args:
            key: The key character or name (e.g., '1', 'd', 'BackSpace', 'Delete')
            ctrl: Boolean indicating if Ctrl modifier is pressed
            state: Raw event state bitmask for detecting Fn+Delete on Mac
            keycode: Numeric keycode (e.g., 0x33 for backspace, 0x77 for delete all)
            keysym: Tkinter keysym name (e.g., 'BackSpace', 'Delete')
        
        Returns:
            Tuple of (action_type, action_data) or None
        """
        # Handle BackSpace and Delete keysyms FIRST (most reliable, before keycode)
        if keysym == 'BackSpace':
            print('[DELETE_TYPE] BackSpace key detected - deleting one char')
            return ('backspace', None)
        elif keysym == 'Delete':
            print('[DELETE_TYPE] Delete key detected - clearing entire description')
            return ('delete_all', None)
        
        # Try direct lookup first (before keycode, to avoid '3' being confused with 0x33 keycode)
        if key in self.shortcuts:
            return self.shortcuts[key]
        
        # Try Ctrl+ combination
        if ctrl:
            ctrl_key = (key, 'ctrl')
            if ctrl_key in self.shortcuts:
                return self.shortcuts[ctrl_key]
        
        # No match found - return None for natural typing
        return None
    
    def get_all_shortcuts(self):
        """Return dict of all registered shortcuts."""
        return self.shortcuts.copy()
    
    def get_names_list(self):
        """Return original names list for UI button creation."""
        return self.names_list.copy()
