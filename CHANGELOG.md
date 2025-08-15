# Changelog

All notable changes to this project will be documented in this file.

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
