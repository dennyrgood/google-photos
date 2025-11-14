# Key Handling Architecture Change

## Overview

The keystroke handling system has been redesigned from a "shortcut-first" model to a "passthrough-first" model with optional shortcuts via the OPTION modifier.

## Before: Shortcut-First Model

```
User Input
    ↓
KeystrokeHandler.on_key_press(key)
    ↓
    ├─ Shortcut registered? → Execute Action
    └─ Unregistered? → Ignore / Print warning
```

**Behavior:**
- Only registered shortcuts work
- All other input ignored
- No free-form typing capability

## After: Passthrough-First Model

```
User Input
    ↓
UI.on_key_press(event)
    ↓
    Extract OPTION modifier from event.state
    ↓
KeystrokeHandler.on_key_press(key, option_pressed)
    ↓
    ├─ option_pressed=True?
    │  ├─ Shortcut registered? → Return ('action_type', data)
    │  └─ Not registered? → Return None
    │
    └─ option_pressed=False?
       └─ Always return ('passthrough', key)
           ↓
           UI.send_key_to_browser(key)
           ↓
           BrowserController.send_key_to_browser(key)
           ↓
           Queue Command: ('key_passthrough', key)
           ↓
           Worker Thread: page.keyboard.type(key)
           ↓
           Browser: Character appears in description field
```

**Behavior:**
- Unmodified keystrokes pass through to browser
- OPTION+key triggers registered shortcuts
- OPTION+other combinations → silent (ignored)
- Any key can be typed in description field

## State Diagram

```
    ┌─────────────────────────────────────┐
    │   Python Window Has Focus           │
    │   Google Photos in Browser Window   │
    └─────────────────────────────────────┘
                    ↓
            Key Pressed in Python
                    ↓
        ┌───────────────────────────┐
        │ OPTION Modifier Pressed?  │
        └───────────────────────────┘
               ↙                ↘
            YES                NO
             ↓                  ↓
    Check Shortcuts       Passthrough
         ↓                  ↓
    ┌────────┐      Send to Browser
    │  N  = │         ↓
    │ NEXT  │   page.keyboard.type()
    └────────┘         ↓
                  Appears in
                   Description
```

## Command Queue Integration

### Before
```python
# Direct action execution
if key == 'n':
    browser.goto_next_photo()
```

### After
```python
# Queue-based passthrough
self._cmd_queue.put(('key_passthrough', 'n'))

# In worker thread:
elif cmd == 'key_passthrough':
    self._do_key_passthrough(arg)  # page.keyboard.type('n')
```

**Benefit:** Consistent queuing for all operations, no race conditions

## Keystroke Handler Logic

### Method Signature Change

**Before:**
```python
def on_key_press(self, key):
    if key in self.shortcuts:
        return self.shortcuts[key]
    # ...
    return None
```

**After:**
```python
def on_key_press(self, key, option_pressed=False):
    if option_pressed:
        if key in self.shortcuts:
            return self.shortcuts[key]
        if key.lower() == 'x':
            return ('backspace', None)
        return None
    
    # No OPTION - always passthrough
    return ('passthrough', key)
```

### Return Values

| Scenario | Return Value |
|----------|--------------|
| OPTION+N pressed | `('next', None)` |
| OPTION+D pressed | `('name', 'Dennis ')` |
| OPTION+X pressed | `('backspace', None)` |
| Regular 'd' pressed | `('passthrough', 'd')` |
| Regular 'enter' pressed | `('passthrough', '\n')` |
| OPTION+unknown | `None` |

## UI Event Handling

### Event Object Extraction

```python
# Check for OPTION modifier (macOS)
option_pressed = (event.state & 0x20) != 0

# event.state is a bitmask:
# 0x20 = OPTION/ALT on macOS
# 0x04 = CTRL on all platforms
# 0x01 = SHIFT on all platforms
```

### Action Routing

```python
action = self.keystroke.on_key_press(key, option_pressed=option_pressed)

if action:
    action_type, action_data = action
    
    if action_type == 'next':
        self.next_photo()
    elif action_type == 'passthrough':
        self.send_key_to_browser(action_data)  # ← NEW
    # ... other actions
```

## Browser Controller Extension

### New Public Method

```python
def send_key_to_browser(self, key):
    """Queue key passthrough to browser - send keystroke directly to page."""
    if not self._running:
        raise RuntimeError('Browser not running')
    self._cmd_queue.put(('key_passthrough', key))
```

### New Private Handler

```python
def _do_key_passthrough(self, key):
    """Send a keystroke directly to the browser page."""
    if not self.page:
        return
    try:
        print(f'[KEY_PASSTHROUGH] Typing: {repr(key)}')
        self.page.keyboard.type(key)
    except Exception as e:
        print(f'[KEY_PASSTHROUGH] ERROR: {e}')
```

### Command Queue Integration

Added to `_worker_main()` command loop:
```python
elif cmd == 'key_passthrough':
    self._do_key_passthrough(arg)
```

## Special Cases

### 1. Unmodified Keys While Browser Running

```
'a' pressed (no OPTION)
    ↓
keystroke.on_key_press('a', option_pressed=False)
    ↓
returns ('passthrough', 'a')
    ↓
UI: self.send_key_to_browser('a')
    ↓
Browser: 'a' typed in description
```

### 2. Shortcut with OPTION

```
OPTION+D pressed
    ↓
keystroke.on_key_press('d', option_pressed=True)
    ↓
'd' in self.shortcuts?  YES
    ↓
returns ('name', 'Dennis ')
    ↓
UI: self.add_name('Dennis ')
    ↓
Browser: " Dennis " appended
```

### 3. Browser Not Running

```
'a' pressed
    ↓
UI checks: if not self.browser._running: return
    ↓
Print warning, ignore keystroke
```

## Testing the New System

### Test Case 1: Free-form Typing
```python
# Type "hello world" without OPTION
# Expected: All characters pass through to browser
# Result: Description field shows "hello world"
```

### Test Case 2: Name Shortcut
```python
# Press OPTION+D
# Expected: ('name', 'Dennis ') returned
# Result: "Dennis " added to description
```

### Test Case 3: Navigation
```python
# Press OPTION+N
# Expected: ('next', None) returned
# Result: Move to next photo
```

### Test Case 4: Backspace
```python
# Press OPTION+X
# Expected: ('backspace', None) returned
# Result: Remove last character
```

## Performance Implications

### Positive
- ✓ Fewer function calls for normal typing
- ✓ Consistent queue-based approach
- ✓ No special-casing needed

### No Change
- Queue processing still 0.5ms interval
- Same threading model
- Same browser automation

## Security Considerations

### Keystroke Passthrough
- ✓ Only passes to focused Playwright browser page
- ✓ Cannot affect system outside browser
- ✓ Browser must be launched and focused first
- ✓ No shell injection or system command access

### OPTION Modifier Detection
- ✓ Event.state is from Tkinter event object
- ✓ Cannot be spoofed from outside
- ✓ Only works when Tkinter window has focus

## Migration Notes

If switching from old system to this new system:

1. **Documentation**: Update all user docs to use OPTION modifier
2. **Training**: Explain passthrough-first model
3. **Testing**: Verify all special shortcuts still work with OPTION
4. **Backward Compatibility**: None - this is a breaking change

## Future Enhancements

See FUTURE_IMPROVEMENTS.md for suggestions on:
- Configurable modifier keys
- Key blocking list
- Platform-specific detection
- Macro support
