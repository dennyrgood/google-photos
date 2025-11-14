# Quick Testing Guide

## Run the Application
```bash
python3 inject.py --debug
```

## Test Cases

### A. Space Key (Most Critical Fix)
**Expected**: Type spaces between words without navigation
```
1. Type: a b c d e
2. Expected Result: "a b c d e" in description
3. No navigation should occur
4. No duplicate focus messages
```

### B. Single Backspace
**Expected**: Delete one character from end
```
1. Type: hello
2. Press Backspace
3. Expected: "hell"
4. Logs should show: "[SPECIAL] BackSpace key pressed"
```

### C. Shift+Backspace (Important Fix)
**Expected**: Clear entire field with 50 deletions
```
1. Type: this is a very long description that needs to be cleared
2. Press Shift+Backspace
3. Expected: Field completely empty
4. Logs should show: "[SPECIAL] Shift+BackSpace pressed → Clear entire description"
5. Look for: "[SHIFT_DELETE] Clearing description field (50 deletes)"
```

### D. Ctrl+Backspace (New Support)
**Expected**: Clear field (same as Shift+Backspace)
```
1. Type: test text
2. Press Ctrl+Backspace
3. Expected: Field completely empty
4. Logs should show: "[SPECIAL] Ctrl+BackSpace pressed"
```

### E. Cmd+Backspace (macOS)
**Expected**: Clear field (same as Shift+Backspace)
```
1. Type: some content
2. Press Cmd+Backspace
3. Expected: Field completely empty
4. Logs should show: "[SPECIAL] Cmd+BackSpace pressed"
```

### F. Delete Key (Single Delete)
**Expected**: Delete one character from end
```
1. Type: testing
2. Press Delete
3. Expected: "testin"
4. Logs should show: "[SPECIAL] Delete key pressed"
```

### G. Shift+Delete (Important Fix)
**Expected**: Clear entire field
```
1. Type: long text here
2. Press Shift+Delete
3. Expected: Field completely empty
4. Logs should show: "[SPECIAL] Shift+Delete pressed"
```

### H. Navigation (Unchanged, but verify still works)
**Expected**: Still works with no regression
```
Test: Up Arrow → Previous photo
Test: Down Arrow → Next photo
Test: Left Arrow → Previous photo
Test: Right Arrow → Next photo
Test: Enter → Next photo
```

### I. Tab, Comma, Period (Unchanged, but verify)
```
Test: Tab → Add "Dennis "
Test: Comma → Add ", "
Test: Period → Add ". "
```

### J. Rapid Typing with Spaces
**Expected**: All characters appear including spaces
```
1. Type quickly: "this is a test"
2. Expected: All characters including spaces appear
3. No navigation should occur
4. All characters should be in order
```

## Log Analysis

### Good Signs ✓
```
[KEY_DEBUG] keysym=BackSpace ...
[SPECIAL] BackSpace key pressed → Backspace (from end)
[BACKSPACE] Starting...
[FOCUS] Focusing on description textarea at end...
[FOCUS] Successfully focused on end of description
[BACKSPACE] SUCCESS
```

### Good Signs - Space ✓
```
[PASSTHROUGH] " " -> passthrough: ' '
[FOCUS] Focusing on description textarea at end...
[FOCUS] Successfully focused on end of description
[KEY_PASSTHROUGH] Typing: ' '
```
(Should only show ONCE per space, not twice)

### Good Signs - Shift+Delete ✓
```
[SPECIAL] Shift+Delete pressed → Clear entire description
[SHIFT_DELETE] Starting...
[FOCUS] Focusing on description textarea at end...
[SHIFT_DELETE] Clearing description field (50 deletes)
[SHIFT_DELETE] SUCCESS
```

### Bad Signs ✗
```
- Space causing "[NEXT] Starting navigation"
- Multiple "[FOCUS]" messages for single keystroke
- "[SPECIAL] BackSpace key pressed" followed by no deletion
- Shift+Delete only deleting one character
```

## Expected Behavior Summary

| Input | Expected Action | Verify |
|-------|-----------------|--------|
| a-z, A-Z | Type character | Character appears |
| Space | Type space | Space appears, no nav |
| Backspace | Delete 1 char | Last char removed |
| Shift+Backspace | Clear field | Entire field empty |
| Ctrl+Backspace | Clear field | Entire field empty |
| Delete | Delete 1 char | Last char removed |
| Shift+Delete | Clear field | Entire field empty |
| Arrows | Navigate | Photo changes |
| Enter | Next photo | Photo changes |
| Tab | Add Dennis | "Dennis " appears |
| Comma | Add comma-space | ", " appears |
| Period | Add period-space | ". " appears |

## Focus Verification

After EVERY keystroke, you should see:
```
[FOCUS] Focusing on description textarea at end...
[FOCUS] Successfully focused on end of description
```

This ensures the next character you type will be at the end of the description.

## Red Flags (Stop Testing If You See These)

1. **Space causes navigation**
   - Issue: Special space handling not removed
   - Action: Check ui_components.py lines 255-261

2. **Multiple focus messages per keystroke**
   - Issue: Focus being called multiple times
   - Action: Check _do_key_passthrough in browser_controller.py

3. **Shift+Delete only deletes one character**
   - Issue: 50-character loop not implemented
   - Action: Check _do_shift_delete in browser_controller.py

4. **Backspace with modifiers not recognized**
   - Issue: Modifier detection not working
   - Action: Check ui_components.py lines 206-222

## Success Criteria

**All tests pass if**:
✓ Space types without navigation
✓ Backspace deletes one character
✓ Shift+Backspace clears entire field
✓ Delete keys work as expected
✓ Navigation arrows still work
✓ No duplicate focus messages in logs
✓ All typed text appears correctly
