#!/usr/bin/env python3
"""
Google Photos description tagger with old device spoofing
- Launch browser with different user agent modes
- Navigate photos (next/prev with keyboard)
- Read current description
- Append names to description
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
        self._launch_mode = 'default'
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
            
            
            if mode == 'ios10':
                user_agent = 'Mozilla/5.0 (iPad; CPU OS 10_3_3 like Mac OS X) AppleWebKit/603.3.8 (KHTML, like Gecko) Version/10.0 Mobile/14G60 Safari/602.1'
                print('[BROWSER] Mode: iOS 10 iPad')
            elif mode == 'android8':
                user_agent = 'Mozilla/5.0 (Linux; Android 8.0.0; Pixel 2 XL Build/OPD1.170816.004) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Mobile Safari/537.36'
                print('[BROWSER] Mode: Android 8 Chrome 67')
            elif mode == 'chrome60':
                user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36'
                print('[BROWSER] Mode: Desktop Chrome 60 (2017)')
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
                    '--disable-web-security',
                ],
            )
            
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            
            # Additional spoofing via CDP
            try:
                self.page.evaluate("""() => {
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
            
            print('[BROWSER] Started, navigated to Google Photos')
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
                elif cmd == 'backspace':
                    self._do_backspace()

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
            
            print('[DUMP] Checking for textareas...')
            textareas = self.page.query_selector_all('textarea')
            print(f'[DUMP] Found {len(textareas)} textareas')
            
            for i, ta in enumerate(textareas[:5]):
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
            
            url_before = self.page.url
            print(f'[NEXT] Current URL: {url_before}')
            
            # Click center of large image if possible
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
                            pass
                        self.page.wait_for_timeout(300)
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

            print('[NEXT] Pressing ArrowRight')
            self.page.keyboard.press('ArrowRight')
            
            self.page.wait_for_timeout(1500)
            
            try:
                self._last_url = self.page.url
            except Exception:
                pass
            
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
    
    let candidates = [];
    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    
    for (let i = 0; i < textareas.length; i++) {
        const ta = textareas[i];
        const rect = ta.getBoundingClientRect();
        const value = (ta.value || '').trim();
        
        const isVisible = rect.width > 0 && rect.height > 0;
        
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
        
        console.log(`Textarea ${i}: visible=${isVisible}, value="${value.substring(0,30)}", distance=${Math.round(distance)}, zIndex=${zIndex}`);
        
        candidates.push({
            element: ta,
            value: value,
            distance: distance,
            zIndex: zIndex,
            hasContent: value.length > 0
        });
    }
    
    if (candidates.length === 0) {
        console.log('No visible textareas found');
        return null;
    }
    
    candidates.sort((a, b) => {
        if (a.hasContent !== b.hasContent) {
            return b.hasContent ? 1 : -1;
        }
        if (Math.abs(a.distance - b.distance) > 50) {
            return a.distance - b.distance;
        }
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
            
            print(f'[APPEND_X] Clicking at ({x}, {y})')
            self.page.mouse.click(x, y)
            self.page.wait_for_timeout(200)

            try:
                self.page.evaluate("(cx,cy) => { const el = document.elementFromPoint(cx, cy); if(el && el.tagName && el.tagName.toLowerCase() === 'textarea') { el.focus(); el.selectionStart = el.value.length; el.selectionEnd = el.value.length; return true; } const t = document.querySelector('textarea[aria-label=Description]'); if(t){ t.focus(); t.selectionStart = t.value.length; t.selectionEnd = t.value.length; return true; } return false; }", x, y)
            except Exception:
                pass

            try:
                self.page.wait_for_function(
                    "() => { const a = document.activeElement; return !!(a && a.getAttribute && a.getAttribute('aria-label') === 'Description'); }",
                    timeout=2000,
                )
                print('[APPEND_X] textarea became active')
            except Exception:
                print('[APPEND_X] WARNING: textarea did not become active within timeout')
            
            print('[APPEND_X] Pressing End key')
            self.page.keyboard.press('End')
            self.page.wait_for_timeout(150)
            
            print('[APPEND_X] Typing space')
            self.page.keyboard.type(' ')
            self.page.wait_for_timeout(200)
            
            print(f'[APPEND_X] SUCCESS - appended X to "{current}"')
            
            self._last_description = (current if current else '') + 'X'
            
        except Exception as e:
            print(f'[APPEND_X] ERROR: {e}')
            import traceback
            traceback.print_exc()

    def _do_append_text(self, text):
        """Append arbitrary text to current description."""
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

            self.page.mouse.click(x, y)
            self.page.wait_for_timeout(300)
            
            try:
                self.page.evaluate("(cx,cy) => { const el = document.elementFromPoint(cx, cy); if(el && el.tagName && el.tagName.toLowerCase() === 'textarea') { el.focus(); el.selectionStart = el.value.length; el.selectionEnd = el.value.length; return true; } const t = document.querySelector('textarea[aria-label=Description]'); if(t){ t.focus(); t.selectionStart = t.value.length; t.selectionEnd = t.value.length; return true; } return false; }", x, y)
            except Exception:
                pass
            
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
            
            self.page.keyboard.type(text + ' ')
            self.page.wait_for_timeout(200)

            self._last_description = (current if current else '') + text
            print(f'[APPEND_TEXT] SUCCESS - appended {repr(text)}')

        except Exception as e:
            print(f'[APPEND_TEXT] ERROR: {e}')
            import traceback
            traceback.print_exc()

    def _do_backspace(self):
        """Send backspace key to the active textarea."""
        try:
            print('[BACKSPACE] Starting...')
            
            # Reuse the same textarea finding logic as append_text
            js_find = """() => {
    const textareas = document.querySelectorAll('textarea[aria-label=\"Description\"]');
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
    const rect = target.rect;
    return { x: rect.left + rect.width/2, y: rect.top + rect.height/2 };
}"""

            result = self.page.evaluate(js_find)
            if not result:
                print('[BACKSPACE] FAILED - No textarea found')
                return

            x = result['x']
            y = result['y']
            
            # Click and focus the textarea
            self.page.mouse.click(x, y)
            self.page.wait_for_timeout(200)
            
            # Focus it
            try:
                self.page.evaluate("(cx,cy) => { const el = document.elementFromPoint(cx, cy); if(el && el.tagName && el.tagName.toLowerCase() === 'textarea') { el.focus(); return true; } return false; }", x, y)
            except Exception:
                pass
            
            # Send backspace
            print('[BACKSPACE] Sending backspace')
            self.page.keyboard.press('Backspace')
            self.page.wait_for_timeout(100)
            
        except Exception as e:
            print(f'[BACKSPACE] ERROR: {e}')
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    print('[DEBUG] Script started')
    try:
        main()
    except Exception as e:
        print(f'[FATAL ERROR] {e}')
        import traceback
        traceback.print_exc()
