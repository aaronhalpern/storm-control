# ASI FW-1000/TGFW Filter Wheel Notes

This note summarizes the ASI FW-1000 filter wheel commands used by the
`tiger.py` and `tigerModule.py` integration.

Source documentation:

- `fw-1000_filter_wheel_manual.pdf`
- `fw-1000_filter_wheel_manual.txt`
- https://asiimaging.com/docs/fw_1000

## Serial Settings

For a Tiger controller filter wheel card (TGFW):

- Baud rate: `115200`
- Data bits: `8`
- Parity: none
- Stop bits: `1`
- Flow control: none
- Command terminator: `\r\n`

The `\r\n` terminator is different from the other Tiger cards already used by
storm-control. The normal Tiger controller commands use the existing `RS232`
terminator, while FW-1000 commands are sent with a dedicated helper.

The standalone FW-1000-SA uses `9600` baud and `\n\r`.

## Basic Commands

These commands do not depend on the current wheel:

- `?`: Busy query. This is special: send only `?`, with no terminator. The
  response is a single status byte.
- `FW n`: Select active wheel `n`, usually `0` or `1`.
- `HA`: Halt all wheel movement and stop protocol execution.
- `F70`: Reset the filter wheel processor.
- `G#`: Move both wheels to protocol entry `#`, where `#` is `0..7`.
- `ST`: Start the timed protocol. This is not used for camera-fire TTL
  sequencing.

These commands apply to the currently selected wheel:

- `HO`: Home the selected wheel.
- `MP n`: Move the selected wheel to filter position `n`.
- `P# n`: Set protocol entry `#` to filter position `n`.
- `D# n`: Set the timed-protocol delay for entry `#` in milliseconds.

The `D#` delays only apply to `ST` timed protocols. They do not affect TTL
triggered sequencing from the `TRIG IN` BNC.

## HAL Behavior

Normal GUI or settings-file filter changes use:

```text
FW <wheel>
MP <position>
```

At film start, HAL preloads the protocol:

```text
HA
FW <wheel>
P0 <position 0>
P1 <position 1>
...
P7 -1
G0
```

After `G0`, the wheel is positioned at the first protocol entry. During the
film, storm-control sends no per-frame serial commands. Each TTL pulse on the
filter wheel `TRIG IN` BNC advances to the next programmed protocol position.

At film stop, HAL sends:

```text
HA
FW <wheel>
MP <pre-film position>
```

The final `MP` is skipped if `restore_on_stop` is false.

## Example Configuration

The Tiger controller configuration can include a filter wheel under `devices`:

```xml
<filter_wheel>
  <wheel type="int">0</wheel>
  <maximum type="int">8</maximum>
  <filters type="string">488,561,647,Empty</filters>
  <sequence type="string">488,561,647</sequence>
  <protocol_length type="int">8</protocol_length>
  <restore_on_stop type="boolean">True</restore_on_stop>
</filter_wheel>
```

The optional `filters` list maps names to integer filter wheel positions by
order:

```text
488   -> 0
561   -> 1
647   -> 2
Empty -> 3
```

The `sequence` may use either these names or raw integer positions, so
`488,647,Empty` and `0,2,3` are equivalent if the `filters` list above is used.
This mapping is local to the Tiger hardware configuration. If the generic HAL
filter wheel GUI also has a `<filters>` list, keep the two lists in the same
order.

The normal HAL filter wheel GUI can then request:

```xml
<filter_wheel_fn type="string">tiger_controller.filter_wheel</filter_wheel_fn>
```

Multiple wheels can be declared with distinct device names such as
`filter_wheel0` and `filter_wheel1`.

## Timing Notes

The FW-1000 manual reports a typical adjacent-filter switching time of about
60 ms with default speed settings. Frame/filter alignment must account for this
latency in the camera and illumination timing. One practical approach is to add
blank frames after trigger edges so the wheel reaches the commanded position
before useful exposure frames are recorded.

The wheel periodically re-indexes when crossing the encoder home index between
positions `0` and `1`. ASI recommends protocols that cross this index during
the cycle to avoid accumulated indexing drift.
