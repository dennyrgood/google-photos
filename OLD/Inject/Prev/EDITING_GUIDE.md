# Modular Architecture - Where to Edit

This document shows where to make changes for different scenarios.

## To Edit Keystroke Behavior ← THIS IS THE GOAL

**File**: `keystroke_handler.py`

### Add a new keyboard shortcut:
```python
# In _load_shortcuts() method
self.shortcuts['my_key'] = ('my_action', None)
```

### Add a new action type:
```python
# In on_key_press() method
if action_type == 'my_action':
    # Do something
```

### Modify name loading:
```python
# In _load_names() method
# Change path resolution, fallback names, etc.
```

**Benefit**: You can edit keystroke behavior without touching the browser automation code or UI layout.

---

## To Edit Browser Behavior

**File**: `browser_controller.py`

### Modify how the browser interacts with Google Photos:
- Change `_do_next()` / `_do_prev()` click logic
- Modify `_do_append_text()` or `_do_backspace()` 
- Adjust DOM selectors in JavaScript
- Change timeouts or retry logic

**Benefit**: All changes are isolated from keystroke routing and UI.

---

## To Edit the UI

**File**: `ui_components.py`

### Modify the Tkinter interface:
- Change button layout in `_setup_ui()`
- Adjust styling, colors, fonts
- Add/remove UI elements
- Change poll frequency in `poll_browser_state()`

**Benefit**: UI changes don't affect browser automation or keystroke routing.

---

## To Add a New Action

### Example: Add a "SAVE" button that exports description to file

1. **keystroke_handler.py**: Register the shortcut
   ```python
   self.shortcuts['s'] = ('save', None)  # if not already mapped
   ```

2. **browser_controller.py**: Add the action method
   ```python
   def _do_save(self):
       """Save current description to file."""
       # implementation
   
   # Add to command loop in _worker_main()
   elif cmd == 'save':
       self._do_save()
   ```

3. **ui_components.py**: Add a button (optional)
   ```python
   self.save_btn = ttk.Button(btn_frame, text='SAVE', command=self.save, state='disabled')
   self.save_btn.grid(...)
   ```

4. **keystroke_handler.py**: Handle in on_key_press()
   ```python
   # Already routed through keystroke_handler via ('save', None)
   ```

5. **ui_components.py**: Add UI handler
   ```python
   def save(self):
       threading.Thread(target=self.browser.save, daemon=True).start()
   ```

---

## Module Dependencies

```
inject.py (main entry)
  ├── BrowserController
  │   ├── threading
  │   ├── queue
  │   └── playwright
  ├── KeystrokeHandler
  │   ├── json
  │   ├── os
  │   └── re
  └── AssistantUI
      ├── tkinter
      ├── BrowserController
      └── KeystrokeHandler
```

---

## Testing Each Module Independently

```python
# Test BrowserController alone
from browser_controller import BrowserController
browser = BrowserController()
browser._launch_mode = 'default'
browser.start()
browser.goto_next_photo()

# Test KeystrokeHandler alone
from keystroke_handler import KeystrokeHandler
handler = KeystrokeHandler(None)  # Can pass None for browser
action = handler.on_key_press('n')  # Returns ('next', None)

# Test UI without browser
import tkinter as tk
from ui_components import AssistantUI
root = tk.Tk()
app = AssistantUI(root, browser, handler, debug_mode=True)
# UI won't launch browser automatically, just shows interface
```

---

## Key Design Principles

1. **Single Responsibility**: Each module has one job
   - BrowserController: automation
   - KeystrokeHandler: routing
   - AssistantUI: display

2. **Loose Coupling**: Modules communicate through simple interfaces
   - UI calls browser methods via queue
   - UI routes keys through keystroke handler
   - No circular dependencies

3. **Easy Swapping**: Can replace any component
   - Swap KeystrokeHandler for VoiceHandler
   - Swap AssistantUI for CLIui
   - Keep BrowserController for any interface

4. **Testability**: Test each module separately
   - Mock browser for keystroke tests
   - Mock UI for browser tests
   - No hidden dependencies

---

## Original Code Location (inject_v3.py → modules)

| Task | Was in | Now in |
|------|--------|--------|
| Browser init | lines 77-182 | browser_controller.py |
| Page navigation | lines 211-342 | browser_controller.py |
| Textarea finding | lines 344-414 | browser_controller.py |
| Text appending | lines 416-626 | browser_controller.py |
| Backspace logic | lines 627-707 | browser_controller.py |
| Command queue | lines 141-169 | browser_controller.py |
| Public API | lines 708-760 | browser_controller.py |
| Keyboard routing | lines 811-915 | keystroke_handler.py + ui_components.py |
| Names loading | lines 821-848 | keystroke_handler.py |
| UI buttons | lines 774-876 | ui_components.py |
| Event polling | lines 1003-1022 | ui_components.py |
| Window setup | lines 765-876 | ui_components.py |
