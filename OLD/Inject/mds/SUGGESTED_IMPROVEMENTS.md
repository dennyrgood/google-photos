# Suggested Improvements for Google Photos Tagger

## Current Issues to Debug/Fix

### 1. **BackSpace Key Not Working**
- **Issue**: BackSpace key press doesn't trigger backspace action
- **Root Cause**: Could be keysym detection issue or browser command queue not processing
- **Debug Steps**:
  1. Check `[KEY_DEBUG]` output to see keysym value for BackSpace
  2. Verify `_do_backspace()` in browser_controller is being called
  3. Check if browser worker thread is alive when backspace is queued
- **Suggested Fix**: Add fallback keysym detection (try 'BackSpace', 'Backspace', 'BckSpace')

### 2. **Space Key Appearing Twice**
- **Issue**: Pressing space adds two spaces to description
- **Likely Cause**: 
  - Double focus calls (need to investigate timing)
  - Space being typed, then focus triggering another space
- **Suggested Fix**: 
  - Remove space-specific handling in _do_key_passthrough
  - Rely only on standard keyboard.type()
  - Ensure focus is called AFTER space, not before

### 3. **Space Key Still Triggering Next Photo**
- **Issue**: Despite having space_btn as default focus, space still advances to next
- **Root Cause**: Space button focus might be lost after navigation
- **Suggested Fix**: 
  - Force focus back to space_btn after EVERY browser action
  - Add explicit check: if next_btn has focus when space pressed, refuse event
  - Or move space_btn to top of tab order so it never loses focus

### 4. **Ctrl+1 and Ctrl+2 Not Adding Grouped Names**
- **Status**: FIXED - Now strips numbered prefix "(1) " and "( 2) " before sending
- **Tests Needed**: Verify Ctrl+1 adds "Dennis Laura " and Ctrl+2 adds "Dennis Bekah "

### 5. **Shift+Delete Not Clearing Description**
- **Issue**: Shift+Delete only deletes one character instead of clearing all
- **Root Cause**: Focus might not be at end, or selection might not work
- **Suggested Fix**: 
  - Go to End first
  - Then select all with Shift+Home
  - Verify something IS selected before deleting
  - Or use Ctrl+A to select all instead

### 6. **Delete Key vs Shift+Delete Confusion**
- **Current State**:
  - Delete: Should delete at cursor (forward delete)
  - Shift+Delete: Should clear entire field
  - BackSpace: Should delete from end of description
- **Issue**: Test results unclear if each works correctly
- **Suggested Fix**: 
  - Add debug output showing what's being deleted
  - Test with various cursor positions
  - Verify selection before delete

## Keyboard Shortcuts Needing Review

### Current Mappings:
- **Ctrl+N / Cmd+N**: Next photo ✓
- **Ctrl+P / Cmd+P**: Previous photo ✓
- **Ctrl+1-9**: Numbered shortcuts (0-8 for group names) ✓
- **Ctrl+X**: Backspace (should change to Shift+BackSpace?)
- **Up/Left Arrow**: Previous ✓
- **Down/Right Arrow**: Next ✓
- **Tab**: Add Dennis ✓
- **Comma**: Add ", " ✓
- **Period**: Add ". " ✓
- **BackSpace**: Backspace from end ❓
- **Delete**: Delete at cursor ✓
- **Shift+Delete**: Clear field ❓
- **Enter**: Next photo ✓
- **Shift+Enter**: Reserved for future ✓

## Potential Improvements for Bulk Tagging

### 1. **Album-Based Pre-population**
- **Goal**: Auto-suggest names based on album membership
- **Implementation**:
  - Parse album list from right panel: `<div class="DgVY7">` selector
  - Extract album names (e.g., "Laura", "Beach", "2024")
  - Fuzzy-match against names.json
  - Auto-populate or suggest names
- **Example**: If image in "Laura" album, suggest Ctrl+L

### 2. **Undo/Redo System**
- **Goal**: Allow recovery from mistakes
- **Implementation**:
  - Keep description history in memory or on-disk
  - Ctrl+Z for undo, Ctrl+Y for redo
  - Or: Minus key for undo (already mentioned)

### 3. **Batch Operations**
- **Goal**: Apply same names to multiple consecutive photos
- **Implementation**:
  - "Apply to next N photos" feature
  - Or: Shift+Ctrl+Next to apply current desc to next 10

### 4. **Smart Name Completion**
- **Goal**: Faster typing of common patterns
- **Implementation**:
  - Ctrl+; to add last used name again
  - Ctrl+' to add most recently added name
  - Auto-complete common phrases (type "den" -> "Dennis")

### 5. **Comma/Period Shortcuts Already Implemented**
- **Current**: Comma -> ", " and Period -> ". "
- **Suggested Additions**:
  - Semicolon -> "; "
  - Colon -> ": "
  - Hyphen -> "- "

### 6. **Better Numeric Group Handling**
- **Current**: Ctrl+1-9 maps to name indices
- **Issue**: Only works for first 9 items
- **Suggested**: 
  - Ctrl+0 for item 10
  - Ctrl+Shift+1 for item 11, etc.
  - Or: Allow up to Ctrl+9 for 0-8, then +10 offset

### 7. **Description Field Status**
- **Add to UI**: Show current description length, word count
- **Add to UI**: Show whether description will fit Google Photos limits
- **Add to UI**: Last 5 descriptions for quick copy/paste

### 8. **Keyboard Reference Panel**
- **Current**: Help shown on browser launch
- **Suggested**: 
  - Ctrl+H for help overlay
  - Quick cheat sheet side panel
  - Customizable shortcuts configuration file

### 9. **Performance Optimization**
- **Issue**: Threading might cause race conditions
- **Improvement**: Use proper event queue with synchronization
- **Improvement**: Pre-load next image while typing on current

### 10. **Better Error Handling**
- **Current**: Some errors might silently fail
- **Improvement**: Queue of recent errors visible in UI
- **Improvement**: Auto-retry on network failures
- **Improvement**: Better logging for debugging

## Code Quality Improvements

### 1. **Remove Slash Command Trigger**
- **Issue**: User wants to remove "/" prefix for special commands
- **Status**: Keep but maybe make optional via config
- **Alternative**: Use only Ctrl/Cmd and keysym detection

### 2. **Better Keysym Handling**
- **Current**: Hardcoded keysym names might differ by OS
- **Improvement**: Create KEYSYM_MAP dictionary with platform detection
- **Example**:
  ```python
  KEYSYM_MAP = {
      'linux': {'backspace': 'BackSpace', ...},
      'darwin': {'backspace': 'BackSpace', ...},
      'windows': {'backspace': 'BackSpace', ...}
  }
  ```

### 3. **Configuration File**
- **Create**: `config.json` for customizable settings
- **Options**:
  - Keyboard shortcut mappings
  - Debug mode settings
  - Browser launch parameters
  - Focus behavior settings

### 4. **Better Browser Detection**
- **Current**: Window found by looking for "textarea[aria-label='Description']"
- **Improvement**: Add fallback selectors for different Google Photos UI versions
- **Improvement**: Log all textareas found for debugging

### 5. **Focus Management Overhaul**
- **Issue**: Focus seems to be the root of several problems
- **Improvement**: 
  - Centralized focus manager
  - Always track which UI element should have focus
  - Reset focus explicitly after every major action

## Testing Recommendations

### Test Suite Needed:
1. **Keystroke Tests**:
   - Test each keysym combination
   - Test on macOS, Linux, Windows if possible
   
2. **Browser Integration Tests**:
   - Verify focus works as expected
   - Test description field detection on different page layouts
   - Test keyboard input reaches description field

3. **Bulk Operation Tests**:
   - Type 100 characters, verify all appear
   - Rapidly press keys, check for missed inputs
   - Navigate photos while typing

4. **Edge Cases**:
   - Empty description
   - Very long description (Google Photos limit)
   - Special characters in names
   - Non-ASCII characters

## Documentation Updates Needed

### 1. **Keyboard Shortcuts Reference**
- Create printable cheat sheet
- Organize by use case (navigation, text entry, cleanup)

### 2. **Troubleshooting Guide**
- Common issues and solutions
- How to debug keyboard issues
- How to collect debug logs

### 3. **Architecture Documentation**
- Document the thread communication model
- Explain focus handling strategy
- Document browser selection logic

## UI/UX Improvements

### 1. **Button Highlighting**
- Highlight most recently pressed button
- Show count of times each name was used (current session)

### 2. **Status Updates**
- Show "Processing..." while browser is acting
- Show "Waiting for input..." when ready
- Show "Error" status when something fails

### 3. **Keyboard Indicator**
- Show which modifier keys are currently pressed
- Show which button would fire if you press spacebar

### 4. **Undo Button**
- Add UI button for undo last action
- Show last 3 actions in UI

## File Structure Recommendations

```
inject/
├── inject.py                    # Main entry point
├── browser_controller.py        # Playwright wrapper
├── keystroke_handler.py         # Keyboard shortcuts
├── ui_components.py             # Tkinter UI
├── config.py                    # Configuration manager (NEW)
├── keysym_map.py                # OS-specific keysym handling (NEW)
├── names.json                   # Name shortcuts
├── config.json                  # User configuration (NEW)
└── tests/                       # Test suite (NEW)
    ├── test_keystroke.py
    ├── test_browser.py
    └── test_integration.py
```

## Priority Ranking

### HIGH PRIORITY (Fixes Required):
1. BackSpace key not working
2. Space appearing twice or triggering next
3. Shift+Delete not clearing properly
4. Ctrl+1-9 shortcuts with groups

### MEDIUM PRIORITY (Nice to Have):
1. Better error handling
2. Focus management cleanup
3. Album-based suggestions
4. Configuration file support

### LOW PRIORITY (Future Enhancements):
1. Undo/Redo system
2. Batch operations
3. Smart name completion
4. Extended numeric shortcuts

---

**Last Updated**: 2025-11-13
**Baseline Code Version**: Modular version with browser_controller, keystroke_handler, ui_components
**Status**: Debugging keyboard input issues
