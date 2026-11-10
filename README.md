# Firewalla MSP for Home Assistant

Brings your Firewalla box into Home Assistant through the [Firewalla MSP API](https://docs.firewalla.net/) (v2). Cloud polling; needs a Firewalla MSP account with your box linked and a personal access token.

## What you get

Per Firewalla box (one HA device):

| Entity | What it shows |
|---|---|
| `binary_sensor.<box>_online` | Box online in MSP (attributes: public IP, mode) |
| `sensor.<box>_active_alarms` | Active (unarchived) alarms among the latest 200 |
| `sensor.<box>_devices_online` / `_devices_offline` | Device counts |
| `sensor.<box>_latest_alarm` | Timestamp of the newest alarm; type, message, device and WAN details as attributes |
| `sensor.<box>_public_ip`, `_firmware` | Diagnostics |
| `switch.<box>_rule_*` | One per rule: **on = active, off = paused**. Created disabled; enable the ones you want |

Optional, chosen in **Configure**: a connectivity `binary_sensor` per network device you select (e.g. Powerwall gateway, Hunter Douglas Platinum gateway, Homebridge, Starling hub).

### Event: `firewalla_msp_alarm`

Fired once for every new alarm (history is not replayed after a restart). Data:

`aid, type, type_name, message, ts, box_gid, box_name, device_id, device_name, device_ip, remote_ip, remote_domain, remote_category, direction` and, for Internet Connectivity alarms (type 15), `wan_name, wan_status, wan_active, wan_switched`.

Alarm types: 1 Security Activity · 2 Abnormal Upload · 3 Large Bandwidth · 4 Data Plan · 5 New Device · 6 Device Back Online · 7 Device Offline · 8 Video · 9 Gaming · 10 Porn · 11 VPN Activity · 12 VPN Restored · 13 VPN Error · 14 Open Port · 15 Internet Connectivity · 16 Large Upload.

## Install

1. HACS → ⋮ → Custom repositories → add `https://github.com/Walschots/hacs-firewalla-msp`, type **Integration**.
2. Download **Firewalla MSP**, restart Home Assistant.
3. Settings → Devices & services → Add integration → **Firewalla MSP**.
4. Enter your MSP domain (`yourname.firewalla.net`) and a token from MSP → Account Settings → API.
5. Open **Configure** to pick devices to track and set the poll interval (default 120 s, minimum 60 s).

## Example automations

Change `notify.mobile_app_iphone_pascal` to your phone's notify service.

**New device joined the network**

```yaml
alias: Firewalla - new device
triggers:
  - trigger: event
    event_type: firewalla_msp_alarm
    event_data:
      type: 5
actions:
  - action: notify.mobile_app_iphone_pascal
    data:
      title: New device on the network
      message: "{{ trigger.event.data.message }}"
```

**WAN failover (Comcast ↔ Starlink)**

```yaml
alias: Firewalla - internet connectivity change
triggers:
  - trigger: event
    event_type: firewalla_msp_alarm
    event_data:
      type: 15
actions:
  - action: notify.mobile_app_iphone_pascal
    data:
      title: "Internet: {{ trigger.event.data.wan_name }} {{ trigger.event.data.wan_status }}"
      message: >
        {{ trigger.event.data.message }}
        {% if trigger.event.data.wan_switched %}(switched over){% endif %}
```

**Security alarms only (types 1, 2, 14, 16)**

```yaml
alias: Firewalla - security alarm
triggers:
  - trigger: event
    event_type: firewalla_msp_alarm
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.type in [1, 2, 14, 16] }}"
actions:
  - action: notify.mobile_app_iphone_pascal
    data:
      title: "Firewalla: {{ trigger.event.data.type_name }}"
      message: "{{ trigger.event.data.message }}"
```

**A tracked hub has been offline for 10 minutes**

```yaml
alias: Firewalla - hub offline
triggers:
  - trigger: state
    entity_id: binary_sensor.firewalla_platinum_gateway   # your tracked device
    to: "off"
    for: "00:10:00"
actions:
  - action: notify.mobile_app_iphone_pascal
    data:
      message: "{{ trigger.to_state.name }} has been offline for 10 minutes"
```

**Pause a rule for an hour**

```yaml
alias: Pause gaming block for 1 hour
sequence:
  - action: switch.turn_off
    target:
      entity_id: switch.firewalla_rule_block_gaming
  - delay: "01:00:00"
  - action: switch.turn_on
    target:
      entity_id: switch.firewalla_rule_block_gaming
```

## Notes and limits

- **Rules need MSP 2.7.0+.** If `GET /v2/rules` fails, the integration logs a warning and skips rule switches; everything else keeps working.
- **Rule IDs change if a rule is edited** (the API has no edit endpoint, so edits recreate the rule). The old switch becomes unavailable and a new one appears disabled. Reference rules by entity in automations and re-point after edits.
- Pause has no duration in the official API; a paused rule stays paused until resumed. Use a script with a delay (above).
- Polling every 120 s means alarms arrive within about two minutes, not instantly.
- Rate limits: alarms and devices are polled every interval, boxes every 10 minutes and rules every 30 minutes (or right after you toggle a rule). On HTTP 429 the integration backs off (honouring `Retry-After`, otherwise 2 → 4 → … → 30 minutes) and keeps the last known values instead of going unavailable.
- The token is stored in the HA config entry. If it's revoked, HA prompts you to re-authenticate.

## License

MIT
