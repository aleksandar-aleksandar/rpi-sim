"""Minimal gpiozero.tones: musical notes <-> frequencies."""
import re

_NOTES = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}


class Tone(float):
    """A frequency in Hz. Tone("A4"), Tone(440.0), Tone(frequency=440), Tone(note="C#5")."""

    def __new__(cls, value=None, *, frequency=None, note=None, midi=None):
        if note is not None or isinstance(value, str):
            hz = cls._note_to_hz(note if note is not None else value)
        elif midi is not None:
            hz = 440.0 * 2 ** ((midi - 69) / 12)
        else:
            hz = float(frequency if frequency is not None else value)
        if hz <= 0:
            raise ValueError("frequency must be greater than 0")
        return super().__new__(cls, hz)

    @staticmethod
    def _note_to_hz(note):
        m = re.fullmatch(r"([A-Ga-g])([#♯b♭]?)(-?\d)", note.strip())
        if not m:
            raise ValueError(f"invalid note: {note!r}")
        letter, acc, octave = m.groups()
        semis = _NOTES[letter.upper()] + {"#": 1, "♯": 1, "b": -1, "♭": -1}.get(acc, 0)
        return 440.0 * 2 ** ((semis + (int(octave) - 4) * 12) / 12)

    @classmethod
    def from_frequency(cls, freq):
        return cls(frequency=freq)

    @classmethod
    def from_note(cls, note):
        return cls(note=note)

    @property
    def frequency(self):
        return float(self)

    def __repr__(self):
        return f"<Tone frequency={float(self):.2f}Hz>"
