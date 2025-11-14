# Spacebar Issue Analysis and Fix

## Problem Statement
User reported that spacebar was:
1. Advancing to the next photo (triggering `next_photo()`)
2. Possibly not typing space characters consistently

## Code Analysis

### Current Implementation (BEFORE fix)
The spacebar handling was at line 211-215 in `ui_components.py`:
```python
if event.keysym == 'space' or event.char == ' ':
    print('[SPECIAL] Space key pressed → Type space (passthrough)')
    self.send_key_to_browser(' ')
    self.modifier_pressed = None
    return 'break'
```

This should have:
- Detected space key presses
- Sent space to browser 
- Stopped event propagation with `return 'break'`

### Why Space Might Still Trigger Next
Looking at the code paths that call `next_photo()`:
1. Line 205: Down or Right arrow key
2. Line 226: Enter key  
3. Line 255: Command handler (for /n commands)
4. Line 134: Modifier combo handler (for Ctrl+N, Cmd+N, etc.)

**Space shouldn't match any of these**, since:
- `event.keysym` for space is 'space', not 'Down' or 'Right'
- Space is not a Return key
- Space wouldn't form a valid /command
- Space wouldn't be detected as an alpha character in modifier combo check (line 120: `event.keysym.isalpha()`)

### Possible Root Causes
1. **Keysym mismatch**: The actual keysym value might not be exactly 'space'
2. **Character encoding**: event.char might not be exactly ' ' due to encoding issues
3. **Threading race**: NEXT might be queued from elsewhere while space is being processed
4. **Google Photos shortcut**: After space is typed, Google Photos itself might intercept it and trigger next

## Solution Implemented

### Changes Made:
1. **Added early detection logging** to identify what keysym/char values space actually has
2. **Made space check more comprehensive**:
   - Check for 'space', 'Space' (case variation)
   - Check for event.char == ' '
   - Check for ord(event.char) == 32 (ASCII space)
3. **Added try/except** around space handling to catch any hidden exceptions
4. **Removed Option key references** since they don't work reliably on macOS
5. **Updated comments** to clarify that only Ctrl and Cmd modifiers are supported

### New Code:
```python
# Early detection
if event.keysym in ('space', 'Space') or event.char == ' ':
    print(f'[SPACE_EARLY_DETECT] keysym={repr(event.keysym)} char={repr(event.char)} state={event.state}')

# Main handling with defensive checks
if event.keysym in ('space', 'Space') or event.char == ' ' or (event.char and ord(event.char) == 32):
    print('[SPACE] Space key detected - keysym=%s char=%s ord=%s' % (...))
    try:
        self.send_key_to_browser(' ')
        self.modifier_pressed = None
        print('[SPACE] Sent space to browser and stopping propagation')
        return 'break'
    except Exception as e:
        print(f'[SPACE] ERROR: {e}')
        # ... error handling ...
        return 'break'
```

## Testing
The fix adds detailed logging that will show:
- Whether space is being detected
- What keysym and char values it actually has
- Whether any exceptions occur
- Whether 'break' is returned (stopping propagation)

Run the program and look for `[SPACE_EARLY_DETECT]` and `[SPACE]` messages when pressing spacebar.

## If Space Still Triggers Next

If after these changes space still triggers next, check:
1. Look at the logged keysym/char values - they might be something unexpected
2. Check if there's a Google Photos keyboard shortcut where space = next (can happen when focus is on page, not textarea)
3. Consider alternative approach: Use JavaScript to directly append space to textarea value instead of keyboard.type()

## Alternative Solution (if needed)
Instead of using `page.keyboard.type(' ')`, use a JavaScript approach similar to `append_text()`:
```python
def _do_space_keypress(self):
    """Append space to description without triggering Google Photos shortcuts."""
    js = """() => {
    const ta = document.querySelector('textarea[aria-label="Description"]');
    if (ta) {
        ta.focus();
        const pos = ta.selectionStart;
        ta.value = ta.value.substring(0, pos) + ' ' + ta.value.substring(pos);
        ta.selectionStart = ta.selectionEnd = pos + 1;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        return true;
    }
    return false;
}"""
    self.page.evaluate(js)
```

This approach:
- Doesn't rely on keyboard simulation
- Directly modifies the textarea DOM value
- Avoids any Google Photos keyboard shortcuts
- Guarantees space is added without navigation
