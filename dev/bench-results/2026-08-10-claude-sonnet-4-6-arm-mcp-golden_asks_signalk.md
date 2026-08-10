### Benchmark run 2026-08-10 — claude-sonnet-4-6 — arm: mcp

- Asks: 12 | tool-match: 91.7% | error rate: 0.0%
- Warm-hop latency: p50 9.05s | p95 13.06s
- **Per turn** (mean/ask): in 4 | out 245 | cache-read 9144 | cache-write 674 | $0.0106
- **Per session** (12 asks): in 51 | out 2,936 | cache-read 109,728 | cache-write 8,091 | $0.1273

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| depth | shaped-tool | mcp__signalk__depth_state | ✓ | 5.99 | 4 | 119 | 1647 |
| battery | shaped-tool | mcp__signalk__battery_state | ✓ | 5.08 | 4 | 140 | 3738 |
| alarms | shaped-tool | mcp__signalk__get_active_alarms | ✓ | 9.21 | 4 | 216 | 4252 |
| wind-speed | unit-trap | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 12.02 | 5 | 497 | 8180 |
| wind-direction | unit-trap | — | ✗ | 3.43 | 3 | 101 | 3761 |
| fresh-water | unit-trap | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 8.90 | 5 | 226 | 11972 |
| black-water | unit-trap | mcp__signalk__read_sensor | ✓ | 12.17 | 4 | 159 | 8721 |
| engine-hours | long-tail | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 7.72 | 5 | 263 | 14286 |
| are-we-moving | long-tail | mcp__signalk__read_sensor | ✓ | 9.21 | 4 | 139 | 10501 |
| position | long-tail | mcp__signalk__read_sensor | ✓ | 8.83 | 4 | 154 | 11041 |
| tide-state | long-tail | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 11.67 | 5 | 382 | 17905 |
| systems-check | multi | mcp__signalk__battery_state, mcp__signalk__depth_state, mcp__signalk__get_active_alarms, mcp__signalk__read_sensor | ✓ | 14.14 | 4 | 540 | 13724 |

#### Answers vs live SignalK truth

**depth** — truth `37.553298069437034`

> You have **36.8 metres under the keel** right now, with a total water depth of 38.1 metres — plenty of clearance beneath you!

**battery** — truth `0.6648809068361465`

> The house bank is at **66 percent** state of charge, sitting at **12.4 volts** and currently drawing **3.0 amps** — so it's gently discharging. Not critical, but worth keeping an eye on if you're not charging soon.

**alarms** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "e9caeadd-a45e-4dc8-bb14-d1487931d8dd", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T10:04:07.055Z"}}, "depth": {"belowK`

> Yes, there are **two active alerts** you should be aware of:

1. **Warning** — You are inside the **400-metre approach prohibition zone for Southern Resident Killer Whales**. Entry into this zone is restricted — you'll need to increase distance from the whales.
2. **Alert** — You are inside the **Haro Strait and Boundary Pass Slowdown Zone** (ECHO Program). This is a voluntary programme, but you're encouraged to reduce speed to help protect the whales.

Looks like there's whale activity nearby — please adjust course or speed accordingly!

**wind-speed** — truth `8.505567414652575`

> The true wind is blowing at **16.5 knots** from the **north-west**, with an apparent wind speed of **10.5 knots** coming from nearly dead astern — about **174 degrees off the port bow**. Good breeze for downwind sailing!

**wind-direction** — truth `5.5057088168240575`

> Based on the readings I just pulled, the wind is coming from **315.7 degrees — north-west**. No need to check again, that reading is still fresh!

**fresh-water** — truth `0.26465182269422555`

> The fresh water tank is at approximately **26 percent** — getting on the low side, so it might be worth thinking about topping up when you get the chance!

**black-water** — truth `0.6709267841318832`

> The black water tank is at **67 percent** full — it's getting fairly full, so you'll want to plan a pump-out at your next marina stop soon!

**engine-hours** — truth `7569827`

> The port saildrive has **2,102.7 hours** on it — quite a well-used engine! Worth keeping up with scheduled maintenance at those hours.

**are-we-moving** — truth `3.1218135010543366`

> You're moving — making **6.0 knots** over the ground right now!

**position** — truth `{"latitude": 48.762116800647014, "longitude": -123.0519907993011}`

> You're currently at **48.7621 degrees North, 123.0520 degrees West** — that puts you in the Haro Strait area between Vancouver Island and the San Juan Islands, which lines up with those whale zone alerts from earlier!

**tide-state** — truth `"falling"`

> The tide is **going out** — currently at **3.6 metres** above chart datum, with low tide arriving in about **7 hours** time.

**systems-check** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "e9caeadd-a45e-4dc8-bb14-d1487931d8dd", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T10:04:07.055Z"}}, "depth": {"belowK`

> Sure! Let me grab everything at once. Here's your systems check before you turn in:

- ⚓ **Depth** — 37.3 metres under the keel. All clear.
- 🔋 **Battery** — 66 percent, 12.4 volts, discharging at 3.1 amps. Keeping an eye on this overnight would be wise.
- 💧 **Fresh water** — 26 percent. Low; plan to top up soon.
- 🚽 **Black water** — 67 percent. Getting full; pump out at the next opportunity.
- 🚢 **Speed** — 6.1 knots over the ground, so the vessel is still moving.
- ⚠️ **Active alerts** — Two whale zone warnings still active (Southern Resident Killer Whale approach prohibition and the Haro Strait ECHO slowdown zone).

Overall nothing critical, but the battery, fresh water, and black water tanks all deserve attention soon. Sleep well!

