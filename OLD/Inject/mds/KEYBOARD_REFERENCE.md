# Quick Keyboard Reference Guide

## Primary Shortcuts (Ctrl+Key or Cmd+Key)

### Navigation
- **Ctrl+N** / **Cmd+N** - Go to Next photo
- **Ctrl+P** / **Cmd+P** - Go to Previous photo

### Names (Single Letters)
- **Ctrl+D** / **Cmd+D** - Add "Dennis"
- **Ctrl+L** / **Cmd+L** - Add "Laura"
- **Ctrl+B** / **Cmd+B** - Add "Bekah"
- **Ctrl+S** / **Cmd+S** - Add "Steph"
- **Ctrl+H** / **Cmd+H** - Add "Sarah"
- **Ctrl+T** / **Cmd+T** - Add "Tim"
- **Ctrl+C** / **Cmd+C** - Add "Creighton"
- **Ctrl+J** / **Cmd+J** - Add "Jeff"
- **Ctrl+G** / **Cmd+G** - Add "Graeme"
- **Ctrl+X** / **Cmd+X** - Backspace (delete from end)

### Group Shortcuts (Multiple Names)
- **Ctrl+1** - Add "(1) Dennis Laura"
- **Ctrl+2** - Add "(2) Dennis Bekah"
- **Ctrl+3** - Add "(3) Dennis Steph"

---

## Arrow Key Navigation

- **Up Arrow** - Go to Previous photo
- **Left Arrow** - Go to Previous photo
- **Down Arrow** - Go to Next photo
- **Right Arrow** - Go to Next photo
- **Enter** - Go to Next photo

---

## Special Keys for Text Editing

### Deletion
- **BackSpace** - Delete character from END of description (backward delete)
- **Delete** - Delete character AT CURSOR (forward delete)
- **Shift+Delete** - Clear ENTIRE description field

### Quick Helpers
- **Tab** - Add "Dennis" (most common name)
- **Comma (,)** - Add ", " (comma + space)
- **Period (.)** - Add ". " (period + space)

### Text Input
- **Space** - Insert a space (type normally)
- **Type normally** - Add any text character to description

---

## Slash Commands (Type / then Letter)

Alternative method if modifiers don't work. Type these sequences:
- **/n** - Go to Next photo
- **/p** - Go to Previous photo
- **/d** - Add "Dennis"
- **/l** - Add "Laura"
- **/b** - Add "Bekah"
- **/s** - Add "Steph"
- **/h** - Add "Sarah"
- **/t** - Add "Tim"
- **/c** - Add "Creighton"
- **/j** - Add "Jeff"
- **/g** - Add "Graeme"
- **/x** - Backspace (delete from end)

---

## Recommended Workflow for Bulk Tagging

### Simple Workflow
1. **Ctrl+D** → Add "Dennis"
2. Type description or additional names
3. **Ctrl+N** → Go to next photo
4. Repeat

### Fast Workflow with Groups
1. **Ctrl+1** → Add "(1) Dennis Laura" automatically
2. **Ctrl+N** → Go to next photo
3. **Ctrl+2** → Add "(2) Dennis Bekah"
4. **Ctrl+N** → Go to next photo
5. Continue...

### With Natural Typing
1. **Ctrl+D** → Add "Dennis"
2. Type: " Beach vacation "
3. **Ctrl+L** → Add "Laura"
4. **Ctrl+N** → Go to next photo
5. Type: "Mountain hiking"
6. **Ctrl+D** → Add "Dennis"
7. **Ctrl+N** → Go to next photo

### With Punctuation
1. **Ctrl+D** → Add "Dennis"
2. Type: " at the beach"
3. **Comma** → Adds ", "
4. **Ctrl+L** → Add "Laura"
5. **Ctrl+N** → Go to next photo

---

## Mouse Buttons (If Keyboard Fails)

All of these have mouse button equivalents in the UI:
- **PREV (P)** button - Previous photo
- **NEXT (N)** button - Next photo
- **BACKSPACE** button - Delete from end
- **Space** button - Add space
- **Name buttons** - Add individual names
- **READ** button (debug mode) - Read current description
- **DUMP HTML** button (debug mode) - Save page HTML for debugging

---

## Troubleshooting Shortcuts

### If Ctrl+key doesn't work:
1. Try the corresponding slash command: Type **/* then letter
   - Example: Type **/d* for Dennis
   
2. Try the arrow keys for navigation:
   - **Up/Down arrows** or **Left/Right arrows** for prev/next
   - **Enter** key for next

3. Use the **Name buttons** with mouse as fallback

### If spaces are double:
- This has been fixed - spaces should now insert normally
- If issue persists, try typing with Tab key instead of space

### If backspace isn't working:
1. Try **Shift+Delete** to clear entire field
2. Use **Delete** key to delete character forward
3. Try the **BACKSPACE** button with mouse

### If you're not in the description field:
1. Click in the description textarea in Google Photos
2. Click the **Space** button in this application
3. Try typing again

---

## Advanced Tips

### Batch Naming
- Use groups (Ctrl+1, Ctrl+2, Ctrl+3) for photos with multiple names
- No need to manually type group names - just press one shortcut

### Quick Punctuation
- **Comma** auto-adds comma + space
- **Period** auto-adds period + space
- **Tab** auto-adds most common name (Dennis)

### Undo Not Available
- Currently no built-in undo
- To undo a mistake: Use **Shift+Delete** to clear, then re-add names

### Multiple Photos
- You can navigate through thousands of photos using just:
  - **Ctrl+N** to go next
  - **Ctrl+P** to go previous
- Names persist across photos

---

## Keyboard State Indicators

While typing, the bottom of the window shows:
- Current key information
- Current state/modifiers
- Keyboard status (READY = all systems go)

Green text = "READY" - Keyboard shortcuts are active
Blue text = Waiting for browser to start

---

## macOS Specific Notes

- **Cmd+N** preferred over Ctrl+N (though both work)
- Command key works as modifier for shortcuts
- If having issues, use **Ctrl+key** or **slash commands** as fallback
- Some keyboard layouts may have different Cmd key positions

---

## Windows Specific Notes

- Use **Ctrl+key** (not Command key, which may not work)
- Windows behaves consistently with this guide
- All shortcuts documented above should work as-is

---

Version: 1.0 - November 13, 2025
Last Updated: Keyboard handling refactored with proper keysym detection
