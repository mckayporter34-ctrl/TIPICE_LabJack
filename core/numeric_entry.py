"""Shared validation for editable numeric fields in every apparatus screen."""

import math
import re
from tkinter import messagebox


_NUMBER_PREFIX = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d*)(?:[eE][+-]?\d*)?$")
_EDIT_STATES = {"", "+", "-", ".", "+.", "-."}


def finite_number(value):
    """Parse a numeric input and reject NaN/infinity as well as invalid text."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Enter a finite number.")
    return number


def install_numeric_validation(widget):
    """Reject invalid keystrokes/pastes and show a message after Tk validation.

    Allow temporary edit states; Enter/focus loss requires a complete number.
    Read widget text, avoiding DoubleVar/IntVar conversion errors. Resolve the
    textvariable dynamically for the shared packed-column panel.
    """
    pending = False
    last_valid = {}

    def remember(text):
        try:
            finite_number(text)
        except (ValueError, TypeError, OverflowError):
            return False
        last_valid[str(widget.cget("textvariable"))] = text
        return True

    remember(widget.get())

    def report():
        nonlocal pending
        if pending:
            return
        pending = True

        def show():
            nonlocal pending
            try:
                if widget.winfo_exists():
                    messagebox.showerror("Invalid Number", "Please enter a finite numeric value.",
                                         parent=widget.winfo_toplevel())
            finally:
                pending = False
        widget.after_idle(show)

    def validate(proposed, reason):
        if reason == "forced":
            # Programmatic updates/rebinding must not disable Tk validation.
            remember(proposed)
            return True
        if remember(proposed):
            return True
        allowed = proposed in _EDIT_STATES or (
            bool(_NUMBER_PREFIX.fullmatch(proposed)) and
            proposed.endswith(("e", "E", "e+", "e-", "E+", "E-")))
        if not allowed:
            report()
        return allowed

    def commit(event=None):
        if not remember(widget.get()):
            report()
            name = str(widget.cget("textvariable"))
            widget.set(last_valid.get(name, "0"))

    widget.configure(validate="key", validatecommand=(widget.register(validate), "%P", "%V"))
    # Validate before existing handlers read numeric Tk variables.
    for event in ("<Return>", "<FocusOut>"):
        existing = widget.bind(event)
        widget.bind(event, commit)
        if existing:
            widget.bind(event, widget.bind(event) + "\n" + existing)
