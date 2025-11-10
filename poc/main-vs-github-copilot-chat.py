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
        # timestamp (seconds) when _last_description was updated
        self._last_description_ts = 0.0
        # track which URL we last sampled a description for so we don't sample too early
        self._desc_sampled_for_url = None
        # track which photo src we last sampled for (preferred over url)
        self._desc_sampled_for_photo = None

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
                    cmd, arg = self._cmd_queue.get(timeout=0.2)
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
                elif cmd == 'sample':
                    self._do_sample()
                elif cmd == 'apply':
                    self._do_apply(arg)
                elif cmd == 'inspect':
                    self._do_inspect()
                # else: ignore unknown
                # update last seen state for UI polling
                try:
                    self._last_url = self.page.url
                except Exception:
                    pass
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
                    self._last_image_box = big_box
                except Exception:
                    pass
                # lightweight description sampler: only sample when the URL changed since
                # the last description sample to avoid taking the previous-photo text.
                try:
                    # Determine a more stable photo identifier (large image src) because
                    # Google Photos sometimes updates the viewer image before the URL
                    # or vice-versa. We'll prefer a photo_src when available.
                    current_url = None
                    try:
                        current_url = self.page.url
                    except Exception:
                        current_url = None
                    # get current large-image src via page.evaluate to avoid racing on url
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

                    # choose identifier: prefer photo_src, fall back to url
                    identifier = photo_src or current_url
                    already_sampled = (identifier and identifier == self._desc_sampled_for_photo) or (current_url and current_url == self._desc_sampled_for_url)
                    if identifier and not already_sampled:
                        try:
                            print(f"_sampler: attempting description sample for id={identifier[:200]}")
                            desc = None
                            # Try a few times with short delays because the info panel may take a moment to render
                            attempts = 5
                            for i in range(attempts):
                                photo_src, desc = self._sample_description()
                                print(f"_sampler: attempt {i+1}/{attempts} -> photo_src={repr(photo_src)[:160]} desc={repr(desc)[:240]}")
                                if desc:
                                    try:
                                        self._last_description_ts = time.time()
                                    except Exception:
                                        pass
                                    break
                                try:
                                    self.page.wait_for_timeout(200)
                                except Exception:
                                    time.sleep(0.2)
                            self._last_description = desc
                            try:
                                if desc:
                                    self._last_description_ts = time.time()
                            except Exception:
                                pass
                            # Mark that we sampled for this photo (and url as a fallback)
                            try:
                                if photo_src:
                                    self._desc_sampled_for_photo = photo_src
                                if current_url:
                                    self._desc_sampled_for_url = current_url
                            except Exception:
                                pass
                        except Exception as e:
                            print(f'_sampler: error while sampling description: {e}')
                            self._last_description = None
                    # if urls match, keep previous description (no-op)
                except Exception:
                    pass
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

    # Worker-side helpers (executed inside _worker_main thread)
    def _do_next(self):
        """Robust navigate to next photo.

        Approach:
        - Record before state (url and large-image bbox).
        - Perform a single action (click center, click right edge, or click visible Next button) in order.
        - Wait briefly for the page to change (url or image bbox).
        - If the page changes but then immediately reverts to the before-state, retry once.
        - Log helpful debug info for diagnosis.
        """
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

            # If not acted, try clicking right edge
            if not acted:
                try:
                    imgs = self.page.query_selector_all('img')
                    for img in imgs:
                        try:
                            box = img.bounding_box()
                            if box and box.get('width', 0) > 200 and box.get('height', 0) > 100:
                                rx = box['x'] + box['width'] * 0.85
                                ry = box['y'] + box['height'] / 2
                                self.page.mouse.click(rx, ry)
                                print(f'_do_next: clicked right edge at ({int(rx)},{int(ry)})')
                                self.page.wait_for_timeout(150)
                                acted = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            # If still not acted, look for visible next button
            if not acted:
                try:
                    next_selectors = [
                        "button[aria-label='Next']",
                        "button[aria-label='Next photo']",
                        "button[aria-label='Next item']",
                        "[aria-label='Next']",
                        "[aria-label='Next photo']",
                    ]
                    for selector in next_selectors:
                        try:
                            btn = self.page.query_selector(selector)
                            if btn and btn.is_visible():
                                btn.click()
                                print(f'_do_next: clicked next button {selector}')
                                self.page.wait_for_timeout(150)
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

            # If changed, wait a short moment to detect immediate revert
            if _changed(before, after):
                self.page.wait_for_timeout(300)
                final = _get_snapshot()
                if not _changed(before, final):
                    # It reverted — retry once
                    print('_do_next: detected immediate revert, retrying once')
                    try:
                        self.page.keyboard.press('ArrowRight')
                    except Exception:
                        pass
                    # wait again for change
                    self.page.wait_for_timeout(400)
                    final2 = _get_snapshot()
                    print(f'_do_next: final2 snapshot url={final2[0]} box={final2[1]}')
                    # sample description for the new current photo
                    try:
                        photo_src, desc = self._sample_description()
                        self._last_description = desc
                        try:
                            if desc:
                                self._last_description_ts = time.time()
                        except Exception:
                            pass
                        print(f"_do_next: sampled description -> photo_src={repr(photo_src)[:160]} desc={repr(desc)[:200]}")
                    except Exception:
                        pass
                else:
                    print('_do_next: navigation stable')
                # if navigation was detected and stable, also sample description
                try:
                    if _changed(before, after):
                        photo_src, desc = self._sample_description()
                        self._last_description = desc
                        try:
                            if desc:
                                self._last_description_ts = time.time()
                        except Exception:
                            pass
                        print(f"_do_next: sampled description (stable) -> photo_src={repr(photo_src)[:160]} desc={repr(desc)[:200]}")
                except Exception:
                    pass
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

        # Strategy 1: Find and click the large image to focus, then use arrow key
        try:
            imgs = self.page.query_selector_all('img')
            big_img = None
            big_box = None
            for img in imgs:
                try:
                    box = img.bounding_box()
                    if box and box.get('width', 0) > 200 and box.get('height', 0) > 100:
                        big_img = img
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
                    print(f'Clicked center of image at ({int(cx)}, {int(cy)})')
                except Exception as e:
                    print(f'Failed to click image center: {e}')
                
                # Try arrow key with multiple methods
                try:
                    # Method 1: Direct keyboard press
                    self.page.keyboard.press('ArrowLeft')
                    print('Pressed ArrowLeft key (direct)')
                    self.page.wait_for_timeout(500)
                    return
                except Exception as e:
                    print(f'Direct ArrowLeft failed: {e}')
                
                try:
                    # Method 2: Dispatch keyboard event via JavaScript
                    self.page.evaluate("""() => {
                        const event = new KeyboardEvent('keydown', {
                            key: 'ArrowLeft',
                            code: 'ArrowLeft',
                            keyCode: 37,
                            which: 37,
                            bubbles: true,
                            cancelable: true
                        });
                        document.body.dispatchEvent(event);
                        document.activeElement.dispatchEvent(event);
                    }""")
                    print('Dispatched ArrowLeft via JavaScript')
                    self.page.wait_for_timeout(500)
                    return
                except Exception as e:
                    print(f'JS dispatch ArrowLeft failed: {e}')
        except Exception as e:
            print(f'Strategy 1 failed: {e}')

        # Strategy 2: Click left edge of photo (like manual click)
        try:
            imgs = self.page.query_selector_all('img')
            for img in imgs:
                try:
                    box = img.bounding_box()
                    if box and box.get('width', 0) > 200 and box.get('height', 0) > 100:
                        # Click 10% across the width (left side)
                        lx = box['x'] + box['width'] * 0.15
                        ly = box['y'] + box['height'] / 2
                        self.page.mouse.click(lx, ly)
                        print(f'Clicked left edge at ({int(lx)}, {int(ly)})')
                        self.page.wait_for_timeout(500)
                        return
                except Exception:
                    continue
        except Exception as e:
            print(f'Strategy 2 failed: {e}')

        # Strategy 3: Look for visible previous button and click it
        try:
            prev_selectors = [
                "button[aria-label='Previous']",
                "button[aria-label='Previous photo']",
                "button[aria-label='Previous item']",
                "[aria-label='Previous']",
                "[aria-label='Previous photo']",
            ]
            for selector in prev_selectors:
                try:
                    btn = self.page.query_selector(selector)
                    if btn and btn.is_visible():
                        btn.click()
                        print(f'Clicked button: {selector}')
                        self.page.wait_for_timeout(500)
                        return
                except Exception:
                    continue
        except Exception as e:
            print(f'Strategy 3 failed: {e}')

    def _do_apply(self, text):
        try:
            try:
                self.page.bring_to_front()
            except Exception:
                pass
            # Example pseudocode; replace selector with the real one after inspection
            # self.page.click('button[aria-label="Info"]')
            # self.page.fill('textarea.description-selector', text)
            # self.page.keyboard.press('Enter')
            print('apply_description (worker) ->', text)
        except Exception as e:
            print('apply_description error', e)

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

            # Try to detect a right-hand info/details panel and any description field
            try:
                js_check = (
                    "() => {\n"
                    "  const vp = {w: window.innerWidth, h: window.innerHeight};\n"
                    "  const panelSelectors = [\"[role='complementary']\", \"[aria-label*='Info']\", \"[aria-label*='Details']\", \".uQ4NLd\", \".photo-info\", \".details\", \"[data-pane=\\'info\\']\", \"[data-testid=\\'info-panel\\']\"];\n"
                    "  const panels = [];\n"
                    "  for (const sel of panelSelectors) {\n"
                    "    try { const e = document.querySelector(sel); if (e) { const r = e.getBoundingClientRect(); panels.push({selector: sel, bbox: {x: r.x, y: r.y, width: r.width, height: r.height}, text: (e.innerText||'').slice(0,200)}); } } catch(e){}\n"
                    "  }\n"
                    "  // fallback: find prominent elements on the right side of the viewport\n"
                    "  const rightEls = [];\n"
                    "  try { const all = document.querySelectorAll('div,section,aside'); for (const el of all) { try { const r = el.getBoundingClientRect(); if (r.width && r.x > vp.w*0.6 && r.height>20) { rightEls.push({tag: el.tagName, bbox:{x:r.x,y:r.y,width:r.width,height:r.height}, text:(el.innerText||'').slice(0,200)}); } } catch(e){} } } catch(e){}\n"
                    "  // look for description-like fields\n"
                    "  const descSelectors = [\"textarea[aria-label*='Description']\", \"textarea\", \"div[contenteditable='true']\", \"[data-testid='description']\", \"[aria-label*='Caption']\"];\n"
                    "  let desc = null;\n"
                    "  for (const s of descSelectors) { try { const e = document.querySelector(s); if (e) { desc = {selector: s, text: (e.innerText||e.value||'').slice(0,100), placeholder: e.placeholder||null}; break; } } catch(e){} }\n"
                    "  return {vp, panels, rightEls, desc};\n"
                    "}"
                )
                res = self.page.evaluate(js_check)
                info['inspect_details'] = res
                # Interpret description presence with improved heuristics to avoid
                # picking up short action labels like 'Favorite' as the description.
                desc = res.get('desc') if isinstance(res, dict) else None
                found = False
                desc_text = None
                vp = res.get('vp') or {}

                # 1) Prefer an explicit description field if present and non-empty
                if desc and desc.get('text') and desc.get('text').strip():
                    found = True
                    desc_text = desc.get('text').strip()
                else:
                    # 2) Prefer large panels on the right side with substantive text
                    panels = res.get('panels') or []
                    rightEls = res.get('rightEls') or []
                    candidates = []
                    try:
                        vpw = float(vp.get('w', 0))
                    except Exception:
                        vpw = 0

                    for p in panels:
                        text = (p.get('text') or '').strip()
                        bbox = p.get('bbox') or {}
                        width = bbox.get('width', 0)
                        height = bbox.get('height', 0)
                        if not text or 'Add a description' in text:
                            continue
                        # require panels to be reasonably wide and have some length
                        if width >= max(200, vpw * 0.2) and len(text) > 12:
                            candidates.append((width * height, text))

                    for p in rightEls:
                        text = (p.get('text') or '').strip()
                        bbox = p.get('bbox') or {}
                        width = bbox.get('width', 0)
                        height = bbox.get('height', 0)
                        if not text or 'Add a description' in text:
                            continue
                        if width >= max(200, vpw * 0.2) and len(text) > 12:
                            candidates.append((width * height, text))

                    if candidates:
                        # choose largest candidate by area
                        candidates.sort(reverse=True, key=lambda x: x[0])
                        # candidates may contain full panel text; try to extract a clean description
                        def _extract_from_panel(t):
                            if not t:
                                return None
                            lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
                            if not lines:
                                return None
                            # look for 'Info' header then a following descriptive line
                            for i,ln in enumerate(lines):
                                if ln.lower().startswith('info'):
                                    for j in range(i+1, len(lines)):
                                        cand = lines[j]
                                        low = cand.lower()
                                        if low.startswith(('details','people','albums','add a description','add a location')):
                                            continue
                                        if len(cand) >= 3:
                                            return cand
                            # fallback: pick first reasonably long non-header line
                            blacklist_prefixes = ('favorite','move to trash','more options','info','details','add a location','people')
                            for ln in lines:
                                if len(ln) > 12 and not any(ln.lower().startswith(bp) for bp in blacklist_prefixes):
                                    return ln
                            return None

                        area, text_candidate = candidates[0]
                        extracted = _extract_from_panel(text_candidate)
                        desc_text = extracted or text_candidate
                        found = True
                    else:
                        # 3) Fallback: find any reasonably long text that doesn't look like a small action label
                        blacklist_prefixes = ('Favorite', 'Move to trash', 'More options', 'Info', 'Details', 'Add a location', 'People')
                        for p in (panels + rightEls):
                            text = (p.get('text') or '').strip()
                            if not text:
                                continue
                            if 'Add a description' in text:
                                continue
                            # also try to extract if this is an Info/Details block
                            extracted = None
                            try:
                                extracted = _extract_from_panel(text)
                            except Exception:
                                extracted = None
                            if extracted:
                                desc_text = extracted
                                found = True
                                break
                            if len(text) > 20 and not any(text.startswith(bp) for bp in blacklist_prefixes):
                                desc_text = text
                                found = True
                                break

                info['description_present'] = bool(found)
                if found:
                    info['description_text'] = desc_text
            except Exception as e:
                info['inspect_details_error'] = str(e)

            print('\n--- Page Inspect ---')
            for k, v in info.items():
                print(f"{k}: {v}")
            print('--- End Inspect ---\n')
        except Exception as e:
            print('inspect error', e)

    def _do_sample(self):
        """Worker-side explicit sample command: try to read description now and
        update the last-sampled description for the current URL.
        """
        try:
            try:
                self.page.bring_to_front()
            except Exception:
                pass
            try:
                # read both url and an identifier based on the large image src
                current_url = None
                try:
                    current_url = self.page.url
                except Exception:
                    current_url = None
                photo_src = ''
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
                id_display = photo_src or current_url
                print(f"_do_sample: sampling description for id={(id_display or '')[:200]}")
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
                self._last_description = desc
                # mark sampled for both photo_src and url if available
                try:
                    if photo_src:
                        self._desc_sampled_for_photo = photo_src
                    if current_url:
                        self._desc_sampled_for_url = current_url
                except Exception:
                    pass
                print(f"_do_sample: final description -> {repr(desc)[:300]}")
            except Exception as e:
                print('_do_sample: inner error', e)
        except Exception as e:
            print('_do_sample: error', e)

    def get_state(self):
        """Return last observed URL and image bbox (may be slightly stale)."""
        return {
            'url': self._last_url,
            'image_box': self._last_image_box,
            'description': self._last_description,
            'photo_src': self._last_photo_src,
            'desc_ts': getattr(self, '_last_description_ts', 0.0),
        }

    def _sample_description(self):
        """Evaluate the page and try to extract a clean description for the current photo.

        Returns a string or None. This should be called from the browser worker thread.
        """
        try:
            print('_sample_description: executing richer page.evaluate to extract photo_src and candidate texts...')
            js = """() => {
    function firstLargeImg() {
        const imgs = Array.from(document.querySelectorAll('img'));
        let best = null; let bestArea = 0;
        for (const im of imgs) {
            try { const r = im.getBoundingClientRect(); const area = (r.width||0)*(r.height||0); if (area>bestArea && r.width>200 && r.height>100) { bestArea = area; best = {src: im.src||im.getAttribute('src')||'', bbox: r}; } } catch(e){}
        }
        return best;
    }
    const best = firstLargeImg();
    const vpw = window.innerWidth||0;
    const candidates = [];
    if (best) {
        try { const all = Array.from(document.querySelectorAll('div,section,aside')); for (const el of all) { try { const r = el.getBoundingClientRect(); if (r.width>80 && r.height>20 && (r.x > (best.bbox.x + best.bbox.width*0.45) || (best.bbox.x<vpw*0.5 && r.x>vpw*0.55))) { const t = (el.innerText||'').trim(); if (t) candidates.push({bbox:r, text: t, tag: el.tagName}); } } catch(e){} } } catch(e){}
    } else {
        try { const all = Array.from(document.querySelectorAll('div,section,aside')); for (const el of all) { try { const r = el.getBoundingClientRect(); if (r.width>200 && r.x>vpw*0.6 && r.height>20) { const t = (el.innerText||'').trim(); if (t) candidates.push({bbox:r, text:t, tag: el.tagName}); } } catch(e){} } } catch(e){}
    }
    const explicit = [];
    try { const sels = ["textarea[aria-label*='Description']","textarea","div[contenteditable='true']","[data-testid='description']","[aria-label*='Caption']"]; for (const s of sels) { try { const e = document.querySelector(s); if (e) { explicit.push({sel: s, text: (e.value||e.innerText||'').trim()}); } } catch(e){} } } catch(e){}
    function extractFromText(t) { if (!t) return null; const lines = t.split(/\n+/).map(x=>x.trim()).filter(Boolean); for (let i=0;i<lines.length;i++) { if (/^info$/i.test(lines[i])) { for (let j=i+1;j<lines.length;j++) { const cand = lines[j]; if (/^details$/i.test(cand) || /^people$/i.test(cand) || /^albums$/i.test(cand) || /add a description/i.test(cand)) continue; if (cand.length>=3) return cand; } } } for (const ln of lines) { if (ln.length>12 && !/^(favorite|move to trash|more options|info|details|add a location|people)$/i.test(ln)) return ln; } return null; }
    for (const e of explicit) { if (e.text && e.text.length>0) { return {photo_src: best?best.src:null, selected: e.text, candidates: [{type:'explicit', sel: e.sel, text: e.text}]}; } }
    if (candidates.length>0) { candidates.sort((a,b)=> (b.bbox.width*b.bbox.height)-(a.bbox.width*a.bbox.height)); const texts = candidates.map(c=>c.text); let extracted = extractFromText(texts[0]); if (!extracted) extracted = texts[0]; return {photo_src: best?best.src:null, selected: extracted, candidates: candidates.map(c=>({text:c.text, bbox:c.bbox, tag:c.tag}))}; }
    return {photo_src: best?best.src:null, selected: null, candidates: []};
}"""
            res = self.page.evaluate(js)
            try:
                print(f"_sample_description: raw eval -> photo_src={repr(res.get('photo_src'))[:300]} selected={repr(res.get('selected'))[:300]} candidates={len(res.get('candidates') or [])}")
            except Exception:
                pass

            if not res or not isinstance(res, dict):
                # fallback: try simpler extractor
                try:
                    js_fb = (
                        "() => {"
                        "  const sel = document.querySelector(\"textarea[aria-label*='Description'], div[contenteditable='true']\");"
                        "  if (sel) return (sel.value||sel.innerText||'').slice(0,2000);"
                        "  const vpw = window.innerWidth || 0;"
                        "  const nodes = document.querySelectorAll('div,section,aside');"
                        "  for (const n of nodes) { try { const r = n.getBoundingClientRect(); if (r.width>200 && r.x>vpw*0.6) { const t=(n.innerText||'').trim(); if (t && !t.includes('Add a description')) return t; } } catch(e){} }"
                        "  return '';"
                        "}"
                    )
                    fb = self.page.evaluate(js_fb)
                    if fb and isinstance(fb, str) and fb.strip():
                        return (res.get('photo_src') or None, fb.strip())
                except Exception:
                    pass
                return (None, None)
            photo_src = res.get('photo_src') or None
            selected = res.get('selected') or None
            if selected and isinstance(selected, str) and selected.strip():
                return (photo_src, selected.strip())

            # fallback: if rich extractor didn't produce a 'selected' string, try a simpler extractor
            try:
                js_fb2 = (
                    "() => {"
                    "  const sel = document.querySelector(\"textarea[aria-label*='Description'], div[contenteditable='true']\");"
                    "  if (sel) return (sel.value||sel.innerText||'').slice(0,2000);"
                    "  const vpw = window.innerWidth || 0;"
                    "  const nodes = document.querySelectorAll('div,section,aside');"
                    "  for (const n of nodes) { try { const r = n.getBoundingClientRect(); if (r.width>200 && r.x>vpw*0.6) { const t=(n.innerText||'').trim(); if (t && !t.includes('Add a description')) return t; } } catch(e){} }"
                    "  return '';"
                    "}"
                )
                fb2 = self.page.evaluate(js_fb2)
                if fb2 and isinstance(fb2, str) and fb2.strip():
                    return (photo_src, fb2.strip())
            except Exception:
                pass

            # nothing useful found
            return (photo_src, None)
        except Exception as e:
            print('_sample_description error', e)
            return (None, None)

    def _os_focus_browser(self):
        """Try to bring a real browser app to front on macOS using AppleScript.

        Returns True if it attempted activation (or platform not macOS), False if failed.
        """
        if sys.platform != 'darwin':
            return False
        # Try several AppleScript approaches because different macOS/Chrome states
        # may require slightly different activation commands.
        apps = ['Google Chrome', 'Chromium', 'Microsoft Edge']
        for app in apps:
            # 1) Simple activate
            try:
                subprocess.run(['osascript', '-e', f'tell application "{app}" to activate'], check=True)
                time.sleep(0.15)
            except Exception:
                pass

            # 2) Try via System Events to set process frontmost
            try:
                cmd = f'tell application "System Events" to set frontmost of process "{app}" to true'
                subprocess.run(['osascript', '-e', cmd], check=True)
                time.sleep(0.08)
                print(f'_os_focus_browser: set frontmost for {app}')
                return True
            except Exception:
                pass

            # 3) Try to bring a window whose title contains 'Photos' or 'Google Photos' to front
            try:
                script = (
                    'tell application "System Events"\n'
                    f'\ttell process "{app}"\n'
                    '\t\trepeat with w in windows\n'
                    '\t\t\tif name of w contains "Photos" or name of w contains "Google" then\n'
                    '\t\t\t\tset frontmost to true\n'
                    '\t\t\t\texit repeat\n'
                    '\t\t\tend if\n'
                    '\t\tend repeat\n'
                    '\tend tell\n'
                    'end tell'
                )
                subprocess.run(['osascript', '-e', script], check=True)
                time.sleep(0.08)
                print(f'_os_focus_browser: attempted window-focus for {app}')
                return True
            except Exception:
                pass

        # If none of the attempts worked, return False
        print('_os_focus_browser: could not focus any known browser process')
        return False


class AssistantUI:
    def __init__(self, root):
        self.root = root
        root.title('Google Photos Tagging Assistant - POC')
        self.names = load_names()

        self.browser = BrowserController()

        # Build UI
        top = ttk.Frame(root, padding=10)
        top.grid(row=0, column=0, sticky='nsew')

        # Photo info label
        self.photo_label = ttk.Label(top, text='Photo: (open Google Photos in the browser)')
        self.photo_label.grid(row=0, column=0, columnspan=3, sticky='w')
        # Description label (shows current photo description if present)
        self.desc_label = ttk.Label(top, text='', wraplength=420)
        self.desc_label.grid(row=1, column=0, columnspan=3, sticky='w', pady=(4,8))

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

        apply_btn = ttk.Button(top, text='Apply Selected Name(s)', command=self.apply_selected_names)
        apply_btn.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(8,0))

        # Layout expand
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # internal state: which names selected
        self.name_vars = []
        self.refresh_names_ui()
        # Start polling browser state to reflect current photo
        self._last_seen_desc_ts = 0.0
        self.root.after(1000, self.poll_browser_state)

    def poll_browser_state(self):
        try:
            state = self.browser.get_state()
            url = state.get('url') if state else None
            if url:
                # show short form
                short = url.split('/')[-1]
                self.photo_label.config(text=f'Photo: {short}')
                desc = state.get('description')
                desc_ts = state.get('desc_ts') or 0.0
                # Update description label if we have a new description or a newer timestamp
                if desc and desc.strip():
                    preview = desc if len(desc) < 200 else (desc[:197] + '...')
                    self.desc_label.config(text=f'Description: {preview}')
                    try:
                        self._last_seen_desc_ts = float(desc_ts) or time.time()
                    except Exception:
                        self._last_seen_desc_ts = time.time()
                else:
                    # don't clear the description immediately; keep previous until a new sample appears
                    pass
            else:
                self.photo_label.config(text='Photo: (not connected)')
        except Exception:
            pass
        try:
            self.root.after(1000, self.poll_browser_state)
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
        text = self.selected_names_text()
        if not text:
            messagebox.showwarning('No names selected', 'Choose one or more names to apply.')
            return
        # Send to browser controller
        self.browser.apply_description(text)

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
        """Read the current page description synchronously (runs worker sampling and
        shows the result). Runs the worker call in a background thread to avoid
        freezing the UI, then shows a dialog with the sampled description.
        """
        def _worker():
            try:
                desc = None
                try:
                    desc = self.browser.sample_now(timeout=6.0)
                except Exception as e:
                    err = str(e)
                    self.root.after(0, lambda: messagebox.showerror('Sample error', err))
                    return
                # show result on main thread
                def _show():
                    if desc:
                        preview = desc if len(desc) < 400 else (desc[:397] + '...')
                        messagebox.showinfo('Current Description', preview)
                    else:
                        messagebox.showinfo('Current Description', '(no description found)')
                    # also trigger a UI poll to refresh the small preview label
                    try:
                        self.poll_browser_state()
                    except Exception:
                        pass
                self.root.after(0, _show)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror('Sample error', str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def next_photo(self):
        # Navigate then immediately request sampling in a background thread so
        # the UI is updated as soon as possible without freezing.
        def _worker():
            try:
                self.browser.goto_next_photo()
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror('Navigation error', str(e)))
                return

            # try sampling several times with short delays until we get a description
            desc = None
            attempts = 8
            for i in range(attempts):
                try:
                    # small pause to let the navigation start
                    time.sleep(0.18)
                    desc = self.browser.sample_now(timeout=2.0)
                except Exception:
                    desc = None
                if desc:
                    # update UI immediately with the sampled description
                    self.root.after(0, lambda d=desc: self._apply_description_to_ui(d))
                    break

            # always perform a poll to refresh other UI bits (url, photo id)
            try:
                self.root.after(0, self.poll_browser_state)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def prev_photo(self):
        def _worker():
            try:
                self.browser.goto_prev_photo()
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror('Navigation error', str(e)))
                return

            desc = None
            attempts = 8
            for i in range(attempts):
                try:
                    time.sleep(0.18)
                    desc = self.browser.sample_now(timeout=2.0)
                except Exception:
                    desc = None
                if desc:
                    self.root.after(0, lambda d=desc: self._apply_description_to_ui(d))
                    break

            try:
                self.root.after(0, self.poll_browser_state)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_description_to_ui(self, desc):
        try:
            if desc:
                preview = desc if len(desc) < 200 else (desc[:197] + '...')
                self.desc_label.config(text=f'Description: {preview}')
                try:
                    self._last_seen_desc_ts = time.time()
                except Exception:
                    pass
            else:
                # if no description found, leave current UI unchanged
                pass
        except Exception:
            pass

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
