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

    # Worker-side helpers (executed inside _worker_main thread)
    def _do_next(self):
        """Navigate to next photo by clicking right edge or using keyboard."""
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
                    self.page.keyboard.press('ArrowRight')
                    print('Pressed ArrowRight key (direct)')
                    self.page.wait_for_timeout(500)
                    return
                except Exception as e:
                    print(f'Direct ArrowRight failed: {e}')
                
                try:
                    # Method 2: Dispatch keyboard event via JavaScript
                    self.page.evaluate("""() => {
                        const event = new KeyboardEvent('keydown', {
                            key: 'ArrowRight',
                            code: 'ArrowRight',
                            keyCode: 39,
                            which: 39,
                            bubbles: true,
                            cancelable: true
                        });
                        document.body.dispatchEvent(event);
                        document.activeElement.dispatchEvent(event);
                    }""")
                    print('Dispatched ArrowRight via JavaScript')
                    self.page.wait_for_timeout(500)
                    return
                except Exception as e:
                    print(f'JS dispatch ArrowRight failed: {e}')
        except Exception as e:
            print(f'Strategy 1 failed: {e}')

        # Strategy 2: Click right edge of photo (like manual click)
        try:
            imgs = self.page.query_selector_all('img')
            for img in imgs:
                try:
                    box = img.bounding_box()
                    if box and box.get('width', 0) > 200 and box.get('height', 0) > 100:
                        # Click 90% across the width (right side)
                        rx = box['x'] + box['width'] * 0.85
                        ry = box['y'] + box['height'] / 2
                        self.page.mouse.click(rx, ry)
                        print(f'Clicked right edge at ({int(rx)}, {int(ry)})')
                        self.page.wait_for_timeout(500)
                        return
                except Exception:
                    continue
        except Exception as e:
            print(f'Strategy 2 failed: {e}')

        # Strategy 3: Look for visible next button and click it
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
                        print(f'Clicked button: {selector}')
                        self.page.wait_for_timeout(500)
                        return
                except Exception:
                    continue
        except Exception as e:
            print(f'Strategy 3 failed: {e}')

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

            print('\n--- Page Inspect ---')
            for k, v in info.items():
                print(f"{k}: {v}")
            print('--- End Inspect ---\n')
        except Exception as e:
            print('inspect error', e)

    def get_state(self):
        """Return last observed URL and image bbox (may be slightly stale)."""
        return {'url': self._last_url, 'image_box': self._last_image_box}

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

        # Names frame
        names_frame = ttk.LabelFrame(top, text='Names')
        names_frame.grid(row=1, column=0, columnspan=3, sticky='nsew', pady=8)
        self.names_container = ttk.Frame(names_frame)
        self.names_container.pack(fill='both', expand=True)

        # Input to add new name
        self.new_name_var = tk.StringVar()
        new_name_entry = ttk.Entry(top, textvariable=self.new_name_var)
        new_name_entry.grid(row=2, column=0, sticky='ew')
        add_btn = ttk.Button(top, text='Add', command=self.add_name)
        add_btn.grid(row=2, column=1, sticky='ew')

        # Control buttons
        launch_btn = ttk.Button(top, text='Launch Browser', command=self.launch_browser_thread)
        launch_btn.grid(row=3, column=0, sticky='ew', pady=(8,0))
        focus_btn = ttk.Button(top, text='Focus Browser', command=self.focus_browser)
        focus_btn.grid(row=3, column=1, sticky='ew', pady=(8,0))
        inspect_btn = ttk.Button(top, text='Inspect Page', command=self.inspect_page)
        inspect_btn.grid(row=2, column=2, sticky='ew')
        prev_btn = ttk.Button(top, text='Previous', command=self.prev_photo)
        prev_btn.grid(row=3, column=2, sticky='ew', pady=(8,0))
        next_btn = ttk.Button(top, text='Next', command=self.next_photo)
        next_btn.grid(row=3, column=3, sticky='ew', pady=(8,0))

        apply_btn = ttk.Button(top, text='Apply Selected Name(s)', command=self.apply_selected_names)
        apply_btn.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(8,0))

        # Layout expand
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # internal state: which names selected
        self.name_vars = []
        self.refresh_names_ui()
        # Start polling browser state to reflect current photo
        self.root.after(1000, self.poll_browser_state)

    def poll_browser_state(self):
        try:
            state = self.browser.get_state()
            url = state.get('url') if state else None
            if url:
                # show short form
                short = url.split('/')[-1]
                self.photo_label.config(text=f'Photo: {short}')
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
