#!/usr/bin/env python3
import json
import os
import re
import shutil
import sys

VOCABULARY = ("blocked", "idle", "done", "working", "unknown")
POSITIONS = ("left", "center", "right")

MARK_OPEN = "// >>> herdr-watchr >>>"
MARK_CLOSE = "// <<< herdr-watchr <<<"
INCLUDE_MARK = "/* herdr-watchr include */"
GROUP_MARK = "/* herdr-watchr group */"
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


def value_offset(text, key):
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
                    return _skip_blanks(text, k + 1)
            i = j
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        i += 1
    return None


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


INCLUDE_BLOCK_RE = re.compile(
    "\n  " + re.escape(MARK_OPEN) + "\n  \"include\": \\[\"[^\"]*\"\\],\n  " +
    re.escape(MARK_CLOSE) + "\n")
INCLUDE_ELEM_RE = re.compile("\"[^\"]*\" " + re.escape(INCLUDE_MARK) + ", ?")
GROUP_ENTRY_RE = re.compile(
    ",? ?\"" + re.escape(GROUP) + "\" " + re.escape(GROUP_MARK))


def config_uninstall(text):
    text = INCLUDE_BLOCK_RE.sub("", text, count=1)
    text = INCLUDE_ELEM_RE.sub("", text, count=1)
    return GROUP_ENTRY_RE.sub("", text, count=1)


def manual_install_present(text):
    if MARK_OPEN in text or INCLUDE_MARK in text or GROUP_MARK in text:
        return False
    return "herdr-watchr" in text


def config_install(text, include_path, position):
    if position not in POSITIONS:
        raise ScanError("position must be one of %s" % ", ".join(POSITIONS))
    text = config_uninstall(text)
    open_at = top_level_open(text)
    include_at = value_offset(text, "include")
    if include_at is None:
        block = "\n  %s\n  \"include\": [\"%s\"],\n  %s\n" % (
            MARK_OPEN, include_path, MARK_CLOSE)
        text = text[:open_at + 1] + block + text[open_at + 1:]
    elif text[include_at] == "[":
        close = matching_bracket(text, include_at)
        element = "\"%s\" %s" % (include_path, INCLUDE_MARK)
        if _last_content(text, include_at + 1, close) >= 0:
            element += ", "
        text = text[:include_at + 1] + element + text[include_at + 1:]
    else:
        raise ScanError("include is not an array; add the include entry by hand")

    key = "modules-%s" % position
    array_at = value_offset(text, key)
    if array_at is None or text[array_at] != "[":
        raise ScanError("%s is not an array in this config" % key)
    close = matching_bracket(text, array_at)
    last = _last_content(text, array_at + 1, close)
    entry = "\"%s\" %s" % (GROUP, GROUP_MARK)
    if last < 0:
        return text[:array_at + 1] + entry + text[array_at + 1:]
    return text[:last + 1] + ", " + entry + text[last + 1:]


def css_install(text, css_path):
    line = '%s @import url("%s"); %s\n' % (CSS_OPEN, css_path, CSS_CLOSE)
    return line + css_uninstall(text)


def css_uninstall(text):
    start = text.find(CSS_OPEN)
    if start < 0:
        return text
    end = text.find(CSS_CLOSE, start)
    if end < 0:
        return text
    end += len(CSS_CLOSE)
    if text[end:end + 1] == "\n":
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
