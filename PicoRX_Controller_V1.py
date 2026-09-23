#!/usr/bin/env python3
"""
PicoRX Controller V1
Cross-platform Python/Tkinter controller for a PicoRX-compatible CAT interface.
GUI similar to Pi-Pico-RX-Control-Program V100 PicoRX.exe by ON7DQ and ONL12523.
G3ZBU 17th September 2026.
Modes: 22nd Sep 2026 by ChatGPT for better formatting of frequency.

Requires:
    Python 3
    Tkinter
    pyserial

CAT protocol implemented:
    Poll frequency: FA;
    Set frequency:  FA + 9 decimal digits + ;
    Poll mode:       MD;
    Set mode:        MD + mode number + ;

Mode numbers:
    LSB=1, USB=2, CW=3, FM=4, AM=5
"""

import tkinter as tk
from tkinter import ttk, messagebox
import serial
from serial.tools import list_ports


POLL_MS = 1000
SERIAL_BAUD = 9600
SERIAL_TIMEOUT = 0.25

MODE_VALUES = {
    "LSB": 1,
    "USB": 2,
    "CW": 3,
    "FM": 4,
    "AM": 5,
}


class PicoRX:
    """Small CAT/serial interface independent of the GUI."""

    def __init__(self):
        self.ser = None

    @property
    def connected(self):
        return self.ser is not None and self.ser.is_open

    def open(self, port):
        self.close()
        self.ser = serial.Serial(
            port=port,
            baudrate=SERIAL_BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_TIMEOUT,
            write_timeout=SERIAL_TIMEOUT,
        )
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except serial.SerialException:
                pass
        self.ser = None

    def _write(self, command):
        if not self.connected:
            raise RuntimeError("PicoRX is not open.")
        self.ser.write(command.encode("ascii"))
        self.ser.flush()

    def _read_until_semicolon(self):
        data = bytearray()
        while True:
            b = self.ser.read(1)
            if not b:
                break
            data += b
            if b == b";":
                break
        return data.decode("ascii", errors="ignore")

    def set_frequency(self, frequency):
        frequency = max(0, min(99_999_999, int(frequency)))
        self._write(f"FA{frequency:09d};")

    def get_frequency(self):
        self._write("FA;")
        reply = self._read_until_semicolon()

        # Expected: FA followed by 9 digits and ;
        if reply.startswith("FA") and reply.endswith(";"):
            value = reply[2:-1]
            if value.isdigit():
                return max(0, min(99_999_999, int(value)))
        return None

    def set_mode(self, mode):
        if mode not in MODE_VALUES:
            raise ValueError("Unknown mode")
        self._write(f"MD{MODE_VALUES[mode]};")

    def get_mode(self):
        self._write("MD;")
        reply = self._read_until_semicolon()

        # Expected PicoRX reply: MD followed by the mode number, terminated by ;
        # For example, USB is returned as MD2;
        if reply.startswith("MD") and reply.endswith(";"):
            payload = reply[2:-1]
            if payload.isdigit():
                value = int(payload)
                for name, number in MODE_VALUES.items():
                    if value == number:
                        return name

        return None


class FrequencyDisplay(tk.Canvas):
    """Large frequency display with per-digit upper/lower click tuning."""

    def __init__(self, master, on_frequency_changed, **kwargs):
        super().__init__(master, highlightthickness=0, **kwargs)
        self.on_frequency_changed = on_frequency_changed

        self.frequency = 0
        self.digits = 8
        self.min_frequency = 0
        self.max_frequency = 99_999_999

        self.configure(
            background="#071b45",
            cursor="arrow",
            width=760,
            height=125,
        )

        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self.configure(cursor="arrow"))
        self.bind("<Button-1>", self._click)

        self._digit_boxes = []
        self._draw()

    def set_frequency(self, frequency):
        frequency = max(self.min_frequency, min(self.max_frequency, int(frequency)))
        changed = frequency != self.frequency
        self.frequency = frequency
        self._draw()
        return changed

    def get_frequency(self):
        return self.frequency

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()

        if w < 100:
            w = 760
        if h < 50:
            h = 125

        self.create_rectangle(
            2, 2, w - 2, h - 2,
            outline="#f4e6b3",
            width=1,
        )

        # Eight displayed digits: five kHz digits and three decimal digits.
        # Example: 14,074.000 kHz.  The underlying CAT value is still Hz.
        integer_part = self.frequency // 1000
        fractional_part = self.frequency % 1000
        digits = f"{integer_part:05d}{fractional_part:03d}"

        font_size = max(28, int(h * 0.55))
        font = ("TkFixedFont", font_size, "bold")

        # Fixed-width digit cells.  Extra space is deliberately allowed
        # around the comma and decimal point, and before the kHz suffix.
        digit_width = max(25, int(w * 0.075))
        comma_gap = digit_width * 0.18
        decimal_gap = digit_width * 0.18
        suffix_gap = digit_width * 0.55
        y_center = h / 2 + 3

        total_width = (
            5 * digit_width + comma_gap
            + decimal_gap + 3 * digit_width
            + suffix_gap + 3 * digit_width
        )
        x = (w - total_width) / 2
        self._digit_boxes = []

        # First two integer digits.
        for i in range(2):
            self.create_text(
                x + digit_width / 2, y_center,
                text=digits[i], fill="#fff6d0", font=font, anchor="center"
            )
            self._digit_boxes.append((x, x + digit_width))
            x += digit_width

        # Comma, with a little extra breathing room on both sides.
        x += comma_gap / 2
        self.create_text(
            x, y_center, text=",", fill="#fff6d0", font=font, anchor="center"
        )
        x += comma_gap / 2

        # Remaining three integer digits.
        for i in range(2, 5):
            self.create_text(
                x + digit_width / 2, y_center,
                text=digits[i], fill="#fff6d0", font=font, anchor="center"
            )
            self._digit_boxes.append((x, x + digit_width))
            x += digit_width

        # Decimal point, again with a little extra spacing.
        x += decimal_gap / 2
        self.create_text(
            x, y_center, text=".", fill="#fff6d0", font=font, anchor="center"
        )
        x += decimal_gap / 2

        # Three fractional digits. These remain clickable too: they adjust
        # 100 Hz, 10 Hz and 1 Hz respectively.
        for i in range(5, 8):
            self.create_text(
                x + digit_width / 2, y_center,
                text=digits[i], fill="#fff6d0", font=font, anchor="center"
            )
            self._digit_boxes.append((x, x + digit_width))
            x += digit_width

        # Clear gap before the unit label.
        x += suffix_gap
        self.create_text(
            x + (3 * digit_width) / 2, y_center,
            text="kHz", fill="#fff6d0", font=font, anchor="center"
        )

    def _digit_at(self, x):
        for index, (left, right) in enumerate(self._digit_boxes):
            if left <= x < right:
                return index
        return None

    def _motion(self, event):
        index = self._digit_at(event.x)
        if index is None:
            self.configure(cursor="arrow")
            return

        # Up/down cursor is not available consistently on all platforms.
        # Use the standard pointing hand to indicate an active digit.
        self.configure(cursor="hand2")

    def _click(self, event):
        index = self._digit_at(event.x)
        if index is None:
            return

        # The CAT frequency is stored in Hz.  The eight displayed
        # digits therefore correspond directly to 10,000,000 Hz down
        # to 1 Hz.  The punctuation is only visual; it does not alter
        # the digit values or their click increments.
        step = 10 ** (self.digits - 1 - index)

        # Upper half increments; lower half decrements.
        height = max(1, self.winfo_height())
        if event.y < height / 2:
            new_frequency = self.frequency + step
        else:
            new_frequency = self.frequency - step

        new_frequency = max(
            self.min_frequency,
            min(self.max_frequency, new_frequency)
        )

        if new_frequency != self.frequency:
            self.frequency = new_frequency
            self._draw()
            self.on_frequency_changed(new_frequency)


class PicoRXController(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("PicoRX Controller V1")
        self.minsize(850, 430)
        self.geometry("900x470")

        self.radio = PicoRX()
        self.poll_after_id = None
        self.last_frequency = None
        self.last_mode = None

        self.frequency_var = tk.StringVar(value="000000000")
        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar(value="PicoRX closed")
        self.mode_var = tk.StringVar(value="USB")

        self._build_gui()
        self._refresh_ports()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_gui(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(
            outer,
            text="PicoRX Controller",
            font=("TkDefaultFont", 16, "bold"),
        )
        title.pack(pady=(0, 10))

        display_frame = ttk.Frame(outer)
        display_frame.pack(fill="x", pady=(0, 14))

        self.frequency_display = FrequencyDisplay(
            display_frame,
            self._frequency_clicked,
        )
        self.frequency_display.pack(fill="x", expand=True)

        modes_frame = ttk.LabelFrame(outer, text="Mode", padding=8)
        modes_frame.pack(pady=(0, 14))

        for mode in MODE_VALUES:
            rb = ttk.Radiobutton(
                modes_frame,
                text=mode,
                value=mode,
                variable=self.mode_var,
                command=self._mode_changed,
            )
            rb.pack(anchor="w", padx=12, pady=2)

        port_frame = ttk.Frame(outer)
        port_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(
            port_frame,
            text="Port:",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(side="left", padx=(0, 6))

        self.port_combo = ttk.Combobox(
            port_frame,
            textvariable=self.port_var,
            state="readonly",
            width=25,
        )
        self.port_combo.pack(side="left", padx=(0, 8))

        ttk.Button(
            port_frame,
            text="Refresh",
            command=self._refresh_ports,
        ).pack(side="left", padx=(0, 8))

        self.open_button = ttk.Button(
            port_frame,
            text="Open PicoRX",
            command=self._toggle_connection,
        )
        self.open_button.pack(side="left")

        ttk.Label(
            outer,
            textvariable=self.status_var,
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

    def _refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports

        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])
        elif not ports:
            self.port_var.set("")

    def _toggle_connection(self):
        if self.radio.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_var.get().strip()

        if not port:
            messagebox.showwarning(
                "PicoRX",
                "Please select a serial port first."
            )
            return

        try:
            self.radio.open(port)
        except Exception as exc:
            self.status_var.set("Open failed")
            messagebox.showerror(
                "PicoRX",
                f"Could not open {port}:\n\n{exc}"
            )
            return

        self.open_button.configure(text="Close PicoRX")
        self.status_var.set(f"Connected to {port}")

        self.last_frequency = None
        self.last_mode = None

        self._poll()

    def _disconnect(self):
        if self.poll_after_id is not None:
            self.after_cancel(self.poll_after_id)
            self.poll_after_id = None

        self.radio.close()
        self.open_button.configure(text="Open PicoRX")
        self.status_var.set("PicoRX closed")

    def _frequency_clicked(self, frequency):
        if not self.radio.connected:
            return

        try:
            self.radio.set_frequency(frequency)
            self.last_frequency = frequency
            self.status_var.set(
                f"Frequency set to {frequency/1000:,.3f} kHz"
            )
        except Exception as exc:
            self.status_var.set(f"Serial error: {exc}")

    def _mode_changed(self):
        mode = self.mode_var.get()

        if not self.radio.connected:
            return

        try:
            self.radio.set_mode(mode)
            self.last_mode = mode
            self.status_var.set(f"Mode set to {mode}")
        except Exception as exc:
            self.status_var.set(f"Serial error: {exc}")

    def _poll(self):
        self.poll_after_id = None

        if not self.radio.connected:
            return

        try:
            frequency = self.radio.get_frequency()

            if frequency is not None and frequency != self.last_frequency:
                self.frequency_display.set_frequency(frequency)
                self.last_frequency = frequency

            mode = self.radio.get_mode()

            if mode is not None and mode != self.last_mode:
                self.mode_var.set(mode)
                self.last_mode = mode

            if frequency is not None:
                self.status_var.set(
                    f"Connected    {frequency/1000:,.3f} kHz    {mode or self.mode_var.get()}"
                )

        except (serial.SerialException, OSError) as exc:
            self.status_var.set(f"Serial error: {exc}")
            self._disconnect()
            return
        except Exception as exc:
            # A malformed/missing reply should not kill the GUI.
            self.status_var.set(f"CAT error: {exc}")

        self.poll_after_id = self.after(POLL_MS, self._poll)

    def _on_close(self):
        self._disconnect()
        self.destroy()


def main():
    app = PicoRXController()
    app.mainloop()


if __name__ == "__main__":
    main()
