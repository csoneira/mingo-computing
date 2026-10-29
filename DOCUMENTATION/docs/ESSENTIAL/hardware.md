*Last updated: March 2026*

## Frame of reference convention and nomenclature

The coordinate system used throughout the project is defined as follows:
- **x** axis along the strip direction,
- **z** axis pointing downward (toward the expected cosmic-ray incidence),
- **y** axis completing a right-handed triad.

This frame is later associated with cardinal directions, which simplifies
transformations to equatorial or galactic coordinates for physics analyses.

![Coordinate frame: x along the detector strips, z downward toward incoming cosmic rays, and y completing the right-handed frame](../assets/figures/hardware/coordinate_frame.png)

## Geometry of the telescope

The simulation (digital twin) reproduces the same physical layout and
coordinate conventions described on this page; see the [Digital twin](../simulation/index.md) documentation for
implementation details.

- 4 parallel square RPC detectors (fig. 1):
    - Active area: approximately 30×30 cm.  The precise active dimensions are
      defined in the mechanical drawings provided with the detector kit.
    - Three 2 mm thick glass panes separated by 1 mm nylon monofilaments (fig. 2).
    - Two 1 mm gas gaps filled with R134a.
    - Interior-facing semiconducting paint on the top and bottom glass planes.
    - High voltage applied between the paint layers.
    - Each RPC has four metal readout strips (fig. 3):
        - Asymmetric widths.
        - Dual outputs (front and back) for time‑difference position
          reconstruction.
- Front-end electronics (FEE) on one corner.
- Trigger, DAQ, Control and Monitoring electronics in box between detectors 1 and 2.
- High voltage power supply between detectors 2 and 3.
- Independent R134a gas tank, injected with calibrated holes and a flow-monitor in the output for each RPC (mutom like).

![miniTRASGO four-RPC telescope overview](../assets/photos/minitrasgo/telescope_overview.webp)

_Figure 1_

---

![RPC cross-section showing the detector layers and gas gaps](../assets/figures/hardware/rpc_cross_section.png)

_Figure 2_

---

![RPC readout strips](../assets/photos/minitrasgo/readout_strips.webp)

_Figure 3_

---

## Electronics
![General miniTRASGO electronics and readout diagram](../assets/figures/hardware/electronics_system_diagram.png)

_Figure 4. General diagram._

---

- Front-end electronics (FEE): adapted from HADES designs (GSI).
    - **Daughterboards (DB):** a Hidronav module containing all active
      components on one side.  It converts the analog strip signal into an
      LVDS pulse.  The discriminator threshold is fixed but configurable;
      nominal operating value is –40 mV.
        - 4 input channels per DB (channel order BACD).
        - Inputs via MMCX connectors from the strips; charge is independent of
          incident particle energy.
    - **Motherboard (MB):** provides power (20 W nominal; 40 W recommended for
      margin) to the DBs and aggregates LVDS outputs towards the TRB. A custom
      power supply prototype is being evaluated.
        - Outputs square LVDS pulses whose width scales with deposited charge
          and whose leading edge encodes event time.  A 32‑pin connector
          carries the signals (4 strips × 4 planes × front/back = 32).
- TRB3sc (Time-of-Flight Reconstruction Board). [Official documentation](http://jspc29.x-matter.uni-frankfurt.de/docu/trb3docu.pdf). It has a FPGA (Field-Programmable Gate Array.). TRB only sends the information when its buffer is full. When the rate is very high this is not even noticeable, but when it is very low it could be that the buffer could take some seconds to be full: this will be relevant when setting the times, since the hlds will have times that are not very reliable. This can be seen in the DABC execution window (in the tmux), where the rate will be 0 for seconds, then suddenly get a slightly higer rate.
    - Coming directly from the HADES experiment.
    - Trigger selection and signal digitization.
    - 32 Time-to-Digital Converters (TDC).
    - Inputs: square LVDS (low voltage differential signal) from the DB (2x 16 pin connectors).
    - Outputs: digital timestamp and length of each square signal (USB).
- USB-ethernet board: allows the direct communication with the TRB even though the overall system is not connected to the internet. For example in the FEE test setup we do not have that web board so we need a router to connect TRB and PC aside to the internet and then one to another.
- ODroid Single Board Computer (SBC): general control and LAN communication.
- Solid State Drive (SSD): data storage.
- High Voltage power supply:
    - Common for all detectors, connected in parallel.
    - Software controlled.
    - Positive and negative voltages.
    - I2C protocol.
    - It has a low power consumption since it has only the basic control electronics and it gets the voltage from a fundamentally different way than usual sources (ask Alberto Blanco for more info).
- Enviroment sensors:
    - One inside the electronics box, one outside.
    - Temperature, atmospheric pressure, humidity.
    - I2C protocol.
- Flow meters.
    - Gas flow monitoring.
    - I2C protocol.
- Low voltage power supply for the electronics:
    - Input: 48 V
    - Outputs: 12 V, 30??? V
- Watchdog: ensures the electronics are turned on continuously.

![miniTRASGO electronics box](../assets/photos/minitrasgo/electronics_box.webp)

_Figure 5_

---

## Non-electronical components: gas flow
The gas flow is monitored only by the flow at the end, but not at the beginning.

**The camping blue valve, when "closed", still lets some gas flow.** Also take into account that once closed the gas still has 6 bars of pressure, so it will take around 15-20 min to fully stop flowing. Then the detector will just work with the gas it has, but with no pressure, so it will start to leak and loose the purity of the R134A.

When transporting the equipment, it is essential to remove the gas pipes to allow for a safe release of pressure, especially during changes in pressure due to transportation (e.g., Coimbra-Madrid route). Failure to do so could potentially alter the shape of the RPCs (Resistive Plate Chambers) if they remain closed under varying pressure conditions. In the past, a spark chamber was damaged because this precaution was not taken.
