#!/usr/bin/env python3
"""
Google Photos description tagger with old device spoofing
- Launch browser with different user agent modes
- Navigate photos (next/prev with keyboard)
- Read current description
- Append names to description
- Backspace functionality
- Show current photo URL and description
"""
import argparse
import tkinter as tk
from browser_controller import BrowserController
from keystroke_handler import KeystrokeHandler
from ui_components import AssistantUI


# Parse command line arguments
parser = argparse.ArgumentParser(description='Google Photos Tagger')
parser.add_argument('--debug', action='store_true', help='Enable debug mode (shows READ and DUMP HTML buttons)')
args = parser.parse_args()
DEBUG_MODE = args.debug


def main():
    # Create components
    browser = BrowserController()
    keystroke = KeystrokeHandler(browser)
    
    # Create UI
    root = tk.Tk()
    app = AssistantUI(root, browser, keystroke, debug_mode=DEBUG_MODE)
    
    # Setup shutdown
    root.protocol('WM_DELETE_WINDOW', app.shutdown)
    
    # Auto-launch browser at startup
    root.after(500, lambda: app.launch_with_mode('default'))
    
    # Run
    root.mainloop()


if __name__ == '__main__':
    main()
