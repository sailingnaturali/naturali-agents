### Benchmark run 2026-08-09 — claude-sonnet-4-6 — arm: curl-cold

- Asks: 12 | tool-match: 0.0% | error rate: 0.0%
- Warm-hop latency: p50 6.98s | p95 20.60s
- Tokens/ask: in 4 | out 352 | cache-read 13664 | run cost $0.1803

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| depth | shaped-tool | Bash | ✗ | 6.96 | 4 | 207 | 7831 |
| battery | shaped-tool | Bash | ✗ | 10.09 | 4 | 473 | 8739 |
| alarms | shaped-tool | Bash | ✗ | 11.65 | 4 | 405 | 10383 |
| wind-speed | unit-trap | Bash | ✗ | 15.92 | 4 | 662 | 12385 |
| wind-direction | unit-trap | — | ✗ | 2.04 | 3 | 32 | 7167 |
| fresh-water | unit-trap | Bash | ✗ | 7.00 | 4 | 185 | 15401 |
| black-water | unit-trap | — | ✗ | 2.67 | 3 | 40 | 8113 |
| engine-hours | long-tail | Bash | ✗ | 6.95 | 4 | 290 | 16372 |
| are-we-moving | long-tail | Bash | ✗ | 6.70 | 4 | 180 | 17925 |
| position | long-tail | Bash | ✗ | 5.53 | 4 | 174 | 18706 |
| tide-state | long-tail | Bash | ✗ | 10.08 | 4 | 394 | 19362 |
| systems-check | multi | Bash | ✗ | 26.32 | 4 | 1185 | 21586 |

#### Answers vs live SignalK truth

**depth** — truth `37.11930121594914`

> You've got about 37.1 metres under the keel right now, so plenty of water beneath you!

**battery** — truth `0.8944878422728708`

> The house battery is in good shape — it's sitting at about 90 percent state of charge with a voltage of 12.40 volts, and it's currently drawing about 2.8 amps (discharging).

**alarms** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

> No alarms, but there is one active warning — you're currently inside the 400-metre approach distance prohibition zone for Southern Resident Killer Whales, so you'll want to alter course to increase your distance from them. Everything else, including depth and apparent wind speed, is showing normal.

**wind-speed** — truth `8.426324194295264`

> We're getting about 16.5 knots of true wind, coming from roughly 317 degrees — that's a northwesterly — with the apparent wind reading the same at 16.5 knots, well within normal range.

**wind-direction** — truth `5.5269386332909285`

> I just pulled that data along with the wind speed — the wind is coming from roughly 317 degrees, which is a northwesterly.

**fresh-water** — truth `0.2781963860194625`

> The fresh water tank is at about 28 percent — getting on the low side, so you may want to think about topping up when you get the chance.

**black-water** — truth `0.6592888739538038`

> I already have that reading from my last check — the black water tank is at about 66 percent full, so worth keeping an eye on and pumping out before too long.

**engine-hours** — truth `7549982`

> The port saildrive has about 2,097 hours on it — and for reference, the starboard is just a little behind at about 2,096 hours.

**are-we-moving** — truth `0`

> We're sitting still — speed over ground is reading zero knots.

**position** — truth `{"latitude": 48.4147038473473, "longitude": -123.2758883379383}`

> We're currently at 48 degrees 24.9 minutes North, 123 degrees 16.6 minutes West — that puts us in the waters around Victoria, British Columbia, which lines up with that Southern Resident Killer Whale restricted area warning we saw earlier.

**tide-state** — truth `"rising"`

> The tide is coming in — according to the Oak Bay station, we're currently at 3.3 metres and rising, with high water expected in about 1 hour and 27 minutes at a height of 3.37 metres.

**systems-check** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

> Sure, let me grab everything fresh all at once! Here's your overnight systems check — all readings are live:

**⚓ Safety**
- Depth below keel: 36.3 metres — good and clear
- Wind: 16.6 knots true from 313 degrees (north-northwesterly) — all normal
- ⚠️ **Active warning:** You're still inside the 400-metre Southern Resident Killer Whale approach prohibition — worth sorting before you settle in

**🔋 Power**
- House battery: 89 percent, 12.42 volts, drawing about 3.0 amps — healthy for the night

**💧 Tanks**
- Fresh water: 28 percent — low, plan to top up soon
- Black water: 66 percent — not urgent, but don't leave it too many more days

**🌊 Tide**
- Rising, at 3.3 metres now, hitting high water in about 1 hour 26 minutes — your anchor scope should be good, but worth a quick check

Overall she's in good shape — the main things to sort are that killer whale zone warning and the fresh water level. Sleep well!

