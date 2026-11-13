# rpi-sim – Raspberry Pi GPIO simulator

Write Raspberry Pi GPIO code on your PC, wire up a virtual breadboard, and watch
it behave like the real thing. No Pi required.

rpi-sim is a drop-in replacement for the `RPi.GPIO` library. Your script stays
exactly the same as on a real Raspberry Pi (`import RPi.GPIO as GPIO`). Instead
of real hardware, a window opens with a 40-pin Pi header, a breadboard, and
components you place and wire yourself.

rpi-sim doesn't just show pin states: it **solves the circuit you built**. An LED
only lights if current can actually flow from the GPIO pin through the LED to
ground. Wiring mistakes behave like they would in real life, and the simulator
tells you why.

## Features

- **Real wiring**: a 40-pin header with correct labels, a 30-column breadboard
  with power rails, and wires you draw between pins, holes, and module terminals.
- **Components**: LED (5 colors), resistors (220 Ω, 1 kΩ, 10 kΩ), push button,
  active buzzer, passive buzzer, PIR motion sensor.
- **An electrical model that catches real mistakes**:
  - LED without a resistor → "burning out"
  - LED or buzzer inserted backwards → stays dark or silent
  - both legs in the same breadboard column → shorted
  - a GPIO output tied to GND, or 3V3 tied to GND → short circuit
  - 5V wired to a GPIO pin → warning that this would damage a real Pi
  - an input with no pull-up/down and nothing connected → floating, reads random values
  - a PIR powered from 3V3 instead of 5V → doesn't work
- **Sound**: a passive buzzer plays the actual PWM frequency, an active buzzer
  beeps on HIGH. Sound works on Windows only.
- **PWM**: LED brightness follows the duty cycle, so fading works.
- **Net highlighting**: hover any hole or pin to see everything electrically
  connected to it. This is the fastest way to understand how a breadboard works.
- **Ground check**: shows how many wires go to the Pi's GND pins. One common
  ground plus a GND rail is the clean way to wire a board.
- **Presets**: ready-made circuits for every example, loadable from the toolbar.
- **Matches the real API**: `setmode`, `setup`, `output`, `input`, `PWM`,
  `add_event_detect` with `bouncetime`, `add_event_callback`, `event_detected`,
  `wait_for_edge`, `remove_event_detect`, `cleanup`, `BCM` and `BOARD`
  numbering. Mistakes raise the same errors as the real library (e.g.
  *"Please set pin numbering mode…"*).

## Quick start

Requirements: **Python 3.8+** with tkinter (included in the standard Windows and
macOS installers). There are no other dependencies.

```bash
git clone https://github.com/aleksandar-aleksandar/rpi-sim.git
cd rpi-sim

python main.py examples/01_blink.py      # run an example with its preset circuit
python main.py                           # open an empty editor (circuit.json)
python main.py my_script.py              # run your own script (circuit: my_script.json)
python main.py -c board.json my_script.py
```

Stop a running script with **Ctrl+C** in the terminal. The window stays open so
you can inspect the final state. Close it to exit.

> **Running scripts without the launcher:** copy the `RPi/` folder next to your
> script and run it normally with `python my_script.py`. The circuit is then
> saved to `circuit.json` next to the script.

## Using the editor

| Tool | How |
|---|---|
| **Use** | Hold a button or a PIR sensor with the mouse to press it or simulate motion. |
| **Wire** | Click two points: Pi pins, breadboard holes, or PIR terminals. |
| **LED** | First click is the anode (+), second the cathode (−). |
| **Resistor / Button / Buzzers** | Two clicks, one per leg. For buzzers, + comes first. |
| **PIR** | Click in the grey module area below the breadboard. |
| **Delete** | Click an item, or right-click it in any mode. |

- **Esc** cancels a placement that is in progress.
- Each hole, pin, or terminal holds one item, just like the real hardware.
- The circuit is auto-saved after every change.
- The bottom panels show each pin's state, warnings, and a timestamped log of
  everything your script does.

## Examples

| # | Example | Shows |
|---|---|---|
| 01 | `blink` | digital output, `time.sleep` |
| 02 | `button_led` | input with internal pull-up, polling |
| 03 | `button_callback` | `add_event_detect`, `FALLING`, `bouncetime` |
| 04 | `pwm_fade` | PWM duty cycle → LED brightness |
| 05 | `active_buzzer` | active buzzer = plain HIGH/LOW |
| 06 | `passive_buzzer` | passive buzzer = PWM frequency is the pitch |
| 07 | `pir_motion` | PIR sensor (5V supply, digital output), `BOTH` edges |
| 08 | `reaction_game` | LED + button + passive buzzer, random delay, timeout |
| 09 | `motion_alarm` | LED + PIR + active buzzer |
| 10 | `common_mistakes` | a broken circuit: fix it until the warnings disappear |

Every example has a matching `.json` preset with the circuit already wired.
`tools/build_presets.py` regenerates the presets.

## How it works

```
your_script.py ── import RPi.GPIO ──► RPi/GPIO.py   (same API as the real library)
                                          │
                                          ▼
                                     RPi/_core.py   circuit + electrical model
                                          ▲
                                          │
                                     RPi/_ui.py     tkinter window (separate thread)
```

The core groups connected points into **nets**. A net is a breadboard column
strip, a rail, everything joined by wires, a pressed button, or the Pi's
internally connected GND / 3V3 / 5V pins. Each net is driven by sources: 3V3,
5V, GND, GPIO outputs, or the PIR output.

Resistors join nets without shorting them. An LED lights when its anode
resolves to a higher voltage than its cathode and there is a resistor
somewhere in the loop. Input pins read their net's voltage, fall back to the
internal pull-up or pull-down, or float.

Edge callbacks run sequentially on a background thread, like in `RPi.GPIO`.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests run headless (`RPISIM_HEADLESS=1`), so they also work in CI.

## Limitations

- The button has 2 legs. A real tactile switch has 4, internally connected in
  pairs.
- Power rails run the full length of the board. On some real breadboards the
  rails are split in the middle.
- The model is a simplified DC model. It doesn't calculate currents, so LED
  brightness only comes from PWM, not from the resistor value.
- Sound only works on Windows (`winsound`). On other platforms the buzzers are
  visual only.

## Roadmap ideas

- 4-leg tactile button, RGB LED, potentiometer with an ADC (MCP3008)
- Servo motor, DHT11 temperature/humidity sensor, HC-SR04 ultrasonic sensor
- Drag-to-move components, undo/redo
- `gpiozero` compatibility layer
- Cross-platform sound

## License

MIT, see [LICENSE](LICENSE).
