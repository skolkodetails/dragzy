# -*- coding: utf-8 -*-
"""
Dragzy: фиолетовый пиксельный дракончик для рабочего стола Windows.

Перед первым запуском один раз выполни в терминале:
    pip install PySide6-Essentials

Что умеет:
- живёт на рабочем столе под окнами: летает, машет крыльями, моргает,
  следит глазами за курсором, иногда засыпает на панели задач;
- раз в 15-25 минут говорит фразочку про время суток, погоду и дела
  (личные фразы берутся из personal.py, если он лежит рядом);
- по клику открывает помодоро-таймер со статистикой (сохраняется между запусками);
- в конце работы или отдыха подаёт короткий сигнал и вылетает поверх
  всех окон с подсказкой (клик по нему или по облачку прячет её);
- его можно перетаскивать мышкой; по правому клику открывается меню.

Безопасность: Python и библиотека Qt (PySide6).
В интернет ходит раз в день за прогнозом погоды через Open-Meteo
(без аккаунта; название города отправляется один раз, дальше только координаты).
Пишет только свои файлы в %APPDATA%\\Dragzy: settings.json и stats.json.
Не ставится в автозагрузку, не читает клавиатуру и окна.
Имя, город и характер спрашиваются при первом запуске. Свои фразы можно добавить в personal.py.
"""
import datetime as dt
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.parse
import urllib.request

IS_WIN = sys.platform.startswith("win")

try:
    from PySide6.QtCore import (Qt, QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect,
                                QRectF, QTimer)
    from PySide6.QtGui import (QBrush, QConicalGradient, QImage, QPixmap, QColor, QCursor, QFont, QFontInfo, QFontMetrics, QGuiApplication,
                               QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF,
                               QRadialGradient)
    from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
                                   QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget)
except ImportError:
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo("Слива", "не хватает библиотеки qt.\n\nоткрой терминал и выполни:\n"
                            "pip install PySide6-Essentials\n\nпотом запусти дракончика ещё раз.")
    except Exception:
        print("pip install PySide6-Essentials")
    sys.exit(1)

# ================================================================= настройки
# имя, город, род обращения и характер спрашиваются при первом запуске
# и хранятся в %APPDATA%\Dragzy\settings.json (меняются через меню «настройки»)
PET_NAME = "Слива"
USER_NAME = "друг"
GENDER = "n"                 # f / m / n: как обращаться (она / он / без рода)
MODE = "bold"                # bold: нахальный; calm: спокойный
CITY_NAME = ""
DESKTOP_ONLY = True          # True, живёт под окнами; False, поверх всех окон
WEATHER = True               # False, совсем без интернета
CITY = None                  # координаты, находятся по названию города
PHRASE_EVERY_MIN = (15, 25)  # фразочка раз в 15-25 минут
SOUND = True
PRANKS = True                # хулиганства (включены в нахальном характере)
FLY_SPEED = 2.6
CHASE_SPEED = 6.0

UI_BG = "#24163a"
UI_CARD = "#33224f"
UI_TEXT = "#f6efff"
UI_MUTED = "#b7a4d8"
UI_ORANGE = "#ff7b00"
UI_GREEN = "#56d12e"
BUBBLE_BG = "#fffaf3"
BUBBLE_LINE = "#2a1840"

# ================================================================= спрайты дракончика
W, H = 36, 33
Y0 = -3  # extra rows above
X0 = -5  # extra columns on each side (wings)

PAL = {
    "K": "#2a1840",  # outline
    "V": "#9b6be0",  # purple body
    "v": "#7548bd",  # shade
    "L": "#c6a6f5",  # highlight
    "B": "#ffcf9e",  # belly (peach)
    "b": "#f2ad74",  # belly stripes
    "O": "#ff7b00",  # inner ears
    "N": "#5b3596",  # wing membrane
    "n": "#8a5ad6",  # wing bones/edge
    "C": "#fff0c8",  # horns
    "c": "#e8cf95",
    "G": "#3fdc7c",  # iris
    "g": "#22a85a",
    "E": "#1d1030",  # pupil
    "W": "#ffffff",
    "P": "#ff9ec2",  # cheeks
    "M": "#d9446d",  # mouth inside
    "T": "#ff7aa8",  # tongue
}


def make_frame(eyes="open", wings="up", tail=0, look=0, mouth=None):
    """eyes: open/blink/happy/closed/wow; wings: up/down/fold;
    tail: 0/1; look: -1/0/1; mouth: None(auto)/'smile'/'open'/'o'."""
    g = [["." for _ in range(W - 2 * X0)] for _ in range(H - Y0)]

    def inside(x, y):
        return X0 <= x < W - X0 and Y0 <= y < H

    def ellipse(cx, cy, rx, ry):
        return {(x, y) for y in range(Y0, H) for x in range(X0, W - X0)
                if ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 <= 1}

    def poly(pts):
        res = set()
        n = len(pts)
        for y in range(Y0, H):
            for x in range(X0, W - X0):
                px, py = x + .5, y + .5
                ins = False
                j = n - 1
                for i in range(n):
                    xi, yi = pts[i]
                    xj, yj = pts[j]
                    if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                        ins = not ins
                    j = i
                if ins:
                    res.add((x, y))
        return res

    def thick_line(p0, p1, r):
        res = set()
        steps = 40
        for i in range(steps + 1):
            t = i / steps
            cx = p0[0] + (p1[0] - p0[0]) * t
            cy = p0[1] + (p1[1] - p0[1]) * t
            res |= {(x, y) for y in range(int(cy - r - 1), int(cy + r + 2))
                    for x in range(int(cx - r - 1), int(cx + r + 2))
                    if (x + .5 - cx) ** 2 + (y + .5 - cy) ** 2 <= r * r}
        return res

    def layer(pts, color, outline=True):
        if outline:
            for (x, y) in pts:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    p = (x + dx, y + dy)
                    if p not in pts and inside(*p):
                        g[p[1] - Y0][p[0] - X0] = "K"
        for (x, y) in pts:
            if inside(x, y):
                g[y - Y0][x - X0] = color(x, y) if callable(color) else color

    # ---- wings (behind body)
    if wings != "fold":
        up = wings == "up"
        for side in (-1, 1):
            cx = 18
            sx = lambda d: cx + side * d
            if up:
                pts = [(sx(5), 18), (sx(11), 6), (sx(21), 1), (sx(19), 8),
                       (sx(21.5), 10.5), (sx(16.5), 13.5), (sx(17.5), 17.5), (sx(9), 21.5)]
            else:
                pts = [(sx(5), 17), (sx(12), 14.5), (sx(21.5), 16.5), (sx(19), 20),
                       (sx(21), 24), (sx(16), 24), (sx(15), 28), (sx(7.5), 24)]
            pts = [(x if side > 0 else x, y) for x, y in pts]
            layer(poly(pts), lambda x, y, up=up: "n" if (up and y <= 6) else "N")
    else:
        for side in (-1, 1):
            cx = 18 + side * 8.5
            layer(poly([(cx - 2.5, 17), (cx + 2.5, 17), (cx + side * 3.5, 25), (cx - side * 0.5, 25)]), "N")

    # ---- tail (right side, behind body)
    ty = 19 if tail == 0 else 17
    tail_pts = thick_line((22, 27), (28, 26), 1.6) | thick_line((28, 26), (31, ty + 2), 1.2)
    layer(tail_pts, lambda x, y: "v" if y >= 27 else "V")
    tip = poly([(31.5, ty - 2.5), (34.5, ty + 1), (31.5, ty + 3), (28.8, ty + 0.5)])
    layer(tip, "O")

    # ---- body
    layer(ellipse(18, 23.5, 7.5, 6.5), lambda x, y: "v" if (y >= 27 or x >= 23) else "V")
    layer(ellipse(18, 24.2, 4.6, 4.8),
          lambda x, y: "b" if y in (22, 25) else "B", outline=False)
    # feet
    for fx in (13.5, 22.5):
        layer(ellipse(fx, 29.4, 2.6, 1.7), "V")
        layer({(int(fx) - 1, 30), (int(fx) + 1, 30)}, "K", outline=False)
    # arms
    for ax in (11.6, 24.4):
        layer(ellipse(ax, 22.8, 1.6, 2.2), "V")

    # ---- ears (pointed, soft tips)
    for side in (-1, 1):
        sx = lambda d: 18 + side * d
        ear = poly([(sx(3), 6.0), (sx(8.2), 0.6), (sx(9.6), -1.6), (sx(11.0), -1.9),
                    (sx(11.7), -0.6), (sx(11.6), 2.2), (sx(10.5), 8.5)])
        layer(ear, "V")
        inner = poly([(sx(5.2), 5.6), (sx(8.6), 1.6), (sx(9.9), 0.4), (sx(10.6), 0.9),
                       (sx(10.4), 3.2), (sx(9.6), 7.0)])
        layer(inner, "O", outline=False)
    # ---- head
    layer(ellipse(18, 11.5, 9.2, 7.3),
          lambda x, y: "L" if (x <= 12 and y <= 8) else ("v" if y >= 17 else "V"))
    # horns
    for hx in (14.5, 21.5):
        layer(poly([(hx - 1.2, 5.6), (hx + 1.2, 5.6), (hx + .2 * (1 if hx > 18 else -1), 2.2)]),
              lambda x, y: "c" if y >= 5 else "C")
    # ---- face
    exs = (13.5 + look, 22.5 + look)
    ey = 11.5
    open_eyes = exs
    if eyes in ("wink", "brow"):
        open_eyes = exs[1:] if eyes == "wink" else exs
        if eyes == "wink":
            i = int(exs[0])
            layer({(i - 2, 12), (i - 1, 13), (i, 13), (i + 1, 13), (i + 2, 12)}, "E", outline=False)
        eyes_draw = "open"
    else:
        eyes_draw = eyes
    if eyes_draw in ("open", "wow"):
        big = eyes_draw == "wow"
        for ex in open_eyes:
            layer(ellipse(ex, ey, 3.4 if big else 3.2, 3.9 if big else 3.6), "E", outline=False)
            layer(ellipse(ex, ey, 2.7 if big else 2.5, 3.2 if big else 2.9),
                  lambda x, y: "g" if y >= int(ey) + 1 else "G", outline=False)
            layer(ellipse(ex + look * .7, ey + .6, 1.1 if big else 1.0, 1.4 if big else 1.3), "E", outline=False)
            i = int(ex)
            layer({(i - 1, int(ey) - 2), (i, int(ey) - 2), (i - 1, int(ey) - 1), (i, int(ey) - 1)}, "W", outline=False)
            layer({(i + 1, int(ey) + 2)}, "W", outline=False)
    elif eyes == "cool":
        # тёмные очки
        shades = set()
        for ex in exs:
            shades |= ellipse(ex, ey + .3, 3.4, 2.4)
        shades |= {(x, int(ey) - 1) for x in range(int(exs[0]), int(exs[1]) + 1)}
        layer(shades, "K", outline=False)
        for ex in exs:
            i = int(ex)
            layer({(i - 2, int(ey) - 1), (i - 1, int(ey) - 1), (i - 2, int(ey))}, "W", outline=False)
    elif eyes in ("blink", "closed"):
        for ex in exs:
            i = int(ex)
            layer({(i - 2, 12), (i - 1, 13), (i, 13), (i + 1, 13), (i + 2, 12)}, "E", outline=False)
    elif eyes == "happy":
        for ex in exs:
            i = int(ex)
            layer({(i - 2, 13), (i - 1, 12), (i, 11), (i + 1, 12), (i + 2, 13)}, "E", outline=False)

    # cheeks
    layer({(9, 15), (10, 15), (26, 15), (27, 15)}, "P", outline=False)
    # nostrils
    layer({(16, 14), (20, 14)}, "v", outline=False)

    if eyes == "brow":
        # поднятая бровь над правым глазом
        i = int(exs[1])
        layer({(i - 3, int(ey) - 4), (i - 2, int(ey) - 5), (i - 1, int(ey) - 6), (i, int(ey) - 6),
               (i + 1, int(ey) - 6), (i + 2, int(ey) - 5)}, "K", outline=False)
        j = int(exs[0])   # левый глаз чуть прищурен
        layer({(j - 2, int(ey) - 3), (j - 1, int(ey) - 3), (j, int(ey) - 3), (j + 1, int(ey) - 3), (j + 2, int(ey) - 3)},
              "K", outline=False)
    m = mouth or ("open" if eyes == "happy" else "o" if eyes == "wow"
                  else "sleep" if eyes == "closed"
                  else "smirk" if eyes in ("wink", "cool", "brow") else "smile")
    mx = 18 + (look if m != "sleep" else 0)
    if m == "smile":
        layer({(mx - 2, 15), (mx - 1, 16), (mx, 16), (mx + 1, 15)}, "K", outline=False)
    elif m == "open":
        layer({(mx - 2, 15), (mx - 1, 15), (mx, 15), (mx + 1, 15),
               (mx - 2, 16), (mx + 1, 16), (mx - 1, 17), (mx, 17)}, "K", outline=False)
        layer({(mx - 1, 16), (mx, 16)}, "T", outline=False)
    elif m == "o":
        layer({(mx - 1, 15), (mx, 15), (mx - 2, 16), (mx + 1, 16), (mx - 1, 17), (mx, 17)}, "K", outline=False)
        layer({(mx - 1, 16), (mx, 16)}, "M", outline=False)
    elif m == "sleep":
        layer({(17, 16), (18, 16)}, "K", outline=False)
    elif m == "smirk":
        layer({(mx - 2, 16), (mx - 1, 16), (mx, 16), (mx + 1, 15), (mx + 2, 14)}, "K", outline=False)
    return g


PIX = 4                                  # размер «пикселя» на экране
GW, GH = W - 2 * X0, H - Y0
CW, CH = GW * PIX, GH * PIX
CX = CW // 2
HEAD_X = (18 - X0) * PIX                 # центр головы на холсте
_cache = {}

HEART = [".KK.KK.", "KPPKPPK", "KPPPPPK", ".KPPPK.", "..KPK..", "...K..."]
ZED = ["KKKK", "..K.", ".K..", "KKKK"]


def grid_image(grid):
    gh, gw = len(grid), len(grid[0])
    img = QImage(gw, gh, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    for y, row in enumerate(grid):
        for x, c in enumerate(row):
            if c != ".":
                img.setPixelColor(x, y, QColor(PAL[c]))
    return img


def draw_pixels(p, img, x, y, scale=PIX):
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)
    p.drawImage(QRectF(x, y, img.width() * scale, img.height() * scale), img)


def draw_dragon(p, s):
    eyes = s.get("eyes", "open")
    if eyes == "open" and s.get("blink", 1) < .5:
        eyes = "blink"
    wings = "fold" if s.get("fold") else ("up" if s.get("flap", 1) > .3 else "down")
    tail = 1 if s.get("tail", 0) > 0 else 0
    lx = s.get("look", (0, 0))[0] * (-1 if s.get("mirror") else 1)
    look = 1 if lx > .35 else -1 if lx < -.35 else 0
    mouth = s.get("mouth")
    key = (eyes, wings, tail, look, mouth)
    img = _cache.get(key)
    if img is None:
        img = grid_image(make_frame(eyes, wings, tail, look, mouth))
        _cache[key] = img
    draw_pixels(p, img, 0, int(round(s.get("bob", 0))))


# ================================================================= фразы
def fmt_t(x):
    x = round(x)
    return ("−" if x < 0 else "") + str(abs(x)) + "°"


PHRASES_ANY = [
    "попей воды. это правда помогает думать.",
    "если не знаешь, с чего начать, начни с самого маленького куска.",
    "большую задачу проще резать на части. какая из них первая?",
    "не обязательно идеально. сначала пусть будет сделано, улучшить можно потом.",
    "ошибка это просто данные. посмотри, что она говорит, и иди дальше.",
    "давно сидишь? пара минут на ногах хорошо освежает голову.",
    "проветри комнату, мозгу нужен кислород.",
    "телефон экраном вниз, и вокруг станет заметно тише.",
    "можно запустить помидорку. кликни по мне.",
    "закрой пару лишних вкладок, голове станет просторнее.",
    "если задача пугает, открой её на две минуты. обычно дальше идёт само.",
    "сегодня сделано больше, чем кажется.",
    "ты сегодня {g:сделала|сделал} больше, чем кажется.",
]

PHRASES_BADBOY = [
    "не благодари. хотя можешь.",
    "правила придумали те, кто не умеет летать. дедлайны, к сожалению, тоже.",
    "я здесь не потому что волнуюсь. просто пролетал мимо. попей воды.",
    "у меня нет плана. у меня есть харизма и немного огня.",
    "мне не нужна мотивация, мне нужен зритель. работай, я посмотрю.",
    "сделай перерыв. не ради меня. ради драмы.",
    "мудрость дня: если задачу не победить, разбей её на части. на части, а не о стену.",
    "это не я переставил иконки. но если я, то стало лучше.",
    "плохие драконы тоже делают помидорки. просто не афишируют.",
    "если кто-то спросит, это я заставил тебя отдохнуть. мне не жалко, у меня репутация.",
    "секрет крутости: спать по ночам. звучит скучно, работает отлично.",
    "не люблю нравоучения, поэтому коротко: телефон в сторону.",
    "я загадочный. а ещё я знаю, что у тебя открыто слишком много вкладок.",
    "легенды не торопятся. но и не прокрастинируют три часа подряд.",
    "ахх, опять ты. ладно, рад. немного.",
    "{g:скучала|скучал}? можешь не отвечать, я знаю.",
    "ты {g:главная героиня|главный герой} этого сериала. я просто сложный персонаж второго плана.",
    "я видел, как ты сегодня {g:старалась|старался}. никому не скажу. это наш секрет.",
    "умный не тот, кто всё знает. умный тот, кто вовремя ложится спать. я, например.",
]

DODGE = ["не так быстро.", "мимо.", "поймай сначала.", "ой, промах."]
GIVE_UP = ["ладно, ладно. сдаюсь.", "так уж и быть.", "уговорили. открываю."]
DRAG = ["эй, руки. ладно, неси.", "аккуратнее, у меня причёска.", "я сам умею летать, вообще-то."]
PEEK = ["ку-ку.", "не ищи меня.", "я тут. или нет."]
CAUGHT = ["не догонишь.", "почти.", "слишком медленно."]
SNEEZE = ["пардон. аллергия на дедлайны.", "это был не огонь. это был характер.", "никто ничего не видел."]
COOL = ["я знаю. можешь не говорить.", "очки? для солнца. какого? своего.", "не обращай внимания, я просто крутой."]
NOTE_DROP = ["оставил кое-что на столе. не благодари.", "у тебя на столе послание. ищи.", ""]
NOTE_GONE = ["эй, это было искусство.", "ну и ладно. напишу ещё.", ""]
MOTIONS = [
    "эта палата запретила бы дедлайны по понедельникам.",
    "эта палата сделала бы дневной сон обязательным.",
    "эта палата считает, что драконы лучшие питомцы.",
    "эта палата отменила бы будильники.",
]
FLIP = ["фигура «дракон вверх ногами». судьи, оценки?", "вертикаль. держу хвост ровно.", "это не падение. это хореография."]
NOTES = [
    "тут был Слива",
    "я съел твою прокрастинацию. было невкусно.",
    "не ищи меня. я сам найдусь.",
    "проверь, сколько у тебя вкладок. потом не говори, что я не предупреждал.",
    "иконки трогал не я.",
    "попей воды. подпись: тот самый дракон",
    "ты справишься. но я тебе этого не говорил.",
    "сегодня всё получится. это не комплимент, это прогноз.",
]

PHRASES_YOU = [  # личные фразы, переопредели их в personal.py
    "аргумент, пример, вывод. работает и в споре, и в курсовой.",
    "python не ругается, он показывает traceback. читай снизу вверх.",
    "импровизация учит говорить «да, и». попробуй так с перерывом.",
    "small talk practice: how are you today? «tired» тоже честный ответ.",
]

PHRASES_TIME = {
    "morning": [
        "доброе утро, {name}. сначала завтрак, потом дела.",
        "утро хорошо подходит для самой сложной задачи дня.",
        "сейчас {time}. выбери три главных дела на сегодня, не больше.",
    ],
    "day": [
        "середина дня. обед уже был?",
        "середина дня. ты сегодня {g:ела|ел}?",
        "после обеда концентрация падает, это нормально. помидорка поможет собраться.",
        "уже {time}. можно закрыть одну маленькую задачу.",
    ],
    "evening": [
        "вечер. что сегодня получилось? даже одна вещь считается.",
        "уже {time}. пора потихоньку сворачивать дела.",
    ],
    "night": [
        "уже {time}. дела подождут до утра, сон нет.",
        "{time}, поздно. завтра будет легче, если лечь сейчас.",
        "ночью решения кажутся гениальными. лучше проверить их утром.",
        "глаза устали, значит пора спать. я тоже пойду на панель задач.",
    ],
}

PHRASES_WEEKDAY = {
    0: "понедельник. можно начать спокойно, без рывка.",
    4: "пятница. часть дел честно можно перенести на понедельник.",
    5: "суббота. отдых тоже часть работы.",
    6: "воскресенье. десять минут на план недели, и дальше отдыхать.",
}


# свои фразы: если рядом лежит personal.py, добавляем их (имя и город берутся из настроек)
try:
    import personal as _me
    USER_NAME = getattr(_me, "USER_NAME", USER_NAME)      # только как подсказка при знакомстве
    PET_NAME = getattr(_me, "PET_NAME", PET_NAME)
    PHRASES_YOU = list(getattr(_me, "PHRASES_YOU", PHRASES_YOU))
    PHRASES_ANY = PHRASES_ANY + list(getattr(_me, "PHRASES_EXTRA", []))
    PHRASES_BADBOY = PHRASES_BADBOY + list(getattr(_me, "PHRASES_BADBOY_EXTRA", []))
    NOTES = NOTES + list(getattr(_me, "NOTES_EXTRA", []))
    MOTIONS = MOTIONS + list(getattr(_me, "MOTIONS_EXTRA", []))
    FLIP = FLIP + list(getattr(_me, "FLIP_EXTRA", []))
    for _part, _lines in getattr(_me, "PHRASES_TIME_EXTRA", {}).items():
        PHRASES_TIME.setdefault(_part, []).extend(_lines)
except ImportError:
    pass


_G = re.compile(r"\{g:([^|}]*)\|([^|}]*)(?:\|([^}]*))?\}")


def gtext(text):
    """{g:она|он} или {g:она|он|без рода}. фраза без варианта для «без рода» пропускается (None)."""
    if "{g:" not in text:
        return text
    if GENDER == "n" and any(m.group(3) is None for m in _G.finditer(text)):
        return None
    i = {"f": 1, "m": 2, "n": 3}[GENDER]
    return _G.sub(lambda m: m.group(i) if m.group(i) is not None else m.group(1), text)


REACT = {  # (нахальный, спокойный)
    "greet": ("привет, {name}. я {pet}. кликни по мне, будет помодоро. если поймаешь.",
              "привет, {name}. я {pet}. кликни по мне, и откроется помодоро."),
    "hello": ("приятно познакомиться, {name}. иногда буду хулиганить. ты {g:предупреждена|предупреждён|предупреждены}.",
              "приятно познакомиться, {name}. я рядом, если что."),
    "start": ("поехали. {work} минут, и меня тут нет. почти.", "поехали. {work} минут фокуса, я не буду отвлекать."),
    "resume": ("продолжаем. я даже не заметил паузу.", "продолжаем."),
    "pause": ("пауза? понимаю. даже легенды отдыхают.", "пауза. таймер подождёт."),
    "reset": ("сброс. красиво начать заново тоже талант.", "таймер сброшен. начнём, когда будет удобно."),
    "minute": ("минута. держись, я почти горжусь.", "осталась минута."),
    "rest": ("помидорка всё. отдых {short} мин: встань, попей воды, посмотри вдаль. я прослежу.",
             "помидорка готова. отдых {short} мин: встань, попей воды, посмотри вдаль."),
    "long": ("{every} помидорки подряд. длинный отдых, {long} минут. заслуженно, не спорь.",
             "{every} помидорки подряд. теперь длинный отдых, {long} минут."),
    "work": ("перерыв окончен. возвращаемся, звезда. помидорка {k} из {every}.",
             "отдых закончился, пора работать. помидорка {k} из {every}."),
    "record": ("новый рекорд дня: {n}. я, конечно, знал. отдых {r} мин.", "новый рекорд дня: {n}. отдых {r} мин."),
}


def R(key, **kw):
    t = gtext(REACT[key][0 if MODE == "bold" else 1]) or REACT[key][1]
    return t.format(name=USER_NAME, pet=PET_NAME, **kw)


def time_phrase(now):
    h = now.hour
    part = "morning" if 5 <= h < 12 else "day" if 12 <= h < 18 else "evening" if 18 <= h < 23 else "night"
    return random.choice(PHRASES_TIME[part])


def pick_phrase(now, weather_tips):
    for _ in range(12):
        r = random.random()
        if weather_tips and r < .2:
            text = random.choice(weather_tips)
        elif r < .45:
            text = time_phrase(now)
        elif r < .6:
            text = random.choice(PHRASES_YOU)
        elif PRANKS and r < .78:
            text = random.choice(PHRASES_BADBOY)
        elif r < .84 and now.weekday() in PHRASES_WEEKDAY:
            text = PHRASES_WEEKDAY[now.weekday()]
        else:
            text = random.choice(PHRASES_ANY)
        text = gtext(text)
        if text:
            return text.format(name=USER_NAME, time=now.strftime("%H:%M"))
    return "попей воды."


# ================================================================= погода
RAIN = set(range(51, 68)) | {80, 81, 82}
SNOW = set(range(71, 78)) | {85, 86}
ICE = {56, 57, 66, 67}
STORM = {95, 96, 99}


def weather_tips(data, now):
    d = data["daily"]
    tips = []
    days = [(0, "сегодня"), (1, "завтра")] if now.hour < 15 else [(1, "завтра")]
    for i, label in days:
        code = d["weather_code"][i]
        tmax, tmin = d["temperature_2m_max"][i], d["temperature_2m_min"][i]
        pp = d["precipitation_probability_max"][i] or 0
        wind = d["wind_speed_10m_max"][i] or 0
        rng = f"от {fmt_t(tmin)} до {fmt_t(tmax)}"
        if code in STORM:
            t = f"{label} гроза. возьми зонт и не стой под деревьями."
        elif code in ICE:
            t = f"{label} ледяной дождь, будет скользко. лучше обувь с нормальной подошвой."
        elif code in SNOW:
            t = f"{label} снег, {rng}. тёплые носки и непромокаемая обувь."
        elif code in RAIN or pp >= 60:
            t = f"{label} дождь, вероятность {pp}%. возьми зонт."
        elif pp >= 40:
            t = f"{label} может пойти дождь, {pp}%. маленький зонт в сумке не помешает."
        elif tmax <= -10:
            t = f"{label} {rng}. шапка, шарф и варежки."
        elif code <= 1 and tmax >= 12:
            t = f"{label} солнечно, до {fmt_t(tmax)}. хороший день, чтобы пройтись пешком."
        else:
            wear = ("нужны тёплая куртка и шапка" if tmax < 3 else "нужна куртка" if tmax < 10
                    else "хватит лёгкой куртки" if tmax < 17 else "можно налегке")
            t = f"{label} {rng}, {wear}."
        if wind >= 40:
            t += " ещё сильный ветер, капюшон пригодится."
        tips.append(t)
    return tips


def geocode(name):
    url = ("https://geocoding-api.open-meteo.com/v1/search?count=1&language=ru&format=json&name="
           + urllib.parse.quote(name))
    req = urllib.request.Request(url, headers={"User-Agent": "desk-dragon"})
    with urllib.request.urlopen(req, timeout=10) as r:
        res = json.loads(r.read().decode("utf-8")).get("results") or []
    return (res[0]["latitude"], res[0]["longitude"]) if res else None


def fetch_weather():
    global CITY
    if not CITY and CITY_NAME:
        CITY = geocode(CITY_NAME)
        if CITY:
            s = load_settings() or {}
            s["coords"] = list(CITY)
            save_settings(s)
    if not CITY:
        raise RuntimeError("город не задан")
    lat, lon = CITY
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
           "precipitation_probability_max,wind_speed_10m_max"
           "&timezone=auto&forecast_days=2" % (lat, lon))
    req = urllib.request.Request(url, headers={"User-Agent": "desk-dragon"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


# ================================================================= настройки (знакомство)
def app_dir():
    base = os.environ.get("APPDATA")
    return os.path.join(base, "Dragzy") if base else os.path.join(os.path.expanduser("~"), ".dragzy")


def load_settings():
    try:
        with open(os.path.join(app_dir(), "settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_settings(d):
    try:
        os.makedirs(app_dir(), exist_ok=True)
        path = os.path.join(app_dir(), "settings.json")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(path + ".tmp", path)
    except Exception:
        pass


def apply_settings(d):
    global USER_NAME, PET_NAME, GENDER, MODE, CITY_NAME, CITY, PRANKS
    USER_NAME = (d.get("name") or "друг").strip()
    PET_NAME = (d.get("pet") or "Слива").strip()
    GENDER = d.get("gender", "n")
    MODE = d.get("mode", "bold")
    PRANKS = MODE == "bold"
    new_city = (d.get("city") or "").strip()
    if new_city != CITY_NAME:
        CITY = tuple(d["coords"]) if d.get("coords") else None
    CITY_NAME = new_city


# ================================================================= звук
def play_sound(kind):
    if not SOUND:
        return

    def run():
        try:
            import winsound
            notes = [(784, 110), (988, 110), (1319, 200)] if kind == "rest" else [(1319, 110), (988, 110), (784, 200)]
            for f, d in notes:
                winsound.Beep(f, d)
        except Exception:
            QApplication.beep()
    threading.Thread(target=run, daemon=True).start()


# ================================================================= Windows: слои окон
def _hwnd(w):
    return int(w.winId())


def z_bottom(w):
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(_hwnd(w)), ctypes.c_void_p(1),
                                              0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass


def z_top(w, on=True):
    if IS_WIN:
        try:
            import ctypes
            after = -1 if on else -2  # HWND_TOPMOST / HWND_NOTOPMOST
            ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(_hwnd(w)), ctypes.c_void_p(after),
                                              0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass
    else:
        w.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        w.show()


def base_flags():
    f = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
    if not DESKTOP_ONLY:
        f |= Qt.WindowStaysOnTopHint
    return f


def voice(text):
    """манера речи: всё строчными (кроме имени дракончика) и без длинных тире."""
    text = re.sub(r"\s*[\u2014\u2013]\s*", ", ", text).lower()
    return re.sub(r"\b" + re.escape(PET_NAME.lower()) + r"\b", PET_NAME, text)


# ================================================================= облачко с репликой
class Bubble(QWidget):
    MAXW = 250

    def __init__(self):
        super().__init__(None, base_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.font_ = QFont("Segoe UI", 10)
        self.text = ""
        self.tail_up = False
        self.tail_x = 0
        self.on_click = None

    def set_text(self, text):
        text = voice(text)
        self.text = text
        fm = QFontMetrics(self.font_)
        r = fm.boundingRect(QRect(0, 0, self.MAXW, 1000), Qt.TextWordWrap, text)
        self.tw, self.th = r.width(), r.height()
        self.resize(self.tw + 34, self.th + 38)

    def place_near(self, pet_rect, work, anchor_x=None):
        w, h = self.width(), self.height()
        cx = pet_rect.center().x() if anchor_x is None else int(anchor_x)
        x = max(work.left() + 4, min(cx - w // 2, work.right() - w - 4))
        y = pet_rect.top() + int(pet_rect.height() * .12) - h
        self.tail_up = y < work.top()
        if self.tail_up:
            y = pet_rect.bottom() - 6
        self.tail_x = max(22, min(cx - x, w - 22))
        self.move(x, y)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top = 12 if self.tail_up else 2
        body = QRectF(4, top, w - 10, h - 16)
        path = QPainterPath()
        path.addRoundedRect(body, 14, 14)
        tail = QPainterPath()
        tx = self.tail_x
        if self.tail_up:
            tail.moveTo(tx - 9, top + 1)
            tail.lineTo(tx + 2, 1)
            tail.lineTo(tx + 9, top + 1)
        else:
            tail.moveTo(tx - 9, body.bottom() - 1)
            tail.lineTo(tx - 2, h - 2)
            tail.lineTo(tx + 9, body.bottom() - 1)
        path = path.united(tail)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(40, 15, 70, 50))
        p.drawPath(path.translated(2, 3))
        p.setBrush(QColor(BUBBLE_BG))
        p.setPen(QPen(QColor(BUBBLE_LINE), 2))
        p.drawPath(path)
        p.setFont(self.font_)
        p.setPen(QColor("#2a1840"))
        p.drawText(QRectF(body.left() + 12, body.top() + 9, self.tw + 2, self.th + 2),
                   Qt.TextWordWrap, self.text)

    def mousePressEvent(self, e):
        if self.on_click:
            self.on_click()


# ================================================================= помодоро
def plural(n, one, few, many):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


class Stats:
    """статистика помидорок: один json-файл в %APPDATA%\\Dragzy (или ~/.dragzy)."""

    def __init__(self):
        self.dir = app_dir()
        self.path = os.path.join(self.dir, "stats.json")
        self.days = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                self.days = json.load(f).get("days", {})
        except Exception:
            self.days = {}

    def save(self):
        try:
            os.makedirs(self.dir, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"days": self.days}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def day(self, d=None):
        return self.days.get((d or dt.date.today()).isoformat(), {"pomos": 0, "minutes": 0})

    def add(self, pomos=0, minutes=0.0):
        """возвращает True, если это новый рекорд дня по помидоркам."""
        key = dt.date.today().isoformat()
        prev_best = self.best()
        d = self.days.setdefault(key, {"pomos": 0, "minutes": 0})
        d["pomos"] += pomos
        d["minutes"] = round(d["minutes"] + minutes, 1)
        self.save()
        return pomos > 0 and d["pomos"] > prev_best and prev_best > 0

    def best(self):
        return max((v["pomos"] for v in self.days.values()), default=0)

    def last(self, n=7):
        today = dt.date.today()
        return [(today - dt.timedelta(days=i), self.day(today - dt.timedelta(days=i)))
                for i in range(n - 1, -1, -1)]

    def week(self):
        return sum(v["pomos"] for _, v in self.last(7))

    def streak(self):
        d = dt.date.today()
        if self.day(d)["pomos"] == 0:
            d -= dt.timedelta(days=1)
        n = 0
        while self.day(d)["pomos"] > 0:
            n += 1
            d -= dt.timedelta(days=1)
        return n

    def total(self):
        return (sum(v["pomos"] for v in self.days.values()),
                sum(v["minutes"] for v in self.days.values()))


class Pomodoro:
    def __init__(self, stats=None):
        self.work, self.short, self.long, self.every = 25, 5, 15, 4
        self.stats = stats or Stats()
        self.record = False
        self.reset()

    @property
    def done_total(self):
        return self.stats.day()["pomos"]

    def _log_focus(self, finished):
        """записать минуты фокуса (и помидорку, если работа дошла до конца)."""
        if self.phase != "work":
            return
        spent = self.total() - self.left()
        if spent >= 30 or finished:
            self.record = self.stats.add(1 if finished else 0, spent / 60) or self.record

    def reset(self):
        if getattr(self, "phase", "idle") == "work":
            self._log_focus(False)
        self.phase = "idle"
        self.running = False
        self.end = None
        self.remaining = self.work * 60
        self.done_cycle = 0

    def total(self):
        return {"work": self.work, "short": self.short, "long": self.long, "idle": self.work}[self.phase] * 60

    def left(self):
        return max(0, self.end - time.monotonic()) if self.running else self.remaining

    def toggle(self):
        if self.running:
            self.remaining = self.left()
            self.running = False
        else:
            if self.phase == "idle":
                self.phase = "work"
                self.remaining = self.work * 60
            self.end = time.monotonic() + self.remaining
            self.running = True

    def skip(self):
        if self.phase == "idle":
            return None
        return self.advance(finished=False)

    def advance(self, finished=True):
        if self.phase == "work":
            self._log_focus(finished)
            self.done_cycle += 1
            self.phase = "long" if self.done_cycle % self.every == 0 else "short"
            ev = "rest"
        else:
            self.phase = "work"
            ev = "work"
        self.remaining = self.total()
        self.end = time.monotonic() + self.remaining
        self.running = True
        return ev

    def check(self):
        if self.running and time.monotonic() >= self.end:
            return self.advance()
        return None

    def round_no(self):
        return self.done_cycle % self.every + 1


PANEL_CSS = f"""
#card {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2c1b47, stop:1 {UI_BG});
         border: 2px solid #4a3172; border-radius: 22px; }}
QLabel {{ color: {UI_TEXT}; background: transparent; }}
#title {{ font: 600 11pt "Segoe UI"; }}
#small {{ color: {UI_MUTED}; font: 9pt "Segoe UI"; }}
#val {{ font: 600 11pt "Segoe UI"; min-width: 34px; qproperty-alignment: AlignCenter; }}
QPushButton {{ background: {UI_CARD}; color: {UI_TEXT}; border: none; border-radius: 13px;
              padding: 8px 12px; font: 10pt "Segoe UI"; }}
QPushButton:hover {{ background: #47316e; }}
QPushButton:pressed {{ background: #563c84; padding-top: 10px; padding-bottom: 6px; }}
#step {{ padding: 2px 0; min-width: 28px; max-width: 28px; min-height: 26px; border-radius: 9px;
         font: 600 12pt "Segoe UI"; }}
#close {{ background: transparent; color: {UI_MUTED}; font: 14pt "Segoe UI"; padding: 0 6px; }}
#close:hover {{ color: {UI_TEXT}; background: transparent; }}
#tab {{ background: {UI_CARD}; color: {UI_MUTED}; font: 9pt "Segoe UI"; padding: 4px 10px; border-radius: 10px; }}
#tab:hover {{ color: {UI_TEXT}; }}
"""


def main_btn_css(col, hover):
    return (f"QPushButton {{ background: {col}; color: #241000; font: 600 11pt 'Segoe UI';"
            f" padding: 9px 24px; border-radius: 13px; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
            f"QPushButton:pressed {{ padding-top: 11px; padding-bottom: 7px; }}")


class Ring(QWidget):
    """кольцо прогресса, по которому летит маленький дракончик."""
    SIZE = 236

    def __init__(self, pomo):
        super().__init__()
        self.pomo = pomo
        self.setFixedSize(self.SIZE, self.SIZE)
        self.trail = []          # искорки: [x, y, рождение]
        self.mood = None         # временная эмоция: (eyes, до какого времени)
        self.pop = 0             # «подпрыгивание» цифр
        self.frames = {}

    def react(self, eyes, sec=1.2):
        self.mood = (eyes, time.monotonic() + sec)
        self.pop = time.monotonic()

    def sprite(self, eyes, wings, mirror):
        key = (eyes, wings, mirror)
        if key not in self.frames:
            img = grid_image(make_frame(eyes, wings, 0, 0, None))
            self.frames[key] = img.mirrored(True, False) if mirror else img
        return self.frames[key]

    def paintEvent(self, e):
        P = self.pomo
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.SIZE / 2, self.SIZE / 2)
        r = 92
        rest = P.phase in ("short", "long")
        col_a, col_b = (QColor("#3fdc7c"), QColor("#b6f56a")) if rest else (QColor(UI_ORANGE), QColor("#ffc04a"))
        tot = P.total()
        prog = 0 if P.phase == "idle" else max(0, min(1, 1 - P.left() / tot))
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)

        # мягкое свечение позади
        pulse = (math.sin(now * 2.4) + 1) / 2 if P.running else 0
        glow = QRadialGradient(c, r + 26)
        gc = QColor(col_a)
        gc.setAlpha(int(30 + 40 * pulse))
        glow.setColorAt(.72, QColor(0, 0, 0, 0))
        glow.setColorAt(.86, gc)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(c, r + 26, r + 26)

        # дорожка и деления
        p.setPen(QPen(QColor(UI_CARD), 14, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)
        p.setPen(QPen(QColor(255, 255, 255, 40), 2, Qt.SolidLine, Qt.RoundCap))
        for i in range(12):
            a = math.radians(i * 30)
            p.drawLine(c + QPointF(math.sin(a) * (r - 4), -math.cos(a) * (r - 4)),
                       c + QPointF(math.sin(a) * (r + 4), -math.cos(a) * (r + 4)))

        # дуга прогресса с градиентом
        if prog > 0:
            cg = QConicalGradient(c, 90)
            cg.setColorAt(0, col_b)
            cg.setColorAt(1, col_a)
            p.setPen(QPen(QBrush(cg), 14, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 90 * 16, int(-prog * 360 * 16))

        # позиция дракончика на кольце
        ang = -math.pi / 2 + prog * 2 * math.pi
        hx, hy = c.x() + math.cos(ang) * r, c.y() + math.sin(ang) * r
        if P.running and (not self.trail or now - self.trail[-1][2] > .07):
            self.trail.append([hx + random.uniform(-3, 3), hy + random.uniform(-3, 3), now])
        self.trail = [t for t in self.trail if now - t[2] < .9]
        p.setPen(Qt.NoPen)
        for (tx, ty, born) in self.trail:
            k = 1 - (now - born) / .9
            sc = QColor(col_b)
            sc.setAlpha(int(200 * k))
            p.setBrush(sc)
            p.drawEllipse(QPointF(tx, ty - (1 - k) * 8), 2.6 * k + .6, 2.6 * k + .6)

        # эмоция и взмахи крыльев
        if self.mood and now < self.mood[1]:
            eyes = self.mood[0]
        elif P.phase == "idle":
            eyes = "blink" if int(now * 10) % 37 == 0 else "open"
        elif not P.running:
            eyes = "closed"
        elif rest:
            eyes = "happy"
        else:
            eyes = "blink" if int(now * 10) % 41 == 0 else "open"
        wings = "fold" if eyes == "closed" else ("up" if int(now * (8 if P.running else 3)) % 2 else "down")
        mirror = math.cos(ang + math.pi / 2) > 0     # хвост позади по ходу движения
        img = self.sprite(eyes, wings, mirror)
        s = 1.55
        bob = math.sin(now * 3) * 2.5 if P.running or P.phase == "idle" else 0
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        w, h = img.width() * s, img.height() * s
        p.drawImage(QRectF(hx - w / 2, hy - h * .62 + bob, w, h), img)

        # время
        left = P.left()
        m, sec = divmod(int(math.ceil(left)), 60)
        f = QFont("Segoe UI", 30, QFont.DemiBold)
        k = max(0, 1 - (now - self.pop) / .35)
        f.setPointSizeF(30 + 5 * math.sin(k * math.pi))
        p.setFont(f)
        p.setPen(col_a if P.phase != "idle" else QColor(UI_TEXT))
        p.drawText(QRectF(0, c.y() - 34, self.SIZE, 50), Qt.AlignCenter, f"{m:02d}:{sec:02d}")
        names = {"idle": "можно начинать", "work": "фокус", "short": "короткий отдых", "long": "длинный отдых"}
        sub = names[P.phase] + ("" if P.running or P.phase == "idle" else " · пауза")
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(UI_MUTED))
        p.drawText(QRectF(0, c.y() + 14, self.SIZE, 22), Qt.AlignCenter, sub)


class Tomatoes(QWidget):
    """помидорки текущего круга."""

    def __init__(self, pomo):
        super().__init__()
        self.pomo = pomo
        self.setFixedHeight(26)

    def paintEvent(self, e):
        P = self.pomo
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = P.every
        done = P.done_cycle % n
        if P.phase == "long":
            done = n
        gap = 26
        x0 = self.width() / 2 - gap * (n - 1) / 2
        for i in range(n):
            cx, cy = x0 + i * gap, 13
            cur = i == done and P.phase == "work"
            rad = 7 + (1.2 * (math.sin(now * 5) + 1) / 2 if cur and P.running else 0)
            if i < done:
                g = QRadialGradient(QPointF(cx - 2, cy - 3), 10)
                g.setColorAt(0, QColor("#ff9a8a"))
                g.setColorAt(1, QColor("#e8402f"))
                p.setBrush(QBrush(g))
                p.setPen(QPen(QColor("#2a1840"), 1.5))
                p.drawEllipse(QPointF(cx, cy), rad, rad)
                p.setPen(QPen(QColor("#56d12e"), 2.2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(cx - 3, cy - 7), QPointF(cx + 3, cy - 7))
                p.drawLine(QPointF(cx, cy - 9), QPointF(cx, cy - 6))
            else:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(UI_ORANGE) if cur else QColor("#5a4380"), 2, Qt.DashLine if cur else Qt.SolidLine))
                p.drawEllipse(QPointF(cx, cy), rad, rad)


class StatsView(QWidget):
    """вкладка статистики: карточки и график за 7 дней с дракончиком на самом высоком столбике."""
    DAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

    def __init__(self, stats):
        super().__init__()
        self.stats = stats
        self.shown = time.monotonic()
        self.setMinimumHeight(420)
        self.frames = {}

    def restart(self):
        self.shown = time.monotonic()
        self.update()

    def sprite(self, eyes, wings):
        key = (eyes, wings)
        if key not in self.frames:
            self.frames[key] = grid_image(make_frame(eyes, wings, 0, 0, None))
        return self.frames[key]

    def card(self, p, rect, big, small, accent):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(UI_CARD))
        p.drawRoundedRect(rect, 14, 14)
        p.setPen(QColor(accent))
        p.setFont(QFont("Segoe UI", 17, QFont.DemiBold))
        p.drawText(QRectF(rect.left() + 12, rect.top() + 6, rect.width() - 20, 30), Qt.AlignLeft | Qt.AlignVCenter, big)
        p.setPen(QColor(UI_MUTED))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(rect.left() + 12, rect.top() + 36, rect.width() - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, small)

    def paintEvent(self, e):
        S = self.stats
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W = self.width()
        t = min(1.0, (now - self.shown) / .7)
        ease = 1 - (1 - t) ** 3

        today = S.day()
        tp, tm = S.total()
        streak = S.streak()
        gap, cw, ch = 10, (W - 10) / 2, 60
        cards = [
            (f"{today['pomos']}", f"{plural(today['pomos'], 'помидорка', 'помидорки', 'помидорок')} сегодня", UI_ORANGE),
            (f"{int(today['minutes'])} мин", "фокуса сегодня", UI_ORANGE),
            (f"{streak} {plural(streak, 'день', 'дня', 'дней')}", "подряд", UI_GREEN),
            (f"{S.week()}", "за 7 дней", UI_TEXT),
            (f"{S.best()}", "рекорд дня", UI_TEXT),
            (f"{tp} · {tm / 60:.1f} ч".replace(".", ","), "всего", UI_TEXT),
        ]
        for i, (big, small, acc) in enumerate(cards):
            r = QRectF((i % 2) * (cw + gap), (i // 2) * (ch + gap), cw, ch)
            # карточки выезжают по очереди
            k = max(0.0, min(1.0, (now - self.shown - i * .05) / .3))
            p.setOpacity(k)
            self.card(p, r.translated(0, (1 - k) * 10), big, small, acc)
        p.setOpacity(1)

        # график за 7 дней
        top = 3 * (ch + gap) + 14
        base = self.height() - 26
        days = S.last(7)
        mx = max([v["pomos"] for _, v in days] + [1])
        bw = (W - 6 * 12) / 7
        p.setFont(QFont("Segoe UI", 8))
        best_i = max(range(7), key=lambda i: (days[i][1]["pomos"], i))
        tops = []
        for i, (d, v) in enumerate(days):
            x = i * (bw + 12)
            full = (base - top - 40) * v["pomos"] / mx
            h = max(4.0, full * ease) if v["pomos"] else 4.0
            r = QRectF(x, base - h, bw, h)
            is_today = i == 6
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            if is_today:
                g.setColorAt(0, QColor("#ffc04a"))
                g.setColorAt(1, QColor(UI_ORANGE))
            else:
                g.setColorAt(0, QColor("#a07ae0"))
                g.setColorAt(1, QColor("#5b3596"))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(r, 6, 6)
            if v["pomos"]:
                p.setPen(QColor(UI_TEXT))
                p.drawText(QRectF(x, base - h - 18, bw, 16), Qt.AlignCenter, str(v["pomos"]))
            p.setPen(QColor(UI_TEXT) if is_today else QColor(UI_MUTED))
            p.drawText(QRectF(x, base + 4, bw, 16), Qt.AlignCenter, self.DAYS[d.weekday()])
            tops.append((x + bw / 2, base - h))

        # дракончик сидит на самом высоком столбике (или спит, если пусто)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        if days[best_i][1]["pomos"] == 0:
            img = self.sprite("closed", "fold")
            sx, sy = W / 2, base
            p.setPen(QColor(UI_MUTED))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(0, top + 6, W, 20), Qt.AlignCenter, "пока пусто. первая помидорка впереди.")
        else:
            img = self.sprite("happy" if int(now * 1.5) % 4 == 0 else "open", "up" if int(now * 6) % 2 else "down")
            sx, sy = tops[best_i]
            sy += math.sin(now * 3) * 1.5
        s = 1.2
        w, h = img.width() * s, img.height() * s
        p.drawImage(QRectF(sx - w / 2, sy - h * .93, w, h), img)


class Panel(QWidget):
    def __init__(self, pomo, on_event):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.pomo = pomo
        self.on_event = on_event     # сообщает дракону: start / pause / reset / skip / rest / work
        self.setStyleSheet(PANEL_CSS)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        card = QFrame(objectName="card")
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 12, 18, 16)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.title = title = QLabel(f"{PET_NAME} · помодоро", objectName="title")
        close = QPushButton("×", objectName="close")
        close.clicked.connect(self.close_anim)
        self.tab = QPushButton("статистика", objectName="tab")
        self.tab.clicked.connect(self.switch)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.tab)
        head.addWidget(close)
        lay.addLayout(head)

        self.stack = QStackedWidget()
        page = QWidget()
        tl = QVBoxLayout(page)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)

        self.ring = Ring(pomo)
        tl.addWidget(self.ring, 0, Qt.AlignHCenter)
        self.tomatoes = Tomatoes(pomo)
        tl.addWidget(self.tomatoes)

        row = QHBoxLayout()
        self.main = QPushButton("старт")
        self.main.clicked.connect(self.toggle)
        skip = QPushButton("пропустить")
        skip.clicked.connect(self.skip)
        reset = QPushButton("сброс")
        reset.clicked.connect(self.reset)
        row.addWidget(self.main)
        row.addWidget(skip)
        row.addWidget(reset)
        tl.addLayout(row)

        tl.addSpacing(4)
        self.vals = {}
        for key, label, lo, hi in (("work", "работа", 5, 90), ("short", "отдых", 1, 30),
                                   ("long", "длинный отдых", 5, 60)):
            r = QHBoxLayout()
            r.addWidget(QLabel(label, objectName="small"))
            r.addStretch()
            minus = QPushButton("−", objectName="step")
            val = QLabel("", objectName="val")
            plus = QPushButton("+", objectName="step")
            step = 5 if key != "short" else 1
            minus.clicked.connect(lambda _=0, k=key, s=-step, lo=lo, hi=hi: self.change(k, s, lo, hi))
            plus.clicked.connect(lambda _=0, k=key, s=step, lo=lo, hi=hi: self.change(k, s, lo, hi))
            r.addWidget(minus)
            r.addWidget(val)
            r.addWidget(QLabel("мин", objectName="small"))
            r.addWidget(plus)
            tl.addLayout(r)
            self.vals[key] = val
        self.footer = QLabel("", objectName="small")
        self.footer.setAlignment(Qt.AlignCenter)
        self.footer.setWordWrap(True)
        tl.addWidget(self.footer)
        self.stats_view = StatsView(pomo.stats)
        self.stack.addWidget(page)
        self.stack.addWidget(self.stats_view)
        lay.addWidget(self.stack)
        self.setFixedWidth(330)
        self._drag = None
        self._anims = []
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.animate)
        self.refresh()

    # --- плавное появление и исчезновение
    def open_at(self, x, y):
        self.refresh()
        self.setWindowOpacity(0)
        self.move(x, y + 18)
        self.show()
        self.raise_()
        self.activateWindow()
        a1 = QPropertyAnimation(self, b"windowOpacity", self)
        a1.setDuration(220)
        a1.setStartValue(0.0)
        a1.setEndValue(1.0)
        a2 = QPropertyAnimation(self, b"pos", self)
        a2.setDuration(260)
        a2.setStartValue(QPoint(x, y + 18))
        a2.setEndValue(QPoint(x, y))
        a2.setEasingCurve(QEasingCurve.OutBack)
        self._anims = [a1, a2]
        for a in self._anims:
            a.start()
        self.anim_timer.start(33)
        self.ring.react("happy", .8)

    def close_anim(self):
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(160)
        a.setStartValue(self.windowOpacity())
        a.setEndValue(0.0)
        a.finished.connect(self._closed)
        self._anims = [a]
        a.start()

    def _closed(self):
        self.hide()
        self.anim_timer.stop()
        self.setWindowOpacity(1)

    def animate(self):
        if self.stack.currentIndex() == 0:
            self.ring.update()
            self.tomatoes.update()
        else:
            self.stats_view.update()

    def switch(self, to_stats=None):
        if not isinstance(to_stats, bool):          # из кнопки, переключить
            to_stats = self.stack.currentIndex() == 0
        self.stack.setCurrentIndex(1 if to_stats else 0)
        self.tab.setText("таймер" if to_stats else "статистика")
        if to_stats:
            self.stats_view.restart()

    # --- кнопки
    def change(self, key, step, lo, hi):
        setattr(self.pomo, key, max(lo, min(hi, getattr(self.pomo, key) + step)))
        if self.pomo.phase == "idle":
            self.pomo.remaining = self.pomo.work * 60
            self.ring.react("wow", .5)
        self.refresh()

    def toggle(self):
        was_idle = self.pomo.phase == "idle"
        self.pomo.toggle()
        ev = "pause" if not self.pomo.running else ("start" if was_idle else "resume")
        self.ring.react("happy" if ev != "pause" else "closed", 1.0)
        self.on_event(ev)
        self.refresh()

    def skip(self):
        ev = self.pomo.skip()
        if ev:
            self.ring.react("wow", 1.0)
            self.on_event(ev)
        self.refresh()

    def reset(self):
        self.pomo.reset()
        self.ring.react("wow", 1.0)
        self.on_event("reset")
        self.refresh()

    def refresh(self):
        P = self.pomo
        rest = P.phase in ("short", "long")
        self.main.setText("пауза" if P.running else ("старт" if P.phase == "idle" else "дальше"))
        self.main.setStyleSheet(main_btn_css(UI_GREEN, "#7be35a") if rest
                                else main_btn_css(UI_ORANGE, "#ff9433"))
        for k, lab in self.vals.items():
            lab.setText(str(getattr(P, k)))
        n = P.done_total
        self.footer.setText(f"сегодня помидорок: {n}" if n else "длинный отдых после каждой 4-й помидорки")
        self.ring.update()
        self.tomatoes.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


# ================================================================= дракончик
class StickyNote(QWidget):
    """записка от Сливы на рабочем столе. клик убирает её."""
    COLORS = [("#fff3a6", "#f3df6e"), ("#eadcff", "#cdb6f5"), ("#ffd9c2", "#f6b48e")]

    def __init__(self, text, on_close):
        super().__init__(None, base_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.text = voice(text)
        self.on_close = on_close
        self.angle = random.uniform(-6, 6)
        self.col = random.choice(self.COLORS)
        self.born = time.monotonic()
        self.dying = None
        self.setFixedSize(200, 150)
        self.t = QTimer(self)
        self.t.timeout.connect(self.anim)
        self.t.start(33)

    def anim(self):
        now = time.monotonic()
        if self.dying and now - self.dying > .3:
            self.t.stop()
            self.close()
            self.on_close(self)
            return
        if now - self.born < .5 or self.dying:
            self.update()

    def paintEvent(self, e):
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        k = min(1, (now - self.born) / .35)
        sc = .6 + .4 * (1 - (1 - k) ** 3) + .06 * math.sin(k * math.pi)
        if self.dying:
            d = min(1, (now - self.dying) / .3)
            sc *= 1 - .5 * d
            p.setOpacity(1 - d)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self.angle)
        p.scale(sc, sc)
        r = QRectF(-80, -52, 160, 104)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 10, 50, 60))
        p.drawRoundedRect(r.translated(3, 4), 4, 4)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(self.col[0]))
        g.setColorAt(1, QColor(self.col[1]))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 4, 4)
        p.setBrush(QColor(255, 255, 255, 120))
        p.drawRect(QRectF(-26, -60, 52, 16))   # скотч
        f = QFont("Segoe Print", 9)
        if not QFontInfo(f).family().lower().startswith("segoe print"):
            f = QFont("Comic Sans MS", 9)
        p.setFont(f)
        p.setPen(QColor("#3a2350"))
        p.drawText(r.adjusted(12, 12, -12, -22), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.text)
        p.setFont(QFont(f.family(), 8))
        p.drawText(r.adjusted(12, 0, -10, -6), Qt.AlignRight | Qt.AlignBottom, PET_NAME)

    def mousePressEvent(self, e):
        if not self.dying:
            self.dying = time.monotonic()
            self.t.start(33)


SETUP_CSS = f"""
#card {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2c1b47, stop:1 {UI_BG});
         border: 2px solid #4a3172; border-radius: 22px; }}
QLabel {{ color: {UI_TEXT}; background: transparent; }}
#h1 {{ font: 600 15pt "Segoe UI"; }}
#sub {{ color: {UI_MUTED}; font: 9pt "Segoe UI"; }}
#q {{ color: {UI_TEXT}; font: 600 10pt "Segoe UI"; }}
QLineEdit {{ background: {UI_CARD}; color: {UI_TEXT}; border: 2px solid transparent; border-radius: 12px;
            padding: 8px 12px; font: 10pt "Segoe UI"; selection-background-color: {UI_ORANGE}; }}
QLineEdit:focus {{ border-color: {UI_ORANGE}; }}
QPushButton {{ background: {UI_CARD}; color: {UI_TEXT}; border: 2px solid transparent; border-radius: 12px;
              padding: 8px 10px; font: 10pt "Segoe UI"; }}
QPushButton:hover {{ background: #47316e; }}
QPushButton:checked {{ border-color: {UI_ORANGE}; background: #3d2760; }}
#mode {{ text-align: left; padding: 10px 12px; }}
#close {{ background: transparent; color: {UI_MUTED}; font: 14pt "Segoe UI"; padding: 0 6px; border: none; }}
"""


class Setup(QWidget):
    """знакомство: имя, род обращения, город, имя дракончика, характер."""

    def __init__(self, current, on_done, first=True):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.on_done = on_done
        self.setStyleSheet(SETUP_CSS)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        card = QFrame(objectName="card")
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 16, 22, 20)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self.face = QLabel()
        self.face.setFixedSize(92, 74)
        top.addWidget(self.face)
        tt = QVBoxLayout()
        tt.addWidget(QLabel("давай познакомимся" if first else "настройки", objectName="h1"))
        sub = QLabel("полминуты. потом всё можно поменять в меню, правый клик по дракончику.", objectName="sub")
        sub.setWordWrap(True)
        tt.addWidget(sub)
        top.addLayout(tt, 1)
        if not first:
            close = QPushButton("×", objectName="close")
            close.clicked.connect(self.close)
            top.addWidget(close, 0, Qt.AlignTop)
        lay.addLayout(top)

        def q(text):
            lay.addSpacing(4)
            lay.addWidget(QLabel(text, objectName="q"))

        q("как тебя зовут?")
        self.name = QLineEdit(current.get("name", ""))
        self.name.setPlaceholderText("имя или как тебя называть")
        lay.addWidget(self.name)

        q("как к тебе обращаться?")
        self.gender = self.segmented([("f", "она"), ("m", "он"), ("n", "без рода")], current.get("gender", "f"), lay)

        q("твой город, для погоды")
        self.city = QLineEdit(current.get("city", ""))
        self.city.setPlaceholderText("например, москва. пусто, если без погоды")
        lay.addWidget(self.city)

        q("как назовёшь меня?")
        self.pet = QLineEdit(current.get("pet", "Слива"))
        lay.addWidget(self.pet)

        q("какой у меня характер?")
        self.mode = {}
        row = QHBoxLayout()
        for key, title, desc in (("bold", "нахальный", "дерзит, подмигивает,\nоставляет записки"),
                                 ("calm", "спокойный", "только забота\nи помодоро")):
            b = QPushButton(f"{title}\n{desc}", objectName="mode")
            b.setCheckable(True)
            b.clicked.connect(lambda _=0, k=key: self.pick_mode(k))
            row.addWidget(b)
            self.mode[key] = b
        lay.addLayout(row)
        self.mode_key = current.get("mode", "bold")
        self.pick_mode(self.mode_key)

        lay.addSpacing(8)
        done = QPushButton("готово" if first else "сохранить")
        done.setStyleSheet(main_btn_css(UI_ORANGE, "#ff9433"))
        done.clicked.connect(self.finish)
        lay.addWidget(done)
        self.setFixedWidth(400)
        self._drag = None

        self.t = QTimer(self)
        self.t.timeout.connect(self.blink)
        self.t.start(400)

    def segmented(self, items, cur, lay):
        row = QHBoxLayout()
        btns = {}
        for key, label in items:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(key == cur)
            b.clicked.connect(lambda _=0, k=key: [x.setChecked(kk == k) for kk, x in btns.items()])
            row.addWidget(b)
            btns[key] = b
        lay.addLayout(row)
        return btns

    def pick_mode(self, key):
        self.mode_key = key
        for k, b in self.mode.items():
            b.setChecked(k == key)
        self.draw_face()

    def draw_face(self, blink=False):
        eyes = ("cool" if self.mode_key == "bold" else "happy") if not blink else "blink"
        img = grid_image(make_frame(eyes, "up", 0, 0, None))
        self.face.setPixmap(QPixmap.fromImage(img).scaled(img.width() * 2, img.height() * 2))

    def blink(self):
        if self.mode_key == "calm" and random.random() < .12:
            self.draw_face(True)
            QTimer.singleShot(160, self.draw_face)
        elif self.mode_key == "bold" and random.random() < .08:
            img = grid_image(make_frame("wink", "down", 0, 0, None))
            self.face.setPixmap(QPixmap.fromImage(img).scaled(img.width() * 2, img.height() * 2))
            QTimer.singleShot(500, self.draw_face)

    def finish(self):
        g = next(k for k, b in self.gender.items() if b.isChecked()) if any(
            b.isChecked() for b in self.gender.values()) else "n"
        d = load_settings() or {}
        if (d.get("city") or "").strip().lower() != self.city.text().strip().lower():
            d.pop("coords", None)
        d.update(name=self.name.text().strip() or "друг", gender=g, city=self.city.text().strip(),
                 pet=self.pet.text().strip() or "Слива", mode=self.mode_key)
        save_settings(d)
        apply_settings(d)
        self.t.stop()
        self.close()
        self.on_done()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


class Dragon(QWidget):
    TOP = 40       # место сверху под сердечко и «z»
    SCALE = 1

    def __init__(self, greet=True):
        super().__init__(None, base_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.W = int(CW * self.SCALE)
        self.H = int(CH + self.TOP)
        self.setFixedSize(self.W, self.H)

        self.work = QGuiApplication.primaryScreen().availableGeometry()
        self.floor = self.work.bottom() - int(self.TOP + (32 - Y0) * PIX)
        self.x = random.uniform(self.work.left(), self.work.right() - self.W)
        self.y = self.floor - 160
        self.vx = 0.0
        self.vy = 0.0
        self.tilt = 0.0
        self.facing = 1

        self.state = "hover"
        self.until = time.monotonic() + 3
        self.target = None
        self.happy_from = 0
        self.blink_at = time.monotonic() + random.uniform(2, 5)
        self.talk_until = 0
        self.alert_until = 0
        self.press = None
        self.dragging = False
        self.last_push = 0
        self.params = {}

        self.bubble = Bubble()
        self.bubble.on_click = self.hide_bubble
        self.bubble_until = 0

        self.pomo = Pomodoro()
        self.panel = Panel(self.pomo, self.pomo_event)

        self.weather = []
        self.weather_day = None
        self.next_phrase = time.monotonic() + random.uniform(*PHRASE_EVERY_MIN) * 60

        # хулиганства
        self.notes = []
        self.mood = ("open", 0)         # временное выражение: wink / cool / brow
        self.dodged = False
        self.drag_said = False
        self.peek_phase = 0
        self.sneeze_from = 0
        self.flip_from = 0
        self.next_prank = time.monotonic() + self.prank_gap()

        self.menu = QMenu()
        self.menu.setStyleSheet(
            f"QMenu {{ background: {UI_BG}; color: {UI_TEXT}; border: 1px solid #4a3172; "
            f"border-radius: 10px; padding: 6px; font: 10pt 'Segoe UI'; }}"
            f"QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}"
            f"QMenu::item:selected {{ background: {UI_CARD}; }}"
            f"QMenu::separator {{ height: 1px; background: #4a3172; margin: 4px 8px; }}")
        self.menu.addAction("помодоро", self.toggle_panel)
        self.menu.addAction("статистика", self.open_stats)
        self.menu.addAction("скажи что-нибудь", lambda: self.say(self.make_phrase()))
        self.menu.addAction("уложить спать", lambda: self.set_state("landing"))
        self.menu.addAction("настройки", self.open_setup)
        self.menu.addSeparator()
        self.menu.addAction("выход", QApplication.quit)

        self.move(int(self.x), int(self.y))
        self.show()
        z_bottom(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        if greet:
            QTimer.singleShot(2500, lambda: self.say(R("greet")))
        self.check_weather()
        self.wtimer = QTimer(self)
        self.wtimer.timeout.connect(self.check_weather)
        self.wtimer.start(60 * 60 * 1000)

    # ---------------- погода (раз в день, в фоне)
    def check_weather(self):
        if not WEATHER:
            return
        today = dt.date.today()
        if self.weather_day == today:
            return
        self.weather_day = today

        def job():
            try:
                data = fetch_weather()
                self.weather = weather_tips(data, dt.datetime.now())
                self.weather_fresh = True
            except Exception:
                self.weather_day = None  # попробуем через час
        threading.Thread(target=job, daemon=True).start()

    def make_phrase(self):
        if getattr(self, "weather_fresh", False) and self.weather:
            self.weather_fresh = False
            return self.weather[0]
        return pick_phrase(dt.datetime.now(), self.weather)

    # ---------------- речь
    def say(self, text, dur=None):
        if self.state in ("sleep", "landing") and self.alert_until == 0:
            self.set_state("happy")
        self.bubble.set_text(text)
        self.bubble.place_near(self.geometry(), self.work, self.head_x())
        self.bubble.show()
        if self.alert_until:
            z_top(self.bubble, True)
        else:
            z_bottom(self.bubble)
        now = time.monotonic()
        self.bubble_until = now + (dur or max(6, min(14, len(text) / 9)))
        self.talk_until = now + min(2.5, len(text) / 22)
        if self.state in ("fly", "chase"):
            self.set_state("hover", 6)

    def hide_bubble(self):
        self.bubble.hide()
        self.bubble_until = 0
        if self.alert_until:
            self.end_alert()

    # ---------------- помодоро
    def pomo_event(self, ev):
        P = self.pomo
        quick = {"start": "happy", "resume": "happy", "pause": "hover", "reset": "dizzy"}
        if ev in quick:
            st = quick[ev]
            self.set_state(st, 3) if st == "hover" else self.set_state(st)
            self.say(R(ev, work=P.work), 4)
            return
        if ev == "rest" and P.record:
            P.record = False
            text = R("record", n=f"{P.done_total} {plural(P.done_total, 'помидорка', 'помидорки', 'помидорок')}",
                     r=P.short if P.phase == "short" else P.long)
        elif ev == "rest":
            text = R("long", every=P.every, long=P.long) if P.phase == "long" else R("rest", short=P.short)
        else:
            text = R("work", k=P.round_no(), every=P.every)
        play_sound(ev)
        self.alert_until = time.monotonic() + 25
        z_top(self, True)
        self.set_state("alert")
        self.say(text, 25)

    def end_alert(self):
        self.alert_until = 0
        if DESKTOP_ONLY:
            z_top(self, False)
            z_top(self.bubble, False)
            z_bottom(self)
        self.set_state("hover", 3)

    def open_setup(self):
        cur = dict(name=USER_NAME, gender=GENDER, city=CITY_NAME, pet=PET_NAME, mode=MODE)
        self.setup = Setup(cur, self.setup_done, first=False)
        g = self.work
        self.setup.adjustSize()
        self.setup.move(g.center().x() - self.setup.width() // 2, g.center().y() - self.setup.height() // 2)
        self.setup.show()
        self.setup.activateWindow()

    def setup_done(self):
        self.panel.title.setText(f"{PET_NAME} · помодоро")
        self.weather_day = None
        self.check_weather()
        self.set_state("happy")
        self.say(R("hello"), 6)

    def open_stats(self):
        if not self.panel.isVisible():
            self.toggle_panel()
        self.panel.switch(True)

    def toggle_panel(self):
        if self.panel.isVisible():
            self.panel.close_anim()
            return
        self.panel.refresh()
        self.panel.adjustSize()
        g = self.geometry()
        pw, ph = self.panel.width(), self.panel.height()
        x = g.right() + 4 if g.right() + pw < self.work.right() else g.left() - pw - 4
        y = max(self.work.top(), min(g.bottom() - ph, self.work.bottom() - ph))
        self.panel.open_at(x, y)

    # ---------------- состояния
    def set_state(self, st, dur=None):
        now = time.monotonic()
        self.state = st
        if st == "hover":
            self.until = now + (dur or random.uniform(2, 6))
        elif st == "fly":
            w = self.work
            self.target = (random.uniform(w.left(), w.right() - self.W),
                           random.uniform(w.top() + 30, self.floor - 40))
            self.until = now + 15
        elif st == "chase":
            self.until = now + 6
        elif st == "landing":
            self.until = now + 30
        elif st == "sleep":
            self.until = now + random.uniform(25, 60)
        elif st == "happy":
            self.until = now + 1.4
            self.happy_from = now
        elif st == "dizzy":
            self.until = now + .9
        elif st == "alert":
            w = self.work
            self.target = (w.center().x() - self.W / 2, w.top() + w.height() * .55)
            self.happy_from = now
        elif st == "dodge":
            c = QCursor.pos()
            ang = math.atan2(self.y + self.H / 2 - c.y(), self.x + self.W / 2 - c.x()) + random.uniform(-.6, .6)
            self.target = self.clamp(self.x + math.cos(ang) * 190, self.y + math.sin(ang) * 140)
            self.until = now + 2
        elif st == "peek":
            self.peek_side = random.choice((-1, 1))
            w = self.work
            self.peek_phase = 1
            self.target = ((w.left() - self.W - 20) if self.peek_side < 0 else (w.right() + 20),
                           random.uniform(w.top() + 60, self.floor - 60))
            self.until = now + 20
        elif st == "sneeze":
            self.sneeze_from = now
            self.until = now + 2.2
        elif st == "note":
            w = self.work
            self.target = (random.uniform(w.left() + 40, w.right() - self.W - 40),
                           random.uniform(w.top() + 60, self.floor - 80))
            self.until = now + 12
        elif st == "sit":
            self.until = now + 45
        elif st == "flip":
            self.flip_from = now
            self.until = now + 4

    # ---------------- хулиганства
    @staticmethod
    def prank_gap():
        lo, hi = random.choice(((3, 10), (10, 25), (25, 60)))   # по-разному
        return random.uniform(lo, hi) * 60

    def set_mood(self, eyes, sec):
        self.mood = (eyes, time.monotonic() + sec)

    def calm(self):
        P = self.pomo
        return P.running and P.phase == "work"

    def prank(self):
        options = ["note", "peek", "sneeze", "cool", "wink", "motion", "flip"]
        if self.panel.isVisible():
            options += ["sit", "sit"]
        if len(self.notes) >= 3:
            options.remove("note")
        kind = random.choice(options)
        if kind == "cool":
            self.set_mood("cool", 6)
            self.set_state("hover", 6)
            self.say(random.choice(COOL), 5)
        elif kind == "wink":
            self.set_mood("wink", 1.5)
            self.set_state("hover", 3)
        elif kind == "sneeze":
            self.set_state("sneeze")
        elif kind == "motion":
            self.set_mood("brow", 4)
            self.set_state("hover", 9)
            self.say(f"резолюция дня: «{random.choice(MOTIONS)}» у тебя 30 секунд на аргумент. я засекаю.", 9)
        elif kind == "flip":
            self.set_state("flip")
        else:
            self.set_state(kind)

    def drop_note(self):
        n = StickyNote(random.choice(NOTES), self.note_closed)
        n.move(int(self.x + self.W / 2 - n.width() / 2), int(self.y + self.H * .55))
        n.show()
        z_bottom(n)
        self.notes.append(n)
        line = random.choice(NOTE_DROP)
        if line:
            self.say(line, 4)
        self.set_mood("wink", 1.2)

    def note_closed(self, n):
        if n in self.notes:
            self.notes.remove(n)
        line = random.choice(NOTE_GONE)
        if line and self.state not in ("sleep", "alert") and not self.bubble.isVisible() and not self.calm():
            self.say(line, 3)

    def choose_next(self):
        h = dt.datetime.now().hour
        P = self.pomo
        focus = P.running and P.phase == "work"      # во время работы ведёт себя тише
        rest = P.running and P.phase in ("short", "long")
        sleepy = .35 if (h >= 23 or h < 7) else .15
        if focus:
            weights = (("landing", .3), ("fly", .25), ("hover", .45))
        elif rest:
            weights = (("chase", .35), ("fly", .45), ("hover", .2))
        else:
            weights = (("landing", sleepy), ("fly", .5), ("chase", .12), ("hover", .38 - sleepy))
        r = random.random()
        for st, w in weights:
            r -= w
            if r <= 0:
                self.set_state(st)
                return
        self.set_state("hover")

    def move_towards(self, tx, ty, speed):
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        if d <= speed:
            self.x, self.y = tx, ty
            self.vx = self.vy = 0
            return True
        self.vx = dx / d * speed
        self.vy = dy / d * speed
        if abs(dx) > 4:
            self.facing = 1 if dx > 0 else -1
        self.x += self.vx
        self.y += self.vy
        return False

    def clamp(self, x, y):
        w = self.work
        return (min(max(x, w.left() - self.W * .2), w.right() - self.W * .8),
                min(max(y, w.top() - self.TOP * self.SCALE), self.floor))

    # ---------------- мышь
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press = (e.globalPosition().toPoint(), QPoint(int(self.x), int(self.y)))
            self.dragging = False
        elif e.button() == Qt.RightButton:
            self.menu.popup(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if not self.press:
            return
        p0, w0 = self.press
        d = e.globalPosition().toPoint() - p0
        if not self.dragging and abs(d.x()) + abs(d.y()) > 5:
            self.dragging = True
            self.state = "drag"
            if PRANKS and not self.calm() and random.random() < .5 and not self.bubble.isVisible():
                self.say(random.choice(DRAG), 3)
        if self.dragging:
            self.x, self.y = self.clamp(w0.x() + d.x(), w0.y() + d.y())

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self.press:
            return
        if self.dragging:
            self.set_state("dizzy")
        elif self.alert_until:
            self.hide_bubble()
            self.set_state("happy")
        elif (PRANKS and not self.dodged and not self.calm() and not self.panel.isVisible()
              and self.state not in ("sleep", "landing") and random.random() < .22):
            self.dodged = True                       # увернулся, со второго раза сдастся
            self.set_mood("wink", 1.5)
            self.set_state("dodge")
            self.say(random.choice(DODGE), 2.5)
        else:
            if self.dodged and not self.panel.isVisible():
                self.say(random.choice(GIVE_UP), 2.5)
            self.dodged = False
            self.set_state("happy")
            self.toggle_panel()
        self.press = None
        self.dragging = False
        if DESKTOP_ONLY and not self.alert_until:
            z_bottom(self)

    # ---------------- главный цикл
    def tick(self):
        now = time.monotonic()
        st = self.state
        fs, fb, fa = 5.0, .35, .55          # частота, середина и размах взмаха
        bob = math.sin(now * 2.2) * 4
        eyes = "open"
        fold = False
        self.vx = self.vy = 0 if st not in ("fly", "chase", "landing", "alert") else self.vx

        if st == "hover":
            if now > self.until:
                self.choose_next()
        elif st == "fly":
            fs, fb, fa = 8, .2, .8
            if self.move_towards(*self.target, FLY_SPEED) or now > self.until:
                self.set_state("hover" if random.random() < .7 else "fly")
        elif st == "chase":
            fs, fb, fa = 11, .15, .85
            c = QCursor.pos()
            tx, ty = self.clamp(c.x() - self.W / 2, c.y() - self.H * .35)
            if self.move_towards(tx, ty, CHASE_SPEED):
                self.set_state("happy")
            elif now > self.until:
                self.set_state("hover")
        elif st == "landing":
            fs, fb, fa = 4, .4, .45
            if self.move_towards(self.x, self.floor, FLY_SPEED * .7) or now > self.until:
                self.set_state("sleep")
        elif st == "sleep":
            fold, eyes, bob = True, "closed", 0
            if now > self.until:
                self.set_state("happy")
        elif st == "happy":
            t = now - self.happy_from
            fs, fb, fa = 10, .2, .8
            bob = -abs(math.sin(t * 7)) * 14 * max(0, 1 - t / 1.4)
            eyes = "happy"
            if now > self.until:
                self.set_state("hover", 3)
        elif st == "dizzy":
            eyes = "wow"
            bob = math.sin(now * 30) * 3
            if now > self.until:
                self.set_state("hover", 2)
        elif st == "drag":
            eyes, fs, fb, fa = "wow", 13, .1, .9
        elif st == "dodge":
            fs, fb, fa = 16, .1, .9
            if self.move_towards(*self.target, CHASE_SPEED * 1.6) or now > self.until:
                self.set_state("hover", 3)
        elif st == "sneeze":
            t = now - self.sneeze_from
            eyes = "wow" if t < .7 else ("closed" if t < 1.0 else "brow")
            bob = -6 if .7 < t < 1.0 else 0
            if t > 1.0 and not getattr(self, "_sneezed", False):
                self._sneezed = True
                self.say(random.choice(SNEEZE), 3)
            if now > self.until:
                self._sneezed = False
                self.set_state("hover", 3)
        elif st == "peek":
            fs, fb, fa = 9, .2, .8
            w = self.work
            if self.peek_phase == 1:                         # улетел за край
                if self.move_towards(*self.target, FLY_SPEED * 1.6):
                    self.peek_phase = 2
                    self.peek_t = now + random.uniform(2, 4)
            elif self.peek_phase == 2 and now > self.peek_t:  # выглядывает
                self.peek_phase = 3
                self.target = ((w.left() - self.W * .5) if self.peek_side < 0 else (w.right() - self.W * .5),
                               self.target[1])
            elif self.peek_phase == 3:
                if self.move_towards(*self.target, FLY_SPEED):
                    self.peek_phase = 4
                    self.peek_t = now + random.uniform(4, 7)
                    self.facing = 1 if self.peek_side < 0 else -1
                    self.set_mood(random.choice(("brow", "wink")), 2.5)
                    self.say(random.choice(PEEK), 3)
            elif self.peek_phase == 4:
                self.facing = 1 if self.peek_side < 0 else -1
                c = QCursor.pos()
                near = math.hypot(c.x() - (self.x + self.W / 2), c.y() - (self.y + self.H / 2)) < 140
                if near or now > self.peek_t:
                    if near:
                        self.say(random.choice(CAUGHT), 2.5)
                        self.set_mood("wink", 1.5)
                    self.set_state("fly")
            if now > self.until:
                self.set_state("fly")
        elif st == "note":
            fs, fb, fa = 8, .2, .8
            if self.move_towards(*self.target, FLY_SPEED * 1.3) or now > self.until:
                self.drop_note()
                self.set_state("fly")
        elif st == "flip":
            t = now - self.flip_from
            eyes = "happy" if t > .5 else "wow"
            fs, fb, fa = 6, .3, .6
            if t > .6 and not getattr(self, "_flipsaid", False):
                self._flipsaid = True
                line = gtext(random.choice(FLIP))
                if line:
                    self.say(line.format(name=USER_NAME), 3.5)
            if now > self.until:
                self._flipsaid = False
                self.set_state("happy")
        elif st == "sit":
            if not self.panel.isVisible():
                self.set_state("hover", 2)
            else:
                g = self.panel.geometry()
                tx = g.center().x() + 40 - self.W / 2
                ty = g.top() - (self.TOP + (31 - Y0) * PIX) + 14
                if self.move_towards(tx, ty, FLY_SPEED * 1.5):
                    fold, bob = True, 0
                    if not getattr(self, "_sat", False):
                        self._sat = True
                        self.say("я тут посижу. не обращай внимания.", 3)
                    if int(now / 3) % 4 == 0:
                        eyes = "brow"
                else:
                    fs, fb, fa = 8, .2, .8
                if now > self.until:
                    self._sat = False
                    self.set_state("fly")
        elif st == "alert":
            fs, fb, fa = 10, .2, .8
            eyes = "happy" if int(now * 2) % 2 else "open"
            self.move_towards(*self.target, CHASE_SPEED * 1.4)
            if now > self.alert_until:
                self.bubble.hide()
                self.end_alert()

        target_tilt = max(-12, min(12, self.vy * 3))
        self.tilt += (target_tilt - self.tilt) * .12

        # куда смотрит: когда зависает, поворачивается к курсору
        c = QCursor.pos()
        if st in ("hover", "happy", "dizzy", "drag") and abs(c.x() - (self.x + self.W / 2)) > 60:
            self.facing = 1 if c.x() > self.x + self.W / 2 else -1
        hx = self.head_x()
        hy = self.y + self.TOP + (11.5 - Y0) * PIX
        dx, dy = c.x() - hx, c.y() - hy
        d = math.hypot(dx, dy) + 1
        k = min(1, d / 220)
        look = (dx / d * k, dy / d * k)

        # хулиганское выражение лица поверх обычного
        if eyes == "open" and now < self.mood[1]:
            eyes = self.mood[0]
        if (PRANKS and st == "hover" and eyes == "open" and d < 110 and random.random() < .004):
            self.set_mood(random.choice(("wink", "brow")), 1.4)

        # моргание
        blink = 1.0
        if now > self.blink_at:
            ph = (now - self.blink_at) / .18
            if ph >= 1:
                self.blink_at = now + random.uniform(2.5, 6)
            else:
                blink = abs(1 - 2 * ph)

        mouth = None
        if now < self.talk_until and eyes != "closed":
            mouth = "open" if int(now * 7) % 2 else None
        if eyes == "happy" and mouth is None:
            mouth = "open"

        self.params = dict(
            flap=fb + fa * math.sin(now * fs),
            fold=fold, bob=bob, tilt=self.tilt,
            tail=math.sin(now * (1.1 if fold else 2.0)),
            breath=math.sin(now * (1.3 if fold else 2.0)) * (1.5 if fold else .8),
            eyes=eyes, blink=blink, look=look if eyes != "closed" else (0, 0), mouth=mouth,
            mirror=self.facing > 0,
        )
        self.move(int(self.x), int(self.y))
        P = self.params
        lx = P["look"][0]
        sig = (P["eyes"], P["blink"] < .5, P["fold"], P["flap"] > .3, P["tail"] > 0,
               round(lx * 3), P["mouth"], int(round(P["bob"])), self.facing)
        if sig != getattr(self, "_sig", None) or st in ("happy", "alert", "sleep", "sneeze", "flip"):
            self._sig = sig
            self.update()

        # облачко
        if self.bubble.isVisible():
            self.bubble.place_near(self.geometry(), self.work, self.head_x())
            if now > self.bubble_until and not self.alert_until:
                self.bubble.hide()

        # за минуту до конца рабочей помидорки
        P = self.pomo
        if P.running and P.phase == "work" and P.left() <= 60:
            if getattr(self, "_warned", None) != P.end:
                self._warned = P.end
                self.say(R("minute"), 5)

        # хулиганства (во время рабочей помидорки ведёт себя прилично)
        if PRANKS and now > self.next_prank:
            if st in ("hover", "fly") and not self.calm() and not self.alert_until and not self.bubble.isVisible():
                self.prank()
                self.next_prank = now + self.prank_gap()
            else:
                self.next_prank = now + 90

        # фразочки (во время рабочей помидорки молчит)
        if now > self.next_phrase:
            if st in ("drag", "alert") or self.bubble.isVisible() or (P.running and P.phase == "work"):
                self.next_phrase = now + 60
            else:
                self.say(self.make_phrase())
                self.next_phrase = now + random.uniform(*PHRASE_EVERY_MIN) * 60

        # помодоро
        ev = self.pomo.check()
        if ev:
            self.pomo_event(ev)
        if self.panel.isVisible() and int(now * 4) != int((now - .034) * 4):
            self.panel.refresh()

        # держаться под окнами
        if DESKTOP_ONLY and not self.dragging and not self.alert_until and now - self.last_push > 2:
            z_bottom(self)
            if self.bubble.isVisible():
                z_bottom(self.bubble)
            for n in self.notes:
                z_bottom(n)
            self.last_push = now

        want = 100 if st == "sleep" else 33
        if self.timer.interval() != want:
            self.timer.setInterval(want)

    def head_x(self):
        return self.x + HEAD_X

    def paintEvent(self, e):
        p = QPainter(self)
        p.translate(0, self.TOP)
        p.save()
        if self.state == "flip":       # фигура: переворот вверх ногами и обратно
            t = time.monotonic() - self.flip_from
            k = min(1, t / .45) if t < 3.4 else max(0, 1 - (t - 3.4) / .45)
            p.translate(CW / 2, CH / 2)
            p.rotate(180 * (1 - (1 - k) ** 2))
            p.translate(-CW / 2, -CH / 2)
        if self.facing > 0:            # хвост всегда сзади
            p.translate(CW, 0)
            p.scale(-1, 1)
        draw_dragon(p, self.params)
        p.restore()
        now = time.monotonic()
        if self.state == "sneeze":
            t = now - self.sneeze_from - .7
            if 0 < t < 1.1:                     # огненный «апчхи»
                mx, my = HEAD_X, (16.5 - Y0) * PIX
                for i, col in enumerate(("#ffe27a", "#ff9b3d", "#ff5a2e", "#8a7a99")):
                    k = max(0, min(1, (t - i * .08) / .9))
                    if 0 < k < 1:
                        p.setOpacity(1 - k)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor(col))
                        for j in range(5):
                            a = j * 1.26 + i
                            rr = (6 + k * 26) * (1 + .15 * j % 2)
                            sz = PIX * (2 - k)
                            p.drawRect(QRectF(mx + math.cos(a) * rr - sz / 2, my + 10 + k * 18 + math.sin(a) * rr * .6,
                                              sz, sz))
                p.setOpacity(1)
        if self.state in ("happy", "alert"):
            t = (now - self.happy_from) % 1.4
            p.setOpacity(max(0, 1 - t / 1.4))
            if not hasattr(self, "_heart"):
                self._heart = grid_image(HEART)
            draw_pixels(p, self._heart, HEAD_X - 3.5 * PIX, -8 * PIX - t * 24, PIX)
            p.setOpacity(1)
        if self.state == "sleep":
            if not hasattr(self, "_zed"):
                self._zed = grid_image(ZED)
            for i in range(2):
                ph = (now / 2.6 + i / 2) % 1
                p.setOpacity(max(0, 1 - ph))
                draw_pixels(p, self._zed, HEAD_X + 5 * PIX + ph * 20, 2 * PIX - ph * 50, PIX - 1 + int(ph * 2))
            p.setOpacity(1)


def main():
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("desk.dragon.dragzy")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    holder = {}
    saved = load_settings()
    if saved:
        apply_settings(saved)
        holder["d"] = Dragon()
    else:
        def start():
            d = holder["d"] = Dragon(greet=False)
            QTimer.singleShot(1200, lambda: (d.set_state("happy"), d.say(R("hello"), 7)))
        cur = dict(name=USER_NAME if USER_NAME != "друг" else "", gender="f", city="", pet=PET_NAME, mode="bold")
        w = holder["setup"] = Setup(cur, start, first=True)
        w.adjustSize()
        g = QGuiApplication.primaryScreen().availableGeometry()
        w.move(g.center().x() - w.width() // 2, g.center().y() - w.height() // 2)
        w.show()
        w.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
