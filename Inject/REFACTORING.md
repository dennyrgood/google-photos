# Module Refactoring - inject.py

## New Structure

The monolithic `inject.py` has been refactored into 4 focused modules:

### 1. `browser_controller.py` - BrowserController class
- All Playwright/browser interaction code
- Worker thread and command queue logic
- Methods: `_do_next()`, `_do_prev()`, `_do_append_text()`, `_do_backspace()`, etc.
- No UI code, no keyboard handling
- **Pure browser automation layer**

### 2. `keystroke_handler.py` - KeystrokeHandler class
- Mapping of keys to actions
- `on_key_press()` logic
- Shortcut registration from names.json
- Action dispatch (what happens when each key is pressed)
- Completely independent of UI layout
- **Pure keystroke routing layer**

### 3. `ui_components.py` - AssistantUI class
- Tkinter window setup
- Button creation and layout
- Status labels, frames, text widgets
- Polling and display updates
- Uses KeystrokeHandler for key events
- **Pure UI layer**

### 4. `inject.py` - main.py
- Argument parsing (--debug flag)
- Instantiates and connects the other modules
- `main()` function
- **Minimal glue code**

## Benefits

✓ **Edit keystroke behavior without touching browser or UI code**
  - Change key mappings in `keystroke_handler.py` only

✓ **Could swap out KeystrokeHandler entirely for different key schemes**
  - Create alternative implementations easily

✓ **Easier testing**
  - Test keystroke logic without browser
  - Test browser logic without UI
  - Mock any layer for unit tests

✓ **Browser controller reusable for other interfaces**
  - CLI, web, API, etc. can all use the same BrowserController

✓ **Clear separation of concerns**
  - Each module has one job
  - Easier to understand and maintain

## Usage

```bash
# Standard launch
python3 inject.py

# Debug mode (shows READ and DUMP HTML buttons)
python3 inject.py --debug
```

## Module Dependencies

```
inject.py (main)
├── browser_controller.py
│   └── playwright (external)
├── keystroke_handler.py
│   └── names.json (config)
└── ui_components.py
    └── tkinter (standard library)
    └── keystroke_handler.py
    └── browser_controller.py
```

## Keyboard Shortcuts

### Navigation
- **N** - Next photo
- **P** - Previous photo

### Names (from names.json)
- **D** - Dennis
- **L** - Laura
- **B** - Bekah
- **H** - Sarah
- **S** - Steph
- **T** - Tim
- **C** - Creighton
- **J** - Jeff

### Buttons
- **Add X** - Append "X" to description
- **<< Backspace** - Remove last character
- **READ** (debug only) - Read current description
- **DUMP HTML** (debug only) - Save page HTML to /tmp/google_photos_debug.html
