### Benchmark run 2026-08-09 — claude-sonnet-4-6 — arm: cli

- Asks: 12 | tool-match: 0.0% | error rate: 0.0%
- Warm-hop latency: p50 6.73s | p95 19.18s
- Tokens/ask: in 4 | out 255 | cache-read 14925 | run cost $0.1405

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| depth | shaped-tool | Bash | ✗ | 4.74 | 4 | 157 | 7980 |
| battery | shaped-tool | Bash | ✗ | 5.03 | 4 | 179 | 8570 |
| alarms | shaped-tool | Bash | ✗ | 5.31 | 4 | 163 | 9159 |
| wind-speed | unit-trap | Bash | ✗ | 22.26 | 5 | 303 | 14943 |
| wind-direction | unit-trap | Bash | ✗ | 5.68 | 4 | 162 | 11144 |
| fresh-water | unit-trap | Bash | ✗ | 7.43 | 5 | 237 | 17745 |
| black-water | unit-trap | Bash | ✗ | 6.04 | 4 | 156 | 12483 |
| engine-hours | long-tail | Bash | ✗ | 9.97 | 5 | 223 | 19811 |
| are-we-moving | long-tail | Bash | ✗ | 8.19 | 5 | 221 | 21241 |
| position | long-tail | Bash | ✗ | 5.85 | 4 | 160 | 14776 |
| tide-state | long-tail | Bash | ✗ | 11.51 | 5 | 254 | 23738 |
| systems-check | multi | Bash | ✗ | 16.66 | 4 | 840 | 17508 |

#### Answers vs live SignalK truth

**depth** — truth `36.38176712809626`

> You've got 36.4 metres of water beneath the keel right now, with a total depth of 37.8 metres to the surface. Plenty of clearance!

**battery** — truth `0.8922541086312807`

> The house battery is in good shape — sitting at 89 percent state of charge, 12.4 volts, and drawing 3.0 amps in discharge right now.

**alarms** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

> There is one active warning — you're inside the 400 metre approach distance prohibition for Southern Resident Killer Whales, meaning entry into this area is restricted. You'll want to alter course to increase your distance from the protected zone.

**wind-speed** — truth `8.538368036427629`

> You're seeing 16.5 knots of true wind speed, with the apparent wind coming in at 175 degrees off the port bow — so it's essentially straight from behind on the port side, almost a dead run.

**wind-direction** — truth `5.491930834175385`

> The wind is coming from 314.7 degrees, so it's blowing in from the north-west.

**fresh-water** — truth `0.2778598846352769`

> The fresh water tank is at about 28 percent capacity, so you're getting low — worth keeping an eye on that and planning a top-up when you get the chance.

**black-water** — truth `0.6591632924684293`

> The black water tank is at 66 percent full — it's getting up there, so you'll want to plan a pump-out before too long.

**engine-hours** — truth `7550207`

> The port saildrive has logged approximately 2,097 hours of total run time.

**are-we-moving** — truth `0`

> We're sitting still — speed over ground is reading 0.0 knots right now.

**position** — truth `{"latitude": 48.41466806272659, "longitude": -123.27594551387018}`

> We're currently at 48.4147 degrees North, 123.2759 degrees West — that puts us in the waters around Victoria, British Columbia, in the southern Strait of Juan de Fuca.

**tide-state** — truth `"rising"`

> The tide is coming in — currently at 3.3 metres and rising, with high tide arriving in about 83 minutes.

**systems-check** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

> Here's your evening systems check:

⚠️ **Active Warning**
You're still inside the 400 metre approach prohibition zone for Southern Resident Killer Whales — worth resolving before you settle in.

**🔋 House Battery**
89 percent, 12.4 volts, drawing 3.0 amps. Good shape for the night, but keep an eye on overnight consumption.

**⚓ Depth**
36.1 metres under the keel — plenty of water beneath you.

**🌊 Tide**
Rising, currently at 3.3 metres, with high tide about 83 minutes away. No concerns there.

**💨 Wind**
16.4 knots from the north-west at 313.7 degrees. Moderate breeze overnight.

**🚢 Vessel**
Stationary at 0.0 knots — she's not going anywhere.

**💧 Tanks**
- Fresh water at 28 percent — running low, plan a top-up soon.
- Black water at 66 percent — plan a pump-out at your next opportunity.

Overall the boat looks settled for the night. The main thing to sort is that killer whale zone warning. Sleep well! 🌙

