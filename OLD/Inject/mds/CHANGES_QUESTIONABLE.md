# Questionable or Notable Changes - Review List

## Changes That Might Need Adjustment

### 1. Shift+Delete Implementation (20 Backstrokes Limit)
**Location**: `browser_controller.py`, `_do_shift_delete()` method

**Concern**: Uses up to 20 backstrokes, hardcoded limit

**Current Implementation**:
```python
for _ in range(min(20, count)):
    self.page.keyboard.press('Backspace')
    self.page.wait_for_timeout(30)
```

**Potential Issue**: 
- Descriptions longer than 20 characters won't be fully cleared
- Adds 600ms delay (20 * 30ms) for clearing

**Alternatives to Consider**:
1. ✓ Current: Simple and reliable, works for most use cases
2. Use Ctrl+A + Delete instead (more atomic)
3. Recursive call if description still has content after 20 strokes
4. Increase to 50 backstrokes for longer descriptions

**Recommendation**: Monitor in testing. If descriptions > 20 chars are common, increase limit to 50 and add notification.

---

### 2. Event Dispatch in _focus_description_end()
**Location**: `browser_controller.py`, line 439-440

**Addition**: 
```javascript
target.dispatchEvent(new Event('input', { bubbles: true }));
target.dispatchEvent(new Event('change', { bubbles: true }));
```

**Concern**: 
- Might trigger unwanted side effects in Google Photos
- Could interfere with auto-save functionality
- Might cause multiple update events

**Potential Issue**:
- Google Photos might interpret these as user-initiated changes
- Could mark photo as "modified" even if just viewing
- Might trigger validation or sanitization

**Testing Needed**:
- Check if events cause unwanted page behavior
- Verify descriptions don't get accidentally modified
- Monitor for performance impact

**Recommendation**: These events are necessary for proper cursor positioning but should be monitored in testing.

---

### 3. Order of Keyboard Handler Checks
**Location**: `ui_components.py`, lines 194-242

**Change**: Moved Shift+Delete check to line 195 (BEFORE other checks)

**Concern**: 
- Early exit might prevent other handlers from running
- Careful ordering is necessary to avoid missed detections

**Original Order**:
1. Ctrl+Letter combinations
2. Ctrl+Digit combinations  
3. Shift+Delete ← Was here

**New Order**:
1. Shift+Delete ← Moved here
2. Ctrl+Letter combinations
3. Ctrl+Digit combinations
4. Other special keys

**Potential Issue**:
- If Shift+Delete check fails silently, no Delete handling occurs
- Early return ('break') prevents fallthrough to other handlers

**Why This Was Done**: 
- Shift modifier could be lost if Delete check happened after other state modifications
- Ctrl+Shift combinations need proper precedence

**Recommendation**: No changes needed, but be aware of the precedence if adding new handlers.

---

### 4. Null Check for Ctrl+Digit
**Location**: `ui_components.py`, line 160

**Change**: 
```python
if event.keysym and event.keysym.isdigit():  # Added "event.keysym and" check
```

**Concern**: 
- What if keysym is None? This silently skips the digit check
- No error message when keysym is unexpected type

**Potential Issue**:
- Ctrl+1 might fail silently if keysym is None
- User won't know why group shortcut didn't work

**Try/Except Wrapper**: Added to handle exceptions (line 174-188)

**Recommendation**: This is safer than before. Consider logging when keysym is None for debugging.

---

### 5. Delete and BackSpace Key Distinction
**Location**: `ui_components.py`, lines 200-212

**Concern**: 
- Physical Delete key vs. logical delete operation
- On some keyboards, these might send same keysym

**Testing Needed**:
- Verify Delete key sends keysym='Delete'
- Verify BackSpace key sends keysym='BackSpace'
- Test on different keyboard layouts (US, UK, Mac, etc.)

**Potential Issue**:
- Some non-standard keyboards might not send keysym='Delete'
- Might send 'BackSpace' for both keys

**Recommendation**: Test with your specific keyboard to verify both keys are detected properly.

---

## Changes That Are Fine (No Issues Identified)

✅ Command queue additions ('delete', 'shift_delete')
- Standard pattern already used for 'backspace'
- No side effects

✅ Public methods send_delete() and send_shift_delete()
- Follow existing pattern
- Simple queue additions
- No complex logic

✅ Enhanced cursor verification in _focus_description_end()
- Checking selectionStart === length is safe
- Improves reliability without side effects

✅ Tab/Comma/Period handler order
- These are independent of other handlers
- Order change doesn't affect their function

✅ Error handling for digit shortcut processing
- Try/except wrapper is defensive programming
- Won't break existing functionality

---

## Behavior Changes Summary

| Change | Type | Risk Level | Status |
|--------|------|-----------|--------|
| Shift+Delete uses 20 backstrokes | Implementation | Medium | ⚠️ Monitor |
| Event dispatch in focus method | Side effect | Medium | ⚠️ Monitor |
| Handler precedence reordering | Order | Low | ✅ OK |
| Null check for digit keysym | Safety | Low | ✅ OK |
| Delete vs BackSpace distinction | Functionality | Low | ⚠️ Test |

---

## Recommendations for Testing

### Critical Tests
1. [ ] Test with very long descriptions (>20 chars) using Shift+Delete
2. [ ] Test Delete key on multiple keyboard layouts
3. [ ] Test Ctrl+1/2 for group shortcuts (digit detection)
4. [ ] Test after navigation - type should appear at end, not middle

### Important Tests
5. [ ] Test event dispatch doesn't cause unwanted auto-saves
6. [ ] Test Tab, Comma, Period still work after handler reordering
7. [ ] Test BackSpace still works for single char deletion
8. [ ] Test cursor position is correct in multi-line descriptions

### Nice-to-Have Tests
9. [ ] Performance test with 1000+ consecutive operations
10. [ ] Test with non-English keyboard layouts
11. [ ] Test with very short descriptions (1-2 chars)

---

## No Issues Found With

✅ No changes to names.json loading
✅ No changes to shortcut registration
✅ No changes to browser launching
✅ No changes to Ctrl+Letter key handling
✅ No changes to keyboard focus management
✅ No changes to threading model
✅ No changes to public API

---

**Review Status**: Complete
**Risk Assessment**: Low-Medium (mostly monitoring concerns)
**Ready for Testing**: YES
