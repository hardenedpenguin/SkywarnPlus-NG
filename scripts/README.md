# SkywarnPlus-NG Scripts

This directory contains development and utility scripts for SkywarnPlus-NG.

## Scripts

### `generate_asterisk_config.py`
Generates Asterisk configuration files for DTMF integration.

**Usage:**
```bash
# Generate rpt.conf functions for app_rpt
python3 scripts/generate_asterisk_config.py --type rpt --output /etc/asterisk/custom/skywarnplus_functions.conf

# Generate extensions.conf dialplan for standard Asterisk
python3 scripts/generate_asterisk_config.py --type extensions --output /etc/asterisk/custom/skywarnplus_extensions.conf

# Show generated config without writing to file
python3 scripts/generate_asterisk_config.py --type rpt --show
```

### `test_asterisk_integration.py`
Tests various aspects of the Asterisk integration including DTMF commands and configuration.

**Usage:**
```bash
python3 scripts/test_asterisk_integration.py
```

**Tests:**
- Configuration validation
- Sound file availability
- DTMF command processing

### `create_release.py`
Creates a production-ready tarball for deployment.

**Usage:**
```bash
python3 scripts/create_release.py
```

**Creates:**
- `skywarnplus-ng-3.0.0.tar.gz` - Production tarball
- Includes all necessary files for deployment
- Sets proper permissions on scripts

### `restart.sh`
Safely restarts the SkywarnPlus-NG server with proper process management.

**Usage:**
```bash
./scripts/restart.sh
```

**Features:**
- Graceful process termination with fallback to force kill
- Port availability checking
- Server startup verification
- Comprehensive logging and status reporting
- Health endpoint testing

### `test_pushover.py`
Tests PushOver notification functionality.

**Usage:**
```bash
python3 scripts/test_pushover.py <API_TOKEN> <USER_KEY>
```

**What it tests:**
- Simple notification delivery
- Weather alert notification with proper formatting
- Priority and sound selection based on alert severity

**To get your credentials:**
1. Create a PushOver application at: https://pushover.net/apps/build
2. Get your user key from: https://pushover.net/
3. Use the API token from your application in the test script

**Note:** You can also configure PushOver through the web dashboard at `/configuration` under the Monitoring tab.

## Requirements

These scripts require the SkywarnPlus-NG source code to be available in the parent directory. They are designed to be run from the project root directory.

## Integration with Asterisk

### For app_rpt (Repeater Nodes)
1. Generate functions: `python3 scripts/generate_asterisk_config.py --type rpt --output /etc/asterisk/custom/skywarnplus_functions.conf`
2. Include in rpt.conf: `#include /etc/asterisk/custom/skywarnplus_functions.conf`
3. Test with DTMF codes on your repeater

### For Standard Asterisk (PBX/Phone Systems)
1. Generate dialplan: `python3 scripts/generate_asterisk_config.py --type extensions --output /etc/asterisk/custom/skywarnplus_extensions.conf`
2. Include in extensions.conf: `#include custom/skywarnplus_extensions.conf`
3. Add to context: `include => skywarnplus-ng`
4. Test with DTMF codes from connected phones/devices

## Notes

- All scripts are designed to work with the default configuration in `config/default.yaml`
- Scripts can be customized by modifying the configuration file
- Ensure `skywarnplus-ng` command is in PATH for the asterisk user
