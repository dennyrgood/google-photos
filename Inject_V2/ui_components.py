"""UI components - extracted from inject_v3.py"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading


class AssistantUI:
    """Minimal UI for Google Photos tagger."""
    
    def __init__(self, root, browser_controller, keystroke_handler, debug_mode=False):
        print('[UI] Initializing...')
        self.root = root
        self.browser = browser_controller
        self.keystroke = keystroke_handler
        self.debug_mode = debug_mode
        
        root.title('Google Photos Tagger - Old Device Mode')
        
        # Main frame
        main = ttk.Frame(root, padding=10)
        main.grid(row=0, column=0, sticky='nsew')

        # LAUNCH BUTTONS FRAME - First row
        launch_frame = ttk.LabelFrame(main, text='Launch Browser Mode', padding=5)
        launch_frame.grid(row=0, column=0, columnspan=4, sticky='ew', pady=(0, 8))
        
        self.launch_default_btn = ttk.Button(launch_frame, text='LAUNCH BROWSER', 
                                              command=lambda: self.launch_with_mode('default'))
        self.launch_default_btn.grid(row=0, column=0, sticky='ew', padx=2)
        
        launch_frame.columnconfigure(0, weight=1)

        # CONTROL BUTTONS FRAME - Second row
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=1, column=0, columnspan=4, sticky='ew', pady=(0, 8))

        self.prev_btn = ttk.Button(btn_frame, text='◄ PREV (P)', command=self.prev_photo, state='disabled')
        self.prev_btn.grid(row=0, column=0, sticky='ew', padx=2)

        self.next_btn = ttk.Button(btn_frame, text='NEXT (N) ►', command=self.next_photo, state='disabled')
        self.next_btn.grid(row=0, column=1, sticky='ew', padx=2)

        self.read_btn = ttk.Button(btn_frame, text='READ', command=self.read_current, state='disabled')
        if self.debug_mode:
            self.read_btn.grid(row=0, column=2, sticky='ew', padx=2)

        self.add_btn = ttk.Button(btn_frame, text='ADD Space', command=self.add_x, state='disabled')
        self.add_btn.grid(row=0, column=3, sticky='ew', padx=2)
        
        self.backspace_btn = ttk.Button(btn_frame, text='⌫ BACKSPACE', command=self.do_backspace, state='disabled')
        self.backspace_btn.grid(row=0, column=4, sticky='ew', padx=2)
        
        self.dump_btn = ttk.Button(btn_frame, text='DUMP HTML', command=self.dump_html, state='disabled')
        if self.debug_mode:
            self.dump_btn.grid(row=0, column=5, sticky='ew', padx=2)
        
        # Name buttons
        self.name_buttons = []
        base_col = 6
        for idx, raw in enumerate(self.keystroke.get_names_list()):
            label = raw
            pushed = ''.join(ch for ch in raw if ch not in '()')
            
            btn = ttk.Button(btn_frame, text=label, command=(lambda p=pushed: self.add_name(p)), state='disabled')
            btn.grid(row=0, column=base_col + idx, sticky='ew', padx=2)
            self.name_buttons.append(btn)
        
        # Configure columns
        for i in range(6 + len(self.name_buttons)):
            btn_frame.columnconfigure(i, weight=1)

        # Photo URL label - row 2
        self.photo_label = ttk.Label(main, text='Photo: (not connected)', font=('Courier', 10))
        self.photo_label.grid(row=2, column=0, columnspan=4, sticky='w', pady=(8, 8))

        # Description label - row 3
        desc_frame = ttk.LabelFrame(main, text='Current Description')
        desc_frame.grid(row=3, column=0, columnspan=4, sticky='nsew', pady=8)
        self.desc_label = ttk.Label(desc_frame, text='(no description)', wraplength=600, justify='left')
        self.desc_label.pack(padx=8, pady=8, anchor='w')

        # Keyboard status label - row 4
        self.keyboard_status = ttk.Label(main, text='Keyboard: Click window to focus, then press keys', 
                                          font=('Courier', 9), foreground='blue')
        self.keyboard_status.grid(row=4, column=0, columnspan=4, sticky='w', pady=(4, 0))

        # Bind keyboard events
        root.bind('<KeyPress>', self.on_key_press)
        main.bind('<KeyPress>', self.on_key_press)
        # Intercept space bar on buttons to prevent them from being triggered
        # Must return 'break' to stop event propagation and prevent button activation
        def handle_button_space(event):
            self.on_key_press(event)
            return 'break'  # Prevent default button behavior
        
        root.bind_class('Button', '<KeyPress-space>', handle_button_space)
        root.bind_class('Button', '<space>', handle_button_space)
        root.bind_class('TButton', '<KeyPress-space>', handle_button_space)  # For ttk.Button
        root.bind_class('TButton', '<space>', handle_button_space)  # For ttk.Button
        main.focus_set()
        
        print(f'[UI] Registered {len(self.keystroke.get_all_shortcuts())} keyboard shortcuts')
        print(f'[UI] Shortcuts: {list(self.keystroke.get_all_shortcuts().keys())}')
        
        print('[UI] Starting poll loop')
        self.poll_browser_state()
    
    def on_key_press(self, event):
        """Handle keyboard shortcuts and natural typing."""
        # Extract keycode if available (from event.keysym_num on some systems)
        keycode = getattr(event, 'keysym_num', None)
        keysym = event.keysym
        
        self.keyboard_status.config(text=f'Last key pressed: "{event.char}" (keysym: {keysym}, state: {event.state}, keycode: {keycode})')
        
        if not self.browser._running:
            print(f'[SHORTCUT] Ignored key "{event.char}" - browser not running')
            return

        # Check for Ctrl modifier using state bitmask (0x04 on Mac/Linux)
        ctrl_pressed = bool(event.state & 0x04)
        
        # Map keysym to key char for Ctrl combinations
        key = event.char if event.char else keysym
        
        # If it's a printable character (not a special key) and not a control combo
        # Reserved keys: numbers 1-9 and '=' only
        # Letters (including n, N, p, P) pass through as natural keystrokes
        reserved_keys = {'=', '1', '2', '3', '4', '5', '6', '7', '8', '9'}
        if len(key) == 1 and key.isprintable() and not ctrl_pressed and event.char and key not in reserved_keys:
            print(f'[NATURAL_TYPING] Sending "{key}" directly to description field')
            self.add_name(key)
            return 'break'
        
        # Special case: ignore unregistered keys message for unmatched letters
        if len(key) == 1 and key.isalpha() and not self.keystroke.on_key_press(key, ctrl=ctrl_pressed, state=event.state, keycode=keycode, keysym=keysym):
            print(f'[NATURAL_TYPING] Letter "{key}" passes through (not a registered shortcut)')
            return 'break'
        
        # Handle numeric keys for Ctrl+1, Ctrl+2, Ctrl+3
        if ctrl_pressed and key.isdigit():
            print(f'[MODIFIER_COMBO] Ctrl+{key} pressed')
            action = self.keystroke.on_key_press(key, ctrl=True, state=event.state, keycode=keycode, keysym=keysym)
        else:
            action = self.keystroke.on_key_press(key, ctrl=ctrl_pressed, state=event.state, keycode=keycode, keysym=keysym)
        
        if action:
            action_type, action_data = action
            print(f'[SHORTCUT] Key "{key}" (ctrl={ctrl_pressed}, state={event.state}) -> {action_type}: {action_data}')
    
            if action_type == 'next':
                self.next_photo()
            elif action_type == 'prev':
                self.prev_photo()
            elif action_type == 'name':
                self.add_name(action_data)
            elif action_type == 'space':
                self.add_x()
            elif action_type == 'backspace':
                self.do_backspace()
            elif action_type == 'delete_all':
                self.delete_all_description()
            elif action_type == 'delete_50':
                self.delete_50_chars()
            elif action_type == 'tab_dennis':
                self.add_name('Dennis ')
                self.next_photo()
            
            return 'break'

    def add_name(self, name):
        """Append a given name string to the current description."""
        print(f'[ADD_NAME] Queueing append for: {name}')
        threading.Thread(target=lambda: self.browser.append_text(name), daemon=True).start()

    def launch_with_mode(self, mode):
        """Launch browser with specific user agent mode."""
        def _launch():
            try:
                print(f'[LAUNCH] Starting browser with mode: {mode}')
                
                self.browser._launch_mode = mode
                
                self.browser.start(headful=True)
                print('[LAUNCH] Browser started')
                self.root.after(0, self._on_browser_ready)
            except Exception as e:
                print(f'[LAUNCH] ERROR: {e}')
                import traceback
                traceback.print_exc()
                self.root.after(0, lambda: messagebox.showerror('Error', str(e)))

        threading.Thread(target=_launch, daemon=True).start()

    def _on_browser_ready(self):
        """Called when browser is ready."""
        self.launch_default_btn.config(state='disabled')
        
        self.prev_btn.config(state='normal')
        self.next_btn.config(state='normal')
        if self.debug_mode:
            self.read_btn.config(state='normal')
        self.add_btn.config(state='normal')
        self.backspace_btn.config(state='normal')
        if self.debug_mode:
            self.dump_btn.config(state='normal')
        
        try:
            for b in getattr(self, 'name_buttons', []):
                try:
                    b.config(state='normal')
                except Exception:
                    pass
        except Exception:
            pass
        
        self.keyboard_status.config(text='Keyboard: READY - Press N/P for next/prev, or name keys', 
                                     foreground='green')
        
        messagebox.showinfo('Browser Ready', 'Browser launched. Please log into Google Photos if needed.\n\nKeyboard shortcuts are active!')

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
                msg = desc if desc else '(no description)'
                self.root.after(0, lambda m=msg: self.desc_label.config(text=m))
            except Exception as e:
                print(f'[READ] ERROR: {e}')
                self.root.after(0, lambda: messagebox.showerror('Error', str(e)))

        threading.Thread(target=_read, daemon=True).start()

    def add_x(self):
        """Append X to description."""
        threading.Thread(target=self.browser.append_x, daemon=True).start()

    def do_backspace(self):
        """Send backspace to browser."""
        threading.Thread(target=self.browser.send_backspace, daemon=True).start()

    def delete_all_description(self):
        """Delete entire description."""
        threading.Thread(target=self.browser.delete_all_description, daemon=True).start()

    def delete_50_chars(self):
        """Delete last 50 characters from description."""
        threading.Thread(target=self.browser.delete_50_chars, daemon=True).start()

    def dump_html(self):
        """Dump current page HTML for debugging."""
        threading.Thread(target=self.browser.dump_html, daemon=True).start()

    def poll_browser_state(self):
        """Poll browser state and update UI."""
        try:
            state = self.browser.get_state()
            
            url = state.get('url')
            if url:
                short = url.split('/')[-1]
                self.photo_label.config(text=f'Photo: {short}')
            
            desc = state.get('description')
            if desc:
                preview = desc if len(desc) < 200 else (desc[:197] + '...')
                self.desc_label.config(text=preview)
            else:
                self.desc_label.config(text='(no description)')
        except Exception as e:
            print(f'[POLL] ERROR: {e}')

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
