#!/usr/bin/env python3
"""
Renders docs/demo.gif: a terminal-style replay of a real Token Saver run.

The prompts and replies below are the actual text of a run in Claude Code 2.1.261 on
Windows 11 (threshold answered as 30k so a short session reaches it). It is a rendered
replay, not a screen capture. Needs Pillow:  pip install pillow && python docs/make_demo.py
"""
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 900, 560
PAD, TOP, LINE = 22, 52, 23
COLS = 84
BG, BAR = (13, 17, 23), (22, 27, 34)
DIM, TXT, YOU = (139, 148, 158), (230, 237, 243), (88, 166, 255)
OK, WARN, NOTE = (63, 185, 80), (210, 153, 34), (163, 113, 247)

SCRIPT = [
    ("title", "claude · first session with Token Saver"),
    ("type", "What does main.py print? One line."),
    ("out", NOTE, "ⓘ Token Saver: no notification threshold set yet. Reply with a number such as "
                  "100k (or two, like 150k,300k) to choose when a fresh session is offered, "
                  "or type: token-saver off"),
    ("out", TXT, "● It prints `1`."),
    ("type", "30k"),
    ("out", OK, "● Got it — I'll offer a fresh session when context hits 30k tokens. You can adjust "
                "it anytime with `token-saver 200k` or turn it off with `token-saver off`."),
    ("type", "Rename foo to bar in main.py, but keep the print call"),
    ("out", WARN, "● Context is at ~41k tokens. To save tokens, shall I continue this request in a "
                  "fresh session? (yes/no)"),
    ("type", "yes"),
    ("out", DIM, "  Write(.token-saver/handoff.md)\n"
                 "    ## Pending request\n"
                 "    Rename foo to bar in main.py, but keep the print call"),
    ("out", OK, "● Done. Type /clear, then say 'continue'."),
    ("rule", "new session · handoff loaded automatically"),
    ("title", "claude · fresh session"),
    ("type", "continue"),
    ("out", OK, "● Done. Renamed `foo` to `bar` in main.py on both the assignment and the print call."),
    ("hold", 3500),
]


def font(size):
    for name in ("CascadiaMono.ttf", "consola.ttf", "DejaVuSansMono.ttf", "Menlo.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT, SMALL = font(16), font(14)


def wrap(text, indent="  "):
    lines = []
    for para in text.split("\n"):
        lead = len(para) - len(para.lstrip(" "))
        lines += textwrap.wrap(para, COLS, subsequent_indent=" " * lead + indent,
                               drop_whitespace=False) or [""]
    return lines


def render(lines, title, cursor=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 36], fill=BAR)
    for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse([16 + i * 20, 12, 28 + i * 20, 24], fill=c)
    d.text((W / 2, 18), title, font=SMALL, fill=DIM, anchor="mm")
    visible = lines[-((H - TOP - 10) // LINE):]
    y = TOP
    for kind, color, text in visible:
        if kind == "rule":
            d.line([PAD, y + LINE // 2, W - PAD, y + LINE // 2], fill=(48, 54, 61))
            box = d.textbbox((W / 2, y + LINE // 2), f"  {text}  ", font=SMALL, anchor="mm")
            d.rectangle(box, fill=BG)
            d.text((W / 2, y + LINE // 2), text, font=SMALL, fill=DIM, anchor="mm")
        elif kind == "you":
            d.text((PAD, y), "> ", font=FONT, fill=YOU)
            d.text((PAD + d.textlength("> ", font=FONT), y), text, font=FONT, fill=TXT)
        else:
            d.text((PAD, y), text, font=FONT, fill=color)
        y += LINE
    if cursor and visible:
        kind, _, text = visible[-1]
        x = PAD + d.textlength(("> " if kind == "you" else "") + text, font=FONT)
        d.rectangle([x + 1, y - LINE + 2, x + 9, y - 4], fill=TXT)
    return img


def main():
    frames, lines, title = [], [], ""

    def shot(ms, cursor=False):
        frames.append((render(lines, title, cursor), ms))

    for step in SCRIPT:
        kind = step[0]
        if kind == "title":
            title = step[1]
        elif kind == "type":
            lines.append(("gap", None, ""))
            lines.append(("you", None, ""))
            shot(500, cursor=True)
            text = step[1]
            for i in range(2, len(text) + 2, 2):
                lines[-1] = ("you", None, text[:i])
                shot(45, cursor=True)
            shot(450, cursor=True)
        elif kind == "out":
            lines.append(("gap", None, ""))
            lines += [("out", step[1], t) for t in wrap(step[2])]
            shot(1500 + 22 * len(step[2]))
        elif kind == "rule":
            lines.append(("gap", None, ""))
            lines.append(("rule", None, step[1]))
            shot(1400)
        elif kind == "hold":
            shot(step[1])

    out = Path(__file__).with_name("demo.gif")
    palette = frames[-1][0].quantize(colors=48, dither=Image.Dither.NONE)
    images = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f, _ in frames]
    images[0].save(out, save_all=True, append_images=images[1:], optimize=True, loop=0,
                   duration=[ms for _, ms in frames], disposal=1)
    print(f"{out.name}: {len(frames)} frames, {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
