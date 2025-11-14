#!/usr/bin/env python3
"""
Script to fix browser_controller.py
Run with: python3 fix_browser_controller.py
"""

import re
import shutil
import os

def fix_browser_controller():
    filename = 'browser_controller.py'
    
    # Make a backup
    backup = filename + '.backup'
    shutil.copy2(filename, backup)
    print(f"Created backup: {backup}")
    
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fix 1: Replace the entire _position_cursor_at_end method
    # Find the method start
    pattern1 = r'    def _position_cursor_at_end\(self\):.*?(?=\n    def |\nclass |\Z)'
    
    replacement1 = '''    def _position_cursor_at_end(self):
        """Position cursor at END of description textarea."""
        try:
            print('[CURSOR] Positioning cursor at END...')
            
            js_find = """() => {
      const textareas = document.querySelectorAll('textarea[aria-label="Description"]');
      let candidates = [];
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;
      
      for (const ta of textareas) {
          try {
              const rect = ta.getBoundingClientRect();
              const isVisible = rect.width > 0 && rect.height > 0;
              if (!isVisible) continue;
              
              const value = (ta.value || '').trim();
              const taCenter = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
              const distance = Math.sqrt(Math.pow(taCenter.x - centerX, 2) + Math.pow(taCenter.y - centerY, 2));
              const style = window.getComputedStyle(ta);
              const zIndex = parseInt(style.zIndex) || 0;
              
              candidates.push({ element: ta, value: value, rect: rect, distance: distance, zIndex: zIndex, 
  hasContent: value.length > 0 });
          } catch (e) {}
      }
      
      if (candidates.length === 0) return null;
      
      candidates.sort((a, b) => {
          if (a.hasContent !== b.hasContent) return b.hasContent ? 1 : -1;
          if (Math.abs(a.distance - b.distance) > 50) return a.distance - b.distance;
          return b.zIndex - a.zIndex;
      });
      
      const target = candidates[0];
      return {
          x: target.rect.left + target.rect.width / 2,
          y: target.rect.top + target.rect.height / 2,
          textLength: target.value.length,
          value: target.value
      };
  }"""
            
            result = self.page.evaluate(js_find)
            if not result:
                print('[CURSOR] No textarea found')
                return
                
            # Click and PROPERLY focus the textarea (using the same logic as _focus_textarea)
            self.page.mouse.click(result['x'], result['y'])
            self.page.wait_for_timeout(15)
            
            # Ensure textarea is focused and cursor is at end via JavaScript
            try:
                self.page.evaluate(
                    "(cx,cy) => { const el = document.elementFromPoint(cx, cy); "
                    "if(el && el.tagName && el.tagName.toLowerCase() === 'textarea') { "
                    "el.focus(); el.selectionStart = el.value.length; el.selectionEnd = el.value.length; "
                    "return true; } "
                    "const t = document.querySelector('textarea[aria-label=Description]'); "
                    "if(t){ t.focus(); t.selectionStart = t.value.length; t.selectionEnd = t.value.length; "
                    "return true; } return false; }", 
                    result['x'], result['y']
                )
            except Exception:
                pass
            
            # Wait for textarea to become active
            try:
                self.page.wait_for_function(
                    "() => { const a = document.activeElement; "
                    "return !!(a && a.getAttribute && a.getAttribute('aria-label') === 'Description'); }",
                    timeout=2000,
                )
                print('[CURSOR] textarea became active')
            except Exception:
                print('[CURSOR] WARNING: textarea did not become active within timeout')
            
            # THEN press End key
            self.page.keyboard.press('End')
            self.page.wait_for_timeout(5)
            
            print(f'[CURSOR] Positioned cursor at END (text length: {result["textLength"]})')
                
        except Exception as e:
            print(f'[CURSOR] ERROR: {e}')
            import traceback
            traceback.print_exc()

'''
    
    content = re.sub(pattern1, replacement1, content, flags=re.DOTALL)
    
    # Fix 2: Add End key press to _do_backspace before the backspace operation
    old_backspace_section = '''            print(f'[BACKSPACE] Textarea at ({x}, {y})')
            self._focus_textarea(x, y)
            
            print('[BACKSPACE] Sending backspace')'''
    
    new_backspace_section = '''            print(f'[BACKSPACE] Textarea at ({x}, {y})')
            self._focus_textarea(x, y)
            
            # Position cursor at END before backspacing
            print('[BACKSPACE] Positioning cursor at END')
            self.page.keyboard.press('End')
            self.page.wait_for_timeout(5)
            
            print('[BACKSPACE] Sending backspace')'''
    
    content = content.replace(old_backspace_section, new_backspace_section)
    
    # Write the fixed content
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Fixed {filename}")
    print(f"Backup saved as {backup}")
    print("\nChanges made:")
    print("1. Fixed _position_cursor_at_end() - corrected indentation and added focus verification")
    print("2. Fixed _do_backspace() - added End key press before backspace")
    print("\nTo restore from backup if needed: mv browser_controller.py.backup browser_controller.py")

if __name__ == '__main__':
    try:
        fix_browser_controller()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
