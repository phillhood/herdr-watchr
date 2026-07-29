#!/usr/bin/env python3
import json
import os
import re
import shutil
import sys

VOCABULARY = ("blocked", "idle", "done", "working", "unknown")
POSITIONS = ("left", "center", "right")

MARK_OPEN = "/* >>> herdr-watchr >>> */"
MARK_CLOSE = "/* <<< herdr-watchr <<< */"
INC_OPEN = "/* >>> herdr-watchr include >>> */"
INC_CLOSE = "/* <<< herdr-watchr include <<< */"
GRP_OPEN = "/* >>> herdr-watchr group >>> */"
GRP_CLOSE = "/* <<< herdr-watchr group <<< */"
CSS_OPEN = "/* >>> herdr-watchr >>> */"
CSS_CLOSE = "/* <<< herdr-watchr <<< */"
GROUP = "group/herdr-watchr"


class ScanError(Exception):
    pass


def _end_of_string(text, i):
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    raise ScanError("unterminated string")


def _is_comment(text, i):
    return text[i] == "/" and i + 1 < len(text) and text[i + 1] in "/*"


def _end_of_comment(text, i):
    if text[i + 1] == "/":
        j = text.find("\n", i)
        return len(text) if j < 0 else j
    j = text.find("*/", i + 2)
    if j < 0:
        raise ScanError("unterminated comment")
    return j + 2


def _skip_blanks(text, i):
    while i < len(text):
        if text[i].isspace():
            i += 1
        elif _is_comment(text, i):
            i = _end_of_comment(text, i)
        else:
            return i
    return i


def top_level_open(text):
    i = _skip_blanks(text, 0)
    if i >= len(text) or text[i] != "{":
        raise ScanError("top level is not an object")
    return i


def value_offsets(text, key):
    found = []
    depth = 0
    i = 0
    while i < len(text):
        if _is_comment(text, i):
            i = _end_of_comment(text, i)
            continue
        c = text[i]
        if c == '"':
            j = _end_of_string(text, i)
            if depth == 1 and text[i + 1:j - 1] == key:
                k = _skip_blanks(text, j)
                if k < len(text) and text[k] == ":":
                    found.append(_skip_blanks(text, k + 1))
            i = j
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        i += 1
    return found


def value_offset(text, key):
    found = value_offsets(text, key)
    return found[0] if found else None


def _newline(text):
    return "\r\n" if "\r\n" in text else "\n"


def matching_bracket(text, start):
    open_c = text[start]
    close_c = {"{": "}", "[": "]"}[open_c]
    depth = 0
    i = start
    while i < len(text):
        if _is_comment(text, i):
            i = _end_of_comment(text, i)
            continue
        c = text[i]
        if c == '"':
            i = _end_of_string(text, i)
            continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ScanError("unbalanced %s" % open_c)


HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE_CSS = os.path.join(HERE, "examples", "style.css")

def comment_marks(text, mark):
    found = []
    i = 0
    try:
        while i < len(text):
            if _is_comment(text, i):
                if text.startswith(mark, i):
                    found.append(i)
                i = _end_of_comment(text, i)
                continue
            if text[i] == '"':
                i = _end_of_string(text, i)
                continue
            i += 1
    except ScanError:
        return []
    return found


def _cut_span(text, open_mark, close_mark, eat_newline=False):
    opens = comment_marks(text, open_mark)
    if not opens:
        return text
    start = opens[0]
    closes = [c for c in comment_marks(text, close_mark) if c > start]
    if not closes:
        return text
    end = closes[0] + len(close_mark)
    if eat_newline:
        if text[end:end + 2] == "\r\n":
            end += 2
        elif text[end:end + 1] == "\n":
            end += 1
    return text[:start] + text[end:]


def config_uninstall(text):
    text = _cut_span(text, MARK_OPEN, MARK_CLOSE)
    text = _cut_span(text, INC_OPEN, INC_CLOSE)
    return _cut_span(text, GRP_OPEN, GRP_CLOSE)


def manual_install_present(text):
    for mark in (MARK_OPEN, INC_OPEN, GRP_OPEN):
        if comment_marks(text, mark):
            return False
    return "herdr-watchr" in text


def config_install(text, include_path, position):
    if position not in POSITIONS:
        raise ScanError("position must be one of %s" % ", ".join(POSITIONS))
    text = config_uninstall(text)
    open_at = top_level_open(text)
    nl = _newline(text)
    key = "modules-%s" % position
    for duplicated in ("include", key):
        if len(value_offsets(text, duplicated)) > 1:
            raise ScanError("%s appears more than once at the top level; "
                            "remove the duplicate before installing" % duplicated)
    include_at = value_offset(text, "include")
    if include_at is None:
        block = "%s%s  \"include\": [\"%s\"],%s  %s" % (
            MARK_OPEN, nl, include_path, nl, MARK_CLOSE)
        text = text[:open_at + 1] + block + text[open_at + 1:]
    elif text[include_at] == "[":
        close = matching_bracket(text, include_at)
        element = "%s\"%s\"" % (INC_OPEN, include_path)
        if _last_content(text, include_at + 1, close) >= 0:
            element += ","
        element += INC_CLOSE
        text = text[:include_at + 1] + element + text[include_at + 1:]
    else:
        raise ScanError("include is not an array; add the include entry by hand")

    array_at = value_offset(text, key)
    if array_at is None or text[array_at] != "[":
        raise ScanError("%s is not an array in this config" % key)
    close = matching_bracket(text, array_at)
    last = _last_content(text, array_at + 1, close)
    if last < 0:
        span = "%s\"%s\"%s" % (GRP_OPEN, GROUP, GRP_CLOSE)
        return text[:array_at + 1] + span + text[array_at + 1:]
    separator = " " if text[last] == "," else ", "
    span = "%s%s\"%s\"%s" % (GRP_OPEN, separator, GROUP, GRP_CLOSE)
    return text[:last + 1] + span + text[last + 1:]


def css_install(text, css_path):
    line = '%s @import url("%s"); %s%s' % (
        CSS_OPEN, css_path, CSS_CLOSE, _newline(text))
    return line + css_uninstall(text)


def css_uninstall(text):
    start = text.find(CSS_OPEN)
    if start < 0:
        return text
    end = text.find(CSS_CLOSE, start)
    if end < 0:
        return text
    end += len(CSS_CLOSE)
    if text[end:end + 2] == "\r\n":
        end += 2
    elif text[end:end + 1] == "\n":
        end += 1
    return text[:start] + text[end:]


def module_config(binary):
    modules = {
        GROUP: {
            "orientation": "inherit",
            "modules": ["custom/herdr-watchr-notify"] +
                       ["custom/herdr-%s" % s for s in VOCABULARY],
        },
        "custom/herdr-watchr-notify": {
            "exec": "%s notify" % binary,
            "return-type": "json",
            "format": "{}",
            "hide-empty-text": True,
            "tooltip": False,
        },
    }
    for status in VOCABULARY:
        modules["custom/herdr-%s" % status] = {
            "exec": "%s status %s" % (binary, status),
            "return-type": "json",
            "format": "{}",
            "hide-empty-text": True,
            "tooltip": True,
            "signal": 8,
            "on-click": "%s focus-status %s" % (binary, status),
        }
    return json.dumps(modules, indent=2) + "\n"


def _last_content(text, start, stop):
    i = start
    last = -1
    while i < stop:
        if _is_comment(text, i):
            i = _end_of_comment(text, i)
            continue
        c = text[i]
        if c == '"':
            j = _end_of_string(text, i)
            last = j - 1
            i = j
            continue
        if not c.isspace():
            last = i
        i += 1
    return last


def config_file(waybar_dir):
    for name in ("config.jsonc", "config"):
        path = os.path.join(waybar_dir, name)
        if os.path.exists(path):
            return path
    raise ScanError("no waybar config found in %s" % waybar_dir)


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_in_place(path, text):
    with open(os.path.realpath(path), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _backup(path, stamp):
    real = os.path.realpath(path)
    shutil.copyfile(real, "%s.herdr-watchr-backup-%s" % (real, stamp))


def install(waybar_dir, binary, position, stamp, force=False):
    cfg_path = config_file(waybar_dir)
    css_path = os.path.join(waybar_dir, "style.css")
    if not os.path.exists(css_path):
        raise ScanError("no style.css found in %s" % waybar_dir)

    cfg_text = _read(cfg_path)
    css_text = _read(css_path)
    if not force and manual_install_present(cfg_text):
        raise ScanError("config already wires herdr-watchr by hand; "
                        "remove that wiring or pass --force")

    owned_jsonc = os.path.join(waybar_dir, "herdr-watchr.jsonc")
    owned_css = os.path.join(waybar_dir, "herdr-watchr.css")
    new_cfg = config_install(cfg_text, owned_jsonc, position)
    new_css = css_install(css_text, owned_css)

    with open(owned_jsonc, "w", encoding="utf-8") as fh:
        fh.write(module_config(binary))
    shutil.copyfile(EXAMPLE_CSS, owned_css)

    changed = []
    for path, old, new in ((cfg_path, cfg_text, new_cfg),
                           (css_path, css_text, new_css)):
        if old != new:
            _backup(path, stamp)
            _write_in_place(path, new)
            changed.append(path)
    return changed


def uninstall(waybar_dir, stamp):
    changed = []
    targets = []
    try:
        targets.append((config_file(waybar_dir), config_uninstall))
    except ScanError:
        pass
    css_path = os.path.join(waybar_dir, "style.css")
    if os.path.exists(css_path):
        targets.append((css_path, css_uninstall))
    for path, reverse in targets:
        text = _read(path)
        new = reverse(text)
        if new != text:
            _backup(path, stamp)
            _write_in_place(path, new)
            changed.append(path)
    for name in ("herdr-watchr.jsonc", "herdr-watchr.css"):
        owned = os.path.join(waybar_dir, name)
        if os.path.exists(owned):
            os.remove(owned)
    return changed


def main(argv):
    args = argv[1:]
    if not args:
        sys.stderr.write("usage: wire.py install|uninstall --waybar-dir DIR\n")
        return 2
    action = args[0]
    opts = {"--waybar-dir": None, "--binary": None,
            "--position": "center", "--stamp": "0"}
    force = False
    i = 1
    while i < len(args):
        if args[i] == "--force":
            force = True
            i += 1
        elif args[i] in opts and i + 1 < len(args):
            opts[args[i]] = args[i + 1]
            i += 2
        else:
            sys.stderr.write("wire.py: unknown option %s\n" % args[i])
            return 2
    try:
        if action == "install":
            changed = install(opts["--waybar-dir"], opts["--binary"],
                              opts["--position"], opts["--stamp"], force)
        elif action == "uninstall":
            changed = uninstall(opts["--waybar-dir"], opts["--stamp"])
        else:
            sys.stderr.write("wire.py: unknown action %s\n" % action)
            return 2
    except ScanError as exc:
        sys.stderr.write("herdr-watchr: %s\n" % exc)
        return 1
    for path in changed:
        real = os.path.realpath(path)
        if real == path:
            sys.stdout.write("edited %s\n" % real)
        else:
            sys.stdout.write("edited %s (via symlink)\n" % real)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
