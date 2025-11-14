#!/usr/bin/env python3
"""
Keystroke Debugger Utility - Terminal Output Version
Listens to keystrokes and displays hex values to terminal.
Compatible with the Google Photos Tagger codebase.
"""
import tkinter as tk
from tkinter import ttk
import sys


class KeystrokeDebugger:
    """Debug utility to display keystroke information including hex values."""
    
    def __init__(self, root):
        self.root = root
        root.title('Keystroke Debugger - Press Keys Here')
        root.geometry('400x200')
        
        # Main frame
        main = ttk.Frame(root, padding=20)
        main.pack(fill='both', expand=True)
        
        # Instructions
        instructions = ttk.Label(
            main, 
            text='Click in this window and press keys.\n'
                 'Keystroke info will print to terminal.\n\n'
                 'Press Ctrl+Q to quit.',
            font=('Arial', 12),
            justify='center'
        )
        instructions.pack(expand=True)
        
        # Status label
        self.status_label = ttk.Label(
            main,
            text='Waiting for keystrokes...',
            font=('Courier', 10),
            foreground='blue'
        )
        self.status_label.pack(pady=10)
        
        # Bind keyboard events
        root.bind('<KeyPress>', self.on_key_press)
        main.bind('<KeyPress>', self.on_key_press)
        
        # Focus on main frame
        main.focus_set()
        
        # Print header to terminal
        print('=' * 100)
        print('KEYSTROKE DEBUGGER - Press keys in the window to see hex values')
        print('=' * 100)
        print()
    
    def on_key_press(self, event):
        """Handle key press and display detailed information."""
        # Special handling for Ctrl+Q (quit)
        if event.keysym == 'q' and (event.state & 0x04):
            print('\nCtrl+Q pressed - Quitting...\n')
            self.root.quit()
            return 'break'
        
        # Extract key information
        keysym = event.keysym
        char = event.char
        keycode = event.keycode
        state = event.state
        
        # Determine modifiers
        modifiers = []
        if state & 0x01:
            modifiers.append('Shift')
        if state & 0x04:
            modifiers.append('Ctrl')
        if state & 0x08:
            modifiers.append('Alt')
        if state & 0x10:
            modifiers.append('NumLock')
        if state & 0x20:
            modifiers.append('Cmd/Meta')
        
        modifier_str = '+'.join(modifiers) if modifiers else 'None'
        
        # Print to terminal
        print('-' * 100)
        print(f'keysym:    {keysym!r}')
        print(f'char:      {char!r}')
        print(f'keycode:   {keycode} (0x{keycode:04x})')
        print(f'state:     {state} (0x{state:02x})')
        print(f'modifiers: {modifier_str}')
        
        # Hex values for char
        if char:
            hex_values = ' '.join([f'0x{ord(c):04x}' for c in char])
            dec_values = ' '.join([str(ord(c)) for c in char])
            print(f'char hex:  {hex_values}')
            print(f'char dec:  {dec_values}')
            
            # Character info
            if len(char) == 1:
                print(f'char info: U+{ord(char):04X} ({self.char_description(char)})')
        
        # Hex values for keysym
        keysym_hex = ' '.join([f'0x{ord(c):04x}' for c in keysym])
        print(f'keysym hex: {keysym_hex}')
        print()
        sys.stdout.flush()
        
        # Update status in window
        display = f'Last key: {keysym!r}'
        if char and char != keysym:
            display += f' (char: {char!r})'
        if modifiers:
            display = f'{modifier_str}+{keysym!r}'
        self.status_label.config(text=display)
        
        return 'break'
    
    def char_description(self, char):
        """Get a description of the character."""
        c = ord(char)
        
        if c == 32:
            return 'SPACE'
        elif c == 9:
            return 'TAB'
        elif c == 10:
            return 'LINE FEED'
        elif c == 13:
            return 'CARRIAGE RETURN'
        elif c < 32:
            return f'CONTROL CHARACTER'
        elif 32 < c < 127:
            return f'ASCII printable'
        elif c == 127:
            return 'DELETE'
        elif c < 256:
            return f'Extended ASCII'
        else:
            return f'Unicode character'


def main():
    """Main entry point."""
    print('\nKeystroke Debugger started.')
    print('A window will open - click in it and press keys.')
    print('Keystroke information will print here in the terminal.')
    print('Press Ctrl+Q in the window to quit.\n')
    
    root = tk.Tk()
    app = KeystrokeDebugger(root)
    
    root.mainloop()
    
    print('\nKeystroke Debugger stopped.\n')


if __name__ == '__main__':
    main()
