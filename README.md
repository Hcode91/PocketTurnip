# PocketTurnip

A Mesa Turnip Vulkan driver build tuned for the **Galaxy S23 (Snapdragon 8 Gen 2 for Galaxy, Adreno 740)**, packaged as an AdrenoTools zip for Winlator, GameNative-based apps, PS3/Switch emulators and anything else with a custom-driver option.

## What's different from stock Turnip

- **A740-only build**, compiled with Snapdragon 8 Gen 2 CPU tuning (`-mcpu=cortex-a715`).
- **UBWC gralloc fix**: newer Qualcomm gralloc drops a marker Mesa relies on, which can garble the picture on Android 14+.
- **Built-in frame limiter** at present time, to cut heat and battery drain in games without their own FPS cap.

## Building

Actions → **Build PocketTurnip** → Run workflow. The zip shows up under **Releases**.

- `mesa_ref`: Mesa tag (stable, default) or `main` (newest, less tested).
- `default_fps`: frame cap baked into the driver. `0` = off.

## Frame limiter

The cap is re-read once a second, so changes apply live. First match wins:

1. Environment variable `POCKETTURNIP_FPS=30`. Set it in the app's environment variables (Winlator / GameNative container settings).
2. System property: `setprop debug.pocketturnip.fps 30`. Run it through LADB or a Shizuku shell. `setprop debug.pocketturnip.fps 0` turns it off.
3. The `default_fps` the zip was built with.

It only affects apps that present frames through this driver.

## Licence

Mesa is MIT-licensed; this repo only contains build scripts and patches.
