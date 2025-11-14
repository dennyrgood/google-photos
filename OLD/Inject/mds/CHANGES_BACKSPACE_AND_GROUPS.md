# Changes Made: Backspace Fix and Group Names Support

## Summary
Fixed two critical issues:
1. BackSpace and Delete key mappings were reversed
2. Group names (with number prefixes like "(1)", "(2)") now strip the numeric prefix before sending to Google Photos

## Detailed Changes

### 1. Fixed Backspace/Delete Key Mappings in `ui_components.py`

**Issue:** The key handlers had the logic reversed.

**Before:**
- `Delete` key → Called `do_backspace()` (backwards)
- `BackSpace` key → Sent `Delete` character key (backwards)

**After:**
- `BackSpace` key → Calls `do_backspace()` (correct - deletes from end)
- `Delete` key → Sends `Delete` character key (correct - deletes at cursor)

**Lines changed:** 189-201

### 2. Enhanced Group Name Handling

**In `keystroke_handler.py` (_load_shortcuts method):**
- Added regex to detect and strip numbered group prefixes: `^\(\d+\)\s*`
- Examples:
  - `"(1) Dennis Laura "` → `"Dennis Laura "`
  - `"(2) Dennis Bekah "` → `"Dennis Bekah "`
  - `"(D)ennis "` → `"Dennis "` (existing behavior preserved)

**In `ui_components.py` (button creation):**
- Applied same stripping logic when creating name buttons
- This ensures consistency between keystroke shortcuts and UI buttons

**Key additions:**
- Import `re` module in ui_components.py
- Use `re.sub(r'^\(\d+\)\s*', '', raw)` to strip group prefixes

## Files Modified

1. **keystroke_handler.py**
   - Modified `_load_shortcuts()` method
   - Added regex-based number prefix stripping

2. **ui_components.py**
   - Added `import re`
   - Fixed BackSpace/Delete key mapping (lines 189-201)
   - Enhanced name button creation with group prefix stripping (lines 63-75)

## Testing Notes

- BackSpace key should now properly delete from the end of description
- Delete key should forward-delete at cursor position
- Group name buttons should show "(1) Dennis Laura" but send "Dennis Laura" (without the number prefix) to Google Photos
- Individual name shortcuts (D, L, B, S, T, C, J, G, H) should work as before

## No Functional Changes
- All other functionality remains unchanged
- No changes to browser interaction logic
- No changes to focus management
- No changes to keyboard passthrough behavior
