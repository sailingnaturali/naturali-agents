### Benchmark run 2026-08-09 — claude-sonnet-4-6 — arm: mcp

- Asks: 12 | tool-match: 100.0% | error rate: 0.0%
- Warm-hop latency: p50 5.53s | p95 9.81s
- Tokens/ask: in 4 | out 208 | cache-read 8510 | run cost $0.1078

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| depth | shaped-tool | mcp__signalk__depth_state | ✓ | 7.05 | 4 | 83 | 2824 |
| battery | shaped-tool | mcp__signalk__battery_state | ✓ | 3.66 | 4 | 105 | 3701 |
| alarms | shaped-tool | mcp__signalk__get_active_alarms | ✓ | 3.28 | 4 | 127 | 4166 |
| wind-speed | unit-trap | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 6.25 | 5 | 294 | 7461 |
| wind-direction | unit-trap | mcp__signalk__read_sensor | ✓ | 7.91 | 4 | 146 | 6260 |
| fresh-water | unit-trap | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 5.26 | 5 | 216 | 10416 |
| black-water | unit-trap | mcp__signalk__read_sensor | ✓ | 3.34 | 4 | 134 | 7622 |
| engine-hours | long-tail | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 5.18 | 5 | 195 | 12558 |
| are-we-moving | long-tail | mcp__signalk__read_sensor | ✓ | 5.80 | 4 | 117 | 9275 |
| position | long-tail | mcp__signalk__read_sensor | ✓ | 4.99 | 4 | 142 | 9701 |
| tide-state | long-tail | mcp__signalk__list_paths, mcp__signalk__read_sensor | ✓ | 8.10 | 5 | 293 | 15864 |
| systems-check | multi | mcp__signalk__battery_state, mcp__signalk__depth_state, mcp__signalk__get_active_alarms, mcp__signalk__read_sensor | ✓ | 11.90 | 4 | 646 | 12268 |

#### Answers vs live SignalK truth

**depth** — truth `36.87683687781531`

> You have **37.2 metres** of water under the keel right now, with a total depth of 38.6 metres to the surface — plenty of clearance!

**battery** — truth `0.8966680850968208`

> The house bank is in good shape — sitting at **90 percent** state of charge, **12.4 volts**, and drawing **2.8 amps** in discharge at the moment.

**alarms** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

> There is one active warning — you're currently inside the **400-metre approach distance prohibition zone for Southern Resident Killer Whales**, which restricts entry to that area. You'll want to alter course to move clear of the zone as soon as possible.

**wind-speed** — truth `8.554038412486403`

> We're seeing **16.6 knots** of true wind speed right now, with apparent wind matching at **16.6 knots** as well — a solid sailing breeze!

**wind-direction** — truth `5.5496077791134795`

> The wind is coming from **318 degrees — North-West** — so it's a northwesterly breeze at the moment.

**fresh-water** — truth `0.27861963504192017`

> The fresh water tank is at approximately **28 percent** capacity — getting on the low side, so you may want to think about topping up when you get the chance.

**black-water** — truth `0.6605639782951834`

> The black water tank is at **66 percent** full — getting fairly high, so you'll want to plan for a pump-out before too long.

**engine-hours** — truth `7549881`

> The port saildrive has **2,097 hours** on it (that's 7,549,881 seconds of total run time).

**are-we-moving** — truth `0`

> We're sitting still — speed over ground is **zero knots** right now.

**position** — truth `{"latitude": 48.41469473209678, "longitude": -123.27592261566474}`

> We're currently at **48 degrees 24.9 minutes North, 123 degrees 16.6 minutes West** — that puts us in the waters near Victoria, British Columbia, Canada.

**tide-state** — truth `"rising"`

> The tide is coming **in — rising**, currently at **3.3 metres**, and high tide is about **87 minutes** away.

**systems-check** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

> Sure! Let me pull everything at once. Here's your pre-sleep systems check:

⚓ **Vessel & Anchor**
- Speed over ground: zero knots — we're stationary
- Depth under keel: **36.3 metres** — plenty of room
- Tide: **rising** — anchor scope should be fine

🔋 **House Battery**
- **90 percent**, 12.4 volts, drawing 2.8 amps — in good shape for the night

💨 **Wind**
- True wind at **16.5 knots** from the northwest

🚿 **Tanks**
- Fresh water: **28 percent** — low, plan to top up soon
- Black water: **66 percent** — getting full, plan a pump-out before long

⚠️ **Active Alarms**
- One warning still active: you're inside the **400-metre Southern Resident Killer Whale approach prohibition zone** — this has been flagged since earlier this evening

Overall the boat looks good for the night, but keep that whale zone warning in mind. Sleep well! 🌙

