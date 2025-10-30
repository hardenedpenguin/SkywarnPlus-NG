# SkywarnPlus-NG Sound Files

This directory contains audio files used by SkywarnPlus-NG for alert notifications and system sounds.

## Required Sound Files

These files are referenced in the default configuration and are essential for proper operation:

### **Duncecap.wav** (35KB)
- **Purpose**: Default alert sound
- **Usage**: Played when weather alerts are announced
- **Config**: `audio.alert_sound: "Duncecap.wav"`

### **Triangles.wav** (11KB)
- **Purpose**: All-clear sound
- **Usage**: Played when alerts expire or are cancelled
- **Config**: `audio.all_clear_sound: "Triangles.wav"`

### **Woodblock.wav** (12KB)
- **Purpose**: Separator sound
- **Usage**: Played between different alert announcements
- **Config**: `audio.separator_sound: "Woodblock.wav"`

## Additional Sound Files

These files provide alternative options for customization:

### **Apollo.wav** (17KB)
- **Purpose**: Alternative alert tone
- **Character**: Space-themed, rising tone

### **BeeBoo.wav** (35KB)
- **Purpose**: Alternative alert tone
- **Character**: Two-tone emergency sound

### **Beep.wav** (8KB)
- **Purpose**: Simple notification sound
- **Character**: Short, single beep

### **Boop.wav** (8KB)
- **Purpose**: Simple notification sound
- **Character**: Soft, single tone

### **Comet.wav** (26KB)
- **Purpose**: Alternative alert tone
- **Character**: Swooshing, space-themed sound

### **PianoChord.wav** (8KB)
- **Purpose**: Gentle notification sound
- **Character**: Pleasant piano chord

## Configuration

To use different sound files, edit your configuration file:

```yaml
audio:
  sounds_path: "SOUNDS"
  alert_sound: "Duncecap.wav"      # Change to any .wav file in this directory
  all_clear_sound: "Triangles.wav" # Change to any .wav file in this directory
  separator_sound: "Woodblock.wav" # Change to any .wav file in this directory
```

## File Format

- **Format**: WAV (Waveform Audio File Format)
- **Compatibility**: Compatible with Asterisk and standard audio systems
- **Quality**: Various sample rates and bit depths optimized for voice systems

## Source

These sound files are sourced from the original SkywarnPlus project and are included for compatibility and functionality.

## Adding Custom Sounds

To add your own sound files:

1. Place `.wav` files in this directory
2. Update your configuration to reference the new files
3. Ensure files are in a format compatible with your audio system
4. Test the sounds through the web dashboard or DTMF commands

## Usage in Application

These sounds are used in:
- **Alert Announcements**: When weather alerts are received and processed
- **All-Clear Notifications**: When alerts expire or are cancelled
- **DTMF Responses**: When users request information via touch-tone commands
- **System Notifications**: For various application events
