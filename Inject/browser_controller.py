"""Browser controller - extracted from inject_v3.py"""
import time
import queue
import threading

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


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
        
        # Check if browser is already running
        import os
        import pathlib
        user_data_dir = str(pathlib.Path.home() / '.googlephotos_profile')
        lock_file = os.path.join(user_data_dir, 'SingletonLock')
      
        if os.path.exists(lock_file):
            print(f'\n[ERROR] Browser appears to be already running!')
            print(f'[ERROR] Lock file exists: {lock_file}')
            print(f'[ERROR] Please close any existing browser windows first.')
            print(f'[ERROR] If no browser is visible, remove the lock file manually.\n')
            #raise RuntimeError(f'Browser already running (lock file: {lock_file})')
            return  # Just return instead of raising exception


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
            
            # Default to iOS 12 iPad (most compatible with Google Photos)
            user_agent = 'Mozilla/5.0 (iPad; CPU OS 12_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Mobile/15E148 Safari/604.1'
            print('[BROWSER] Mode: iOS 12 iPad')
            print(f'[BROWSER] Using user agent: {user_agent}')
            
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=not headful,
                channel='chrome',
                #user_agent=user_agent,
                #viewport={'width': 1024, 'height': 768},
                #device_scale_factor=1,
                #is_mobile=True,
                #has_touch=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    # '--user-agent=' + user_agent,
                    # '--disable-web-security',
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
                elif cmd == 'delete_all':
                    self._do_delete_all()
                elif cmd == 'keystroke':
                    self.page.keyboard.press(arg)

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


    def _position_cursor_at_end(self):
        """Position cursor at END of description textarea WITHOUT scrolling."""
        try:
            print('[CURSOR] Positioning cursor at END...')
            
            # Use pure JavaScript to find and position cursor - NO clicking, NO key pressing
            result = self.page.evaluate("""() => {
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
                
                // Focus and position cursor WITHOUT any scrolling
                target.element.focus();
                target.element.selectionStart = target.element.value.length;
                target.element.selectionEnd = target.element.value.length;
                
                // Prevent default scroll behavior
                target.element.scrollTop = target.element.scrollHeight;
                
                return {
                    textLength: target.value.length,
                    value: target.value,
                    success: true
                };
            }""")
            
            if result:
                print(f'[CURSOR] Positioned cursor at END (text length: {result.get("textLength", 0)})')
            else:
                print('[CURSOR] No textarea found')
                
        except Exception as e:
            print(f'[CURSOR] ERROR: {e}')

        def _scroll_right_panel_to_top(self):
            """Scroll the right information panel to the top to ensure description is visible."""
            try:
                print('[SCROLL] Ensuring right panel is scrolled to top...')
                js_scroll = """() => {
        // Focus the description textarea first
        const textarea = document.querySelector('textarea.tL9Q4c');
        if (textarea) textarea.focus();
        // Then scroll the right panel
        const container = document.querySelector('.ZPTMcc');
        if (container) {
            container.scrollTop = 0;
            return { success: true, selector: '.ZPTMcc' };
        }
        return { success: false };
    }"""
                result = self.page.evaluate(js_scroll)
                if result.get('success'):
                    print(f'[SCROLL] Scrolled right panel to top (found: {result["selector"]})')
                else:
                    print('[SCROLL] Warning: Could not find scrollable right panel')
            except Exception as e:
                print(f'[SCROLL] Error: {e}')
                # Don't fail the operation, log and continue


    def _extract_and_add_names(self, avoid_scroll=True):
        """Extract names from webpage section and add to description if not already there.
        
        Args:
            avoid_scroll: If True, skip clicking/positioning to avoid scrolling the right panel
        """
        try:
            print('[NAMES] Extracting names from webpage...')
            
            # Load names and special cases from names.json
            import json
            with open('names.json') as f:
                data = json.load(f)
                names_list = data.get('names', [])
                special_cases = data.get('special_cases', {})
            
            print(f'[NAMES] Loaded special cases: {special_cases}')
            
            # Extract clean names (without parentheses)
            clean_names = []
            for name_entry in names_list:
                clean = ''.join(c for c in name_entry if c not in '()').strip()
                if clean and clean != '4':
                    clean_names.append(clean)
            
            print(f'[NAMES] Searching for names: {clean_names}')
            
            js_find_names = """() => {
    let foundNames = [];
    const allDivs = document.querySelectorAll('div.DgVY7');
    const allSpans = document.querySelectorAll('span.Y8X4Pc');
    
    if (allDivs.length > 0) {
        const lastDiv = allDivs[allDivs.length - 1];
        const nameDiv = lastDiv.querySelector('div.AJM7gb');
        if (nameDiv && nameDiv.textContent) {
            foundNames.push(nameDiv.textContent.trim());
        }
    }
    
    if (allSpans.length > 0) {
        for (let i = Math.max(0, allSpans.length - 5); i < allSpans.length; i++) {
            const span = allSpans[i];
            const rect = span.getBoundingClientRect();
            if (rect.height > 0 && rect.width > 0) {
                if (span.textContent) {
                    foundNames.push(span.textContent.trim());
                }
            }
        }
    }
    
    return foundNames.length > 0 ? foundNames : null;
}"""
            
            found_names = self.page.evaluate(js_find_names)
            
            if not found_names:
                print('[NAMES] No name sections found on webpage')
                return
            
            print(f'[NAMES] Found names in webpage: {found_names}')
            
            current_desc = self._sample_description()
            if not current_desc:
                current_desc = ''
            
            print(f'[NAMES] Current description: {repr(current_desc)[:80]}')
            
            if not avoid_scroll:
                print('[NAMES] Positioning cursor at END before adding names')
                self._position_cursor_at_end()
            else:
                print('[NAMES] Skipping cursor positioning to avoid scroll')
            
            for found_name in found_names:
                print(f'[NAMES] Processing: {repr(found_name)}')
                found_name = ' '.join(found_name.split())
                
                if found_name and found_name[0:4].isdigit():
                    print(f'[NAMES] Skipping year-prefixed text: "{found_name}"')
                    continue

                if found_name and found_name.startswith("0"):
                    print(f'[NAMES] Skipping name starting with 0: "{found_name}"')
                    continue
                
                if found_name in special_cases:
                    mapped_name = special_cases[found_name]
                    print(f'[NAMES] Special case: "{found_name}" -> "{mapped_name}"')
                    found_name = mapped_name
                
                desc_normalized = ' '.join(current_desc.split())
                if found_name in desc_normalized:
                    print(f'[NAMES] "{found_name}" already in description, skipping')
                    continue
                
                if not avoid_scroll:
                    self._position_cursor_at_end()
                
                print(f'[NAMES] Adding " {found_name}" to description')
                self.append_text(' ' + found_name + ' ')
                current_desc += ' ' + found_name + ' '
            
            if not avoid_scroll:
                print('[NAMES] Positioning cursor at END after adding all names')
                self._position_cursor_at_end()
            
        except Exception as e:
            print(f'[NAMES] ERROR: {e}')
    def _navigate_photo(self, direction):
        """Common navigation logic for next/prev photo.
        
        Click image center to focus it, then send arrow key.
        
        NOTE: Alternative approach if dynamic image finding breaks in future:
        Instead of searching for image elements, could use fixed viewport:
          - Set viewport={'width': 1024, 'height': 768} in browser launch
          - Always click at viewport center (512, 384) to focus image
          - This guarantees focus but loses responsive behavior
        Currently using dynamic image detection which is more flexible.
        """
        arrow_key = 'ArrowRight' if direction == 'next' else 'ArrowLeft'
        label = direction.upper()
        
        try:
            print(f'[{label}] Step 1: Starting navigation...')
            
            # Find and click the main viewer image
            result = self.page.evaluate("""() => {
                // Look for the main image in the viewer - be more specific
                // Try multiple selectors in order of likelihood
                const selectors = [
                    'img[alt="View photo"]',
                    'img[alt*="View"]',
                    'img[role="button"]',
                    'img[jsname]'
                ];
                
                for (let selector of selectors) {
                    const imgs = document.querySelectorAll(selector);
                    for (let img of imgs) {
                        const rect = img.getBoundingClientRect();
                        const style = window.getComputedStyle(img);
                        
                        // Must be visible and reasonably sized
                        if (rect.width > 100 && rect.height > 100 && style.display !== 'none' && style.visibility !== 'hidden') {
                            // Click the center
                            return {
                                x: rect.left + rect.width / 2,
                                y: rect.top + rect.height / 2,
                                width: rect.width,
                                height: rect.height,
                                selector: selector,
                                found: true
                            };
                        }
                    }
                }
                return { found: false };
            }""")
            
            print(f'[{label}] Step 2: Image location found')
            
            if result and result.get('found'):
                x = result['x']
                y = result['y']
                width = result.get('width', 0)
                height = result.get('height', 0)
                selector = result.get('selector', 'unknown')
                print(f'[{label}] Step 3a: Found via "{selector}", size {int(width)}x{int(height)}, clicking center at ({int(x)}, {int(y)})')
                self.page.mouse.click(x, y)
                print(f'[{label}] Step 3b: Click completed')
                self.page.wait_for_timeout(100)
                print(f'[{label}] Step 3c: Wait after click completed')
            else:
                print(f'[{label}] Step 3: WARNING: Could not find image to click')
            
            # Now send arrow key
            print(f'[{label}] Step 4a: About to send {arrow_key}')
            self.page.keyboard.press(arrow_key)
            print(f'[{label}] Step 4b: Arrow key sent')
            self.page.wait_for_timeout(500)
            print(f'[{label}] Step 4c: Wait after arrow key completed')
            
            try:
                self._last_url = self.page.url
                print(f'[{label}] Step 5: URL updated')
            except Exception:
                pass
            
            # Just read description, don't interact with textarea (no clicking, no pressing keys)
            print(f'[{label}] Step 6a: About to sample description...')
            desc = self._sample_description()
            print(f'[{label}] Step 6b: Description sampled')
            self._last_description = desc
            print(f'[{label}] Step 6c: New description: {repr(desc)[:100]}')
            
            print(f'[{label}] Step 7a: About to extract and add names...')
            self._extract_and_add_names()
            print(f'[{label}] Step 7b: Extract and add names completed')
            
            print(f'[{label}] Step 8: Focusing textarea for keystroke input...')
            self._position_cursor_at_end()
            print(f'[{label}] Step 8b: Textarea focused and cursor positioned at end')
            
        except Exception as e:
            print(f'[{label}] ERROR: {e}')

    def _do_next(self):
        """Navigate to next photo."""
        self._navigate_photo('next')

    def _do_prev(self):
        """Navigate to previous photo."""
        self._navigate_photo('prev')

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

    def _focus_textarea(self, x, y):
        """Common logic to focus and position cursor at end of textarea."""
        self.page.mouse.click(x, y)
        self.page.wait_for_timeout(15)
        
        try:
            self.page.evaluate(
                "(cx,cy) => { const el = document.elementFromPoint(cx, cy); "
                "if(el && el.tagName && el.tagName.toLowerCase() === 'textarea') { "
                "el.focus(); el.selectionStart = el.value.length; el.selectionEnd = el.value.length; "
                "return true; } "
                "const t = document.querySelector('textarea[aria-label=Description]'); "
                "if(t){ t.focus(); t.selectionStart = t.value.length; t.selectionEnd = t.value.length; "
                "return true; } return false; }", 
                x, y
            )
        except Exception:
            pass
        
        try:
            self.page.wait_for_function(
                "() => { const a = document.activeElement; "
                "return !!(a && a.getAttribute && a.getAttribute('aria-label') === 'Description'); }",
                timeout=2000,
            )
            print('[FOCUS] textarea became active')
        except Exception:
            print('[FOCUS] WARNING: textarea did not become active within timeout')

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
            self._focus_textarea(x, y)
            
            print('[APPEND_X] Pressing End key')
            self.page.keyboard.press('End')
            self.page.wait_for_timeout(5)
            
            print('[APPEND_X] Typing space')
            self.page.keyboard.type(' ')
            self.page.wait_for_timeout(10)
            
            print(f'[APPEND_X] SUCCESS - appended space to "{current}"')
            self._last_description = (current if current else '') + ' '
            
        except Exception as e:
            print(f'[APPEND_X] ERROR: {e}')
            import traceback
            traceback.print_exc()

    def _do_append_text(self, text):
        """Append arbitrary text to current description WITHOUT scrolling right panel."""
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
    const rect = target.rect;
    
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
                self.page.wait_for_timeout(5)
                result2 = self.page.evaluate(js_find)
                if result2 and result2.get('y') is not None and result2.get('y') >= 0:
                    x = result2['x']
                    y = result2['y']
                    current = result2.get('currentValue')
                    print(f"[APPEND_TEXT] Re-sampled textarea at ({x}, {y}), current value: {repr(current)[:80]}")
                else:
                    print('[APPEND_TEXT] FAILED - target remains off-screen after re-sample')
                    return

            # Freeze scroll - disable scroll events and save position
            self.page.evaluate("""() => {
                const panels = document.querySelectorAll('[data-has-scrollable="true"], .ZPTMcc, [role="complementary"]');
                for (let panel of panels) {
                    if (panel.scrollHeight > panel.clientHeight) {
                        window.__savedScrollPos = panel.scrollTop;
                        window.__scrollPanel = panel;
                        // Prevent scroll changes
                        panel.addEventListener('scroll', (e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            panel.scrollTop = window.__savedScrollPos;
                        }, true);
                    }
                }
            }""")
            print('[APPEND_TEXT] Scroll frozen')
            
            print('[APPEND_TEXT] Positioning cursor at END before typing')
            self._position_cursor_at_end()
            
            print(f'[APPEND_TEXT] Typing text: {repr(text)}')
            self.page.keyboard.type(text)
            self.page.wait_for_timeout(10)

            # Unfreeze scroll
            self.page.evaluate("""() => {
                if (window.__scrollPanel) {
                    window.__scrollPanel.scrollTop = window.__savedScrollPos;
                    window.__scrollPanel = null;
                    window.__savedScrollPos = null;
                }
            }""")
            print('[APPEND_TEXT] Scroll unfrozen')

            self._last_description = (current if current else '') + text
            print(f'[APPEND_SUCCESS] Appended {repr(text)} to description')

        except Exception as e:
            print(f'[APPEND_TEXT] ERROR: {e}')
            import traceback
            traceback.print_exc()
    def _do_backspace(self):
        """Send backspace key to the active textarea WITHOUT scrolling right panel."""
        try:
            print('[BACKSPACE] Starting...')
            
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
    const rect = target.rect;
    return { x: rect.left + rect.width/2, y: rect.top + rect.height/2 };
}"""

            result = self.page.evaluate(js_find)
            if not result:
                print('[BACKSPACE] FAILED - No textarea found')
                return

            x = result['x']
            y = result['y']
            
            print(f'[BACKSPACE] Textarea at ({x}, {y})')

            # Freeze scroll - disable scroll events and save position
            self.page.evaluate("""() => {
                const panels = document.querySelectorAll('[data-has-scrollable="true"], .ZPTMcc, [role="complementary"]');
                for (let panel of panels) {
                    if (panel.scrollHeight > panel.clientHeight) {
                        window.__savedScrollPos = panel.scrollTop;
                        window.__scrollPanel = panel;
                        // Prevent scroll changes
                        panel.addEventListener('scroll', (e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            panel.scrollTop = window.__savedScrollPos;
                        }, true);
                    }
                }
            }""")
            print('[BACKSPACE] Scroll frozen')

            self._focus_textarea(x, y)
            
            # Position cursor at END before backspacing
            print('[BACKSPACE] Positioning cursor at END')
            self.page.keyboard.press('End')
            self.page.wait_for_timeout(5)
            
            print('[BACKSPACE] Sending backspace')
            self.page.keyboard.press('Backspace')
            self.page.wait_for_timeout(15)

            # Unfreeze scroll
            self.page.evaluate("""() => {
                if (window.__scrollPanel) {
                    window.__scrollPanel.scrollTop = window.__savedScrollPos;
                    window.__scrollPanel = null;
                    window.__savedScrollPos = null;
                }
            }""")
            print('[BACKSPACE] Scroll unfrozen')

            print('[BACKSPACE] SUCCESS')
            
        except Exception as e:
            print(f'[BACKSPACE] ERROR: {e}')
            import traceback
            traceback.print_exc()

    def _do_delete_all(self):
        """Delete entire description."""
        try:
            print('[DELETE_ALL] Starting...')
            
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
    const rect = target.rect;
    return { x: rect.left + rect.width/2, y: rect.top + rect.height/2 };
}"""

            result = self.page.evaluate(js_find)
            if not result:
                print('[DELETE_ALL] FAILED - No textarea found')
                return

            x = result['x']
            y = result['y']
            
            print(f'[DELETE_ALL] Textarea at ({x}, {y})')
            self._focus_textarea(x, y)
            self._position_cursor_at_end()  # Explicitly position cursor at end
   
            
            print('[DELETE_ALL] Pressing backspace 50 times to clear description')
            for _ in range(50):
                self.page.keyboard.press('Backspace')
            self.page.wait_for_timeout(5)
            print('[DELETE_ALL] SUCCESS')
            
            self._last_description = ''
            
        except Exception as e:
            print(f'[DELETE_ALL] ERROR: {e}')
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

    def send_backspace(self):
        """Queue backspace command."""
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('backspace', None))

    def send_keystroke(self, key):
        """Send a raw keystroke to the web page without any focus/cursor manipulation."""
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('keystroke', key))

    def delete_all_description(self):
        """Queue delete all description command."""
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('delete_all', None))

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
