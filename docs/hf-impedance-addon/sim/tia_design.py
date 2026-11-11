#!/usr/bin/env python3
"""Design calculator for the high-frequency transimpedance amplifier (TIA).

Prints the feedback capacitor, bandwidth and input-referred noise for each
gain setting and input capacitance, plus the expected signal levels for the
two sensing geometries discussed in ../README.md.

Only needs the Python standard library.  Edit the constants below to match
your op-amp, chip and electrode geometry, then run:

    python3 tia_design.py
"""
from math import pi, sqrt

# --- Op-amp (defaults: TI OPA656; edit for another part) -------------------
GBW = 230e6        # gain-bandwidth product [Hz]
E_N = 6e-9         # input voltage noise [V/rtHz]
C_OPAMP = 3.5e-12  # op-amp common-mode + differential input capacitance [F]

# --- Board parasitics on the summing node -----------------------------------
C_CLAMP = 3e-12    # anti-parallel clamp diodes (BAV99 pair) [F]
C_RELAY = 2e-12    # relay + pad + trace [F]

K_T = 4 * 1.380649e-23 * 300  # 4kT at 300 K

RF_VALUES = (1e3, 10e3, 100e3)
C_SOURCE_VALUES = (20e-12, 100e-12, 300e-12)  # electrode + cable capacitance


def cf_butterworth(rf, c_in, gbw=GBW):
    """Feedback capacitor for a maximally flat (Q = 0.707) response."""
    return sqrt(c_in / (pi * rf * gbw))


def f_3db(rf, c_in, gbw=GBW):
    """Closed-loop -3 dB bandwidth with the Butterworth feedback capacitor."""
    return sqrt(gbw / (2 * pi * rf * c_in))


def noise_density(rf, c_in, f):
    """Input-referred current noise density [A/rtHz] at frequency f."""
    thermal = sqrt(K_T / rf)
    en_c = E_N * 2 * pi * f * c_in     # op-amp voltage noise across C_in
    en_r = E_N / rf
    return sqrt(thermal ** 2 + en_c ** 2 + en_r ** 2)


def main():
    print("TIA feedback network (op-amp GBW = %.0f MHz, e_n = %.1f nV/rtHz)"
          % (GBW / 1e6, E_N * 1e9))
    print("%8s %8s %8s %9s %12s %12s" % ("Rf", "C_src", "Cf", "f_-3dB",
                                         "i_n @1MHz", "i_n @10MHz"))
    for rf in RF_VALUES:
        for c_src in C_SOURCE_VALUES:
            c_in = c_src + C_OPAMP + C_CLAMP + C_RELAY
            print("%6.0fk %6.0fpF %6.1fpF %6.2fMHz %9.1fpA %9.1fpA"
                  % (rf / 1e3, c_src * 1e12,
                     cf_butterworth(rf, c_in) * 1e12,
                     f_3db(rf, c_in) / 1e6,
                     noise_density(rf, c_in, 1e6) * 1e12,
                     noise_density(rf, c_in, 10e6) * 1e12))

    # --- Expected signals ----------------------------------------------------
    eps0 = 8.854e-12
    print("\nSignal estimate A: standard electrode through the dielectric")
    side, t_diel, eps_diel = 2.2e-3, 5e-6, 3.1     # electrode, Parylene C
    gap, sigma, eps_w = 180e-6, 1.5, 78             # spacer, PBS, water
    area = side ** 2
    c_diel = eps0 * eps_diel * area / t_diel
    r_drop = gap / (sigma * area)
    f_corner = 1 / (2 * pi * r_drop * c_diel)
    print("  dielectric capacitance  %.1f pF" % (c_diel * 1e12))
    print("  droplet resistance      %.1f ohm (sigma = %.2f S/m)"
          % (r_drop, sigma))
    print("  droplet becomes visible above ~%.0f MHz" % (f_corner / 1e6))
    for f in (1e5, 1e6, 1e7):
        i = 1.0 * 2 * pi * f * c_diel
        print("  1 Vrms at %5.1f MHz -> %7.1f uA rms" % (f / 1e6, i * 1e6))
    cell_d = 10e-6
    phi = (pi / 6 * cell_d ** 3) / (area * gap)
    print("  10 um cell volume fraction %.1e -> dR/R ~ %.1e (Maxwell, 1.5*phi)"
          % (phi, 1.5 * phi))

    print("\nSignal estimate B: bare coplanar micro-electrode pair in the drop")
    w = g = h = 20e-6                               # width, gap, sensed height
    r_gap = g / (sigma * w * h)                     # crude parallel estimate
    phi_b = (pi / 6 * cell_d ** 3) / (w * g * h)
    for v in (0.1, 0.3):
        i = v / r_gap
        print("  %.1f Vrms across ~%.0f kohm -> %.1f uA rms; one 10 um cell "
              "(phi = %.1f%%) changes it by up to ~%.0f nA"
              % (v, r_gap / 1e3, i * 1e6, phi_b * 100, 1.5 * phi_b * i * 1e9))
    print("  (upper bound: fringing fields in a real coplanar pair typically "
          "cut this 3-10x)")
    bw = 1e3
    c_in = 20e-12 + C_OPAMP + C_CLAMP + C_RELAY
    for f in (1e6, 10e6):
        n = noise_density(10e3, c_in, f) * sqrt(bw)
        print("  noise in %.0f Hz lock-in bandwidth at %2.0f MHz, Rf = 10k: "
              "%.0f pA rms" % (bw, f / 1e6, n * 1e12))

    pcb_sense_site()


def pcb_sense_site():
    """Sense-electrode pair made by a PCB fabricator (see ../README.md, 3.1).

    Two copper traces face each other across a gap.  The sensed volume is
    taken as the trench between them plus a fringing region half a gap high.
    The traces are coupled to the liquid through the spin-coated Cytop only
    (no Parylene over the sense site).
    """
    eps0 = 8.854e-12
    length = 150e-6            # facing length of the two traces
    t_cytop, eps_cytop = 100e-9, 2.1
    t_par, eps_par = 5e-6, 3.1
    c_cytop = eps0 * eps_cytop / t_cytop      # F/m^2
    c_par = eps0 * eps_par / t_par
    # (gap, finished copper thickness, fabrication class).  Finer spacing
    # needs thinner copper, so the trench gets shallower as the gap shrinks.
    sites = ((127e-6, 35e-6, "2-layer prototype (5 mil)"),
             (100e-6, 35e-6, "standard multilayer (4 mil)"),
             (90e-6, 35e-6, "prototype multilayer (3.5 mil)"),
             (75e-6, 35e-6, "advanced (3 mil)"),
             (50e-6, 18e-6, "HDI, thin copper (2 mil)"),
             (30e-6, 15e-6, "mSAP / substrate-like"))
    print("\nPCB sense site (facing length %.0f um)" % (length * 1e6))
    print("  coupling through 100 nm Cytop: %.0f pF/mm2; through 5 um "
          "Parylene: %.1f pF/mm2" % (c_cytop * 1e6, c_par * 1e6))
    print("%7s %6s %8s | %8s %8s %8s | %s" % ("gap", "copper", "R (PBS)",
                                             "10 um", "15 um", "20 um",
                                             "class"))
    for gap, h_cu, label in sites:
        h_eff = h_cu + gap / 2
        vol = gap * length * h_eff
        r_pbs = gap / (1.5 * length * h_eff)
        dz = [1.5 * (pi / 6 * d ** 3) / vol for d in (10e-6, 15e-6, 20e-6)]
        print("%5.0fum %4.0fum %6.1fk | %7.2f%% %7.2f%% %7.2f%% | %s"
              % (gap * 1e6, h_cu * 1e6, r_pbs / 1e3, dz[0] * 100,
                 dz[1] * 100, dz[2] * 100, label))
    print("  (dZ/Z columns: upper bound on the change from one cell of that "
          "diameter)")

    # Footprint of a three-electrode site inside an actuation electrode:
    # three parallel traces, each ending in a pad for a filled, capped via.
    trace, gap, clr, via_pad, exposed = 0.10, 0.09, 0.09, 0.35, 0.15
    site_w = 2 * via_pad + clr + 2 * clr
    site_h = 2 * via_pad + exposed + 2 * clr
    print("  three traces %.2f mm wide, %.2f mm gaps, %.2f mm via pads: site "
          "%.2f x %.2f mm" % (trace, gap, via_pad, site_w, site_h))
    for pitch in (2.2, 3.0):
        print("    = %.0f%% of a %.1f mm actuation electrode"
              % (100 * site_w * site_h / pitch ** 2, pitch))
    print("  if Cytop is left on: wetted area needed per electrode so that "
          "its reactance is under 5 kohm:")
    for f in (0.5e6, 1e6, 5e6, 10e6):
        area = 1 / (2 * pi * f * 5e3 * c_cytop)
        print("    %4.1f MHz: %.3f mm2" % (f / 1e6, area * 1e6))


if __name__ == "__main__":
    main()
