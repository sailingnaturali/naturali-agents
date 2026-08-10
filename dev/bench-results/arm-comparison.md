## MCP vs CLI — tool-delivery arms

| arm | n | in+cache/ask | Δ vs cheapest | out/ask | p50 (s) | cost/ask | errors |
|-----|---|--------------|---------------|---------|---------|----------|--------|
| mcp | 12 | 8,514 | +0 | 208 | 5.53 | $0.0090 | 0% |
| curl-cold | 12 | 13,668 | +5,154 | 352 | 6.98 | $0.0150 | 0% |
| curl-warm | 12 | 14,509 | +5,995 | 337 | 5.54 | $0.0135 | 0% |
| cli | 12 | 14,929 | +6,415 | 255 | 6.73 | $0.0117 | 0% |

### Per-ask answers vs live truth

#### depth — truth `36.87683687781531`

- **mcp** (2,828 in, 83 out, 7.0s): You have **37.2 metres** of water under the keel right now, with a total depth of 38.6 metres to the surface — plenty of clearance!
- **curl-cold** (7,835 in, 207 out, 7.0s): You've got about 37.1 metres under the keel right now, so plenty of water beneath you!
- **curl-warm** (8,500 in, 186 out, 5.2s): You have **37.4 metres** of water below the keel — plenty of depth, well within the normal range.
- **cli** (7,984 in, 157 out, 4.7s): You've got 36.4 metres of water beneath the keel right now, with a total depth of 37.8 metres to the surface. Plenty of clearance!

#### battery — truth `0.8966680850968208`

- **mcp** (3,705 in, 105 out, 3.7s): The house bank is in good shape — sitting at **90 percent** state of charge, **12.4 volts**, and drawing **2.8 amps** in discharge at the moment.
- **curl-cold** (8,743 in, 473 out, 10.1s): The house battery is in good shape — it's sitting at about 90 percent state of charge with a voltage of 12.40 volts, and it's currently drawing about 2.8 amps (discharging).
- **curl-warm** (9,353 in, 301 out, 7.4s): The house battery is in decent shape — it's at **90 percent** state of charge, sitting at **12.41 volts**, and currently drawing **2.85 amps** (discharging).
- **cli** (8,574 in, 179 out, 5.0s): The house battery is in good shape — sitting at 89 percent state of charge, 12.4 volts, and drawing 3.0 amps in discharge right now.

#### alarms — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

- **mcp** (4,170 in, 127 out, 3.3s): There is one active warning — you're currently inside the **400-metre approach distance prohibition zone for Southern Resident Killer Whales**, which restricts entry to that area. You'll want to alter course to move clear of the zone as soon as possible.
- **curl-cold** (10,387 in, 405 out, 11.7s): No alarms, but there is one active warning — you're currently inside the 400-metre approach distance prohibition zone for Southern Resident Killer Whales, so you'll want to alter course to increase your distance from them. Everything else, including depth and apparent wind speed, is showing normal.
- **curl-warm** (10,605 in, 210 out, 5.7s): There's one active warning you should be aware of: **you are inside the 400-metre approach distance prohibition zone for Southern Resident Killer Whales** — entry into this area is restricted. Everything else, including wind speed and depth under the keel, is showing as normal.
- **cli** (9,163 in, 163 out, 5.3s): There is one active warning — you're inside the 400 metre approach distance prohibition for Southern Resident Killer Whales, meaning entry into this area is restricted. You'll want to alter course to increase your distance from the protected zone.

#### wind-speed — truth `8.554038412486403`

- **mcp** (7,466 in, 294 out, 6.2s): We're seeing **16.6 knots** of true wind speed right now, with apparent wind matching at **16.6 knots** as well — a solid sailing breeze!
- **curl-cold** (12,389 in, 662 out, 15.9s): We're getting about 16.5 knots of true wind, coming from roughly 317 degrees — that's a northwesterly — with the apparent wind reading the same at 16.5 knots, well within normal range.
- **curl-warm** (12,133 in, 878 out, 16.5s): The true wind speed is **16.5 knots**, and the apparent wind is coming from almost directly astern — **173 degrees to port**, so very nearly dead behind you. Good sailing conditions!
- **cli** (14,948 in, 303 out, 22.3s): You're seeing 16.5 knots of true wind speed, with the apparent wind coming in at 175 degrees off the port bow — so it's essentially straight from behind on the port side, almost a dead run.

#### wind-direction — truth `5.5496077791134795`

- **mcp** (6,264 in, 146 out, 7.9s): The wind is coming from **318 degrees — North-West** — so it's a northwesterly breeze at the moment.
- **curl-cold** (7,170 in, 32 out, 2.0s): I just pulled that data along with the wind speed — the wind is coming from roughly 317 degrees, which is a northwesterly.
- **curl-warm** (13,845 in, 254 out, 5.4s): The true wind is coming from **312 degrees**, which is from the northwest.
- **cli** (11,148 in, 162 out, 5.7s): The wind is coming from 314.7 degrees, so it's blowing in from the north-west.

#### fresh-water — truth `0.27861963504192017`

- **mcp** (10,421 in, 216 out, 5.3s): The fresh water tank is at approximately **28 percent** capacity — getting on the low side, so you may want to think about topping up when you get the chance.
- **curl-cold** (15,405 in, 185 out, 7.0s): The fresh water tank is at about 28 percent — getting on the low side, so you may want to think about topping up when you get the chance.
- **curl-warm** (15,137 in, 157 out, 5.0s): The fresh water tank is at **28 percent** — getting on the low side, so it might be worth thinking about topping up when you get the chance.
- **cli** (17,750 in, 237 out, 7.4s): The fresh water tank is at about 28 percent capacity, so you're getting low — worth keeping an eye on that and planning a top-up when you get the chance.

#### black-water — truth `0.6605639782951834`

- **mcp** (7,626 in, 134 out, 3.3s): The black water tank is at **66 percent** full — getting fairly high, so you'll want to plan for a pump-out before too long.
- **curl-cold** (8,116 in, 40 out, 2.7s): I already have that reading from my last check — the black water tank is at about 66 percent full, so worth keeping an eye on and pumping out before too long.
- **curl-warm** (15,754 in, 155 out, 5.1s): The black water tank is at **66 percent** — more than two thirds full, so you'll want to plan for a pump-out fairly soon.
- **cli** (12,487 in, 156 out, 6.0s): The black water tank is at 66 percent full — it's getting up there, so you'll want to plan a pump-out before too long.

#### engine-hours — truth `7549881`

- **mcp** (12,563 in, 195 out, 5.2s): The port saildrive has **2,097 hours** on it (that's 7,549,881 seconds of total run time).
- **curl-cold** (16,376 in, 290 out, 6.9s): The port saildrive has about 2,097 hours on it — and for reference, the starboard is just a little behind at about 2,096 hours.
- **curl-warm** (16,317 in, 249 out, 5.2s): The port saildrive has **2,097 hours** on it.
- **cli** (19,816 in, 223 out, 10.0s): The port saildrive has logged approximately 2,097 hours of total run time.

#### are-we-moving — truth `0`

- **mcp** (9,279 in, 117 out, 5.8s): We're sitting still — speed over ground is **zero knots** right now.
- **curl-cold** (17,929 in, 180 out, 6.7s): We're sitting still — speed over ground is reading zero knots.
- **curl-warm** (17,062 in, 166 out, 6.8s): We're sitting still — speed over ground is **zero knots**.
- **cli** (21,246 in, 221 out, 8.2s): We're sitting still — speed over ground is reading 0.0 knots right now.

#### position — truth `{"latitude": 48.41469473209678, "longitude": -123.27592261566474}`

- **mcp** (9,705 in, 142 out, 5.0s): We're currently at **48 degrees 24.9 minutes North, 123 degrees 16.6 minutes West** — that puts us in the waters near Victoria, British Columbia, Canada.
- **curl-cold** (18,710 in, 174 out, 5.5s): We're currently at 48 degrees 24.9 minutes North, 123 degrees 16.6 minutes West — that puts us in the waters around Victoria, British Columbia, which lines up with that Southern Resident Killer Whale restricted area warning we saw earlier.
- **curl-warm** (17,760 in, 154 out, 4.1s): We're at **48.415 degrees north, 123.276 degrees west** — that puts us in the waters around Victoria, British Columbia, near the southern tip of Vancouver Island.
- **cli** (14,780 in, 160 out, 5.9s): We're currently at 48.4147 degrees North, 123.2759 degrees West — that puts us in the waters around Victoria, British Columbia, in the southern Strait of Juan de Fuca.

#### tide-state — truth `"rising"`

- **mcp** (15,869 in, 293 out, 8.1s): The tide is coming **in — rising**, currently at **3.3 metres**, and high tide is about **87 minutes** away.
- **curl-cold** (19,366 in, 394 out, 10.1s): The tide is coming in — according to the Oak Bay station, we're currently at 3.3 metres and rising, with high water expected in about 1 hour and 27 minutes at a height of 3.37 metres.
- **curl-warm** (18,395 in, 218 out, 6.0s): The tide is **coming in** — currently at **3.3 metres** above chart datum and rising.
- **cli** (23,743 in, 254 out, 11.5s): The tide is coming in — currently at 3.3 metres and rising, with high tide arriving in about 83 minutes.

#### systems-check — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "7ed94260-ebbb-406a-b458-9602bfd98e1f", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T02:38:30.375Z"}}, "depth": {"belowK`

- **mcp** (12,272 in, 646 out, 11.9s): Sure! Let me pull everything at once. Here's your pre-sleep systems check:  ⚓ **Vessel & Anchor** - Speed over ground: zero knots — we're stationary - Depth under keel: **36.3 metres** — plenty of room - Tide: **rising** — anchor scope should be fine  🔋 **House Battery** - **90 percent**, 12.4 volts, drawing 2.8 amps — in good shape for the night  💨 **Wind** - True wind at **16.5 knots** from the northwest  🚿 **Tanks** - Fresh water: **28 percent** — low, plan to top up soon - Black water: **66 percent** — getting full, plan a pump-out before long  ⚠️ **Active Alarms** - One warning still active: you're inside the **400-metre Southern Resident Killer Whale approach prohibition zone** — this has been flagged since earlier this evening  Overall the boat looks good for the night, but keep that whale zone warning in mind. Sleep well! 🌙
- **curl-cold** (21,590 in, 1185 out, 26.3s): Sure, let me grab everything fresh all at once! Here's your overnight systems check — all readings are live:  **⚓ Safety** - Depth below keel: 36.3 metres — good and clear - Wind: 16.6 knots true from 313 degrees (north-northwesterly) — all normal - ⚠️ **Active warning:** You're still inside the 400-metre Southern Resident Killer Whale approach prohibition — worth sorting before you settle in  **🔋 Power** - House battery: 89 percent, 12.42 volts, drawing about 3.0 amps — healthy for the night  **💧 Tanks** - Fresh water: 28 percent — low, plan to top up soon - Black water: 66 percent — not urgent, but don't leave it too many more days  **🌊 Tide** - Rising, at 3.3 metres now, hitting high water in about 1 hour 26 minutes — your anchor scope should be good, but worth a quick check  Overall she's in good shape — the main things to sort are that killer whale zone warning and the fresh water level. Sleep well!
- **curl-warm** (19,249 in, 1118 out, 28.8s): Sure, let me grab everything at once! Here's your overnight systems summary:  **⚓ Navigation** - Vessel is stationary — zero knots over ground - Depth under keel is a comfortable **37.6 metres**  **🔋 House Battery** - **89 percent** charge at **12.40 volts**, drawing **2.84 amps** — should be fine overnight  **💨 Wind & Tide** - True wind at **16.4 knots** - Tide is **rising** at **3.3 metres** above chart datum — no concerns there  **🚰 Tanks** - Fresh water at **28 percent** — worth topping up soon - Black water at **66 percent** — plan for a pump-out before too long  **⚠️ Active Warning** - You're still inside the **400-metre Southern Resident Killer Whale approach prohibition zone** — worth repositioning when you get the chance  Overall the boat looks good for the night — sleep well!
- **cli** (17,512 in, 840 out, 16.7s): Here's your evening systems check:  ⚠️ **Active Warning** You're still inside the 400 metre approach prohibition zone for Southern Resident Killer Whales — worth resolving before you settle in.  **🔋 House Battery** 89 percent, 12.4 volts, drawing 3.0 amps. Good shape for the night, but keep an eye on overnight consumption.  **⚓ Depth** 36.1 metres under the keel — plenty of water beneath you.  **🌊 Tide** Rising, currently at 3.3 metres, with high tide about 83 minutes away. No concerns there.  **💨 Wind** 16.4 knots from the north-west at 313.7 degrees. Moderate breeze overnight.  **🚢 Vessel** Stationary at 0.0 knots — she's not going anywhere.  **💧 Tanks** - Fresh water at 28 percent — running low, plan a top-up soon. - Black water at 66 percent — plan a pump-out at your next opportunity.  Overall the boat looks settled for the night. The main thing to sort is that killer whale zone warning. Sleep well! 🌙

