# Changelog

All notable changes to this project will be documented in this file.

## [1.0.85] - 2025-10-02
- improved software update user experience
- valve commands received within 5 seconds will queue so the valve can finish turning
- added seperate plant-info html page so Murad wouldn't be intimidated by the settings page.
- added date picker for dosing pump calibration

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
