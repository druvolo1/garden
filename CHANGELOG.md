# Changelog

All notable changes to this project will be documented in this file.

## [1.0.92] - 2026-07-26
- starting a plant no longer requires the server: if the server is not in use, or is unreachable, the plant is saved to this device with a locally generated id and the dialog says so. Previously the form was only offered when server_enabled was false, yet the handler demanded credentials and a successful cloud POST, so it could never succeed in the one case it was shown
- the local save is now checked rather than assumed, so a failure to write settings is reported instead of being silently swallowed

## [1.0.91] - 2026-07-26
- settings page "Apply Update" now works on devices whose working tree has local modifications; it delegates to the same reset-then-pull used by /api/system/apply_update instead of running a bare git pull that git refuses
- the update modal now waits for the real result, shows the actual error on failure, and only reloads on success (it previously ran a fake progress bar to 100% and reloaded regardless, so a failed update looked identical to a successful one)
- local JSONL logs are trimmed to the last 14 days, checked on boot and once a day
- added git update and apply-dry-run diagnostic scripts

## [1.0.90] - 2026-05-18
- version bump only, no functional change

## [1.0.89] - 2026-05-18
- granular valve changes now emit as `valve_update` instead of being sent under the `status_update` event name with a truncated payload, which could be misread by clients expecting a full status
- aggregator socket.io client now connects with an explicit `/status` namespace and a 5 second wait timeout

## [1.0.88] - 2025-11-08
- fixed auto dosing not working from improper water sensor interpretation
- added Application Restart and PC Reboot on the settings page on the Application Update Card. 
- added logic for continuous retry of server connection if configured and server is unreachable

## [1.0.87] - 2025-10-16
- if auto fill is set it will not trigger during draining

## [1.0.86] - 2025-10-12
- added calibration mode to bypass ph logic for filtering readings

## [1.0.85] - 2025-10-02
- improved software update user experience
- valve commands received within 5 seconds will queue so the valve can finish turning
- added seperate plant-info html page so Murad wouldn't be intimidated by the settings page.
- added date picker for dosing pump calibration
- added counters for ph up and down pump to track usage.

## [1.0.84] - 2025-09-29
- inverted water sensor feedback to be more logical in backend code

## [1.0.83] - 2025-09-22
- fixed error loading auto dosing loop time at start
- fixed first run script that was referencing old gunicorn config file no longer being used
- added ahavi mdns to first run script to fix dns issues in the virtual environment.

## [1.0.82] - 2025-09-21
- added option for "Remote Feeding" in settings
- fixed websocket for PH to be rouded to 2 decimal places instead of 3 thus reducing socket updates

## [1.0.81] - 2025-09-21
- added 2 hours timeout for "Feeding in Progress"

## [1.0.80] - 2025-09-21
- added API command to toggle valve by name

## [1.0.79] - 2025-09-20
- added additional info container on main page

## [1.0.78] - 2025-09-20
- added "feeding in progress" to prevent ph from adjusting during feeding. Also prevents notifications from being sent.
- modified index page to have expaint HTML container for "feeding in progress" which disables notifications and auto valve triggering"
- added ability to save pump calibration dates for dosing pumps

## [1.0.77] - 2025-08-15
- fixed install script for permissions

## [1.0.76] - 2025-08-14

### Added
- Logic to prevent pH dosing if none of the water sensors detect water.
- Plant name color change based on pH range: green for good, red for high or low.
- Modified log logic to support multiple log files for different things.
- 6-hour logging interval to track pH.
- system will not dispense ph up/down if the bucket is empty
- added color coding to index page to visually indicate if pH is within range
