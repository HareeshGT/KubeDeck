"""ansi_terminal.py — renders a raw PTY byte stream in a Qt text widget the
way a terminal would, instead of dumping it as literal text.

A PTY doesn't send "lines of text". It sends a control stream: ``\\r`` to
rewind to the start of the line (that's how ``wget``/``curl``/``pip``/
``docker pull`` redraw a single progress bar in place), ``\\b`` for
backspace, ``ESC[...m`` for colours, ``ESC[K`` to erase to end of line,
``ESC]0;title BEL`` for the window title, ``ESC[?2004h`` for bracketed
paste, and so on. Inserted as plain text, a download shows hundreds of
progress lines and stray ``ESC[01;34m`` garbage.

This is deliberately NOT a full VT100/xterm emulator — there is no screen
grid, so full-screen programs that address the cursor (vim, less, top,
htop, nano) won't render properly. What it does handle is everything a
scrolling command-line session needs: carriage-return overwrites,
backspace, tabs, erase-in-line, delete-char, 16/256/true-colour SGR,
bold/italic/underline/inverse, ``clear``, and it silently swallows the
sequences it doesn't act on. It is *incremental*: an escape sequence
split across two network reads is held back and completed by the next
one, so the output is identical however the stream is chunked.

Two pieces:

* :class:`AnsiTokenizer` — pure Python, no Qt. Turns text into a list of
  simple tokens. Easy to unit-test.
* :class:`AnsiStreamRenderer` — applies those tokens to a QPlainTextEdit
  using its *own* QTextCursor, so the user's selection and scroll
  position are left alone while output streams in.
"""

import re

from PyQt5.QtGui import QColor, QFont, QTextCharFormat, QTextCursor


# ─── Tokenizer ────────────────────────────────────────────────────────

# Any C0 control (plus DEL) that is not TAB or LF. TAB and LF are ordinary
# content the renderer handles inside text runs.
_SPECIAL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# A complete CSI sequence: ESC [ params intermediates final
_CSI = re.compile(r"\x1b\[([0-?]*)([ -/]*)([@-~])")
# What an *unfinished* CSI can look like at the very end of a chunk.
_CSI_PARTIAL = re.compile(r"\x1b\[[0-?]*[ -/]*$")
# Bounds so a malformed/hostile stream can never make us buffer forever.
_MAX_CSI = 64
_MAX_STRING = 4096


class AnsiTokenizer:
    """Incrementally converts terminal text into tokens.

    Tokens (tuples):
      ("text", str)      printable text; may contain "\\n" and "\\t"
      ("cr",)            carriage return
      ("bs",)            backspace
      ("sgr", [ints])    select-graphic-rendition (colours/attributes)
      ("el", n)          erase in line (0=to end, 1=to start, 2=all)
      ("cuf", n)         cursor forward n
      ("cub", n)         cursor back n
      ("cha", n)         cursor to (1-based) column n
      ("dch", n)         delete n characters at the cursor
      ("clear",)         clear the whole display / scrollback
    """

    def __init__(self):
        self._pending = ""   # an escape sequence cut off by the end of a chunk

    def reset(self):
        self._pending = ""

    def feed(self, data: str):
        s = self._pending + data
        self._pending = ""
        out = []
        run = []     # current run of plain text, merged so big output stays cheap

        def flush():
            if run:
                out.append(("text", "".join(run)))
                run.clear()

        i, n = 0, len(s)
        while i < n:
            m = _SPECIAL.search(s, i)
            if m is None:
                run.append(s[i:])
                break
            j = m.start()
            if j > i:
                run.append(s[i:j])
            c = s[j]

            if c == "\r":
                if j + 1 < n and s[j + 1] == "\n":
                    run.append("\n")            # CRLF == LF (the common case)
                    i = j + 2
                else:
                    flush()
                    out.append(("cr",))
                    i = j + 1
            elif c == "\b":
                flush()
                out.append(("bs",))
                i = j + 1
            elif c == "\x1b":
                consumed = self._escape(s, j, out, flush)
                if consumed is None:            # incomplete: wait for more data
                    self._pending = s[j:]
                    break
                i = j + consumed
            else:
                # BEL and every other control character: drop silently.
                i = j + 1

        flush()
        return out

    # -- escape sequences -------------------------------------------------
    def _escape(self, s, j, out, flush):
        """Handle the sequence starting at s[j] == ESC. Returns how many
        characters it consumed, or None if the chunk ended mid-sequence."""
        n = len(s)
        if j + 1 >= n:
            return None
        k = s[j + 1]

        if k == "[":                                            # CSI
            m = _CSI.match(s, j)
            if m:
                self._csi(m.group(1), m.group(3), out, flush)
                return m.end() - j
            if _CSI_PARTIAL.match(s, j) and n - j <= _MAX_CSI:
                return None
            return 1                                            # junk: drop the ESC

        if k in "]PX^_":                                        # OSC / DCS / SOS / PM / APC
            end = self._string_end(s, j + 2)
            if end is None:
                return None if n - j <= _MAX_STRING else 1
            return end - j                                      # swallowed (e.g. window title)

        if k in "()*+#% ":                                      # 3-char sequences, e.g. ESC ( B
            return 3 if j + 2 < n else None

        return 2                                                # ESC 7, ESC =, ESC > ... ignored

    @staticmethod
    def _string_end(s, start):
        """Index just past the terminator (BEL or ESC \\) of an OSC-style
        string, or None if it hasn't arrived yet."""
        bel = s.find("\x07", start)
        st = s.find("\x1b\\", start)
        cands = [(p, w) for p, w in ((bel, 1), (st, 2)) if p != -1]
        if not cands:
            return None
        p, w = min(cands)
        return p + w

    @staticmethod
    def _csi(params, final, out, flush):
        if params and params[0] in "<=>?":                      # private modes (?2004h, ?25l ...)
            return
        nums = []
        for part in params.replace(":", ";").split(";"):
            try:
                nums.append(int(part) if part else None)
            except ValueError:
                nums.append(None)

        def arg(default):
            v = nums[0] if nums else None
            return default if v is None else v

        if final == "m":
            flush()
            out.append(("sgr", [0 if v is None else v for v in nums] or [0]))
        elif final == "K":
            flush()
            out.append(("el", arg(0)))
        elif final == "C":
            flush()
            out.append(("cuf", max(1, arg(1))))
        elif final == "D":
            flush()
            out.append(("cub", max(1, arg(1))))
        elif final == "G":
            flush()
            out.append(("cha", max(1, arg(1))))
        elif final == "P":
            flush()
            out.append(("dch", max(1, arg(1))))
        elif final == "J":
            v = arg(0)
            flush()
            if v in (2, 3):
                out.append(("clear",))
            elif v == 0:
                out.append(("el", 0))
        # Everything else (cursor up/down, scroll regions, title stack,
        # mode set/reset, ...) needs a real screen grid — ignored.


def plain_text(raw: str) -> str:
    """Flatten raw terminal output to what a person would read: escape
    sequences removed, ``\\r`` rewinds and backspaces applied, per line.
    Used to hand command output to the AI helper without control junk."""
    lines = []
    line = []      # list of chars; col tracks the cursor
    col = 0
    for kind, *rest in AnsiTokenizer().feed(raw):
        if kind == "text":
            for ch in rest[0]:
                if ch == "\n":
                    lines.append("".join(line))
                    line, col = [], 0
                elif col < len(line):
                    line[col] = ch
                    col += 1
                else:
                    line.extend(" " * (col - len(line)))
                    line.append(ch)
                    col += 1
        elif kind == "cr":
            col = 0
        elif kind == "bs":
            col = max(0, col - 1)
        elif kind == "el" and rest[0] == 0:
            del line[col:]
        elif kind == "clear":
            lines, line, col = [], [], 0
    lines.append("".join(line))
    return "\n".join(lines)


# ─── Renderer ─────────────────────────────────────────────────────────

# Dark-background-friendly 16-colour palette (index 0-7 normal, 8-15 bright).
_ANSI16 = [
    "#45475a", "#f38ba8", "#a6e3a1", "#f9e2af",
    "#89b4fa", "#f5c2e7", "#94e2d5", "#bac2de",
    "#585b70", "#f38ba8", "#a6e3a1", "#f9e2af",
    "#89b4fa", "#f5c2e7", "#94e2d5", "#cdd6f4",
]


def _color256(n: int) -> QColor:
    if n < 16:
        return QColor(_ANSI16[n])
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n // 6) % 6, n % 6
        lv = lambda v: 0 if v == 0 else 55 + 40 * v
        return QColor(lv(r), lv(g), lv(b))
    v = 8 + 10 * (n - 232)
    return QColor(v, v, v)


class AnsiStreamRenderer:
    """Feeds terminal output into a QPlainTextEdit.

    The renderer only ever writes on the *last* line of the document (a
    scrolling terminal never edits history) and remembers a cursor column
    there, so ``\\r``/backspace/erase can overwrite in place.
    """

    def __init__(self, edit, default_fg: QColor = None, default_bg: QColor = None,
                 max_lines: int = 10000):
        self._edit = edit
        self._doc = edit.document()
        self._tok = AnsiTokenizer()
        self._cur = QTextCursor(self._doc)   # private: never touches the user's selection
        self._col = 0
        self._default_fg = default_fg or QColor("#cdd6f4")
        self._default_bg = default_bg or QColor("#0d0d1a")
        self._reset_style()
        edit.setMaximumBlockCount(max_lines)    # bounded scrollback

    # -- style ------------------------------------------------------------
    def _reset_style(self):
        self._fg = self._bg = None
        self._bold = self._italic = self._underline = self._inverse = False
        self._rebuild_fmt()

    def _rebuild_fmt(self):
        fg, bg = self._fg, self._bg
        if self._inverse:
            fg, bg = (bg or self._default_bg), (fg or self._default_fg)
        fmt = QTextCharFormat()
        if fg is not None:
            fmt.setForeground(fg)
        if bg is not None:
            fmt.setBackground(bg)
        if self._bold:
            fmt.setFontWeight(QFont.Bold)
        if self._italic:
            fmt.setFontItalic(True)
        if self._underline:
            fmt.setFontUnderline(True)
        self._fmt = fmt

    def _sgr(self, params):
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self._fg = self._bg = None
                self._bold = self._italic = self._underline = self._inverse = False
            elif p == 1:
                self._bold = True
            elif p == 3:
                self._italic = True
            elif p == 4:
                self._underline = True
            elif p == 7:
                self._inverse = True
            elif p == 22:
                self._bold = False
            elif p == 23:
                self._italic = False
            elif p == 24:
                self._underline = False
            elif p == 27:
                self._inverse = False
            elif 30 <= p <= 37:
                self._fg = QColor(_ANSI16[p - 30])
            elif p == 39:
                self._fg = None
            elif 40 <= p <= 47:
                self._bg = QColor(_ANSI16[p - 40])
            elif p == 49:
                self._bg = None
            elif 90 <= p <= 97:
                self._fg = QColor(_ANSI16[8 + p - 90])
            elif 100 <= p <= 107:
                self._bg = QColor(_ANSI16[8 + p - 100])
            elif p in (38, 48):
                color = None
                if i + 2 < len(params) and params[i + 1] == 5:
                    color = _color256(max(0, min(255, params[i + 2])))
                    i += 2
                elif i + 4 < len(params) and params[i + 1] == 2:
                    r, g, b = (max(0, min(255, v)) for v in params[i + 2:i + 5])
                    color = QColor(r, g, b)
                    i += 4
                if color is not None:
                    if p == 38:
                        self._fg = color
                    else:
                        self._bg = color
            i += 1
        self._rebuild_fmt()

    # -- public -----------------------------------------------------------
    def clear(self):
        self._edit.clear()
        self._col = 0
        self._tok.reset()
        self._reset_style()

    def feed(self, data: str):
        tokens = self._tok.feed(data)
        if not tokens:
            return
        bar = self._edit.verticalScrollBar()
        # Only follow the output if the user is already at the bottom, so
        # scrolling up to read something isn't yanked away by new output.
        follow = bar.value() >= bar.maximum() - 2

        c = self._cur
        c.beginEditBlock()
        try:
            for tok in tokens:
                kind = tok[0]
                if kind == "text":
                    self._write(tok[1])
                elif kind == "cr":
                    self._col = 0
                elif kind == "bs":
                    self._col = max(0, self._col - 1)
                elif kind == "sgr":
                    self._sgr(tok[1])
                elif kind == "el":
                    self._erase_line(tok[1])
                elif kind == "cuf":
                    self._col += tok[1]
                elif kind == "cub":
                    self._col = max(0, self._col - tok[1])
                elif kind == "cha":
                    self._col = max(0, tok[1] - 1)
                elif kind == "dch":
                    self._delete_chars(tok[1])
                elif kind == "clear":
                    self._edit.clear()
                    self._col = 0
        finally:
            c.endEditBlock()

        if follow:
            bar.setValue(bar.maximum())

    # -- document ops (always on the last block) ---------------------------
    def _last(self):
        b = self._doc.lastBlock()
        return b.position(), b.length() - 1     # start position, text length

    @staticmethod
    def _expand_tabs(text, col):
        """Expand TABs to 8-column stops, tracking the column across newlines."""
        out = []
        for ch in text:
            if ch == "\t":
                k = 8 - (col % 8)
                out.append(" " * k)
                col += k
            elif ch == "\n":
                out.append(ch)
                col = 0
            else:
                out.append(ch)
                col += 1
        return "".join(out)

    def _write(self, text):
        c = self._cur
        if "\t" in text:
            text = self._expand_tabs(text, self._col)
        while text:
            base, length = self._last()
            if self._col >= length:
                # Fast path — appending at the end of the line (nearly all
                # output). The whole run, newlines included, goes in with a
                # single insert; QTextCursor turns each "\n" into a new block.
                c.setPosition(base + length)
                if self._col > length:                      # cursor was moved past the end
                    c.insertText(" " * (self._col - length))
                c.insertText(text, self._fmt)
                nl = text.rfind("\n")
                self._col = self._col + len(text) if nl == -1 else len(text) - nl - 1
                return
            # Slow path — the cursor is inside existing text (after \r, \b,
            # cursor-left...), so this run overwrites characters in place.
            head, nlsep, tail = text.partition("\n")
            if head:
                n = min(len(head), length - self._col)
                c.setPosition(base + self._col)
                c.setPosition(base + self._col + n, QTextCursor.KeepAnchor)
                c.insertText(head[:n], self._fmt)
                if n < len(head):
                    c.insertText(head[n:], self._fmt)
                self._col += len(head)
            if nlsep:
                c.movePosition(QTextCursor.End)
                c.insertText("\n")
                self._col = 0
            text = tail

    def _erase_line(self, mode):
        base, length = self._last()
        c = self._cur
        if mode == 0:
            if self._col < length:
                c.setPosition(base + self._col)
                c.setPosition(base + length, QTextCursor.KeepAnchor)
                c.removeSelectedText()
        elif mode == 1:
            k = min(self._col + 1, length)
            if k:
                c.setPosition(base)
                c.setPosition(base + k, QTextCursor.KeepAnchor)
                c.insertText(" " * k)
        elif mode == 2:
            if length:
                c.setPosition(base)
                c.setPosition(base + length, QTextCursor.KeepAnchor)
                c.removeSelectedText()

    def _delete_chars(self, n):
        base, length = self._last()
        if self._col < length:
            c = self._cur
            c.setPosition(base + self._col)
            c.setPosition(base + min(self._col + n, length), QTextCursor.KeepAnchor)
            c.removeSelectedText()