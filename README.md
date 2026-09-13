# HA AppDaemon Irrigation Manager

Smart ET0-based lawn irrigation manager for Home Assistant, AppDaemon and a WAGO irrigation controller.

The project is a migration of an existing Home Assistant monolithic automation to a readable AppDaemon application. The first goal is **behavioural compatibility**: keep the same hydric balance and WAGO behaviour while moving the orchestration out of YAML/Jinja.

## Current features

- Daily hydric balance using ET0 × Kc.
- Effective rainfall calculation with initial loss and efficiency factor.
- Temperature/wind fallback when the Open-Meteo ET0 source is unavailable.
- Normal and heat-wave irrigation thresholds.
- Rain forecast postponement with an emergency-deficit override.
- Water quantity -> WAGO cycle count + multiplier conversion.
- Automatic departure after sunset.
- Water-restriction blocking and alternate departure offset.
- Manual hydric start that ignores future-rain postponement but keeps the deficit threshold.
- WAGO start confirmation.
- No hydric credit when a cycle was stopped/abandoned.
- 20-minute WAGO-off confirmation plus a five-minute recovery check.
- Restart recovery for an already planned future departure.

## HACS / AppDaemon layout

HACS AppDaemon repositories use an `apps/` directory. This repository contains:

```text
apps/
└── irrigation_manager/
    └── irrigation_manager.py
```

The repository also contains `hacs.json` at its root.

## AppDaemon configuration

For the original installation, all existing Home Assistant entity IDs are already the defaults. The minimal `apps.yaml` entry is therefore:

```yaml
irrigation_manager:
  module: irrigation_manager
  class: IrrigationManager
```

An example is available in [`examples/apps.yaml`](examples/apps.yaml).

Entity IDs can be overridden individually:

```yaml
irrigation_manager:
  module: irrigation_manager
  class: IrrigationManager
  entities:
    wago_active: binary_sensor.my_irrigation_active
    wago_cycles: number.my_irrigation_cycles
    wago_multiplier: number.my_irrigation_multiplier
    wago_start: button.my_irrigation_start
    wago_stop: button.my_irrigation_stop
```

## Migration strategy

This first AppDaemon version intentionally reuses the existing Home Assistant helpers. That allows the AppDaemon engine and the old automation to be compared using the same input values and the same dashboard entities.

**Do not run the old monolithic automation and AppDaemon in control mode at the same time.** During validation, disable one controller before allowing the other one to press the WAGO start button.

Once parity is validated, a later version can remove many of the compatibility helpers and expose a smaller set of Home Assistant entities.

## Original calculation preserved

The core forecast remains:

```text
ETc = ET0 × Kc
projected deficit = previous deficit + ETc - effective rain - confirmed irrigation credit
```

The projected deficit is clamped between `0` and `deficit_max`.

If the threshold is reached, the requested application is:

```text
min(projected deficit - target after irrigation, maximum application)
```

It is then converted to a total WAGO multiplier and split into up to six cycles exactly as in the original Home Assistant automation.

## Status

Initial migration under development. Validate the calculation and WAGO lifecycle on the target Home Assistant/AppDaemon installation before creating the first stable release.

## License

MIT
