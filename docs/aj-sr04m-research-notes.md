# AJ-SR04M identification and firmware review

Checked 23 October 2026. The supplied photograph shows **AJ-SR04M** on the back of the board and a matching separate waterproof probe. It does **not** show the component side, R19 configuration, or a readable revision. The label therefore identifies the family, not an exact electrical specification or selected operating mode.

## Source documents and differences

The [AJ-SR04M original user manual, supplier-hosted PDF](https://altronics.cl/uploads/manual-aj-sr04m.pdf), pages 1–3, describes 3–5.5V supply and five R19-selected modes. Open R19 selects ordinary trigger/echo; 300kΩ selects low-power trigger/echo; 120kΩ automatic UART; 47kΩ triggered UART; a short selects ASCII. Ordinary pulse mode requires a trigger **greater than 10µs**; its older low-power mode requires **greater than 1ms**. The document states a 20cm blind area and 8m maximum. Its UART waveform uses a 120ms interval and 0x01 serial triggering. These values belong to that manual; they are not proof of the photographed board's configuration.

The manufacturer-authored [Mangze AJ-SR04M-V2.0 manual](https://offer-product.oss-cn-beijing.aliyuncs.com/product/offer/attachment/2211620956069/file/subPdf_485493_241735_20230310-173148512.pdf), pages 2, 3 and 6, specifies 3–5.5V and TRIG high at least 0.7 × VCC. At 5V, a 3.3V GPIO high is therefore **not guaranteed**. It identifies pins as VCC, Trig/RX, Echo/TX, GND and requires at least 50ms between measurements. Open R19 is ordinary pulse mode, requiring >10µs; this revision gives the same trigger duration for low-power mode. Its automatic-UART resistor is 124kΩ. It gives a 20cm blind area and a 300/400/500cm minimum/typical/maximum flat-wall detection range; page 1 itself contains differing range summaries. It must not be substituted blindly for the original module's manual.

[Shenzhen Kangtong's AJ-SR04M manufacturer listing](https://www.szkts.com/Product/5938475629.html) instead specifies 5V supply, 25cm ±1cm blind zone and 8m maximum, with timing dependent on mode. This further demonstrates that the family name alone does not identify interchangeable boards. No exact Robu AJ-SR04M revision document was found during this check.

## Concrete implications for this project

Inspection of `firmware/esp32/src/main.cpp` and `include/control_logic.h` found:

- The interrupt-based pulse capture already supports ordinary AJ-SR04M trigger/echo operation; changing to UART is unnecessary when R19 is confirmed open.
- Use a **20µs** trigger rather than exactly 10µs to satisfy the documented strict >10µs requirement. The existing 120ms sample interval exceeds the documented V2 minimum, and the 40ms timeout covers the project's existing 600cm round trip.
- Keep invalid/no echo as a sensor fault. Never turn a timeout into an empty or full reading. Existing filtering requires five valid samples after a fault; reserve protection already acts on a single credible low-level reading.
- Existing 20–600cm validity limits are project assumptions, not universally verified AJ-SR04M limits. Make bounds explicit for the installed revision and validate the actual full/empty geometry. A **30cm starting standoff** provides clearance beyond the cited 25cm ±1cm blind zone; the mount must still be tested in the actual tank.
- Firmware cannot identify R19 mode automatically or repair a supply/logic mismatch. Confirm the component side before changing resistors. Do not apply JSN-SR04T R27 mode instructions to this AJ board.

For a positively identified 3.3V-rated version, a regulated 3.3V supply permits a direct, GPIO-safe ECHO connection after checking output levels; a 5V-to-3.3V divider would reduce a 3.3V high too far. A 5V-powered board needs ECHO reduction and either documented acceptance of 3.3V TRIG or a suitable non-inverting trigger level shifter. Do not infer either arrangement from the family label alone. Keep the control PCB dry; waterproof construction refers to the probe assembly.

These are document and code findings. No physical electrical, acoustic, or hydraulic measurements were performed.
