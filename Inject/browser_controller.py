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
                    pass
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
                elif cmd == 'dump_analysis':
                    self._do_dump_analysis()
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
            // Helper function to check if element is visually hidden
            function isElementVisuallyHidden(element) {
                let current = element;
                while (current && current.tagName !== 'BODY') {
                    if (current.getAttribute('aria-hidden') === 'true') {
                        return true;
                    }
                    const style = current.getAttribute('style') || '';
                    if (style.toLowerCase().includes('display: none') || style.toLowerCase().includes('display:none')) {
                        return true;
                    }
                    current = current.parentElement;
                }
                return false;
            }

            // Find all description textareas
            const textareas = document.querySelectorAll('textarea[aria-label="Description"]');

            // Find the visible one
            for (const ta of textareas) {
                if (ta.offsetHeight > 0 && !isElementVisuallyHidden(ta)) {
                    // Focus and position cursor WITHOUT any scrolling
                    ta.focus();
                    ta.selectionStart = ta.value.length;
                    ta.selectionEnd = ta.value.length;

                    // Prevent default scroll behavior
                    ta.scrollTop = ta.scrollHeight;

                    return {
                        textLength: ta.value.length,
                        value: ta.value,
                        success: true
                    };
                }
            }

            return null;
        }""")

            if result:
                print(f'[CURSOR] Positioned cursor at END (text length: {result.get("textLength", 0)})')
            else:
                print('[CURSOR] No visible textarea found')

        except Exception as e:
            print(f'[CURSOR] ERROR: {e}')
    
    def _do_dump_analysis(self):
        """Run dump-explorer style analysis on current page."""
        try:
            print('\n' + '='*60)
            print('[ANALYSIS] Starting dump-explorer analysis...')
            print('='*60)
            
            # Execute the analysis JavaScript
            result = self.page.evaluate("""() => {
                // Helper function to check if element is visually hidden
                function isElementVisuallyHidden(element) {
                    let current = element;
                    while (current && current.tagName !== 'BODY') {
                        if (current.getAttribute('aria-hidden') === 'true') {
                            return true;
                        }
                        const style = current.getAttribute('style') || '';
                        if (style.toLowerCase().includes('display: none') || style.toLowerCase().includes('display:none')) {
                            return true;
                        }
                        current = current.parentElement;
                    }
                    return false;
                }
                
                // Find the active sidebar root
                const textarea = document.querySelector('textarea');
                if (!textarea) {
                    return { error: 'No textarea found' };
                }
                
                let sidebarRoot = textarea.closest('.ZPTMcc');
                if (!sidebarRoot) {
                    sidebarRoot = textarea.closest('.YW656b');
                }
                
                if (!sidebarRoot) {
                    return { error: 'No sidebar root found' };
                }
                
                const results = {
                    sidebarClass: sidebarRoot.className,
                    albums: [],
                    allAlbums: [],
                    faces: [],
                    allFaces: [],
                    textareas: [],
                    currentDescription: textarea.value || '',
                    textareaInfo: {
                        ariaLabel: textarea.getAttribute('aria-label'),
                        id: textarea.id,
                        className: textarea.className
                    }
                };
                
                // Analyze ALL textareas in document
                const allTextareas = document.querySelectorAll('textarea[aria-label="Description"]');
                const centerX = window.innerWidth / 2;
                const centerY = window.innerHeight / 2;
                
                for (let i = 0; i < allTextareas.length; i++) {
                    const ta = allTextareas[i];
                    const rect = ta.getBoundingClientRect();
                    const value = (ta.value || '').trim();
                    const hidden = isElementVisuallyHidden(ta);
                    const inSidebar = sidebarRoot.contains(ta);
                    
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
                    
                    results.textareas.push({
                        index: i + 1,
                        ariaLabel: ta.getAttribute('aria-label'),
                        id: ta.id || '(no id)',
                        className: ta.className || '(no class)',
                        offsetHeight: ta.offsetHeight,
                        offsetWidth: ta.offsetWidth,
                        hasContent: value.length > 0,
                        contentLength: value.length,
                        contentPreview: value.substring(0, 50),
                        hidden: hidden,
                        inSidebar: inSidebar,
                        distance: Math.round(distance),
                        zIndex: zIndex,
                        rect: {
                            top: Math.round(rect.top),
                            left: Math.round(rect.left),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    });
                }
                
                // Find ALL Album Names in entire document
                const allDgvy7DivsGlobal = document.querySelectorAll('div.DgVY7');
                for (let i = 0; i < allDgvy7DivsGlobal.length; i++) {
                    const dgvy7Div = allDgvy7DivsGlobal[i];
                    const nameDiv = dgvy7Div.querySelector('div.AJM7gb');
                    if (nameDiv && nameDiv.textContent) {
                        const text = nameDiv.textContent.trim();
                        const hidden = isElementVisuallyHidden(nameDiv);
                        const inSidebar = sidebarRoot.contains(dgvy7Div);
                        results.allAlbums.push({
                            index: i + 1,
                            text: text,
                            hidden: hidden,
                            inSidebar: inSidebar,
                            offsetHeight: nameDiv.offsetHeight
                        });
                    }
                }
                
                // Find albums ONLY in sidebar
                const allDgvy7Divs = sidebarRoot.querySelectorAll('div.DgVY7');
                for (let i = 0; i < allDgvy7Divs.length; i++) {
                    const dgvy7Div = allDgvy7Divs[i];
                    const nameDiv = dgvy7Div.querySelector('div.AJM7gb');
                    if (nameDiv && nameDiv.textContent) {
                        const text = nameDiv.textContent.trim();
                        const hidden = isElementVisuallyHidden(nameDiv);
                        results.albums.push({
                            index: i + 1,
                            text: text,
                            hidden: hidden
                        });
                    }
                }
                
                // Find ALL Face/People Tags in entire document
                const allSpansGlobal = document.querySelectorAll('span.Y8X4Pc');
                for (let i = 0; i < allSpansGlobal.length; i++) {
                    const span = allSpansGlobal[i];
                    const text = span.textContent.trim();
                    if (text) {
                        const hidden = isElementVisuallyHidden(span);
                        const inSidebar = sidebarRoot.contains(span);
                        results.allFaces.push({
                            index: i + 1,
                            text: text,
                            hidden: hidden,
                            inSidebar: inSidebar,
                            offsetHeight: span.offsetHeight
                        });
                    }
                }
                
                // Find faces ONLY in sidebar
                const allSpans = sidebarRoot.querySelectorAll('span.Y8X4Pc');
                const spansToCheck = Array.from(allSpans).slice(-5);
                
                for (let i = 0; i < spansToCheck.length; i++) {
                    const span = spansToCheck[i];
                    const text = span.textContent.trim();
                    if (text) {
                        const hidden = isElementVisuallyHidden(span);
                        results.faces.push({
                            index: i + 1,
                            text: text,
                            hidden: hidden,
                            offsetHeight: span.offsetHeight
                        });
                    }
                }
                
                return results;
            }""")
            
            if result.get('error'):
                print(f'[ANALYSIS] ERROR: {result["error"]}')
                return
            
            # Print results
            print(f'\n[ANALYSIS] Sidebar Root Class: {result.get("sidebarClass", "N/A")}')
            textarea_info = result.get('textareaInfo', {})
            print(f'[ANALYSIS] Textarea: aria-label="{textarea_info.get("ariaLabel", "N/A")}", id="{textarea_info.get("id", "N/A")}"')
            current_description = result.get("currentDescription", "")
            print(f'[ANALYSIS] Current Description: "{current_description[:80]}..."')
            
            # Print textarea analysis
            textareas = result.get('textareas', [])
            print(f'\n[ANALYSIS] === ALL TEXTAREAS FOUND IN DOCUMENT (textarea[aria-label="Description"]): {len(textareas)} ===')
            if textareas:
                for ta in textareas:
                    status = 'HIDDEN' if ta['hidden'] else 'VISIBLE'
                    location = '*** IN SIDEBAR ***' if ta['inSidebar'] else 'outside sidebar'
                    content_status = f"has content ({ta['contentLength']} chars)" if ta['hasContent'] else "empty"
                    
                    print(f'[ANALYSIS]   {ta["index"]}. textarea (aria-label="{ta["ariaLabel"]}", offsetHeight={ta["offsetHeight"]}, {content_status})')
                    print(f'[ANALYSIS]       Location: {location}')
                    print(f'[ANALYSIS]       Visibility: {status}')
                    print(f'[ANALYSIS]       Size: {ta["offsetWidth"]}x{ta["offsetHeight"]} at ({ta["rect"]["left"]}, {ta["rect"]["top"]})')
                    print(f'[ANALYSIS]       Distance from center: {ta["distance"]}px, z-index: {ta["zIndex"]}')
                    if ta['hasContent']:
                        print(f'[ANALYSIS]       Content preview: "{ta["contentPreview"]}..."')
                    print()
            else:
                print('[ANALYSIS]   (none found)')
            
            # Determine which textarea would be selected
            if textareas:
                print('[ANALYSIS] --- TEXTAREA SELECTION ANALYSIS ---')
                candidates = [ta for ta in textareas if ta['offsetHeight'] > 0 and ta['offsetWidth'] > 0]
                if candidates:
                    candidates.sort(key=lambda x: (
                        not x['hasContent'],
                        x['distance'],
                        -x['zIndex']
                    ))
                    selected = candidates[0]
                    print(f'[ANALYSIS] Current logic would select: Textarea {selected["index"]}')
                    print(f'[ANALYSIS]   Reason: hasContent={selected["hasContent"]}, distance={selected["distance"]}px, zIndex={selected["zIndex"]}')
                else:
                    print('[ANALYSIS] Current logic would find NO visible textarea')
                
                visible_only = [ta for ta in textareas if not ta['hidden'] and ta['offsetHeight'] > 0]
                if visible_only:
                    print(f'\n[ANALYSIS] Simple visibility filter would find: {len(visible_only)} textarea(s)')
                    for ta in visible_only:
                        print(f'[ANALYSIS]   - Textarea {ta["index"]} (distance={ta["distance"]}px)')
                print()
            
            # ALL Albums
            all_albums = result.get('allAlbums', [])
            print(f'\n[ANALYSIS] === ALL ALBUMS FOUND IN DOCUMENT (div.DgVY7 > div.AJM7gb): {len(all_albums)} ===')
            if all_albums:
                for album in all_albums:
                    status = 'HIDDEN' if album['hidden'] else 'VISIBLE'
                    location = '*** IN SIDEBAR ***' if album['inSidebar'] else 'outside sidebar'
                    height_info = f'offsetHeight={album["offsetHeight"]}'
                    print(f'[ANALYSIS]   {album["index"]}. "{album["text"]}" ({status}, {location}, {height_info})')
            else:
                print('[ANALYSIS]   (none found)')
            
            # Albums in sidebar
            albums = result.get('albums', [])
            print(f'\n[ANALYSIS] --- ALBUMS IN SIDEBAR (what old script would see): {len(albums)} ---')
            if albums:
                for album in albums:
                    status = 'HIDDEN/IGNORED' if album['hidden'] else 'VISIBLE/PROCESSED'
                    marker = '>>> SELECTED <<<' if not album['hidden'] else ''
                    print(f'[ANALYSIS]   {album["index"]}. "{album["text"]}" ({status}) {marker}')
            else:
                print('[ANALYSIS]   (none found in sidebar)')
            
            # ALL Faces
            all_faces = result.get('allFaces', [])
            print(f'\n[ANALYSIS] === ALL FACES FOUND IN DOCUMENT (span.Y8X4Pc): {len(all_faces)} ===')
            if all_faces:
                for face in all_faces:
                    status = 'HIDDEN' if face['hidden'] else 'VISIBLE'
                    location = '*** IN SIDEBAR ***' if face['inSidebar'] else 'outside sidebar'
                    height_info = f'offsetHeight={face["offsetHeight"]}'
                    print(f'[ANALYSIS]   {face["index"]}. "{face["text"]}" ({status}, {location}, {height_info})')
            else:
                print('[ANALYSIS]   (none found)')
            
            # Faces in sidebar
            faces = result.get('faces', [])
            print(f'\n[ANALYSIS] --- FACES IN SIDEBAR LAST 5 (what old script would see): {len(faces)} ---')
            if faces:
                for face in faces:
                    status = 'HIDDEN/IGNORED' if face['hidden'] else 'VISIBLE/PROCESSED'
                    marker = '>>> SELECTED <<<' if not face['hidden'] else ''
                    height_info = f'offsetHeight={face["offsetHeight"]}'
                    print(f'[ANALYSIS]   {face["index"]}. "{face["text"]}" ({status}, {height_info}) {marker}')
            else:
                print('[ANALYSIS]   (none found in sidebar last 5)')
            
            # NEW: NAME PROCESSING SIMULATION
            print(f'\n[ANALYSIS] === NAME PROCESSING SIMULATION ===')
            
            # Load special cases
            try:
                import json
                with open('names.json') as f:
                    data = json.load(f)
                    special_cases = data.get('special_cases', {})
            except Exception as e:
                print(f'[ANALYSIS] WARNING: Could not load names.json: {e}')
                special_cases = {}
            
            # Collect all visible names (faces + albums)
            visible_names = []
            for face in all_faces:
                if not face['hidden'] and face['offsetHeight'] > 0:
                    visible_names.append(('face', face['text']))
            for album in all_albums:
                if not album['hidden'] and album['offsetHeight'] > 0:
                    visible_names.append(('album', album['text']))
            
            if visible_names:
                desc_normalized = ' '.join(current_description.split()).lower()
                names_would_add = []
                
                for source_type, name in visible_names:
                    print(f'\n[ANALYSIS] Processing {source_type}: "{name}"')
                    
                    # Normalize
                    name_to_check = ' '.join(name.split())
                    
                    # Year/digit prefix check
                    if name_to_check and len(name_to_check) >= 4 and name_to_check[0:4].isdigit():
                        print(f'[ANALYSIS]   → Year check: FAIL (starts with {name_to_check[0:4]})')
                        print(f'[ANALYSIS]   → RESULT: SKIPPED (year-prefixed album)')
                        continue
                    
                    if name_to_check and name_to_check.startswith("0"):
                        print(f'[ANALYSIS]   → Starts with 0: FAIL')
                        print(f'[ANALYSIS]   → RESULT: SKIPPED')
                        continue
                    
                    print(f'[ANALYSIS]   → Year check: PASS (not year-prefixed)')
                    
                    # Special case mapping
                    if name_to_check in special_cases:
                        mapped_name = special_cases[name_to_check]
                        print(f'[ANALYSIS]   → Special case: "{name_to_check}" → "{mapped_name}"')
                        name_to_check = mapped_name
                    else:
                        print(f'[ANALYSIS]   → Special case: "{name_to_check}" (no mapping)')
                    
                    # Duplication check
                    normalized_check = ' '.join(name_to_check.split()).lower()
                    if normalized_check in desc_normalized:
                        print(f'[ANALYSIS]   → Duplication: "{name_to_check}" already in description')
                        print(f'[ANALYSIS]   → RESULT: SKIPPED')
                        continue
                    
                    if normalized_check in [n.lower() for n in names_would_add]:
                        print(f'[ANALYSIS]   → Duplication: "{name_to_check}" already in add list')
                        print(f'[ANALYSIS]   → RESULT: SKIPPED')
                        continue
                    
                    print(f'[ANALYSIS]   → Duplication: NOT in description')
                    print(f'[ANALYSIS]   → RESULT: >>> WOULD BE ADDED <<<')
                    names_would_add.append(name_to_check)
                    desc_normalized += ' ' + normalized_check
                
                print(f'\n[ANALYSIS] -' * 30)
                if names_would_add:
                    print(f'[ANALYSIS] Final names that would be appended: {names_would_add}')
                    print(f'[ANALYSIS] Total: {len(names_would_add)} name(s)')
                else:
                    print(f'[ANALYSIS] No names would be appended (all filtered out)')
            else:
                print('[ANALYSIS] No visible names found to process')
            
            print('\n' + '='*60)
            print('[ANALYSIS] Analysis complete')
            print('='*60 + '\n')
            
        except Exception as e:
            print(f'[ANALYSIS] ERROR: {e}')
            import traceback
            traceback.print_exc()
    
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
            import os
            with open('names.json') as f:
                data = json.load(f)
                names_list = data.get('names', [])
                special_cases = data.get('special_cases', {})

            print(f'[NAMES] Loaded special cases: {special_cases}')

            # Extract clean names (without parentheses) for logging
            clean_names = []
            for name_entry in names_list:
                clean = ''.join(c for c in name_entry if c not in '()').strip()
                if clean and clean != '4':
                    clean_names.append(clean)

            print(f'[NAMES] Searching for names: {clean_names}')

            # JS logic to extract all candidates with visibility check
            # CRITICAL CHANGE: Search entire document, not just sidebar
            js_find_names = r"""() => {
            let foundNames = [];

            // Helper function to check if element is visually hidden
            function isElementVisuallyHidden(element) {
                let current = element;
                while (current && current.tagName !== 'BODY') {
                    if (current.getAttribute('aria-hidden') === 'true') {
                        return true;
                    }
                    const style = current.getAttribute('style') || '';
                    if (style.toLowerCase().includes('display: none') || style.toLowerCase().includes('display:none')) {
                        return true;
                    }
                    current = current.parentElement;
                }
                return false;
            }

            // 1. Search for face/people tags (span.Y8X4Pc)
            const allSpanNames = document.querySelectorAll('span.Y8X4Pc');
            for (const span of allSpanNames) {
                if (span.textContent && !isElementVisuallyHidden(span) && span.offsetHeight > 0) {
                    foundNames.push(span.textContent.trim());
                }
            }

            // 2. Search for album names that might be people (div.DgVY7 > div.AJM7gb)
            const allAlbumDivs = document.querySelectorAll('div.DgVY7');
            for (const albumDiv of allAlbumDivs) {
                const nameDiv = albumDiv.querySelector('div.AJM7gb');
                if (nameDiv && nameDiv.textContent && !isElementVisuallyHidden(nameDiv) && nameDiv.offsetHeight > 0) {
                    const text = nameDiv.textContent.trim();
                    // Filter out year-prefixed albums (they're not people names)
                    if (!text.match(/^\d{4}/)) {
                        foundNames.push(text);
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

            # Retrieve the current description
            current_desc = self._sample_description() 
            if not current_desc:
                current_desc = ''

            # Normalize description early for comparison
            desc_normalized = ' '.join(current_desc.split()).lower()

            print(f'[NAMES] Current description: {repr(current_desc)[:80]}')

            if not avoid_scroll:
                print('[NAMES] Positioning cursor at END before adding names')
                self._position_cursor_at_end()
            else:
                print('[NAMES] Skipping cursor positioning to avoid scroll')
                
            for found_name in found_names:
                print(f'[NAMES] Processing: {repr(found_name)}')
                
                # Normalize spaces
                name_to_check = ' '.join(found_name.split())
                
                # 1. Year/Digit Prefix Check
                if name_to_check and name_to_check[0:4].isdigit():
                    print(f'[NAMES] Skipping year-prefixed text: "{name_to_check}"')
                    continue

                if name_to_check and name_to_check.startswith("0"):
                    print(f'[NAMES] Skipping name starting with 0: "{name_to_check}"')
                    continue
                
                # 2. Special Case Mapping
                if name_to_check in special_cases:
                    mapped_name = special_cases[name_to_check]
                    print(f'[NAMES] Special case: "{name_to_check}" -> "{mapped_name}"')
                    found_name = mapped_name
                else:
                    found_name = name_to_check # Use the cleaned version
                    
                # 3. Duplication Check
                # Use the mapped name (or cleaned original) for duplication check
                if found_name.lower() in desc_normalized: 
                    print(f'[NAMES] "{found_name}" already in description, skipping')
                    continue
                
                # 4. Append to description
                if not avoid_scroll:
                    self._position_cursor_at_end()
                    
                print(f'[NAMES] Adding " {found_name}" to description')
                self.append_text(' ' + found_name + ' ')
                
                # Update normalized description for subsequent duplication checks in this loop
                current_desc += ' ' + found_name + ' '
                desc_normalized = ' '.join(current_desc.split()).lower()
                
            if not avoid_scroll:
                print('[NAMES] Positioning cursor at END after adding all names')
                self._position_cursor_at_end()
            
        except FileNotFoundError as e:
            print(f'[NAMES] ERROR: Could not find or load names.json. Check working directory. ({e})')
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
    // Helper function to check if element is visually hidden
    function isElementVisuallyHidden(element) {
        let current = element;
        while (current && current.tagName !== 'BODY') {
            if (current.getAttribute('aria-hidden') === 'true') {
                return true;
            }
            const style = current.getAttribute('style') || '';
            if (style.toLowerCase().includes('display: none') || style.toLowerCase().includes('display:none')) {
                return true;
            }
            current = current.parentElement;
        }
        return false;
    }
    
    // Find all description textareas
    const textareas = document.querySelectorAll('textarea[aria-label="Description"]');
    console.log('Found textareas:', textareas.length);
    
            // Find the visible one
    for (let i = 0; i < textareas.length; i++) {
        const ta = textareas[i];

        // Simple visibility check: offsetHeight > 0 and not hidden
        if (ta.offsetHeight > 0 && !isElementVisuallyHidden(ta)) {
            const value = (ta.value || '').trim();
            console.log(`Selected visible textarea ${i}: value="${value.substring(0,30)}"`);
            return value;
        }
    }
    
    console.log('No visible textarea found');
    return null;
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
                "const t = document.querySelector('textarea[aria-label=\"Description\"]'); "
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


    def _do_append_text(self, text):
        """Append arbitrary text to current description WITHOUT scrolling right panel."""
        try:
            print(f'[APPEND_TEXT] Starting append of: {repr(text)[:50]}')
            js_find = """() => {
    // Helper function to check if element is visually hidden
    function isElementVisuallyHidden(element) {
        let current = element;
        while (current && current.tagName !== 'BODY') {
            if (current.getAttribute('aria-hidden') === 'true') {
                return true;
            }
            const style = current.getAttribute('style') || '';
            if (style.toLowerCase().includes('display: none') || style.toLowerCase().includes('display:none')) {
                return true;
            }
            current = current.parentElement;
        }
        return false;
    }
    
    // Find all description textareas
    const textareas = document.querySelectorAll('textarea[aria-label="Description"]');
    
    // Find the visible one
    for (const ta of textareas) {
        if (ta.offsetHeight > 0 && !isElementVisuallyHidden(ta)) {
            const rect = ta.getBoundingClientRect();
            const value = (ta.value || '').trim();
            
            return {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
                currentValue: value
            };
        }
    }
    
    return null;
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
            # Ensure cursor is positioned at the end after append
            try:
                self._position_cursor_at_end()
            except Exception as e:
                print(f'[APPEND_TEXT] WARNING: _position_cursor_at_end failed: {e}')

        except Exception as e:
            print(f'[APPEND_TEXT] ERROR: {e}')
            import traceback
            traceback.print_exc()
    def _do_backspace(self):
        """Send backspace key to the active textarea WITHOUT scrolling right panel."""
        try:
            print('[BACKSPACE] Starting...')
            
            js_find = """() => {
    // Helper function to check if element is visually hidden
    function isElementVisuallyHidden(element) {
        let current = element;
        while (current && current.tagName !== 'BODY') {
            if (current.getAttribute('aria-hidden') === 'true') {
                return true;
            }
            const style = current.getAttribute('style') || '';
            if (style.toLowerCase().includes('display: none') || style.toLowerCase().includes('display:none')) {
                return true;
            }
            current = current.parentElement;
        }
        return false;
    }
    
    // Find all description textareas
    const textareas = document.querySelectorAll('textarea[aria-label="Description"]');
    
    // Find the visible one
    for (const ta of textareas) {
        if (ta.offsetHeight > 0 && !isElementVisuallyHidden(ta)) {
            const rect = ta.getBoundingClientRect();
            const value = (ta.value || '').trim();
            
            return {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
                currentValue: value
            };
        }
    }
    
    return null;
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

            # Position cursor at END using programmatic selection (more reliable
            # than sending End key). Then verify the active element and selection
            # are at the end before sending Backspace. If verification fails,
            # fall back to End key.
            print('[BACKSPACE] Positioning cursor at END (programmatic)')
            try:
                self._position_cursor_at_end()

                # Verify active element is the description textarea and caret at end
                try:
                    self.page.wait_for_function(
                        """() => {
                            const a = document.activeElement;
                            if (!a) return false;
                            if (a.tagName && a.tagName.toLowerCase() === 'textarea' && a.getAttribute && a.getAttribute('aria-label') === 'Description') {
                                return a.selectionStart === a.value.length && a.selectionEnd === a.value.length;
                            }
                            return false;
                        }""",
                        timeout=1500,
                    )
                    verified = True
                except Exception:
                    verified = False

                if not verified:
                    print('[BACKSPACE] WARNING: cursor verification failed, falling back to End key')
                    self.page.keyboard.press('End')
                    self.page.wait_for_timeout(50)

            except Exception as e:
                print(f'[BACKSPACE] WARNING: programmatic positioning failed: {e}; falling back to End key')
                try:
                    self.page.keyboard.press('End')
                    self.page.wait_for_timeout(50)
                except Exception:
                    pass

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
    // Helper function to check if element is visually hidden
    function isElementVisuallyHidden(element) {
        let current = element;
        while (current && current.tagName !== 'BODY') {
            if (current.getAttribute('aria-hidden') === 'true') {
                return true;
            }
            const style = current.getAttribute('style') || '';
            if (style.toLowerCase().includes('display: none') || style.toLowerCase().includes('display:none')) {
                return true;
            }
            current = current.parentElement;
        }
        return false;
    }
    
    // Find all description textareas
    const textareas = document.querySelectorAll('textarea[aria-label="Description"]');
    
    // Find the visible one
    for (const ta of textareas) {
        if (ta.offsetHeight > 0 && !isElementVisuallyHidden(ta)) {
            const rect = ta.getBoundingClientRect();
            const value = (ta.value || '').trim();
            
            return {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
                currentValue: value
            };
        }
    }
    
    return null;
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
            for _ in range(150):
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

    def dump_analysis(self):
        """Run dump-explorer analysis on current page state.

        This enqueues a 'dump_analysis' command for the worker to handle.
        The worker must implement handling for the 'dump_analysis' command
        (e.g. a `_do_dump_analysis` method) to perform the actual analysis.
        """
        if not self._running:
            raise RuntimeError('Browser not running')
        self._cmd_queue.put(('dump_analysis', None))
