Google Photos Tagging Assistant - POC
===================================

This is a small proof-of-concept desktop assistant to help semi-automate adding names to photo descriptions in Google Photos.

What this POC does
- Launches a Chromium browser (via Playwright) and opens Google Photos.
- Provides a Tkinter-based assistant UI where you can add and select names, then apply them to the current photo (stubbed).

-Important notes
- The actual DOM selectors and steps to open the info sidebar and edit a photo description in Google Photos vary and are intentionally left as stubs in `main.py`.
- After launching the browser, log in to Google Photos manually in the opened window.

Important macOS note about OS-level key events
----------------------------------------------
If the app falls back to sending real OS-level keyboard events (pyautogui), macOS requires Accessibility permission for the Python process. You will be prompted by macOS to grant the app permission the first time. If automation fails, go to System Settings → Privacy & Security → Accessibility and add the Python interpreter (for example: /usr/bin/python3 or your virtualenv python) and the Terminal app.

Install and run
1. Create and activate a Python venv (recommended):

```sh
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
# on Windows: .\.venv\Scripts\activate
```

2. Install requirements and Playwright browsers:

```sh
pip install -r requirements.txt
playwright install
```

3. Run the app:

```sh
python main.py
```

Windows notes
- Use the Windows PowerShell or CMD equivalents for venv activation.

Next steps to make this production-ready
- Inspect Google Photos DOM and implement robust selectors to open the info panel and update the description field.
- Add confirmation UI and undo safety checks.
- Add batching and rate-limiting to avoid accidental mass edits.
- Optionally support a browser profile for persistent login.
