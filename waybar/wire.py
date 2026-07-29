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
