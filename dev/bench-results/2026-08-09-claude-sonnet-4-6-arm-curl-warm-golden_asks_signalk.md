### Benchmark run 2026-08-09 — claude-sonnet-4-6 — arm: curl-warm

- Asks: 12 | tool-match: 0.0% | error rate: 0.0%
- Warm-hop latency: p50 5.54s | p95 22.02s
- Tokens/ask: in 4 | out 337 | cache-read 14505 | run cost $0.1618

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| depth | shaped-tool | Bash | ✗ | 5.21 | 4 | 186 | 8496 |
| battery | shaped-tool | Bash | ✗ | 7.39 | 4 | 301 | 9349 |
| alarms | shaped-tool | Bash | ✗ | 5.67 | 4 | 210 | 10601 |
| wind-speed | unit-trap | Bash | ✗ | 16.47 | 4 | 878 | 12129 |
| wind-direction | unit-trap | Bash | ✗ | 5.41 | 4 | 254 | 13841 |
| fresh-water | unit-trap | Bash | ✗ | 5.02 | 4 | 157 | 15133 |
| black-water | unit-trap | Bash | ✗ | 5.14 | 4 | 155 | 15750 |
| engine-hours | long-tail | Bash | ✗ | 5.15 | 4 | 249 | 16313 |
| are-we-moving | long-tail | Bash | ✗ | 6.78 | 4 | 166 | 17058 |
| position | long-tail | Bash | ✗ | 4.11 | 4 | 154 | 17756 |
| tide-state | long-tail | Bash | ✗ | 5.99 | 4 | 218 | 18391 |
| systems-check | multi | Bash | ✗ | 28.80 | 4 | 1118 | 19245 |

#### Answers vs live SignalK truth

**depth** — truth `37.38321442003846`

> You have **37.4 metres** of water below the keel — plenty of depth, well within the normal range.

**battery** — truth `0.8957684393831156`

> The house battery is in decent shape — it's at **90 percent** state of charge, sitting at **12.41 volts**, and currently drawing **2.85 amps** (discharging).

**alarms** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

> There's one active warning you should be aware of: **you are inside the 400-metre approach distance prohibition zone for Southern Resident Killer Whales** — entry into this area is restricted. Everything else, including wind speed and depth under the keel, is showing as normal.

**wind-speed** — truth `8.573071271409074`

> The true wind speed is **16.5 knots**, and the apparent wind is coming from almost directly astern — **173 degrees to port**, so very nearly dead behind you. Good sailing conditions!

**wind-direction** — truth `5.4453655173709645`

> The true wind is coming from **312 degrees**, which is from the northwest.

**fresh-water** — truth `0.27877993439082815`

> The fresh water tank is at **28 percent** — getting on the low side, so it might be worth thinking about topping up when you get the chance.

**black-water** — truth `0.6587589049236436`

> The black water tank is at **66 percent** — more than two thirds full, so you'll want to plan for a pump-out fairly soon.

**engine-hours** — truth `7550092`

> The port saildrive has **2,097 hours** on it.

**are-we-moving** — truth `0`

> We're sitting still — speed over ground is **zero knots**.

**position** — truth `{"latitude": 48.414706084875576, "longitude": -123.27590623675685}`

> We're at **48.415 degrees north, 123.276 degrees west** — that puts us in the waters around Victoria, British Columbia, near the southern tip of Vancouver Island.

**tide-state** — truth `"rising"`

> The tide is **coming in** — currently at **3.3 metres** above chart datum and rising.

**systems-check** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

> Sure, let me grab everything at once! Here's your overnight systems summary:

**⚓ Navigation**
- Vessel is stationary — zero knots over ground
- Depth under keel is a comfortable **37.6 metres**

**🔋 House Battery**
- **89 percent** charge at **12.40 volts**, drawing **2.84 amps** — should be fine overnight

**💨 Wind & Tide**
- True wind at **16.4 knots**
- Tide is **rising** at **3.3 metres** above chart datum — no concerns there

**🚰 Tanks**
- Fresh water at **28 percent** — worth topping up soon
- Black water at **66 percent** — plan for a pump-out before too long

**⚠️ Active Warning**
- You're still inside the **400-metre Southern Resident Killer Whale approach prohibition zone** — worth repositioning when you get the chance

Overall the boat looks good for the night — sleep well!

