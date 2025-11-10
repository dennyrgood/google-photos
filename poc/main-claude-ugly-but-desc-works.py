#!/usr/bin/env python3
"""
Simple POC: Tkinter assistant UI that controls a Chromium browser via Playwright.

Notes:
- This is a starter prototype. The Google Photos DOM selectors are application-specific
  and are left as clearly-marked stubs for you to adapt after inspecting the page.
- Install dependencies: pip install -r requirements.txt
  then run: playwright install

Run: python main.py
"""
import json
import os
import threading
import queue
import sys
import time
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

ROOT = os.path.dirname(__file__)
NAMES_FILE = os.path.join(ROOT, 'names.json')


def load_names():
    if not os.path.exists(NAMES_FILE):
        return []
    with open(NAMES_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return []


def save_names(names):
    with open(NAMES_FILE, 'w', encoding='utf-8') as f:
        json.dump(names, f, indent=2, ensure_ascii=False)


class BrowserController:
    """Minimal Playwright wrapper. Keep simple for POC."""
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        # Command queue for communicating with the browser thread
        self._cmd_queue = queue.Queue()
        self._worker = None
        self._running = False
        self._ready_event = threading.Event()
        # last observed page state (updated by worker thread)
        self._last_url = None
        self._last_image_box = None
        self._last_description = None
        # track last-seen large-image source (helps identify current photo)
        self._last_photo_src = None
        # track which URL we last sampled a description for so we don't sample too early
        self._desc_sampled_for_url = None
        # track which photo src we last sampled for (preferred over url)
        self._desc_sampled_for_photo = None
        # Add a lock for thread-safe access to description
        self._state_lock = threading.Lock()

    def start(self, headful=True, timeout=30):
        """Start the browser worker thread and wait until Playwright is ready.

        This runs Playwright entirely inside a dedicated thread and processes commands
        from the UI via a queue to avoid cross-thread usage errors.
        """
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
        # request worker to stop
        self._cmd_queue.put(('stop', None))
        self._running = False
        if self._worker:
            self._worker.join(timeout=5)

    def _worker_main(self, headful):
        import pathlib

        try:
            self.playwright = sync_playwright().start()
            user_data_dir = str(pathlib.Path.home() / '.googlephotos_profile')
            try:
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=not headful,
                    channel='chrome',
                    args=['--disable-blink-features=AutomationControlled'],
                )
            except Exception:
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=not headful,
                    args=['--disable-blink-features=AutomationControlled'],
                )

            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.goto('https://photos.google.com')
            try:
                self._last_url = self.page.url
            except Exception:
                self._last_url = None
            # signal readiness to caller
            self._ready_event.set()

            # main command loop
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
                elif cmd == 'sample_now':
                    # arg is expected to be a tuple (event, result_container)
                    try:
                        ev, res_container = arg
                        self._do_sample()
                        res_container['description'] = self._last_description
                        try:
                            res_container['photo_src'] = self._desc_sampled_for_photo
                        except Exception:
                            res_container['photo_src'] = None
                        ev.set()
                    except Exception as e:
                        try:
                            res_container['error'] = str(e)
                        except Exception:
                            pass
                        try:
                            ev.set()
                        except Exception:
                            pass
                elif cmd == 'force_sample':
                    # Force a completely fresh sample, ignoring all cached state
                    try:
                        ev, res_container = arg
                        print('force_sample: starting fresh sample (bypassing all cache)...')
                        
                        # Debug: dump all textareas (only when explicitly requested)
                        try:
                            self._debug_dump_textareas()
                        except Exception as e:
                            print(f'force_sample: debug dump error (non-fatal): {e}')
                        
                        # Wait a moment for the page to be stable
                        try:
                            self.page.wait_for_timeout(300)
                        except Exception:
                            pass
                        
                        # Sample DIRECTLY and return immediately without touching cache
                        desc = None
                        photo_src = None
                        attempts = 3
                        for i in range(attempts):
                            try:
                                # Call _sample_description which reads the DOM directly RIGHT NOW
                                photo_src, desc = self._sample_description()
                                print(f"force_sample: attempt {i+1}/{attempts} -> photo_src={repr(photo_src)[:200]} desc={repr(desc)[:300]}")
                                if desc:
                                    # Found it! Return immediately WITHOUT updating any cache
                                    res_container['description'] = desc
                                    res_container['photo_src'] = photo_src
                                    print(f"force_sample: SUCCESS - returning fresh description: {repr(desc)[:300]}")
                                    ev.set()
                                    
                                    # NOW update the cache after we've already returned the result
                                    try:
                                        with self._state_lock:
                                            self._last_description = desc
                                            try:
                                                current_url = self.page.url
                                                if current_url:
                                                    self._desc_sampled_for_url = current_url
                                                if photo_src:
                                                    self._desc_sampled_for_photo = photo_src
                                            except Exception:
                                                pass
                                    except Exception as e:
                                        print(f"force_sample: cache update error: {e}")
                                    return
                                try:
                                    self.page.wait_for_timeout(500)
                                except Exception:
                                    pass
                            except Exception as e:
                                print(f"force_sample: attempt {i+1} error: {e}")
                                try:
                                    self.page.wait_for_timeout(500)
                                except Exception:
                                    pass
                        
                        # If we got here, we didn't find a description after all attempts
                        res_container['description'] = None
                        res_container['photo_src'] = photo_src
                        print(f"force_sample: FAILED - no description found after {attempts} attempts")
                        ev.set()
                    except Exception as e:
                        print(f'force_sample error: {e}')
                        import traceback
                        traceback.print_exc()
                        try:
                            res_container['error'] = str(e)
                            res_container['description'] = None
                        except Exception:
                            pass
                        try:
                            ev.set()
                        except Exception:
                            pass
                elif cmd == 'sample':
                    self._do_sample()
                elif cmd == 'apply':
                    self._do_apply(arg)
                elif cmd == 'inspect':
                    self._do_inspect()
                
                # Don't update state here - only do it on explicit commands to avoid constant page.evaluate() calls
                
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

    def _update_state(self):
        """Update the cached state (URL, image box, description) - called from worker thread."""
        try:
            # Update URL
            try:
                with self._state_lock:
                    self._last_url = self.page.url
            except Exception:
                pass
            
            # Update image box
            try:
                imgs = self.page.query_selector_all('img')
                big_box = None
                for im in imgs:
                    try:
                        b = im.bounding_box()
                        if b and b.get('width', 0) > 200 and b.get('height', 0) > 100:
                            big_box = b
                            break
                    except Exception:
                        continue
                with self._state_lock:
                    self._last_image_box = big_box
            except Exception:
                pass
            
            # Lightweight description sampler: only sample when the URL/photo changed
            try:
                current_url = None
                try:
                    current_url = self.page.url
                except Exception:
                    current_url = None
                
                # Get current large-image src
                photo_src = None
                try:
                    js_get_src = (
                        "() => {"
                        "  const imgs = Array.from(document.querySelectorAll('img'));"
                        "  for (const im of imgs) {"
                        "    try { const r = im.getBoundingClientRect(); if (r.width>200 && r.height>100) { return im.src || im.getAttribute('src') || ''; } } catch(e){}"
                        "  }"
                        "  return '';"
                        "}"
                    )
                    photo_src = self.page.evaluate(js_get_src)
                except Exception:
                    photo_src = None

                # Choose identifier: prefer photo_src, fall back to url
                identifier = photo_src or current_url
                already_sampled = (identifier and identifier == self._desc_sampled_for_photo) or (current_url and current_url == self._desc_sampled_for_url)
                
                # Don't auto-sample in the polling loop - only sample after explicit navigation
                # This prevents sampling the old description before navigation completes
                if False:  # Disabled - we now sample explicitly in _do_next/_do_prev
                    if identifier and not already_sampled:
                        try:
                            print(f"_update_state: attempting description sample for id={identifier[:200]}")
                            desc = None
                            # Try a few times with short delays
                            attempts = 5
                            for i in range(attempts):
                                sampled_photo_src, desc = self._sample_description()
                                print(f"_update_state: attempt {i+1}/{attempts} -> photo_src={repr(sampled_photo_src)[:160]} desc={repr(desc)[:240]}")
                                if desc:
                                    break
                                try:
                                    self.page.wait_for_timeout(200)
                                except Exception:
                                    time.sleep(0.2)
                            
                            with self._state_lock:
                                self._last_description = desc
                                # Mark that we sampled for this photo
                                if sampled_photo_src:
                                    self._desc_sampled_for_photo = sampled_photo_src
                                if current_url:
                                    self._desc_sampled_for_url = current_url
                            
                            print(f"_update_state: description updated -> {repr(desc)[:240]}")
                        except Exception as e:
                            print(f'_update_state: error while sampling description: {e}')
            except Exception:
                pass
        except Exception as e:
            print(f'_update_state: error: {e}')

    def goto_next_photo(self):
        # Enqueue next command to be processed in the browser worker thread.
        if not self._running:
            raise RuntimeError('Browser worker not running; call start() first')
        self._cmd_queue.put(('next', None))

    def goto_prev_photo(self):
        if not self._running:
            raise RuntimeError('Browser worker not running; call start() first')
        self._cmd_queue.put(('prev', None))

    def apply_description(self, text):
        if not self._running:
            raise RuntimeError('Browser worker not running; call start() first')
        # enqueue apply command; worker will perform the DOM operations
        self._cmd_queue.put(('apply', text))

    def sample_now(self, timeout=5.0):
        """Request an immediate sample from the worker and wait for the result.

        Returns the sampled description string or None. Raises RuntimeError if the
        worker isn't running.
        """
        if not self._running:
            raise RuntimeError('Browser worker not running; call start() first')
        ev = threading.Event()
        res = {}
        # Put a tuple of (event, result dict) as the arg for 'sample_now'
        self._cmd_queue.put(('sample_now', (ev, res)))
        ok = ev.wait(timeout)
        if not ok:
            return None
        # return description if present, else None
        return res.get('description')
    
    def force_fresh_sample(self, timeout=5.0):
        """Force a completely fresh sample ignoring all cached state.
        
        This is used by 'Read Current' to get the description of whatever
        photo is currently displayed, regardless of sampling history.
        """
        if not self._running:
            raise RuntimeError('Browser worker not running; call start() first')
        ev = threading.Event()
        res = {}
        self._cmd_queue.put(('force_sample', (ev, res)))
        ok = ev.wait(timeout)
        if not ok:
            return None
        return res.get('description')

    # Worker-side helpers (executed inside _worker_main thread)
    def _do_next(self):
        """Robust navigate to next photo."""
        def _get_snapshot():
            try:
                u = None
                try:
                    u = self.page.url
                except Exception:
                    u = None
                imgs = self.page.query_selector_all('img')
                big_box = None
                for im in imgs:
                    try:
                        b = im.bounding_box()
                        if b and b.get('width', 0) > 200 and b.get('height', 0) > 100:
                            big_box = b
                            break
                    except Exception:
                        continue
                return (u, big_box)
            except Exception:
                return (None, None)

        def _changed(before, after):
            bu, bb = before
            au, ab = after
            if bu and au and bu != au:
                return True
            if bb and ab and (bb.get('x') != ab.get('x') or bb.get('width') != ab.get('width')):
                return True
            return False

        try:
            try:
                self.page.bring_to_front()
            except Exception:
                pass

            before = _get_snapshot()
            print(f'_do_next: before snapshot url={before[0]} box={before[1]}')

            acted = False

            # Try clicking center of big image then pressing ArrowRight
            try:
                imgs = self.page.query_selector_all('img')
                for img in imgs:
                    try:
                        box = img.bounding_box()
                        if box and box.get('width', 0) > 200 and box.get('height', 0) > 100:
                            cx = box['x'] + box['width'] / 2
                            cy = box['y'] + box['height'] / 2
                            self.page.mouse.click(cx, cy)
                            print(f'_do_next: clicked image center at ({int(cx)},{int(cy)})')
                            self.page.wait_for_timeout(150)
                            try:
                                self.page.keyboard.press('ArrowRight')
                                print('_do_next: pressed ArrowRight')
                            except Exception:
                                pass
                            acted = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            # Wait for change
            after = _get_snapshot()
            waited = 0
            while waited < 1000 and not _changed(before, after):
                self.page.wait_for_timeout(150)
                waited += 150
                after = _get_snapshot()

            print(f'_do_next: after snapshot url={after[0]} box={after[1]} (waited {waited}ms)')

            # If changed, reset the sampled state and wait for page to fully render
            if _changed(before, after):
                # Wait longer for Google Photos to update the info panel
                self.page.wait_for_timeout(800)
                
                with self._state_lock:
                    self._desc_sampled_for_url = None
                    self._desc_sampled_for_photo = None
                    self._last_description = None
                print('_do_next: navigation detected, reset description state')
                
                # Force immediate sample of new description by waiting for textarea to update
                try:
                    print('_do_next: sampling new description after navigation...')
                    
                    # Just sample directly without waiting - the code already waited 800ms above
                    photo_src, desc = self._sample_description()
                    
                    if desc:
                        with self._state_lock:
                            self._last_description = desc
                            if photo_src:
                                self._desc_sampled_for_photo = photo_src
                            try:
                                self._desc_sampled_for_url = self.page.url
                            except Exception:
                                pass
                        print(f'_do_next: successfully got new description: {repr(desc)[:240]}')
                    else:
                        print('_do_next: no description found after navigation')
                except Exception as e:
                    print(f'_do_next: error sampling description: {e}')
            else:
                print('_do_next: no navigation detected')

        except Exception as e:
            print('goto_next_photo error:', e)

    def _do_prev(self):
        """Navigate to previous photo by clicking left edge or using keyboard."""
        try:
            self.page.bring_to_front()
        except Exception:
            pass

        # Strategy: Find and click the large image to focus, then use arrow key
        try:
            imgs = self.page.query_selector_all('img')
            big_box = None
            for img in imgs:
                try:
                    box = img.bounding_box()
                    if box and box.get('width', 0) > 200 and box.get('height', 0) > 100:
                        big_box = box
                        break
                except Exception:
                    continue
            
            if big_box:
                # Click center of image to focus the viewer
                cx = big_box['x'] + big_box['width'] / 2
                cy = big_box['y'] + big_box['height'] / 2
                try:
                    self.page.mouse.click(cx, cy)
                    self.page.wait_for_timeout(300)
                    self.page.keyboard.press('ArrowLeft')
                    print('Pressed ArrowLeft key')
                    self.page.wait_for_timeout(1500)
                    
                    # Reset description state and force immediate sample after navigation
                    with self._state_lock:
                        old_desc = self._last_description
                        self._desc_sampled_for_url = None
                        self._desc_sampled_for_photo = None
                        self._last_description = None
                    
                    print(f'_do_prev: old_desc={repr(old_desc)[:100]}')
                    
                    # Force immediate sample of new description with smart waiting
                    try:
                        print('_do_prev: sampling new description after navigation...')
                        attempts = 12
                        for i in range(attempts):
                            photo_src, desc = self._sample_description()
                            print(f"_do_prev: sample attempt {i+1}/{attempts} -> desc={repr(desc)[:200]}")
                            
                            # If we got a description AND it's different from old, we're good
                            if desc and (not old_desc or desc != old_desc):
                                with self._state_lock:
                                    self._last_description = desc
                                    if photo_src:
                                        self._desc_sampled_for_photo = photo_src
                                    try:
                                        self._desc_sampled_for_url = self.page.url
                                    except Exception:
                                        pass
                                print(f'_do_prev: successfully sampled new description: {repr(desc)[:240]}')
                                break
                            
                            # If no old_desc and we got something, accept it
                            if not old_desc and desc:
                                with self._state_lock:
                                    self._last_description = desc
                                    if photo_src:
                                        self._desc_sampled_for_photo = photo_src
                                    try:
                                        self._desc_sampled_for_url = self.page.url
                                    except Exception:
                                        pass
                                print(f'_do_prev: successfully sampled description (no old desc): {repr(desc)[:240]}')
                                break
                            
                            self.page.wait_for_timeout(400)
                    except Exception as e:
                        print(f'_do_prev: error sampling description: {e}')
                    
                    return
                except Exception as e:
                    print(f'Arrow key navigation failed: {e}')
        except Exception as e:
            print(f'Previous navigation failed: {e}')

    def _do_apply(self, text):
        """Apply action: click textarea and append 'X' using keyboard."""
        try:
            try:
                self.page.bring_to_front()
            except Exception as e:
                print(f'_do_apply: bring_to_front error: {e}')
            
            print('_do_apply: starting...')
            
            # Find the middle textarea (current photo)
            js_find = """() => {
    const textareas = document.querySelectorAll('textarea[aria-label="Description"]');
    console.log('Found textareas:', textareas.length);
    let visibleWithContent = [];
    
    for (let i = 0; i < textareas.length; i++) {
        const ta = textareas[i];
        const rect = ta.getBoundingClientRect();
        const isVisible = rect.width > 0 && rect.height > 0;
        const value = (ta.value || '').trim();
        
        console.log(`Textarea ${i}: visible=${isVisible}, hasContent=${!!value}, value="${value.substring(0,30)}"`);
        
        if (isVisible && value) {
            visibleWithContent.push({element: ta, value: value, rect: rect});
        }
    }
    
    console.log('Visible with content:', visibleWithContent.length);
    let targetTA = null;
    if (visibleWithContent.length > 0) {
        const middleIndex = Math.floor(visibleWithContent.length / 2);
        targetTA = visibleWithContent[middleIndex].element;
        console.log('Using middle textarea from visible:', middleIndex);
    } else if (textareas.length > 0) {
        targetTA = textareas[Math.floor(textareas.length / 2)];
        console.log('Using middle textarea from all');
    }
    
    if (!targetTA) {
        console.log('No textarea found!');
        return null;
    }
    
    // Return position to click
    const rect = targetTA.getBoundingClientRect();
    console.log('Textarea rect:', rect);
    return {
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
        currentValue: (targetTA.value || '').trim()
    };
}"""
            
            result = self.page.evaluate(js_find)
            print(f'_do_apply: JS result -> {result}')
            
            if not result:
                print('_do_apply: FAILED - No textarea found')
                return
            
            x = result['x']
            y = result['y']
            current = result['currentValue']
            
            print(f'_do_apply: Found textarea with value "{current}" at ({x}, {y})')
            
            # Click on the textarea to focus it
            print(f'_do_apply: Clicking at ({x}, {y})')
            self.page.mouse.click(x, y)
            self.page.wait_for_timeout(200)
            
            # Move to end of text
            print('_do_apply: Pressing End key')
            self.page.keyboard.press('End')
            self.page.wait_for_timeout(100)
            
            # Type 'X'
            print('_do_apply: Typing X')
            self.page.keyboard.type('X')
            self.page.wait_for_timeout(200)
            
            print(f'_do_apply: SUCCESS - appended X to "{current}"')
                
        except Exception as e:
            print(f'_do_apply: error -> {e}')
            import traceback
            traceback.print_exc()

    def _do_inspect(self):
        try:
            try:
                self.page.bring_to_front()
            except Exception:
                pass
            info = {}
            try:
                info['url'] = self.page.url
                try:
                    info['title'] = self.page.title()
                except Exception:
                    info['title'] = '<title-error>'
            except Exception:
                info['url'] = '<no-page>'

            # check next/prev selectors
            next_selectors = [
                "button[aria-label='Next']",
                "button[aria-label='Next photo']",
                "button[aria-label='Next item']",
                "div[aria-label='Next']",
                ".gallery-right-arrow",
            ]
            prev_selectors = [
                "button[aria-label='Previous']",
                "button[aria-label='Previous photo']",
                "button[aria-label='Previous item']",
                "div[aria-label='Previous']",
                ".gallery-left-arrow",
            ]
            info['next_found'] = []
            for sel in next_selectors:
                try:
                    el = self.page.query_selector(sel)
                    info['next_found'].append((sel, bool(el)))
                except Exception:
                    info['next_found'].append((sel, 'error'))

            info['prev_found'] = []
            for sel in prev_selectors:
                try:
                    el = self.page.query_selector(sel)
                    info['prev_found'].append((sel, bool(el)))
                except Exception:
                    info['prev_found'].append((sel, 'error'))

            # find first large image and print bbox
            imgs = self.page.query_selector_all('img')
            info['images'] = len(imgs)
            big_box = None
            for im in imgs:
                try:
                    b = im.bounding_box()
                    if b and b.get('width', 0) > 200 and b.get('height', 0) > 100:
                        big_box = b
                        break
                except Exception:
                    continue
            info['big_image_box'] = big_box

            # Try to detect description
            try:
                photo_src, desc = self._sample_description()
                info['description_present'] = bool(desc)
                if desc:
                    info['description_text'] = desc
                    info['photo_src'] = photo_src
            except Exception as e:
                info['description_error'] = str(e)

            print('\n--- Page Inspect ---')
            for k, v in info.items():
                print(f"{k}: {v}")
            print('--- End Inspect ---\n')
        except Exception as e:
            print('inspect error', e)

    def _do_sample(self):
        """Worker-side explicit sample command: try to read description now."""
        try:
            try:
                self.page.bring_to_front()
            except Exception:
                pass
            
            print(f"_do_sample: sampling description...")
            desc = None
            photo_src = None
            attempts = 6
            for i in range(attempts):
                photo_src, desc = self._sample_description()
                print(f"_do_sample: attempt {i+1}/{attempts} -> photo_src={repr(photo_src)[:200]} desc={repr(desc)[:300]}")
                if desc:
                    break
                try:
                    self.page.wait_for_timeout(250)
                except Exception:
                    time.sleep(0.25)
            
            with self._state_lock:
                self._last_description = desc
                if photo_src:
                    self._desc_sampled_for_photo = photo_src
                try:
                    current_url = self.page.url
                    if current_url:
                        self._desc_sampled_for_url = current_url
                except Exception:
                    pass
            
            print(f"_do_sample: final description -> {repr(desc)[:300]}")
        except Exception as e:
            print('_do_sample: error', e)

    def get_state(self):
        """Return last observed URL, image bbox, and description (thread-safe)."""
        with self._state_lock:
            return {
                'url': self._last_url,
                'image_box': self._last_image_box,
                'description': self._last_description
            }

    def _debug_dump_textareas(self):
        """Debug function to dump all textarea elements and their content."""
        try:
            print('\n========== TEXTAREA DEBUG DUMP ==========')
            js = """() => {
    const textareas = document.querySelectorAll('textarea');
    console.log(`Found ${textareas.length} textarea elements`);
    
    const results = [];
    for (let i = 0; i < textareas.length; i++) {
        const ta = textareas[i];
        results.push({
            index: i,
            outerHTML: ta.outerHTML,
            value: ta.value,
            textContent: ta.textContent,
            ariaLabel: ta.getAttribute('aria-label'),
            className: ta.className,
            jsname: ta.getAttribute('jsname'),
            initialData: ta.getAttribute('initial-data-value')
        });
    }
    return results;
}"""
            textareas = self.page.evaluate(js)
            
            for ta_info in textareas:
                print(f"\n--- Textarea {ta_info['index']} ---")
                print(f"aria-label: {ta_info['ariaLabel']}")
                print(f"jsname: {ta_info['jsname']}")
                print(f"className: {ta_info['className']}")
                print(f".value: {repr(ta_info['value'][:200] if ta_info['value'] else None)}")
                print(f".textContent: {repr(ta_info['textContent'][:200] if ta_info['textContent'] else None)}")
                print(f"initial-data-value: {repr(ta_info['initialData'][:200] if ta_info['initialData'] else None)}")
                print(f"outerHTML:\n{ta_info['outerHTML']}")
            
            print('\n========== END TEXTAREA DEBUG DUMP ==========\n')
        except Exception as e:
            print(f'_debug_dump_textareas error: {e}')
            import traceback
            traceback.print_exc()

    def _wait_for_textarea_update(self, timeout_ms=5000):
        """Wait for the description textarea to actually update its value.
        
        Polls the textarea.value repeatedly to detect when it changes from the previous photo.
        Returns the new value when detected, or None if timeout.
        """
        try:
            print('_wait_for_textarea_update: starting textarea monitor...')
            js_get_textarea = """() => {
    const ta = document.querySelector('textarea[aria-label="Description"]');
    if (ta) {
        return ta.value;
    }
    return null;
}"""
            
            initial_value = None
            start_time = time.time()
            poll_interval = 0.5  # 500ms - reduced from 200ms to avoid overwhelming Playwright
            
            while (time.time() - start_time) * 1000 < timeout_ms:
                try:
                    current_value = self.page.evaluate(js_get_textarea)
                    
                    if initial_value is None:
                        initial_value = current_value
                        print(f'_wait_for_textarea_update: initial textarea value = {repr(current_value)[:100]}')
                    else:
                        # Check if value changed
                        if current_value and current_value != initial_value:
                            print(f'_wait_for_textarea_update: textarea value changed! new = {repr(current_value)[:100]}')
                            return current_value
                    
                    time.sleep(poll_interval)
                except Exception as e:
                    print(f'_wait_for_textarea_update: poll error: {e}')
                    time.sleep(poll_interval)
                    break
            
            print(f'_wait_for_textarea_update: timeout after {timeout_ms}ms, returning last value = {repr(initial_value)[:100]}')
            return initial_value
        except Exception as e:
            print(f'_wait_for_textarea_update error: {e}')
            return None

    def _sample_description(self):
        """Evaluate the page and try to extract a clean description for the current photo.

        Returns (photo_src, description) tuple. Both may be None.
        """
        try:
            print('_sample_description: executing page.evaluate to extract description...')
            js = """() => {
    console.log('JS: Starting description extraction...');
    console.log('JS: Current URL:', window.location.href);
    
    function firstLargeImg() {
        const imgs = Array.from(document.querySelectorAll('img'));
        let best = null; let bestArea = 0;
        for (const im of imgs) {
            try { 
                const r = im.getBoundingClientRect(); 
                const area = (r.width||0)*(r.height||0); 
                if (area>bestArea && r.width>200 && r.height>100) { 
                    bestArea = area; 
                    best = {src: im.src||im.getAttribute('src')||'', bbox: r}; 
                } 
            } catch(e){}
        }
        console.log('JS: Best image:', best ? best.src.substring(0, 100) : 'none');
        return best;
    }
    const best = firstLargeImg();
    
    // Try to find the exact textarea with aria-label="Description"
    const descSelectors = [
        'textarea[aria-label="Description"]',
        "textarea[aria-label='Description']",
        "textarea[placeholder*='description' i]",
        "textarea[placeholder*='Description']",
        "div[contenteditable='true'][aria-label*='Description' i]"
    ];
    
    for (const s of descSelectors) {
        try {
            console.log('JS: Trying selector:', s);
            const elements = document.querySelectorAll(s);
            console.log('JS: Found elements:', elements.length);
            
            // Filter to only non-empty, visible textareas
            const visibleWithContent = [];
            for (const e of elements) {
                // Check if element is visible (not display:none, etc)
                const rect = e.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0;
                
                // Get the actual value
                const value = (e.value || '').trim();
                
                if (isVisible && value) {
                    visibleWithContent.push({element: e, value: value, rect: rect});
                    console.log(`JS: Found visible textarea with content: "${value.substring(0, 50)}"`);
                }
            }
            
            // If we found visible textareas with content, pick the middle one
            // (Google Photos shows prev/current/next in a carousel)
            if (visibleWithContent.length > 0) {
                let selectedTA = visibleWithContent[0].element;
                let selectedValue = visibleWithContent[0].value;
                
                // If there are multiple visible textareas, prefer the middle one (current photo)
                if (visibleWithContent.length > 1) {
                    const middleIndex = Math.floor(visibleWithContent.length / 2);
                    selectedTA = visibleWithContent[middleIndex].element;
                    selectedValue = visibleWithContent[middleIndex].value;
                    console.log(`JS: Multiple textareas found (${visibleWithContent.length}), picking middle one (index ${middleIndex})`);
                }
                
                console.log('JS: SUCCESS - Found visible textarea with content:', selectedValue);
                return {
                    photo_src: best ? best.src : null, 
                    selected: selectedValue,
                    selector: s,
                    method: 'value (visible textarea)',
                    page_url: window.location.href,
                    timestamp: Date.now(),
                    all_methods: {value: selectedValue}
                };
            }
        } catch(e){
            console.log('JS: Error with selector', s, ':', e.message);
        }
    }
    
    console.log('JS: No description found in form fields');
    return {
        photo_src: best ? best.src : null, 
        selected: null, 
        selector: null, 
        method: 'none',
        page_url: window.location.href,
        timestamp: Date.now()
    };
}"""
            res = self.page.evaluate(js)
            
            print(f"_sample_description: JS result -> {res}")
            
            if not res or not isinstance(res, dict):
                print('_sample_description: Invalid result from JS')
                return (None, None)
            
            photo_src = res.get('photo_src') or None
            selected = res.get('selected') or None
            selector = res.get('selector') or 'unknown'
            method = res.get('method') or 'unknown'
            page_url = res.get('page_url') or 'unknown'
            timestamp = res.get('timestamp') or 0
            all_methods = res.get('all_methods') or {}
            
            print(f"_sample_description: page_url={page_url}")
            print(f"_sample_description: timestamp={timestamp}")
            print(f"_sample_description: photo_src={repr(photo_src)[:100]}")
            print(f"_sample_description: selected={repr(selected)[:200]}")
            print(f"_sample_description: method_used={method}")
            print(f"_sample_description: all_methods={all_methods}")
            print(f"_sample_description: selector={selector}")
            
            if selected and isinstance(selected, str) and selected.strip():
                return (photo_src, selected.strip())
            
            print('_sample_description: No valid description found')
            return (photo_src, None)
        except Exception as e:
            print(f'_sample_description error: {e}')
            import traceback
            traceback.print_exc()
            return (None, None)

    def _os_focus_browser(self):
        """Try to bring a real browser app to front on macOS using AppleScript."""
        if sys.platform != 'darwin':
            return False
        apps = ['Google Chrome', 'Chromium', 'Microsoft Edge']
        for app in apps:
            try:
                subprocess.run(['osascript', '-e', f'tell application "{app}" to activate'], check=True)
                time.sleep(0.15)
                return True
            except Exception:
                pass
        return False


class AssistantUI:
    def __init__(self, root):
        print('AssistantUI: INITIALIZING...')
        self.root = root
        root.title('Google Photos Tagging Assistant - POC')
        self.names = load_names()

        self.browser = BrowserController()

        # Build UI
        top = ttk.Frame(root, padding=10)
        top.grid(row=0, column=0, sticky='nsew')
        
        print('AssistantUI: Building UI...')

        # Photo info label
        self.photo_label = ttk.Label(top, text='Photo: (open Google Photos in the browser)')
        self.photo_label.grid(row=0, column=0, columnspan=3, sticky='w')
        
        # Description label (shows current photo description if present)
        desc_frame = ttk.LabelFrame(top, text='Current Description')
        desc_frame.grid(row=1, column=0, columnspan=5, sticky='nsew', pady=(4,8))
        self.desc_label = ttk.Label(desc_frame, text='(no description)', wraplength=500, justify='left')
        self.desc_label.pack(padx=8, pady=8, anchor='w')

        # Names frame
        names_frame = ttk.LabelFrame(top, text='Names')
        names_frame.grid(row=2, column=0, columnspan=3, sticky='nsew', pady=8)
        self.names_container = ttk.Frame(names_frame)
        self.names_container.pack(fill='both', expand=True)

        # Input to add new name
        self.new_name_var = tk.StringVar()
        new_name_entry = ttk.Entry(top, textvariable=self.new_name_var)
        new_name_entry.grid(row=3, column=0, sticky='ew')
        add_btn = ttk.Button(top, text='Add', command=self.add_name)
        add_btn.grid(row=3, column=1, sticky='ew')

        # Control buttons
        launch_btn = ttk.Button(top, text='Launch Browser', command=self.launch_browser_thread)
        launch_btn.grid(row=4, column=0, sticky='ew', pady=(8,0))
        focus_btn = ttk.Button(top, text='Focus Browser', command=self.focus_browser)
        focus_btn.grid(row=4, column=1, sticky='ew', pady=(8,0))
        inspect_btn = ttk.Button(top, text='Inspect Page', command=self.inspect_page)
        inspect_btn.grid(row=3, column=2, sticky='ew')
        sample_btn = ttk.Button(top, text='Sample Description', command=self.sample_description)
        sample_btn.grid(row=3, column=3, sticky='ew')
        read_btn = ttk.Button(top, text='Read Current', command=self.read_current)
        read_btn.grid(row=3, column=4, sticky='ew')
        prev_btn = ttk.Button(top, text='Previous', command=self.prev_photo)
        prev_btn.grid(row=4, column=2, sticky='ew', pady=(8,0))
        next_btn = ttk.Button(top, text='Next', command=self.next_photo)
        next_btn.grid(row=4, column=3, sticky='ew', pady=(8,0))

        apply_btn = ttk.Button(top, text='ADD (append X)', command=self.apply_selected_names)
        apply_btn.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(8,0))

        # Layout expand
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # internal state: which names selected
        self.name_vars = []
        self.refresh_names_ui()
        # Start polling browser state to reflect current photo
        self.root.after(500, self.poll_browser_state)

    def poll_browser_state(self):
        try:
            state = self.browser.get_state()
            url = state.get('url') if state else None
            if url:
                # show short form
                short = url.split('/')[-1]
                self.photo_label.config(text=f'Photo: {short}')
                desc = state.get('description')
                if desc:
                    # show a preview of the description
                    preview = desc if len(desc) < 300 else (desc[:297] + '...')
                    self.desc_label.config(text=preview)
                else:
                    self.desc_label.config(text='(no description)')
            else:
                self.photo_label.config(text='Photo: (not connected)')
                self.desc_label.config(text='(no description)')
        except Exception as e:
            print(f'poll_browser_state error: {e}')
        try:
            self.root.after(500, self.poll_browser_state)
        except Exception:
            pass

    def refresh_names_ui(self):
        # Clear
        for widget in self.names_container.winfo_children():
            widget.destroy()
        self.name_vars = []
        for n in self.names:
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(self.names_container, text=n, variable=var)
            cb.pack(anchor='w', padx=6, pady=2)
            self.name_vars.append((var, n))

    def add_name(self):
        name = self.new_name_var.get().strip()
        if not name:
            return
        if name not in self.names:
            self.names.append(name)
            save_names(self.names)
            self.new_name_var.set('')
            self.refresh_names_ui()

    def launch_browser_thread(self):
        t = threading.Thread(target=self.launch_browser, daemon=True)
        t.start()

    def launch_browser(self):
        try:
            # start the browser worker which will launch a persistent browser context
            self.browser.start(headful=True)
            messagebox.showinfo('Browser Launched', 'Chromium launched. Please log into Google Photos in the opened browser window.')
        except Exception as e:
            messagebox.showerror('Error launching browser', str(e))

    def selected_names_text(self):
        chosen = [n for var, n in self.name_vars if var.get()]
        return ', '.join(chosen)

    def apply_selected_names(self):
        print('apply_selected_names: CLICKED!')
        # Simply send apply command - don't use selected names anymore
        # The apply action just appends 'X' to the current description
        try:
            self.browser.apply_description('')
            print('apply_selected_names: sent to browser')
        except Exception as e:
            print(f'apply_selected_names: error -> {e}')
            messagebox.showerror('Apply Error', str(e))

    def focus_browser(self):
        try:
            ok = self.browser._os_focus_browser()
            if ok:
                messagebox.showinfo('Focus Browser', 'Tried to focus the browser window (macOS AppleScript).')
            else:
                messagebox.showwarning('Focus Browser', 'Could not focus browser (not macOS or no supported browser found).')
        except Exception as e:
            messagebox.showerror('Focus Browser Error', str(e))

    def inspect_page(self):
        try:
            self.browser._cmd_queue.put(('inspect', None))
            messagebox.showinfo('Inspect enqueued', 'Page inspect command sent. Check the terminal for output.')
        except Exception as e:
            messagebox.showerror('Inspect error', str(e))

    def sample_description(self):
        try:
            self.browser._cmd_queue.put(('sample', None))
            messagebox.showinfo('Sample enqueued', 'Description sample requested. Check the terminal for sampling logs.')
            # schedule a quick UI refresh shortly so the polled state may reflect the new sample
            try:
                self.root.after(300, self.poll_browser_state)
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror('Sample error', str(e))

    def read_current(self):
        """Read the current page description synchronously and update UI immediately."""
        def _worker():
            try:
                desc = None
                try:
                    # Force a completely fresh sample right now
                    print('read_current: requesting force_fresh_sample...')
                    desc = self.browser.force_fresh_sample(timeout=8.0)
                    print(f'read_current: got result -> {repr(desc)[:300]}')
                except Exception as e:
                    err = str(e)
                    print(f'read_current: error -> {err}')
                    self.root.after(0, lambda: messagebox.showerror('Sample error', err))
                    return
                
                # Update UI on main thread
                def _update_ui():
                    try:
                        if desc:
                            # Update the description label immediately
                            preview = desc if len(desc) < 300 else (desc[:297] + '...')
                            self.desc_label.config(text=preview)
                            
                            # Also show in a dialog
                            full_preview = desc if len(desc) < 400 else (desc[:397] + '...')
                            messagebox.showinfo('Current Description', full_preview)
                        else:
                            self.desc_label.config(text='(no description found)')
                            messagebox.showinfo('Current Description', '(no description found)')
                    except Exception as e:
                        print(f'read_current: UI update error: {e}')
                
                self.root.after(0, _update_ui)
            except Exception as e:
                err_msg = str(e)
                print(f'read_current: exception -> {err_msg}')
                try:
                    self.root.after(0, lambda: messagebox.showerror('Sample error', err_msg))
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def next_photo(self):
        self.browser.goto_next_photo()

    def prev_photo(self):
        self.browser.goto_prev_photo()

    def shutdown(self):
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
