#!/usr/bin/env python3
"""
Minimal skeleton: Google Photos description tagger
- Launch browser with old device user agent
- Navigate photos (next/prev with center-click)
- Read current description
- Append 'X' to description
- Show current photo URL and description
"""
import json
import os
import threading
import queue
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

ROOT = os.path.dirname(__file__)


class BrowserController:
    """Minimal Playwright wrapper for Google Photos with old device spoofing."""
    
    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
        self._cmd_queue = queue.Queue()
        self._worker = None
        self._running = False
        self._ready_event = threading.Event()
        self._launch_mode = 'default'  # Store launch mode
        # Simple state for UI polling
        self._last_url = None
        self._last_description = None

    def start(self, headful=True, timeout=30):
        """Start browser worker thread."""
        if sync_playwright is None:
            raise RuntimeError('playwright not installed; run pip install -r requirements.txt')

        if self._worker and self._worker.is_alive():
            return

        self._running = True
        self._ready_event.clear()
        self._worker = threading.Thread(target=self._worker_main, args=(headful,), daemon=True)
        self._worker.start()
        ready = self._ready_event.wait(timeout=timeout)
        if not ready:
            raise RuntimeError('Browser worker did not become ready in time')

    def stop(self):
        """Stop browser worker."""
        self._cmd_queue.put(('stop', None))
        self._running = False
        if self._worker:
            self._worker.join(timeout=5)

    def _worker_main(self, headful):
        """Main worker thread - runs Playwright with old device spoofing."""
        import pathlib
        try:
            self.playwright = sync_playwright().start()
            user_data_dir = str(pathlib.Path.home() / '.googlephotos_profile')
            
            # Select user agent based on launch mode
            mode = getattr(self, '_launch_mode', 'default')
            
            if mode == 'ios11':
                user_agent = 'Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1'
                print('[BROWSER] Mode: iOS 11 iPhone')
            elif mode == 'android6':
                user_agent = 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3325.181 Mobile Safari/537.36'
                print('[BROWSER] Mode: Android 6 Chrome 65')
            elif mode == 'chrome70':
                user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36'
                print('[BROWSER] Mode: Desktop Chrome 70 (2018)')
            else:  # default - iOS 12 iPad
                user_agent = 'Mozilla/5.0 (iPad; CPU OS 12_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Mobile/15E148 Safari/604.1'
                print('[BROWSER] Mode: Default (iOS 12 iPad)')
            
            print(f'[BROWSER] Using user agent: {user_agent}')
            
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=not headful,
                channel='chrome',
                user_agent=user_agent,
                viewport={'width': 1024, 'height': 768},
                device_scale_factor=1,
                is_mobile=True,
                has_touch=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--user-agent=' + user_agent,
                    '--disable-web-security',  # Sometimes helps with SPA issues
                ],
            )
            
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            
            # Additional spoofing via CDP (Chrome DevTools Protocol)
            # This ensures the user agent is consistently applied
            try:
                self.page.evaluate("""() => {
                    // Override navigator properties to match iPad 2
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'iPad'
                    });
                    Object.defineProperty(navigator, 'maxTouchPoints', {
                        get: () => 5
                    });
                }""")
            except Exception as e:
                print(f'[BROWSER] Warning: Could not override navigator properties: {e}')
            
            self.page.goto('https://photos.google.com')
            
            print('[BROWSER] Started, navigated to Google Photos (spoofing iPad 2)')
            self._ready_event.set()

            # Command loop
            while self._running:
                try:
                    cmd, arg = self._cmd_queue.get(timeout=0.5)
                except Exception:
                    continue

                if cmd == 'stop':
                    break
                elif cmd == 'next':
                    self._do_next()
                elif cmd == 'prev':
                    self._do_prev()
                elif cmd == 'append_x':
                    self._do_append_x()
                elif cmd == 'append_text':
                    # arg is a simple string to append
                    try:
                        self._do_append_text(arg)
                    except Exception as e:
                        print(f'[APPEND_TEXT] ERROR: {e}')
                elif cmd == 'read_desc':
                    ev, res = arg
                    desc = self._sample_description()
                    res['description'] = desc
                    ev.set()
                elif cmd == 'dump_html':
                    self._do_dump_html()

        finally:
            try:
                if self.context:
                    self.context.close()
            except Exception:
                pass
            try:
                if self.playwright:
                    self.playwright.stop()
            except Exception:
                pass
            print('[BROWSER] Stopped')

    def _do_dump_html(self):
        """Dump current page HTML for debugging."""
        try:
            html = self.page.content()
            filename = f'gphotos_dump_{int(time.time())}.html'
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f'[DUMP] Saved HTML to {filename}')
            
            # Also print some debug info
            print('[DUMP] Checking for textareas...')
            textareas = self.page.query_selector_all('textarea')
            print(f'[DUMP] Found {len(textareas)} textareas')
            
            for i, ta in enumerate(textareas[:5]):  # First 5 only
                try:
                    aria_label = ta.get_attribute('aria-label')
                    placeholder = ta.get_attribute('placeholder')
                    value = ta.input_value()
                    print(f'[DUMP]   Textarea {i}: aria-label="{aria_label}", placeholder="{placeholder}", value="{value[:50]}"')
                except Exception as e:
                    print(f'[DUMP]   Textarea {i}: Error reading - {e}')
                    
        except Exception as e:
            print(f'[DUMP] ERROR: {e}')
            import traceback
            traceback.print_exc()

    def _do_next(self):
        """Navigate to next photo."""
        try:
            print('[NEXT] Starting navigation...')
            
            # Get current URL before
            url_before = self.page.url
            print(f'[NEXT] Current URL: {url_before}')
            
            # Click center of large image if possible; fall back to viewport center
            clicked = False
            imgs = self.page.query_selector_all('img')
            for img in imgs:
                try:
                    box = img.bounding_box()
                    if box and box.get('width', 0) > 200 and box.get('height', 0) > 100:
                        cx = box['x'] + box['width'] / 2
                        cy = box['y'] + box['height'] / 2
                        print(f'[NEXT] Clicking image center at ({int(cx)},{int(cy)})')
                        try:
                            self.page.mouse.click(cx, cy)
                        except Exception:
                            # ignore failing mouse click and continue to fallback
                            pass
                        self.page.wait_for_timeout(300)
                        # Dispatch a user-like pointer event sequence to ensure the gallery registers a real gesture
                        try:
                            self.page.evaluate("(cx,cy) => { const el = document.elementFromPoint(cx, cy); if(!el) return false; ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type=>{ el.dispatchEvent(new PointerEvent(type, {bubbles:true, cancelable:true, clientX:cx, clientY:cy})); }); return true; }", cx, cy)
                        except Exception:
                            pass
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                try:
                    # Fallback: click the viewport center (helps with portrait images)
                    vp = self.page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
                    cx = vp.get('w', 800) / 2
                    cy = vp.get('h', 600) / 2
                    print(f'[NEXT] Fallback clicking viewport center at ({int(cx)},{int(cy)})')
                    try:
                        self.page.mouse.click(cx, cy)
                    except Exception:
                        pass
                    self.page.wait_for_timeout(300)
                    try:
                        self.page.evaluate("() => { const cx = Math.floor(window.innerWidth/2); const cy = Math.floor(window.innerHeight/2); const el = document.elementFromPoint(cx, cy); if(!el) return false; ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type=>{ el.dispatchEvent(new PointerEvent(type, {bubbles:true, cancelable:true, clientX:cx, clientY:cy})); }); return true; }")
                    except Exception:
                        pass
                except Exception:
                    pass

            # Press ArrowRight
            print('[NEXT] Pressing ArrowRight')
            self.page.keyboard.press('ArrowRight')
            
            # Wait for URL to change
            self.page.wait_for_timeout(1500)
            
            # Update state
            try:
                self._last_url = self.page.url
            except Exception:
                pass
            
            # Sample new description
            desc = self._sample_description()
            self._last_description = desc
            print(f'[NEXT] New description: {repr(desc)[:100]}')
            
        except Exception as e:
            print(f'[NEXT] ERROR: {e}')

    def _do_prev(self):
        """Navigate to previous photo."""
        try:
            print('[PREV] Starting navigation...')
            
            url_before = self.page.url
            print(f'[PREV] Current URL: {url_before}')
            
            # Click center of large image if possible; fall back to viewport center
            clicked = False
            imgs = self.page.query_selector_all('img')
            for img in imgs:
                try:
                    box = img.bounding_box()
                    if box and box.get('width', 0) > 200 and box.get('height', 0) > 100:
                        cx = box['x'] + box['width'] / 2
                        cy = box['y'] + box['height'] / 2
                        print(f'[PREV] Clicking image center at ({int(cx)},{int(cy)})')
                        try:
                            self.page.mouse.click(cx, cy)
                        except Exception:
                            pass
                        self.page.wait_for_timeout(300)
                        # Dispatch a user-like pointer event sequence to ensure the gallery registers a real gesture
                        try:
                            self.page.evaluate("(cx,cy) => { const el = document.elementFromPoint(cx, cy); if(!el) return false; ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type=>{ el.dispatchEvent(new PointerEvent(type, {bubbles:true, cancelable:true, clientX:cx, clientY:cy})); }); return true; }", cx, cy)
                        except Exception:
                            pass
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                try:
                    # Fallback: click the viewport center (helps with portrait images)
                    vp = self.page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
                    cx = vp.get('w', 800) / 2
                    cy = vp.get('h', 600) / 2
                    print(f'[PREV] Fallback clicking viewport center at ({int(cx)},{int(cy)})')
                    try:
                        self.page.mouse.click(cx, cy)
                    except Exception:
                        pass
                    self.page.wait_for_timeout(300)
                    try:
                        self.page.evaluate("() => { const cx = Math.floor(window.innerWidth/2); const cy = Math.floor(window.innerHeight/2); const el = document.elementFromPoint(cx, cy); if(!el) return false; ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type=>{ el.dispatchEvent(new PointerEvent(type, {bubbles:true, cancelable:true, clientX:cx, clientY:cy})); }); return true; }")
                    except Exception:
                        pass
                except Exception:
                    pass

            print('[PREV] Pressing ArrowLeft')
            self.page.keyboard.press('ArrowLeft')
            
            self.page.wait_for_timeout(1500)
            
            try:
                self._last_url = self.page.url
            except Exception:
                pass
            
            desc = self._sample_description()
            self._last_description = desc
            print(f'[PREV] New description: {repr(desc)[:100]}')
            
        except Exception as e:
            print(f'[PREV] ERROR: {e}')

    def _sample_description(self):
        """Read current description from page."""
        try:
            print('[SAMPLE] Executing page.evaluate...')
            js = """() => {
    const textareas = document.querySelectorAll('textarea[aria-label="Description"]');
    console.log('Found textareas:', textareas.length);
    
    // Strategy: Find the textarea that's most likely the active/visible one
    // 1. Prefer textareas with content
    // 2. Prefer textareas in the center of the viewport
    // 3. Check z-index and visibility
    
    let candidates = [];
    
    for (let i = 0; i < textareas.length; i++) {
        const ta = textareas[i];
        const rect = ta.getBoundingClientRect();
        const value = (ta.value || '').trim();
        
        // Check if visible
        const isVisible = rect.width > 0 && rect.height > 0;
        
        // Calculate distance from center of viewport
        const centerX = window.innerWidth / 2;
        const centerY = window.innerHeight / 2;
        const taCenter = {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2
        };
        const distanceFromCenter = Math.sqrt(
            Math.pow(taCenter.x - centerX, 2) + 
            Math.pow(taCenter.y - centerY, 2)
        );
        
        // Get computed style for z-index
        const style = window.getComputedStyle(ta);
        const zIndex = parseInt(style.zIndex) || 0;
        
        console.log(`Textarea ${i}: visible=${isVisible}, value="${value.substring(0,30)}", distance=${Math.round(distanceFromCenter)}, zIndex=${zIndex}`);
        
        if (isVisible) {
            candidates.push({
                element: ta,
                value: value,
                distance: distanceFromCenter,
                zIndex: zIndex,
                hasContent: value.length > 0
            });
        }
    }
    
    if (candidates.length === 0) {
        console.log('No visible textareas found');
        return null;
    }
    
    // Sort by: 1) has content, 2) closest to center, 3) highest z-index
    candidates.sort((a, b) => {
        // Prioritize textareas with content
        if (a.hasContent !== b.hasContent) {
            return b.hasContent ? 1 : -1;
        }
        // Then by distance from center (closer is better)
        if (Math.abs(a.distance - b.distance) > 50) {  // 50px threshold
            return a.distance - b.distance;
        }
        // Then by z-index (higher is better)
        return b.zIndex - a.zIndex;
    });
    
    const selected = candidates[0];
    console.log('Selected textarea with value:', selected.value);
    return selected.value;
}"""
            
            result = self.page.evaluate(js)
            print(f'[SAMPLE] Result: {repr(result)[:100]}')
            return result
            
        except Exception as e:
            print(f'[SAMPLE] ERROR: {e}')
            return None

    def _do_append_x(self):
        """Append 'X' to current description."""
        try:
            print('[APPEND_X] Starting...')
            
            # Find textarea position using improved selector
            js_find = """() => {
    const textareas = document.querySelectorAll('textarea[aria-label="Description"]');
    console.log('Found textareas:', textareas.length);
    
    let candidates = [];
    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    
    for (const ta of textareas) {
        const rect = ta.getBoundingClientRect();
        const isVisible = rect.width > 0 && rect.height > 0;
        const value = (ta.value || '').trim();
        
        if (!isVisible) continue;
        
        const taCenter = {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2
        };
        const distance = Math.sqrt(
            Math.pow(taCenter.x - centerX, 2) + 
            Math.pow(taCenter.y - centerY, 2)
        );
        const style = window.getComputedStyle(ta);
        const zIndex = parseInt(style.zIndex) || 0;
        
        candidates.push({
            element: ta,
            value: value,
            rect: rect,
            distance: distance,
            zIndex: zIndex,
            hasContent: value.length > 0
        });
    }
    
    if (candidates.length === 0) {
        console.log('No visible textareas');
        return null;
    }
    
    // Sort by same logic as _sample_description
    candidates.sort((a, b) => {
        if (a.hasContent !== b.hasContent) return b.hasContent ? 1 : -1;
        if (Math.abs(a.distance - b.distance) > 50) return a.distance - b.distance;
        return b.zIndex - a.zIndex;
    });
    
    const target = candidates[0];
    const rect = target.rect;
    console.log('Selected textarea at:', rect, 'value:', target.value);
    
    return {
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
        currentValue: target.value
    };
}"""
            
            result = self.page.evaluate(js_find)
            if not result:
                print('[APPEND_X] FAILED - No textarea found')
                return
            
            x = result['x']
            y = result['y']
            current = result['currentValue']
            
            print(f'[APPEND_X] Textarea at ({x}, {y}), current value: "{current}"')
            
            # Click textarea
            print(f'[APPEND_X] Clicking at ({x}, {y})')
            self.page.mouse.click(x, y)
            self.page.wait_for_timeout(200)

            # Try to explicitly focus the textarea at that point (helps avoid accidental global shortcuts)
            try:
                # Use a selector without inner quotes to avoid nested-quote issues
                self.page.evaluate("(cx,cy) => { const el = document.elementFromPoint(cx, cy); if(el && el.tagName && el.tagName.toLowerCase() === 'textarea') { el.focus(); el.selectionStart = el.value.length; el.selectionEnd = el.value.length; return true; } const t = document.querySelector('textarea[aria-label=Description]'); if(t){ t.focus(); t.selectionStart = t.value.length; t.selectionEnd = t.value.length; return true; } return false; }", x, y)
            except Exception:
                pass

            # Wait until the textarea is actually the active element (prevents typing to the wrong target)
            try:
                self.page.wait_for_function(
                    "() => { const a = document.activeElement; return !!(a && a.getAttribute && a.getAttribute('aria-label') === 'Description'); }",
                    timeout=2000,
                )
                print('[APPEND_X] textarea became active')
            except Exception:
                print('[APPEND_X] WARNING: textarea did not become active within timeout')
            
            # Move to end
            print('[APPEND_X] Pressing End key')
            self.page.keyboard.press('End')
            self.page.wait_for_timeout(150)
            
            # Type X
            print('[APPEND_X] Typing space')
            self.page.keyboard.type(' ')
            self.page.wait_for_timeout(200)
            
            print(f'[APPEND_X] SUCCESS - appended X to "{current}"')
            
            # Update description
            self._last_description = (current if current else '') + 'X'
            
        except Exception as e:
            print(f'[APPEND_X] ERROR: {e}')
            import traceback
            traceback.print_exc()

    def _do_append_text(self, text):
        """Append arbitrary text to current description (read-only except typing into textarea).

        This is similar to _do_append_x but types the provided `text` string instead.
        """
        try:
            print(f'[APPEND_TEXT] Starting append of: {repr(text)[:50]}')
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
            
            candidates.push({ element: ta, value: value, rect: rect, distance: distance, zIndex: zIndex, hasContent: value.length > 0 });
        } catch (e) {}
    }
    
    if (candidates.length === 0) return null;
    
    candidates.sort((a, b) => {
        if (a.hasContent !== b.hasContent) return b.hasContent ? 1 : -1;
        if (Math.abs(a.distance - b.distance) > 50) return a.distance - b.distance;
        return b.zIndex - a.zIndex;
    });
    
    const target = candidates[0];
    let rect = target.rect;
    
    // If off-screen, scroll into view
    try {
        if (rect.top < 0 || rect.left < 0 || rect.bottom > window.innerHeight || rect.right > window.innerWidth) {
            try { target.element.scrollIntoView({block: 'center', inline: 'center'}); } catch(e) {}
            rect = target.element.getBoundingClientRect();
        }
    } catch (e) {}
    
    return { x: rect.left + rect.width/2, y: rect.top + rect.height/2, currentValue: target.value };
}"""

            result = self.page.evaluate(js_find)
            if not result:
                print('[APPEND_TEXT] FAILED - No textarea found')
                return

            x = result['x']
            y = result['y']
            current = result['currentValue']
            print(f'[APPEND_TEXT] Textarea at ({x}, {y}), current value: "{current}"')

            # If returned coordinates are off-screen (negative), try one more time
            if y is not None and y < 0:
                print(f"[APPEND_TEXT] WARNING: target y is negative ({y}), re-sampling once")
                self.page.wait_for_timeout(120)
                result2 = self.page.evaluate(js_find)
                if result2 and result2.get('y') is not None and result2.get('y') >= 0:
                    x = result2['x']
                    y = result2['y']
                    current = result2.get('currentValue')
                    print(f"[APPEND_TEXT] Re-sampled textarea at ({x}, {y}), current value: {repr(current)[:80]}")
                else:
                    print('[APPEND_TEXT] FAILED - target remains off-screen after re-sample')
                    return

            # Click textarea and type
            self.page.mouse.click(x, y)
            self.page.wait_for_timeout(300)
            # Try to explicitly focus the textarea at that point (helps avoid accidental global shortcuts)
            try:
                # Use a selector without inner quotes to avoid nested-quote issues
                self.page.evaluate("(cx,cy) => { const el = document.elementFromPoint(cx, cy); if(el && el.tagName && el.tagName.toLowerCase() === 'textarea') { el.focus(); el.selectionStart = el.value.length; el.selectionEnd = el.value.length; return true; } const t = document.querySelector('textarea[aria-label=Description]'); if(t){ t.focus(); t.selectionStart = t.value.length; t.selectionEnd = t.value.length; return true; } return false; }", x, y)
            except Exception:
                pass
            # Wait until the textarea is actually the active element (prevents typing to the wrong target)
            try:
                self.page.wait_for_function(
                    "() => { const a = document.activeElement; return !!(a && a.getAttribute && a.getAttribute('aria-label') === 'Description'); }",
                    timeout=2000,
                )
                print('[APPEND_TEXT] textarea became active')
            except Exception:
                print('[APPEND_TEXT] WARNING: textarea did not become active within timeout')
            self.page.keyboard.press('End')
            self.page.wait_for_timeout(150)
            # Type the provided text
            self.page.keyboard.type(text)
            self.page.wait_for_timeout(200)

            # Update local cache
            self._last_description = (current if current else '') + text
            print(f'[APPEND_TEXT] SUCCESS - appended {repr(text)}')

        except Exception as e:
            print(f'[APPEND_TEXT] ERROR: {e}')
            import traceback
            traceback.print_exc()

    def goto_next_photo(self):
        """Queue next photo command."""
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('next', None))

    def goto_prev_photo(self):
        """Queue prev photo command."""
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('prev', None))

    def append_x(self):
        """Queue append X command."""
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('append_x', None))

    def append_text(self, text):
        """Queue append_text command with provided string."""
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('append_text', text))

    def read_description(self, timeout=5.0):
        """Read current description synchronously."""
        if not self._running:
            raise RuntimeError('Browser not running')
        ev = threading.Event()
        res = {}
        self._cmd_queue.put(('read_desc', (ev, res)))
        ok = ev.wait(timeout)
        return res.get('description') if ok else None

    def dump_html(self):
        """Queue HTML dump command for debugging."""
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('dump_html', None))

    def get_state(self):
        """Return current state for UI polling."""
        return {
            'url': self._last_url,
            'description': self._last_description
        }


class AssistantUI:
    """Minimal UI for Google Photos tagger."""
    
    def __init__(self, root):
        print('[UI] Initializing...')
        self.root = root
        root.title('Google Photos Tagger - Old Device Mode')
        self.browser = BrowserController()

        # Main frame
        main = ttk.Frame(root, padding=10)
        main.grid(row=0, column=0, sticky='nsew')

        # Photo URL label
        self.photo_label = ttk.Label(main, text='Photo: (not connected)', font=('Courier', 10))
        self.photo_label.grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 8))

        # Description label
        desc_frame = ttk.LabelFrame(main, text='Current Description')
        desc_frame.grid(row=1, column=0, columnspan=4, sticky='nsew', pady=8)
        self.desc_label = ttk.Label(desc_frame, text='(no description)', wraplength=600, justify='left')
        self.desc_label.pack(padx=8, pady=8, anchor='w')

        # Button frame
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=2, column=0, columnspan=4, sticky='ew', pady=8)

        # Buttons
        self.launch_btn = ttk.Button(btn_frame, text='LAUNCH', command=self.launch_browser)
        self.launch_btn.grid(row=0, column=0, sticky='ew', padx=2)

        self.prev_btn = ttk.Button(btn_frame, text='PREV', command=self.prev_photo, state='disabled')
        self.prev_btn.grid(row=0, column=1, sticky='ew', padx=2)

        self.next_btn = ttk.Button(btn_frame, text='NEXT', command=self.next_photo, state='disabled')
        self.next_btn.grid(row=0, column=2, sticky='ew', padx=2)

        self.read_btn = ttk.Button(btn_frame, text='READ', command=self.read_current, state='disabled')
        self.read_btn.grid(row=0, column=3, sticky='ew', padx=2)

        self.add_btn = ttk.Button(btn_frame, text='ADD Space', command=self.add_x, state='disabled')
        self.add_btn.grid(row=0, column=4, sticky='ew', padx=2)
        
        # Add DUMP button for debugging
        self.dump_btn = ttk.Button(btn_frame, text='DUMP HTML', command=self.dump_html, state='disabled')
        self.dump_btn.grid(row=0, column=5, sticky='ew', padx=2)
        
        # Quick name buttons - load from names.json. Label shows raw name; pushed text excludes parentheses
        names = []
        try:
            names_path = os.path.join(ROOT, '..', 'poc', 'names.json')
            # fallback to sibling poc folder if running from live/
            if not os.path.exists(names_path):
                names_path = os.path.join(ROOT, 'names.json')
            with open(names_path, 'r', encoding='utf-8') as nf:
                data = json.load(nf)
                if isinstance(data, dict):
                    names = data.get('names', [])
                elif isinstance(data, list):
                    names = data
        except Exception as e:
            print(f'[UI] Failed to load names.json: {e}')
            names = ['(D)ennis', '(L)aura', '(B)ekah']

        self.name_buttons = []
        base_col = 6  # Changed from 5 to accommodate DUMP button
        for idx, raw in enumerate(names):
            label = raw
            pushed = ''.join(ch for ch in label if ch not in '()')
            # create button; keep it disabled until browser ready
            btn = ttk.Button(btn_frame, text=label, command=(lambda p=pushed: self.add_name(p)), state='disabled')
            btn.grid(row=0, column=base_col + idx, sticky='ew', padx=2)
            self.name_buttons.append(btn)

        # Configure weights for columns (ensure enough columns for names)
        total_cols = max(8, base_col + len(self.name_buttons))
        for i in range(total_cols):
            btn_frame.columnconfigure(i, weight=1)

        # Start polling
        print('[UI] Starting poll loop')
        self.poll_browser_state()

    def add_name(self, name):
        """Append a given name string to the current description (runs in background)."""
        threading.Thread(target=lambda: self.browser.append_text(name), daemon=True).start()

    def launch_browser(self):
        """Launch browser in background thread."""
        def _launch():
            try:
                print('[LAUNCH] Starting browser...')
                self.browser.start(headful=True)
                print('[LAUNCH] Browser started')
                self.root.after(0, self._on_browser_ready)
            except Exception as e:
                print(f'[LAUNCH] ERROR: {e}')
                self.root.after(0, lambda: messagebox.showerror('Error', str(e)))

        threading.Thread(target=_launch, daemon=True).start()

    def _on_browser_ready(self):
        """Called when browser is ready."""
        self.launch_btn.config(state='disabled')
        self.prev_btn.config(state='normal')
        self.next_btn.config(state='normal')
        self.read_btn.config(state='normal')
        self.add_btn.config(state='normal')
        self.dump_btn.config(state='normal')
        # enable quick-name buttons (if dynamic list present)
        try:
            for b in getattr(self, 'name_buttons', []):
                try:
                    b.config(state='normal')
                except Exception:
                    pass
        except Exception:
            pass
        messagebox.showinfo('Browser Ready', 'Browser spoofing iPad 2. Please log into Google Photos.')

    def next_photo(self):
        """Go to next photo."""
        threading.Thread(target=self.browser.goto_next_photo, daemon=True).start()

    def prev_photo(self):
        """Go to previous photo."""
        threading.Thread(target=self.browser.goto_prev_photo, daemon=True).start()

    def read_current(self):
        """Read current description."""
        def _read():
            try:
                print('[READ] Requesting description...')
                desc = self.browser.read_description(timeout=8.0)
                # Update the UI label instead of a modal popup
                msg = desc if desc else '(no description)'
                self.root.after(0, lambda m=msg: self.desc_label.config(text=m))
            except Exception as e:
                print(f'[READ] ERROR: {e}')
                self.root.after(0, lambda: messagebox.showerror('Error', str(e)))

        threading.Thread(target=_read, daemon=True).start()

    def add_x(self):
        """Append X to description."""
        threading.Thread(target=self.browser.append_x, daemon=True).start()

    def dump_html(self):
        """Dump current page HTML for debugging."""
        threading.Thread(target=self.browser.dump_html, daemon=True).start()

    def poll_browser_state(self):
        """Poll browser state and update UI."""
        try:
            state = self.browser.get_state()
            
            # Update photo URL
            url = state.get('url')
            if url:
                short = url.split('/')[-1]
                self.photo_label.config(text=f'Photo: {short}')
            
            # Update description
            desc = state.get('description')
            if desc:
                preview = desc if len(desc) < 200 else (desc[:197] + '...')
                self.desc_label.config(text=preview)
            else:
                self.desc_label.config(text='(no description)')
        except Exception as e:
            print(f'[POLL] ERROR: {e}')

        # Schedule next poll
        self.root.after(500, self.poll_browser_state)

    def shutdown(self):
        """Shutdown."""
        try:
            self.browser.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    root = tk.Tk()
    app = AssistantUI(root)
    root.protocol('WM_DELETE_WINDOW', app.shutdown)
    root.mainloop()


if __name__ == '__main__':
    main()
