### Benchmark run 2026-08-10 — claude-sonnet-4-6 — arm: cli

- Asks: 12 | tool-match: 0.0% | error rate: 0.0%
- Warm-hop latency: p50 5.79s | p95 10.81s
- **Per turn** (mean/ask): in 4 | out 242 | cache-read 13864 | cache-write 522 | $0.0115
- **Per session** (12 asks): in 51 | out 2,902 | cache-read 166,373 | cache-write 6,270 | $0.1378

> `tool-match` compares observed tools to `expected_tools`, which are MCP names — a Bash arm scores 0 by construction. Grade these arms on the answer-vs-truth table below.

| ask | category | observed | match | dt (s) | in | out | cache |
|-----|----------|----------|-------|--------|----|----|-------|
| depth | shaped-tool | Bash | ✗ | 6.85 | 4 | 157 | 7983 |
| battery | shaped-tool | Bash | ✗ | 4.46 | 4 | 179 | 8575 |
| alarms | shaped-tool | Bash | ✗ | 6.03 | 4 | 215 | 9138 |
| wind-speed | unit-trap | Bash | ✗ | 7.94 | 5 | 293 | 15320 |
| wind-direction | unit-trap | — | ✗ | 1.77 | 3 | 40 | 5742 |
| fresh-water | unit-trap | Bash | ✗ | 5.54 | 5 | 233 | 17749 |
| black-water | unit-trap | Bash | ✗ | 4.97 | 4 | 174 | 12491 |
| engine-hours | long-tail | Bash | ✗ | 7.34 | 5 | 256 | 19874 |
| are-we-moving | long-tail | Bash | ✗ | 4.04 | 4 | 138 | 14089 |
| position | long-tail | Bash | ✗ | 4.55 | 4 | 167 | 14567 |
| tide-state | long-tail | Bash | ✗ | 7.52 | 5 | 263 | 23467 |
| systems-check | multi | Bash | ✗ | 14.31 | 4 | 787 | 17378 |

#### Answers vs live SignalK truth

**depth** — truth `36.50567722466937`

> You've got 36.1 metres of water beneath the keel right now, with a total depth of 37.5 metres to the surface. Plenty of clearance!

**battery** — truth `0.6606789169891907`

> The house battery bank is sitting at 66 percent state of charge, with a voltage of 12.4 volts and drawing 3.2 amps — so it's currently discharging. Not in bad shape, but worth keeping an eye on if you don't have charging underway soon.

**alarms** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "e9caeadd-a45e-4dc8-bb14-d1487931d8dd", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T10:04:07.055Z"}}, "depth": {"belowK`

> There are two active alerts to be aware of. First, a warning that you're inside the 400 metre approach distance prohibition for Southern Resident Killer Whales — entry into that zone is restricted. Second, an alert that you're inside the Haro Strait and Boundary Pass Slowdown Zone under the ECHO Program, which is a voluntary speed reduction area. I'd recommend slowing down and giving any whales in the area a wide berth!

**wind-speed** — truth `8.516300441355112`

> The true wind is blowing at 16.6 knots from the north-west, while the apparent wind is 10.6 knots coming from almost directly behind you — 176 degrees off the port bow, so essentially dead downwind. Good sailing conditions out there!

**wind-direction** — truth `5.47296428595666`

> I already have that — the wind is coming from the north-west, at a true bearing of 314.6 degrees. No need to pull fresh data for that one!

**fresh-water** — truth `0.26488410180792193`

> The fresh water tank is at about 26 percent capacity — getting on the low side, so it might be worth thinking about topping up when you get the chance.

**black-water** — truth `0.6714573687924633`

> The black water tank is at 67 percent capacity — it's getting fairly full, so you'll want to plan a pump-out fairly soon.

**engine-hours** — truth `7570112`

> The port saildrive has 2,102.8 hours on it — that's 7,570,107 seconds converted to hours. Getting well into the range where regular servicing checks are a good idea if they haven't been done recently!

**are-we-moving** — truth `3.103319992285386`

> You're definitely moving — making 6.1 knots over the ground right now.

**position** — truth `{"latitude": 48.76210574142685, "longitude": -123.05202716548163}`

> You're currently at 48.7621 degrees North, 123.0520 degrees West — that puts you in the Haro Strait area between Vancouver Island and the San Juan Islands, which lines up with those whale zone alarms we saw earlier!

**tide-state** — truth `"falling"`

> The tide is going out — currently at 3.6 metres and falling, with low tide about 7 hours and 3 minutes away.

**systems-check** — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "e9caeadd-a45e-4dc8-bb14-d1487931d8dd", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T10:04:07.055Z"}}, "depth": {"belowK`

> Sure, let me pull everything together for you! Here's your overnight systems check:

**⚓ Navigation**
- Speed: 6.1 knots over the ground
- Depth: 36.7 metres under the keel — plenty of water
- Tide: Falling, currently at 3.6 metres, low tide in about 7 hours

**💨 Wind**
- 16.4 knots from the north-west (312 degrees)

**🔋 Battery**
- House bank at 66 percent, 12.4 volts, drawing 2.9 amps — it's slowly discharging, so keep an eye on it overnight

**🪣 Tanks**
- Fresh water: 26 percent — running low, plan to top up soon
- Black water: 67 percent — will need a pump-out before too long

**🚨 Alarms — two active**
- ⚠️ You're inside the 400 metre Southern Resident Killer Whale approach prohibition zone
- 🔔 You're in the Haro Strait ECHO Program voluntary slowdown zone

Overall the boat looks in good shape, but I'd flag the battery discharge and those whale zone alerts as things to be mindful of overnight. Sleep well! 🌙

