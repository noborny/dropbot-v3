# High-frequency impedance add-on for DropBot v3

Design notes for adding a 50 kHz – 10 MHz lock-in impedance measurement
(Digilent Analog Discovery 3 + transimpedance amplifier) to a DropBot v3,
while keeping the DropBot's own capacitance sensing intact.

**Status: paper design.** The numbers below come from the DropBot schematics
in this repository, hand calculation and SPICE simulation. Nothing here has
been built or measured. Section 10 lists what could not be verified.

## 1. Summary

1. **Do not sum the two signals. Switch between them.** The DropBot drives
   electrodes with up to 150 V square waves and can never put an electrode in
   a high-impedance state, so the high-frequency (HF) system has to take over
   a line completely, through a relay, while the DropBot is locked out.
2. **Leave the DropBot unmodified.** Put the relays, the protection and the
   amplifier on a new carrier board between the DropBot and the chip, fed by
   the existing [connection adapter](../../hardware/external-connection-adapter).
3. **Use the DropBot's own chip-detect interlock.** Opening the `OE`–`GND`
   loop makes the control board disconnect the high-voltage rail in hardware.
   The carrier opens that loop before any HF relay can close.
4. **Make every HF connection survive the full actuation voltage anyway.**
   A series 630 V capacitor, a series resistor and clamp diodes sit in front
   of the amplifier and the stimulus buffer. The Analog Discovery only ever
   touches op-amp pins, never a chip node.
5. **Electrode geometry decides whether a single cell is visible, not the
   electronics.** Through a standard actuation electrode the measurement sees
   the dielectric layer and almost nothing of the droplet contents. Single-cell
   detection needs a dedicated micro-electrode pair on the chip (section 3).
6. **With a PCB electrode board the add-on gets simpler.** A dedicated sense
   site on the board never connects to a DropBot channel, so most of the
   changeover relays disappear (sections 3.1 and 4.1). The price is that a
   board house's minimum gap is larger than a cell, so the signal is small
   and the measurement has to be differential. Section 3.2 checks each
   dimension against what board houses publish.

## 2. What the existing hardware does

Traced from the KiCad netlists of the submodules at the commits this
repository pins.

### 2.1 Drive path

| Stage | Parts | Notes |
|---|---|---|
| Boost converter | `U2` MAX1771, `U3` digital pot | 12 V to a DC rail, firmware limit 150 V |
| Half bridge | `U6` NCP5304, `Q5`/`Q6` IRF740 | 100 Hz – 10 kHz square wave (firmware `min_frequency`, `max_frequency`) |
| AC coupling | `C10` 100 nF, `R22` 2 MΩ, `F1` PTC, `FB2` | Net `HVAC`: zero-mean square wave |
| Output select | `U5` TLP227G-2, `U9` OR gate | `HVAC` to `VOUT`, **or** `VOUT` to Teensy pin `A0` with 51 kΩ to 3.3 V (short detection) |
| Distribution | front panel `P1.9` to `P2/P4/P6` pin 9 | One shared rail for three switching boards |
| Switching | 120 × AQW214 PhotoMOS | Each electrode is connected **either** to the rail **or** to `HVGND` |
| Return | front panel `JP1` (0 Ω, fitted) | `HVGND` is tied to `GND` |

Files: `hv-square-wave-driver.sch`, `output-select.sch` (control board),
`switches_0-19.sch`, `switches_20-39.sch` (switching board),
`dropbot-front-panel.sch`.

### 2.2 Sense path

The top plate is the sense node. Four pogo pins labelled `FB` carry it as net
`CUR_SENSE` to the control board (`feedback.sch`):

```
top plate ── F2 (PTC) ──┬── C11 1 µF ──┬── U11A (MCP6022) inverting input
                        │              │      feedback: C16 150 nF ∥ R27 100 kΩ
                     R23 1 MΩ       D4 BAV99 clamp to GND and +3.3 V
                        │
                       GND
```

This is a charge amplifier: `V_out = −V_HV · C_device / C16`. The firmware
(`src/channels.h`, `Channels::capacitance`) reads the output differentially on
`A10`/`A11`, takes the inter-quartile range of the samples as the square-wave
amplitude, and computes `C = V2 · C16 / V_HV`. It is a single-frequency
capacitance reading, taken at whatever actuation frequency is set, so it is
bounded by the 10 kHz driver.

Three calibration capacitors (`C12` 10 pF, `C13` 100 pF, `C14` 470 pF) can be
switched from `HVAC` straight to `CUR_SENSE` (`on-board-calibration.sch`).

### 2.3 Interlock and spare lines

- **`HV_OE`** is pulled up by `R36` and must be shorted to `GND` by the chip.
  While it is high, `U9` forces `U5` to disconnect `HVAC` from the switching
  boards, independent of firmware. The firmware also reports
  `output_disabled` / `output_enabled` events and runs `detect_shorts` each
  time the loop closes (`src/OutputEnableDebounce.cpp`, `src/Node.h`).
- **Four spare pogo pins** ("A–D") are wired as two nets, `CH-X1` and `CH-X2`.
  They end at front-panel connector `P5` pins 2 and 1 and connect to nothing.
  The stock connection adapter does not bring them out.
- The firmware checks output current against `output_current_limit` (25 mA)
  **once per second**, then halts.

### 2.4 Consequences for an add-on

| Fact | Consequence |
|---|---|
| An electrode is always at the rail or at ground through about 30 Ω | You cannot inject a signal on a line the DropBot still holds. The line must be disconnected first. |
| With `OE` open, the rail is connected to Teensy pin `A0` | Never drive the rail from outside. A ±1.4 V signal would forward-bias the microcontroller's input protection. |
| All 120 switches share one rail | Driving the rail would mean driving 120 off-state switch capacitances at once (several nF, unverified). Poor above about 1 MHz. |
| Off electrodes are grounded | They act as a guard around the electrode under test. Keep all channels off during HF measurements. |
| The top plate is a virtual-ground sense node | Stray capacitance from any electrode line to the `FB` line adds directly to every DropBot capacitance reading. Route `FB` away from electrode lines and re-run the DropBot calibration with the carrier installed. |
| Over-current response takes up to 1 s | Protection on the add-on must survive a sustained fault, not just a transient. |

## 3. Feasibility: what each electrode geometry can see

Estimates from `sim/tia_design.py`, assuming a 2.2 mm electrode, 5 µm
Parylene C, 180 µm gap and a PBS droplet (1.5 S/m). Replace these with your
chip's values.

**Through a standard actuation electrode.** The dielectric layer is about
27 pF and the droplet below it about 25 Ω. The droplet only starts to affect
the impedance above roughly 240 MHz (lower conductivity moves this down: about
1.6 MHz at 0.01 S/m). A 10 µm cell is 6 × 10⁻⁷ of the droplet volume and
changes the droplet resistance by about one part per million. That is not
detectable at any frequency the Analog Discovery reaches. This geometry is
still useful for droplet presence, volume and, in low-conductivity media,
bulk conductivity.

**Dedicated micro-electrode pair.** Two bare (or thinly passivated)
electrodes about 20 µm wide with a 20 µm gap, in contact with the droplet,
give roughly 30 kΩ in PBS. A cell in the gap occupies a few percent of the
sensed volume and changes the current by 0.1–1 %: a few to tens of nanoamps
on a few microamps, against a noise floor near 60 pA in a 1 kHz lock-in
bandwidth.
This is the geometry impedance cytometers use, and it is what single-cell
detection requires. The cell must also be in the gap, which is a chip design
problem (sedimentation, dielectrophoretic trapping, or a constriction).

A static single-cell reading also has to beat drift: electrolyte conductivity
changes about 2 % per °C. The usual answers are a reference electrode pair
measured differentially, and the ratio of a low frequency (about 0.5 MHz,
where the cell membrane blocks current) to a high one (5–10 MHz, where it
does not). The 10 MHz capability is what makes that ratio possible.

| Configuration | Stimulus | Sense | Top plate | Bandwidth limit | Sees |
|---|---|---|---|---|---|
| A. Vertical | one electrode | top plate | to amplifier | 2–3 MHz (top-plate capacitance) | dielectric, droplet presence |
| B. Lateral | electrode *n* | electrode *n*+1 | floating | about 10 MHz | two dielectric layers in series |
| C. Micro-electrodes | dedicated | dedicated | DropBot or floating | about 10 MHz | droplet contents, single cells |

The electronics below serve all three. Build C into the chip if single cells
are the goal.

### 3.1 Sense site on a PCB electrode board

This applies to an electrode array made as a printed circuit board, coated
with Parylene by the board house and with spin-coated Cytop on top. Numbers
are from `pcb_sense_site()` in `sim/tia_design.py`.

**The gap is set by the board house.** Two copper traces facing each other
across the minimum space form the sense pair. The copper thickness helps: the
trench between the traces is a region of nearly uniform field that a settled
cell can sit in. Finer spacing needs thinner copper, so the trench gets
shallower as the gap shrinks.

| Gap | Copper | Fabrication class | Upper bound on change from one cell: 10 / 15 / 20 µm |
|---|---|---|---|
| 127 µm | 35 µm | 2-layer prototype (5 mil) | 0.04 / 0.14 / 0.33 % |
| 100 µm | 35 µm | standard multilayer (4 mil) | 0.06 / 0.21 / 0.49 % |
| 90 µm | 35 µm | prototype multilayer (3.5 mil) | 0.07 / 0.25 / 0.58 % |
| 75 µm | 35 µm | advanced tier (3 mil) | 0.10 / 0.32 / 0.77 % |
| 50 µm | 18 µm | HDI, thin copper (2 mil) | 0.24 / 0.82 / 1.95 % |
| 30 µm | 15 µm | mSAP, substrate-like | 0.58 / 1.96 / 4.65 % |

Assumes a 150 µm facing length and a cell centred in the gap. Real values
will be several times lower. The site resistance in PBS is about 5 kΩ in
every row.

**Noise is not the limit, drift is.** At 0.2 V rms a 90 µm site carries about
40 µA, so 0.07 % is 28 nA against a 60 pA noise floor. But 0.07 % is also
what a 0.035 °C temperature change does to the electrolyte. A single pair
cannot tell the two apart. Use three electrodes:

```
   ┌─────────┐  gap  ┌──────┐  gap  ┌─────────┐
   │ SENSE A │       │ STIM │       │ SENSE B │
   └─────────┘       └──────┘       └─────────┘
```

Drive `STIM`, put one amplifier on each sense electrode, and take the complex
ratio of the two amplifier outputs. Temperature, conductivity, evaporation
and stimulus amplitude are common to both gaps and cancel. A cell in one gap
does not. The static imbalance between the gaps is measured once with a
cell-free droplet. This needs a second amplifier channel (section 6.3) and
uses both scope inputs (section 7).

**The sense traces must be bare where they face each other.**

- Parylene must not cover them. Coupling through 5 µm of Parylene is
  5.5 pF/mm², which on traces this small hides the liquid completely at every
  frequency the Analog Discovery reaches.
- Cytop should not cover them either. A 100 nm Cytop film couples at
  186 pF/mm², and a 100 µm × 150 µm trace offers about 0.02 mm². That is
  enough only near 10 MHz. Adding area to improve the coupling does not
  help: at low frequency the current then spreads over the whole added area
  instead of crossing the gap, and the cell-sized sensing volume is lost.
- The cleanest way to get there is to apply both coatings over the whole
  board and then have a window of about 0.5 mm × 0.25 mm laser-ablated over
  the three traces. Tape masking during coating is accurate to about a
  millimetre and cannot do this.
- Keep the window edge at least 50 µm inside the site, so that the
  surrounding actuation electrode keeps its Parylene. That electrode is
  grounded whenever it is off, and acts as the guard for the site.
- A bare site is hydrophilic. It will pin the droplet and may keep a small
  volume behind when the droplet leaves. Keep the window small.

### 3.2 Can a board house make it?

Checked against the geometry in this repository and against published
capability tables (JLCPCB and PCBWay, as examples of prototype services).

| Feature | Size | Finding | Verdict |
|---|---|---|---|
| Board outline | 76.0 × 50.8 mm, 1.6 mm thick | Taken from the connection adapter board, which is made to sit where the chip does | Possible |
| Pogo-pin pads | 1.9 mm square, 2.54 mm pitch, 4 columns × 17 rows on each side | Far above any minimum | Possible |
| Electrode array area | 54 mm clear between the two pad fields | The standard chip's array is about 50 mm across | Possible |
| Actuation electrodes | about 2.2 mm (standard chip: 2.2–2.35 mm, the drawing's scale is ambiguous) | Trivial | Possible |
| Gap between actuation electrodes | standard glass chip: about 30 µm | Not reproducible on a board. Expect 90–100 µm. Published board-based devices move droplets across 50–140 µm gaps, at a higher voltage | Possible, with a voltage penalty |
| Sense trace width | 100 µm | Minimum is 90 µm (JLCPCB, 4–6 layers, 1 oz) or 100 µm (PCBWay standard). JLCPCB 2-layer boards need 127 µm | Possible on 4 or more layers |
| Sense gap | 90–100 µm | Same limits as trace width | Possible |
| Sense gap | 75 µm | Advanced tier only (PCBWay lists 3 mil) | Possible, ask for a quote |
| Sense gap | 50 µm | Listed at 2 mil for part of a board, with thin base copper (down to 12 µm) | Possible at HDI cost, confirm first |
| Sense gap | 25–30 µm | Needs a semi-additive (mSAP) process. Not offered by prototype services | Not practical on the board. Use the top plate |
| Copper thickness | 35 µm finished | Standard 1 oz. Capped via-in-pad adds plating to the outer layer | Possible. Ask whether it changes the minimum space |
| Filled, capped via in every electrode | 0.15–0.2 mm drill, 0.30–0.35 mm pad | Offered as standard, at no charge on 6 or more layers at JLCPCB | Possible |
| Via pad on each sense trace | 0.35 mm | Wider than the 100 µm trace, so each trace ends in a pad outside the window | Possible, sets the site size |
| Whole sense site | about 1.0 × 1.0 mm | 21 % of a 2.2 mm electrode, 11 % of a 3.0 mm one | Fits. A 3 mm electrode at the site is more comfortable |
| Coating window | about 0.5 × 0.25 mm, placed to ±50 µm | Laser ablation of Parylene is an established process, but no vendor was checked | Unverified |
| Layer count | 6 | Standard | Possible |

Three things to raise with the board house, because the tables do not answer
them:

1. Whether the minimum space is measured at the foot or the top of the
   copper. Etched copper has sloped walls, so a 90 µm gap at the foot is
   wider at the top.
2. How much the gold finish narrows the gap. Electroless nickel grows
   sideways as well as up, by several micrometres per side.
3. Whether the gold finish will survive saline. Standard immersion gold is
   thin and porous. Ask for ENEPIG or hard gold if offered.

The actuation voltage is a separate risk. One published board-based device
needed 220 V to start droplets moving; others with smoother surfaces worked
below 100 V. The DropBot stops at about 140 V. Wider gaps, rougher copper
and thicker Parylene all push the requirement up.

### 3.3 Board layout

- Use six layers: electrodes and pads, ground, actuation routing, ground,
  sense routing, ground. This puts the three sense lines between two ground
  planes, shielded from the 150 V actuation edges, and makes capped
  via-in-pad a standard option.
- Bring the sense lines out through their own small connector. The DropBot's
  four spare pogo pins give only two nets, one short of three. Whether a
  connector clears the DropBot's chip drawer was not checked; if it does
  not, run the board outside the instrument on the connection adapter.
- Keep the top-plate (`FB`) connection away from every electrode trace.
  Capacitance between them adds to every DropBot reading.
- Use the thinnest outer copper the board house offers in the actuation
  area, to reduce the steps droplets have to cross.
- The pad pattern is in `hardware/external-connection-adapter`
  (`dropbot-v3-connection-adapter.kicad_pcb`), including the `FB`, `OE` and
  `GND` pads.
- Put several site variants on the first board: two or three gaps, plus an
  open and a shorted site for calibration.

**The cell has to reach the gap.** A 10 µm cell settles at a few micrometres
per second, so it reaches the board surface in about a minute, but anywhere
under the droplet. Options are to shrink the droplet footprint around the
site, to sweep the droplet across the site, or to pull the cell into the gap
by positive dielectrophoresis from the same electrodes (a few volts at
megahertz frequencies, which needs a low-conductivity buffer). None of these
has been evaluated here.

**Alternative: sense electrodes on the top plate.** The top plate carries
only Cytop, and thin-film gold or laser-scribed ITO on glass reaches 10–20 µm
gaps, which gives a signal ten or more times larger. It costs a patterning
step and a way to contact the top plate.

## 4. Architecture

```
 DropBot v3 (unmodified)        adapter + cables        HF sense carrier (new)                 chip
┌──────────────────────┐                        ┌────────────────────────────────────────┐
│ channels (116) ──────┼────────────────────────┼── straight through ────────────────────┼─► electrodes
│                      │                        │           NC ┌───────┐ COM             │
│ channels (4 sites) ──┼────────────────────────┼──────────────┤ K1–K4 ├─────────────────┼─► HF-site electrodes
│                      │                        │              └──┬────┘                 │
│                      │                        │           NC ┌──┼────┐ COM             │
│ FB (CUR_SENSE) ──────┼────────────────────────┼──────────────┤ K5    ├─────────────────┼─► top plate
│                      │                        │              └──┬────┘                 │
│ OE ──────────────────┼────────────────────────┼─ NC ┌────┐      │ NO contacts          │
│ GND ─────────────────┼────────────────────────┼─────┤ K0 │   jumper matrix             │
└──────────────────────┘                        │ COM └────┘   │        │                │
                                                │           STIM bus  SENSE bus          │
                                                │              │        │   ┌───────┐    │
                                                │              │        ├───┤ K6,K7 ├────┼─► micro-electrodes
                                                │              ├────────┼───┤ NO    │    │   (normally open)
                                                │          protection  protection        │
                                                │              │        │                │
                                                │           buffer     TIA               │
                                                └──────────────┼────────┼────────────────┘
                                                      W1 ──────┘  REF   └────── OUT
                                                   Analog Discovery 3: W1, scope 2, scope 1
```

The connection adapter already carries everything needed on its `J2`
connector: `FB` on pin 3, `OE` on pin 4, `GND` on pins 5 and 9. The carrier
replaces the external chip holder at the far end of the Samtec cables, so the
relays and the amplifier sit within a few centimetres of the chip and the
cable capacitance stays on the DropBot side of the relays.

### 4.1 Simplified architecture for dedicated sense electrodes

If the only HF measurement is at dedicated sense sites (configuration C),
no DropBot channel and not the top plate ever connects to the HF electronics:

```
 DropBot v3 (unmodified)            PCB electrode board                 HF front end (new)
┌──────────────────────┐        ┌──────────────────────────┐        ┌──────────────────────┐
│ 120 channels ────────┼────────┼─► actuation electrodes   │        │                      │
│ FB ──────────────────┼────────┼─► top plate              │        │                      │
│ OE, GND ─────────────┼────────┼─► OE link (2-pin header) ┼────────┼─ K0 (optional)       │
└──────────────────────┘        │                          │        │                      │
                                │   STIM ──────────────────┼────────┼─ K6 ─ prot. ─ buffer │◄─ W1
                                │   SENSE A ───────────────┼────────┼─ K7 ─ prot. ─ TIA A  ├─► scope 1
                                │   SENSE B ───────────────┼────────┼─ K8 ─ prot. ─ TIA B  ├─► scope 2
                                └──────────────────────────┘        └──────────────────────┘
```

- `K1`–`K5` and the jumper matrix are not needed.
- `K6`–`K8` stay, normally open. They keep the sense electrodes floating
  during actuation, so no actuation current flows through the bare traces
  into the droplet.
- The protection networks stay. The fault they now cover is dielectric
  breakdown on the chip, which puts the actuation voltage into the droplet
  and from there onto the sense electrodes.
- The `OE` interlock becomes optional, because no relay can connect an HF
  port to an actuated line. Fit the 2-pin header in the `OE` link anyway; it
  costs nothing and allows the interlock to be added.
- The DropBot's capacitance sensing is untouched and stays available at all
  times.

Start with the high voltage off during HF measurements. Measuring while a
droplet is held is possible in principle, but each actuation edge couples a
charge pulse into the amplifiers through the droplet.

If the chip must stay inside the DropBot, the only uncommitted contacts are
the `CH-X1`/`CH-X2` spare pogo pins, reachable at front-panel `P5` pins 2
and 1. They run unshielded beside high-voltage traces and suit configuration C
only.

## 5. How the two systems are kept apart

Five independent barriers. Any one of them failing leaves the others.

1. **Open relay contacts.** Unpowered, every relay connects the chip to the
   DropBot and isolates the HF electronics. Losing power, USB or the script
   returns the system to a plain DropBot.
2. **Hardware interlock through `OE`.** Relay `K0` breaks the `OE`–`GND`
   loop. A second pole of `K0` feeds the coil supply of every other relay, so
   no HF relay can close unless the DropBot's high-voltage rail is already
   disconnected by its own `U5`/`U9`.
3. **Software sequence.** High voltage off and all channels off before `K0`
   moves (section 8).
4. **Passive protection rated for a sustained fault.** If barriers 1–3 all
   fail and 150 V at 10 kHz reaches an HF port, the amplifier input stays
   within ±1.6 V and the buffer output within its ratings, indefinitely
   (section 6.2).
5. **Buffering.** The Analog Discovery connects only to the buffer input, the
   buffer output and the amplifier output. The worst-case casualty is an
   op-amp.

Two rules protect the DropBot from the add-on:

- Never connect an HF port to a line the DropBot is still connected to. The
  changeover relays enforce this mechanically.
- Call `turn_off_all_channels()` before entering HF mode, so that no line is
  left connected to the rail (and through it to pin `A0`).

Check that front-panel jumper `JP2` (`HV_OE` to `GND`, listed as not fitted)
is absent. If fitted it defeats barrier 2.

## 6. Circuit

### 6.1 Relays and interlock

Use non-latching DPDT signal relays with at least 500 V between open contacts
and 1 kV coil-to-contact, switched only with no voltage present. Candidates:
Omron G6K-2F-Y, TE/Axicom IM series, Panasonic TQ2. PhotoMOS relays are a
poor fit here: their off-state capacitance is typically tens of picofarads.

| Relay | COM | NC (unpowered) | NO (powered) | Coil supply |
|---|---|---|---|---|
| `K0` pole A | `OE` (adapter `J2.4`) | `GND` (adapter `J2.5`) | open | +5 V |
| `K0` pole B | +5 V coil supply | open | `V_SITE` rail | |
| `K1`–`K4` pole A | chip electrode | DropBot channel | site jumper (STIM / SENSE) | `V_SITE` |
| `K5` pole A | top plate | DropBot `FB` | site jumper (STIM / SENSE / open) | `V_SITE` |
| `K6`, `K7` pole A | micro-electrode | open | STIM bus / SENSE bus | `V_SITE` |
| `K1`–`K7` pole B | readback to a digital input (optional) | | | |

Drive each coil from an Analog Discovery digital output (3.3 V logic) through
a 2N7002 with a flyback diode, or a ULN2003A. Add a 100 kΩ pull-down on every
gate so that an unconfigured or unplugged Analog Discovery leaves all relays
released.

Keep `K5` and the `FB` trace away from `K1`–`K4`, with ground between them.
Never put `FB` and an electrode on two poles of one relay.

The micro-electrode relays are open when unpowered, so that no actuation
current flows through a bare micro-electrode into the droplet.

### 6.2 Protection network

Every wire from the HF electronics to the chip passes through the same chain,
which is the DropBot's own input protection (`F2`, `C11`, `D4`) rescaled for
high frequency:

```
chip side ──┬── CS 4.7 nF ── RS 100 Ω ──┬── electronics side
            │   630 V C0G    2 W pulse  │
          RB 1 MΩ                     clamp
            │                           │
           GND                    GND or ±5 V
```

| Part | Value | Why |
|---|---|---|
| `CS1`, `CS2` | 4.7 nF, 630 V, C0G, 1206 | Limits fault charge to 0.7 µC per edge. Blocks DC, so bare electrodes carry no bias. 34 Ω at 1 MHz. |
| `RS1`, `RS2` | 100 Ω, 2512, 2 W, pulse-withstanding | Limits peak clamp current. **Fit 330 Ω for bring-up** (section 9). |
| `RB1`, `RB2` | 1 MΩ | Defines the DC level of the electrode, discharges `CS`. |
| `D1` (sense) | BAV99, both outer pins to `GND` | Anti-parallel clamp at the virtual ground. Sees 0 V in normal use, so it neither conducts nor distorts. |
| `D2` (stimulus) | BAV99, outer pins to +5 V and −5 V | Rail clamp, so that a 1.4 V peak stimulus passes. |
| `DZ1`, `DZ2` | 5.6 V, 1 W zener on each rail | Absorbs clamp current the Analog Discovery supplies cannot sink. |

Simulated sustained fault (`sim/fault_transient.cir`: 150 V, 10 kHz, DropBot
PTC ignored, both ports faulted at once):

| | `RS` = 100 Ω | `RS` = 330 Ω |
|---|---|---|
| Amplifier input node | ±1.40 V | ±1.07 V |
| Stimulus clamp node | ±5.6 V | ±5.3 V |
| Clamp diode current | 0.90 A peak, 13 mA average | 0.38 A peak, 13 mA average |
| Power in each `RS` | 0.58 W | 0.80 W |
| Buffer output current | 0.11 A peak | 0.11 A peak |
| DropBot output current | 0.15 A rms | 0.10 A rms |

A single faulted port is slightly worse: ±1.52 V, 1.1 A peak and 0.74 W at
100 Ω.
The DropBot current is well above its 25 mA limit, so it should halt within
its one-second check, but the design does not depend on that.

With 100 Ω the diode peak current is inside the BAV99's single-pulse surge
rating but above its repetitive-peak rating (0.45 A, from memory of the
datasheet; confirm for the exact part). Treat a sustained fault at 100 Ω as a
reason to replace `D1` and `D2`. With 330 Ω everything is inside ratings.

The fault power scales as `CS · V² · f`. `CS` and `RS` also cost accuracy:
current divides between the path to the amplifier and stray capacitance to
ground at the electrode. With 300 pF of stray the amplifier sees 6 % less
current at 100 kHz, and `RS` × stray sets a pole at 5 MHz. Keep stray
capacitance low rather than shrinking the protection.

### 6.3 Transimpedance amplifier

```
                                   ┌────── Cf ──────┐
                                   ├────── Rf ──────┤
 SENSE bus ── CS1 ── RS1 ──┬───────┤                │
                           │       │   ┌─────────┐  │
                         D1 (to    └───┤−        │  │
                         GND)          │   U1    ├──┴── RT1 49.9 Ω ──► OUT (scope 1)
                                  GND ─┤+        │
                                       └─────────┘
```

`U1`: OPA656 (230 MHz gain-bandwidth, FET input, 6 nV/√Hz, ±5 V). It is
unity-gain stable and forgiving. Decouple each supply pin with 100 nF and
2.2 µF at the pin, remove ground plane under the inverting input, and keep
that node as small as the footprints allow.

Feedback settings, selected by jumper or a low-capacitance reed relay on the
output side of each network:

| Setting | `Rf` | `Cf` | Simulated −3 dB bandwidth at 20 / 100 / 300 pF source | Noise floor at 1 MHz, 100 pF | Use |
|---|---|---|---|---|---|
| 1 | 1.00 kΩ | 12 pF | 14 / 10 / 5.4 MHz | 8 pA/√Hz | Configurations A and B, anything to 10 MHz |
| 2 | 10.0 kΩ | 3.9 pF | 4.6 / 4.6 / 3.3 MHz | 4 pA/√Hz | Micro-electrodes to about 4 MHz |
| 3 | 100 kΩ | 1.2 pF | 1.5 / 1.7 / 1.3 MHz | 4 pA/√Hz | Low-conductivity media, below 1 MHz |
| C | 1 MΩ | 100 pF | flat gain `C_dut / 100 pF` above 2 kHz | | Capacitive loads (configuration A) |

Values from `sim/tia_design.py` and `sim/tia_ac.cir`, which use a two-pole
op-amp model. Peaking is under 1.5 dB in every case.

Above about 1 MHz the noise is the op-amp's voltage noise working against
the input capacitance (`e_n · 2πf · C_in`), so it rises with frequency and
with every picofarad on the input. That is the reason to mount the amplifier
at the chip.

To reach 10 MHz at 10 kΩ, fit an OPA657 in the same footprint (1.6 GHz
gain-bandwidth, stable only for noise gains of 7 or more, which this circuit
provides) with `Cf` near 0.75 pF for a 20 pF source. Do this after the OPA656 version works.

For the differential site of section 3.1, build two identical channels
(`CS`, `RS`, clamp, `U1`, feedback) with matched layout and 0.1 % feedback
resistors. In PBS the site resistance is a few kilohms. At 0.2 V rms drive,
setting 2 gives about 0.4 V rms out and reaches about 4 MHz. For 10 MHz use
setting 1 (about 40 mV out) or the OPA657 option above.

Setting C makes the amplifier a charge amplifier like the DropBot's own. With
a capacitive load a resistive setting gives an output that rises with
frequency, and 1 V into 27 pF is already 1.7 mA at 10 MHz.

### 6.4 Stimulus buffer and reference

```
 W1 ──┬────────┤ U2 BUF634A ├──┬── RT3 49.9 Ω ──► REF (scope 2)
      │        (wide-bandwidth │
   RT2 49.9 Ω       mode)      └── RO 49.9 Ω ──┬── RS2 ── CS2 ── STIM bus
      │                                        │
     GND                                    D2 (to ±5 V)
```

- `U2`: BUF634A, 250 mA, 210 MHz in wide-bandwidth mode, ±5 V. It isolates
  the generator output from the chip and from faults.
- The reference for the lock-in is the buffer output, not the generator
  setting, so the buffer's gain error and loading drop out of the ratio.
- Add a footprint for a 20 dB pad ahead of `U2`. Running the generator near
  full scale and attenuating gives a cleaner 50–300 mV stimulus than asking
  the generator for a small amplitude.
- Keep the stimulus at or below 0.3 V rms on bare micro-electrodes to stay
  clear of electrode polarisation and of stressing the cell.

### 6.5 Power and grounding

- ±5 V from the Analog Discovery supplies, each through a ferrite bead into
  10 µF and 100 nF, with `DZ1`/`DZ2` to ground.
- Relay coils take about 20 mA each. Feed them from the +5 V input ahead of
  the ferrite. Coil current is static during a measurement. Check the total
  against what your USB port lets the Analog Discovery deliver; use its
  auxiliary supply input if it is short.
- Carrier ground connects to DropBot `GND` at the adapter (`J2.5`, `J2.9`),
  because the guard electrodes and the top-plate reference return there.
- Both instruments also share ground through the PC. A high-speed USB
  isolator on the Analog Discovery removes that loop and keeps fault current
  out of the PC. Recommended, not required.

### 6.6 Calibration standards

Mirror the DropBot's on-board calibration capacitors. Provide jumper
positions between the STIM and SENSE buses, at the chip connector, for:

| Standard | Value |
|---|---|
| Open | nothing fitted |
| Short | 0 Ω |
| Load | 10.0 kΩ, 0.1 % thin film |
| Capacitor | 10 pF, C0G, 1 % |

Open/short/load compensation at this plane removes `CS`, `RS`, the cables and
the amplifier's frequency response from the result.

## 7. Analog Discovery 3 setup

| Connection | Signal |
|---|---|
| W1 | Stimulus to `U2` input |
| Scope 1 | Amplifier `OUT` |
| Scope 2 | `REF` (buffer output), or amplifier B `OUT` for a differential site (jumper) |
| V+ / V− | +5 V / −5 V |
| Digital I/O | Relay drivers, optional readbacks |

- Use the BNC adapter. Digilent specifies 30 MHz or more scope bandwidth and
  12 MHz generator bandwidth with it, against 9 MHz on the flying leads.
- Use equal, short coaxial cables on scope 1 and scope 2 and the ±2.5 V input
  range. Size the gain so the amplifier output is 0.5–1.5 V peak.
- The lock-in result is the complex ratio of scope 1 to scope 2 at the
  stimulus frequency: `Z = −Rf · V_ref / V_out`, then compensated with the
  standards of section 6.6.
- Choose stimulus frequencies that put a whole number of cycles in the
  acquisition record. A 1 ms record gives a noise bandwidth near 1 kHz;
  check the buffer depth available at the sample rate you need.
- For a differential site the result is the complex ratio of amplifier A to
  amplifier B. Record it for a cell-free droplet first; a cell shows as a
  departure from that baseline. Switch scope 2 back to `REF` for calibration
  and absolute impedance.
- WaveForms' Network Analyzer does frequency sweeps of that ratio directly.
  For time-resolved or two-tone measurements, record both channels through
  the WaveForms SDK and demodulate in software. For the low/high frequency
  ratio, generate the sum of two tones as a custom waveform and demodulate at
  both.

## 8. Mode switching sequence

Entering HF mode:

1. `proxy.hv_output_enabled = False`
2. `proxy.turn_off_all_channels()`, then confirm `proxy.state_of_channels`
   is all zero.
3. Energise `K0`. The DropBot emits `output_disabled`.
4. Wait 100 ms.
5. Energise the site relays needed. Wait 10 ms for contact bounce.
6. Measure.

Leaving HF mode:

1. Set the generator amplitude to zero.
2. Release all site relays. Wait 10 ms. Check readbacks if fitted.
3. Release `K0`. The DropBot emits `output_enabled` and runs its short
   detection across all channels.
4. Restore channel states and `proxy.hv_output_enabled = True`.

Each switch looks to the DropBot like a chip being removed and re-inserted.
Droplets are not held while the high voltage is off, so keep HF measurements
short and the chip level.

## 9. Bring-up plan

Do each step before the next. Stop if a pass condition fails.

| Step | Setup | Pass condition |
|---|---|---|
| 1 | Carrier alone, no DropBot, no chip. ±5 V applied. | Rails within ±4.8–5.2 V; amplifier output within ±20 mV. |
| 2 | Fit the 10 kΩ load standard. Sweep 50 kHz – 10 MHz. | Magnitude and bandwidth match section 6.3 for each gain setting. |
| 3 | Open, short and capacitor standards. | 10 pF reads within 5 % after compensation. |
| 4 | Fault test on the bench, `RS` = 330 Ω fitted. Drive each HF port from a signal generator through a high-voltage amplifier or a current-limited supply: 20 V, then 60 V, then 150 V square wave at 10 kHz, for 10 s each. | Amplifier input node stays within ±1.5 V on an oscilloscope; resistors warm, not hot; the circuit still passes step 2 afterwards. |
| 5 | Connect the DropBot through the adapter, chip fitted, all carrier relays released. | DropBot self-tests pass. Capacitance readings differ from the plain adapter by a constant offset only. Re-run the DropBot calibration. |
| 6 | Interlock test. With the DropBot at 20 V, energise `K0`. | `output_disabled` event; a meter on any actuated electrode reads no AC. Site relays cannot be energised with `K0` released. |
| 7 | Full sequence of section 8 with the DropBot voltage set low (20 V). | No amplifier saturation, no DropBot halt event. |
| 8 | Repeat step 7 at working voltage. Then, optionally, change `RS` to 100 Ω. | As step 7. |

## 10. Not verified

- **AQW214 off-state capacitance.** The datasheet could not be retrieved. It
  sets the load a carrier line presents and the feedthrough across a
  switching board. Measure it.
- **Resistance of the DropBot PTCs `F1` and `F2`.** Left out of the fault
  simulation, which makes the simulated fault more severe than the real one.
- **BAV99 surge ratings, relay dielectric ratings, op-amp maximum
  differential input voltage.** Quoted from memory or third-party copies.
  Confirm against the manufacturer datasheet for the exact part ordered.
- **Analog Discovery 3 supply current available on your USB port.**
- **MicroDrop's reaction to `output_disabled` in the middle of a protocol.**
  The firmware behaviour is confirmed from source; the user-interface
  behaviour is not.
- **Chip geometry.** Section 3 assumes typical values. The conclusions about
  single-cell visibility hold across any realistic actuation-electrode size,
  but the absolute numbers will move.
- The op-amp in the simulations is a generic two-pole model, not the vendor
  macromodel.
- **PCB sense site (sections 3.1–3.3).** The signal sizes are parallel-plate
  upper bounds, not field simulations. Board-house limits come from published
  capability tables found by web search, not from a quote, and those tables
  disagree in places. Laser opening of the coatings, the life of the gold
  finish in saline, the actuation voltage a coated board will need, and the
  clearance for a connector in the DropBot's chip drawer are all open.

## 11. Files

| File | Purpose | Run |
|---|---|---|
| `sim/tia_design.py` | Feedback capacitor, bandwidth, noise and signal estimates | `python3 tia_design.py` |
| `sim/tia_ac.cir` | Amplifier frequency response for each gain and source capacitance | `ngspice -b tia_ac.cir` |
| `sim/fault_transient.cir` | 150 V actuation fault into both HF ports | `ngspice -b fault_transient.cir` |
