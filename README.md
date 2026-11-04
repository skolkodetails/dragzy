# Dragzy 🐉

**English** · [Русский](README.ru.md)

A tiny purple pixel dragon that lives on your Windows desktop, chats with you and keeps track of your pomodoros.

![Dragzy and the pomodoro window](docs/screenshot.png)

![Statistics](docs/stats.png)

![Animation frames](docs/frames.png)

> The dragon speaks Russian. All of his lines live in plain Python lists, so you can translate them or write your own.

## Features

- **Lives on your desktop.** Stays beneath your windows, flies around, flaps his wings, blinks, turns toward the cursor, sometimes chases it, and falls asleep on the taskbar when he gets tired.
- **Pomodoro timer.** Click the dragon to open the timer. It has work, short break and long break (after every 4th pomodoro) phases, and you can set their lengths. When a phase ends, a short chime plays and the dragon flies above all windows to tell you it's time for a break or time to get back to work.
- **Statistics.** A tab in the pomodoro window shows today's pomodoros and focus minutes, your day streak, your best day, all-time totals and a 7-day chart. Stats are saved to `%APPDATA%\Dragzy\stats.json`, so they survive restarts.
- **Personality.** Smart and caring, but a troublemaker. He sometimes dodges your click (he gives in on the second try), leaves sticky notes on your desktop, hides behind the edge of the screen, sneezes fire, puts on sunglasses, winks, and sits on top of the pomodoro window. During a work pomodoro he behaves himself. Pick the calm personality to turn the mischief off.
- **Chatter.** Every 15-25 minutes he says something in a speech bubble: about the time of day, the day of the week, a bit of motivation, or your personal topics.
- **Weather.** Once a day he checks the forecast and gives advice like "rain tomorrow, take an umbrella".
- Drag him around with the mouse. Right-click opens a menu: pomodoro, statistics, "say something", "go to sleep", quit.

## Installation

You need Python 3.9+ for Windows.

```bash
pip install -r requirements.txt
```

Then double-click `dragzy.pyw`. The `.pyw` extension keeps the console window from popping up.

## Getting acquainted

On first launch the dragon asks your name, how to address you (she / he / neutral), your city for the weather, what to call him, and his personality: **cheeky** (pranks, sass, sticky notes) or **calm** (just care and the timer). Everything is saved to `%APPDATA%\Dragzy\settings.json` and can be changed later via right-click → settings.

Want your own lines? Copy `personal.example.py` to `personal.py` and add them there. `personal.py` is listed in `.gitignore`, so it never ends up in the repository.

Other settings are at the top of `dragzy.pyw`:

| Setting | What it does |
|---|---|
| `DESKTOP_ONLY` | `True`: lives beneath your windows; `False`: flies above everything |
| `WEATHER` | `False`: no internet access at all |
| `PHRASE_EVERY_MIN` | how often he talks |
| `SOUND` | chime at the end of each phase |

## Privacy and safety

- Uses only the Python standard library and Qt (PySide6).
- Goes online only for the weather, once a day, via Open-Meteo. No account needed. Your city's name is sent once to find its coordinates, after that only the coordinates.
- Writes only its own files in `%APPDATA%\Dragzy`: `settings.json` and `stats.json`. It doesn't add itself to startup and doesn't read your keyboard or the contents of other windows. All it knows about your system is the screen size and where the cursor is.
- CPU usage is about 3% of one core in normal mode and about 1% while he sleeps.

If the dragon doesn't show up after launch, set `DESKTOP_ONLY = False`: some Windows builds hide windows like this beneath the desktop.

## License

[MIT](LICENSE)
