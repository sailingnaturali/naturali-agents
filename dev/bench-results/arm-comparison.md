## MCP vs CLI — tool-delivery arms

### Per turn — what one ask costs

| arm | n | in+cache/ask | Δ vs cheapest | out/ask | p50 (s) | cost/ask | errors |
|-----|---|--------------|---------------|---------|---------|----------|--------|
| mcp | 12 | 9,148 | +0 | 245 | 9.05 | $0.0106 | 0% |
| curl-cold | 12 | 13,168 | +4,020 | 302 | 5.54 | $0.0159 | 0% |
| curl-warm | 12 | 14,881 | +5,733 | 404 | 6.40 | $0.0158 | 0% |
| cli | 12 | 13,869 | +4,720 | 242 | 5.79 | $0.0115 | 0% |

### Per session — what holding the whole conversation costs

| arm | asks | in+cache total | Δ vs cheapest | out total | session cost |
|-----|------|----------------|---------------|-----------|--------------|
| mcp | 12 | 109,779 | +0 | 2,936 | $0.1273 |
| curl-cold | 12 | 158,021 | +48,242 | 3,621 | $0.1913 |
| curl-warm | 12 | 178,577 | +68,798 | 4,847 | $0.1895 |
| cli | 12 | 166,424 | +56,645 | 2,902 | $0.1378 |

### Per-ask answers vs live truth

#### depth — truth `37.553298069437034`

- **mcp** (1,651 in, 119 out, 6.0s): You have **36.8 metres under the keel** right now, with a total water depth of 38.1 metres — plenty of clearance beneath you!
- **curl-cold** (7,810 in, 207 out, 4.9s): The depth under the keel right now is **36.3 metres** — plenty of water beneath you!
- **curl-warm** (8,555 in, 195 out, 5.0s): You have **37.4 metres** of water beneath the keel — plenty of depth, and well clear of any shoaling warnings.
- **cli** (7,987 in, 157 out, 6.9s): You've got 36.1 metres of water beneath the keel right now, with a total depth of 37.5 metres to the surface. Plenty of clearance!

#### battery — truth `0.6648809068361465`

- **mcp** (3,742 in, 140 out, 5.1s): The house bank is at **66 percent** state of charge, sitting at **12.4 volts** and currently drawing **3.0 amps** — so it's gently discharging. Not critical, but worth keeping an eye on if you're not charging soon.
- **curl-cold** (8,693 in, 257 out, 5.5s): The house battery is at **66 percent** state of charge, sitting at **12.38 volts**, and currently drawing **3.11 amps** — it's discharging, so no charging source is active right now. Worth keeping an eye on it if that continues.
- **curl-warm** (9,477 in, 413 out, 6.8s): The house battery is at **66 percent** state of charge, reading **12.38 volts**, and currently drawing **2.97 amps** — so it's in a gentle discharge state. Not critical, but worth keeping an eye on if you're not charging soon.
- **cli** (8,579 in, 179 out, 4.5s): The house battery bank is sitting at 66 percent state of charge, with a voltage of 12.4 volts and drawing 3.2 amps — so it's currently discharging. Not in bad shape, but worth keeping an eye on if you don't have charging underway soon.

#### alarms — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "e9caeadd-a45e-4dc8-bb14-d1487931d8dd", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T10:04:07.055Z"}}, "depth": {"belowK`

- **mcp** (4,256 in, 216 out, 9.2s): Yes, there are **two active alerts** you should be aware of:  1. **Warning** — You are inside the **400-metre approach prohibition zone for Southern Resident Killer Whales**. Entry into this zone is restricted — you'll need to increase distance from the whales. 2. **Alert** — You are inside the **Haro Strait and Boundary Pass Slowdown Zone** (ECHO Program). This is a voluntary programme, but you're encouraged to reduce speed to help protect the whales.  Looks like there's whale activity nearby — please adjust course or speed accordingly!
- **curl-cold** (10,146 in, 315 out, 7.6s): There are two active navigation warnings you should be aware of:  1. **Alert — Restricted Area:** You are inside the **Haro Strait and Boundary Pass Slowdown Zone**, which is part of the voluntary ECHO Program to protect whales. Please reduce speed if you haven't already.  2. **Warning — Whale Protection Zone:** You are inside the **400 metre approach distance prohibition for Southern Resident Killer Whales** — entry into this zone is restricted, so please take immediate action to move clear.  Everything else — wind speed and depth — is showing normal. The whale zone warning is the most urgent item to address right now!
- **curl-warm** (11,089 in, 455 out, 8.7s): There are no critical system alarms, but there are **two active navigation alerts** worth your attention:  1. 🔴 **Alert:** You are inside the **Haro Strait and Boundary Pass Slowdown Zone** — this is a voluntary ECHO Program speed restriction area. 2. 🟡 **Warning:** You are within the **400-metre approach distance prohibition for Southern Resident Killer Whales** — entry into this zone is restricted.  Wind and depth readings are both sitting in normal ranges, so no concerns there.
- **cli** (9,142 in, 215 out, 6.0s): There are two active alerts to be aware of. First, a warning that you're inside the 400 metre approach distance prohibition for Southern Resident Killer Whales — entry into that zone is restricted. Second, an alert that you're inside the Haro Strait and Boundary Pass Slowdown Zone under the ECHO Program, which is a voluntary speed reduction area. I'd recommend slowing down and giving any whales in the area a wide berth!

#### wind-speed — truth `8.505567414652575`

- **mcp** (8,185 in, 497 out, 12.0s): The true wind is blowing at **16.5 knots** from the **north-west**, with an apparent wind speed of **10.5 knots** coming from nearly dead astern — about **174 degrees off the port bow**. Good breeze for downwind sailing!
- **curl-cold** (12,115 in, 212 out, 8.3s): You're seeing about **16.5 knots of true wind** from roughly **317 degrees** (north-northwest), with an apparent wind speed of **10.5 knots** — comfortable sailing conditions at the moment!
- **curl-warm** (13,175 in, 699 out, 12.0s): True wind is blowing at **16.4 knots** from **312 degrees** — that's out of the northwest — with an apparent wind speed of **10.4 knots** coming from nearly dead astern. Well within comfortable sailing conditions!
- **cli** (15,325 in, 293 out, 7.9s): The true wind is blowing at 16.6 knots from the north-west, while the apparent wind is 10.6 knots coming from almost directly behind you — 176 degrees off the port bow, so essentially dead downwind. Good sailing conditions out there!

#### wind-direction — truth `5.5057088168240575`

- **mcp** (3,764 in, 101 out, 3.4s): Based on the readings I just pulled, the wind is coming from **315.7 degrees — north-west**. No need to check again, that reading is still fresh!
- **curl-cold** (6,987 in, 278 out, 5.6s): I already have that from the previous reading — the true wind direction is **317 degrees**, which puts it coming from the **north-northwest**.
- **curl-warm** (7,820 in, 106 out, 3.0s): I already have that from my last reading — the wind is coming from **312 degrees true**, which is out of the **northwest**.
- **cli** (5,745 in, 40 out, 1.8s): I already have that — the wind is coming from the north-west, at a true bearing of 314.6 degrees. No need to pull fresh data for that one!

#### fresh-water — truth `0.26465182269422555`

- **mcp** (11,977 in, 226 out, 8.9s): The fresh water tank is at approximately **26 percent** — getting on the low side, so it might be worth thinking about topping up when you get the chance!
- **curl-cold** (14,385 in, 231 out, 5.9s): The fresh water tank is at **26 percent** — it's getting fairly low, so you may want to think about topping up when you get the chance. Also worth noting, the black water tank is at **67 percent** and will need pumping out before too long.
- **curl-warm** (16,307 in, 194 out, 8.4s): The fresh water tank is at **26 percent** — getting on the low side, so you may want to think about topping up when you get the chance.
- **cli** (17,754 in, 233 out, 5.5s): The fresh water tank is at about 26 percent capacity — getting on the low side, so it might be worth thinking about topping up when you get the chance.

#### black-water — truth `0.6709267841318832`

- **mcp** (8,725 in, 159 out, 12.2s): The black water tank is at **67 percent** full — it's getting fairly full, so you'll want to plan a pump-out at your next marina stop soon!
- **curl-cold** (7,750 in, 37 out, 2.6s): I already have that from the last reading — the black water tank is at **67 percent** full, so it's worth planning a pump-out fairly soon.
- **curl-warm** (17,016 in, 173 out, 9.4s): The black water tank is at **67 percent** — getting fairly full, so you'll want to plan a pump-out soon, especially given you're currently in a restricted area near Southern Resident Killer Whales where discharge would be a concern.
- **cli** (12,495 in, 174 out, 5.0s): The black water tank is at 67 percent capacity — it's getting fairly full, so you'll want to plan a pump-out fairly soon.

#### engine-hours — truth `7569827`

- **mcp** (14,291 in, 263 out, 7.7s): The port saildrive has **2,102.7 hours** on it — quite a well-used engine! Worth keeping up with scheduled maintenance at those hours.
- **curl-cold** (15,691 in, 224 out, 4.8s): The port saildrive (Oceanvolt HighPower ServoProp 25) has **2,102.8 hours** on it. For reference, the starboard unit is sitting at **2,101.2 hours**.
- **curl-warm** (17,596 in, 226 out, 4.6s): The port saildrive has **2,102.8 hours** on it.
- **cli** (19,879 in, 256 out, 7.3s): The port saildrive has 2,102.8 hours on it — that's 7,570,107 seconds converted to hours. Getting well into the range where regular servicing checks are a good idea if they haven't been done recently!

#### are-we-moving — truth `3.1218135010543366`

- **mcp** (10,505 in, 139 out, 9.2s): You're moving — making **6.0 knots** over the ground right now!
- **curl-cold** (17,180 in, 183 out, 4.7s): You're moving — currently making **6.1 knots** over the ground.
- **curl-warm** (18,333 in, 207 out, 5.0s): We're moving — currently making **6.1 knots** over the ground.
- **cli** (14,093 in, 138 out, 4.0s): You're definitely moving — making 6.1 knots over the ground right now.

#### position — truth `{"latitude": 48.762116800647014, "longitude": -123.0519907993011}`

- **mcp** (11,045 in, 154 out, 8.8s): You're currently at **48.7621 degrees North, 123.0520 degrees West** — that puts you in the Haro Strait area between Vancouver Island and the San Juan Islands, which lines up with those whale zone alerts from earlier!
- **curl-cold** (17,906 in, 212 out, 5.3s): You're currently at **48° 45.7' North, 123° 3.1' West**, which puts you in the **Haro Strait** area between Vancouver Island and the San Juan Islands — which lines up with those restricted area alerts we saw earlier!
- **curl-warm** (19,063 in, 200 out, 6.0s): We're currently at **48° 45.7' North, 123° 3.1' West** — that puts us in **Haro Strait**, between Vancouver Island and the San Juan Islands, which lines up with those restricted area alerts we saw earlier.
- **cli** (14,571 in, 167 out, 4.5s): You're currently at 48.7621 degrees North, 123.0520 degrees West — that puts you in the Haro Strait area between Vancouver Island and the San Juan Islands, which lines up with those whale zone alarms we saw earlier!

#### tide-state — truth `"falling"`

- **mcp** (17,910 in, 382 out, 11.7s): The tide is **going out** — currently at **3.6 metres** above chart datum, with low tide arriving in about **7 hours** time.
- **curl-cold** (18,641 in, 236 out, 8.0s): The tide is going out — it's currently **falling**, with the water at **3.6 metres** above chart datum at Tumbo Channel. Low water of **0.5 metres** is expected in about **7.1 hours**.
- **curl-warm** (19,816 in, 167 out, 5.3s): The tide is currently **going out** — it's falling at our position in Haro Strait.
- **cli** (23,472 in, 263 out, 7.5s): The tide is going out — currently at 3.6 metres and falling, with low tide about 7 hours and 3 minutes away.

#### systems-check — truth `{"environment": {"wind": {"speedApparent": {"value": {"state": "normal", "message": "undefined < value < 12.8611", "method": ["visual"], "id": "e9caeadd-a45e-4dc8-bb14-d1487931d8dd", "status": {"silenced": false, "acknowledged": false, "canSilence": true, "canAcknowledge": true, "canClear": false}}, "$source": "self.notificationhandler", "timestamp": "2026-08-10T10:04:07.055Z"}}, "depth": {"belowK`

- **mcp** (13,728 in, 540 out, 14.1s): Sure! Let me grab everything at once. Here's your systems check before you turn in:  - ⚓ **Depth** — 37.3 metres under the keel. All clear. - 🔋 **Battery** — 66 percent, 12.4 volts, discharging at 3.1 amps. Keeping an eye on this overnight would be wise. - 💧 **Fresh water** — 26 percent. Low; plan to top up soon. - 🚽 **Black water** — 67 percent. Getting full; pump out at the next opportunity. - 🚢 **Speed** — 6.1 knots over the ground, so the vessel is still moving. - ⚠️ **Active alerts** — Two whale zone warnings still active (Southern Resident Killer Whale approach prohibition and the Haro Strait ECHO slowdown zone).  Overall nothing critical, but the battery, fresh water, and black water tanks all deserve attention soon. Sleep well!
- **curl-cold** (20,717 in, 1229 out, 20.6s): Let me grab fresh readings across all systems for you. Here's your evening systems check:  **⚓ Navigation** - Speed: **6.1 knots** over the ground - Depth under keel: **37.3 metres** — all clear below  **💨 Wind** - True wind: **16.7 knots** from **312 degrees** (north-northwest) - Apparent wind: **10.7 knots** — conditions are comfortable  **🌊 Tide (Tumbo Channel)** - Tide is **falling**, currently at **3.6 metres** above chart datum - Low water of **0.5 metres** in about **7 hours**  **🔋 Electrical** - House battery: **66 percent**, **12.38 volts**, drawing **3.0 amps** — still discharging with no charge source active, worth monitoring overnight  **💧 Tanks** - Fresh water: **26 percent** — getting low, plan to top up soon - Black water: **67 percent** — will need a pump-out before long  **⚠️ Active Alerts** - You're still inside the **Haro Strait ECHO Slowdown Zone** and the **400 metre Southern Resident Killer Whale exclusion zone** — make sure those are addressed before you settle in for the night.  Otherwise everything looks stable — sleep well!
- **curl-warm** (20,330 in, 1812 out, 27.1s): Here's your full systems check — good night reading! 🌙  ---  **🧭 Navigation** - Speed over ground: **6.1 knots**, heading **129 degrees true** (southeast) - Position: Haro Strait, 48° 45.7' N, 123° 3.1' W - Tide: **falling**  **⚓ Safety / Depth** - Depth below keel: **36.7 metres** ✅  **💨 Wind** - True wind speed: **16.6 knots** ✅  **🔋 Electrical** - House battery: **66 percent**, **12.42 volts** — discharging, worth putting on charge overnight ⚠️  **🚿 Tanks** - Fresh water: **26 percent** — running low, plan to top up soon ⚠️ - Black water: **67 percent** — plan a pump-out at next opportunity ⚠️  **🚨 Active Alerts** - 🔴 Inside the **Haro Strait ECHO Program Slowdown Zone** (voluntary speed restriction) - 🟡 Within **400 metres of the Southern Resident Killer Whale prohibition zone**  ---  Everything is structurally safe, but I'd recommend getting the battery on charge before you turn in. Sleep well!
- **cli** (17,382 in, 787 out, 14.3s): Sure, let me pull everything together for you! Here's your overnight systems check:  **⚓ Navigation** - Speed: 6.1 knots over the ground - Depth: 36.7 metres under the keel — plenty of water - Tide: Falling, currently at 3.6 metres, low tide in about 7 hours  **💨 Wind** - 16.4 knots from the north-west (312 degrees)  **🔋 Battery** - House bank at 66 percent, 12.4 volts, drawing 2.9 amps — it's slowly discharging, so keep an eye on it overnight  **🪣 Tanks** - Fresh water: 26 percent — running low, plan to top up soon - Black water: 67 percent — will need a pump-out before too long  **🚨 Alarms — two active** - ⚠️ You're inside the 400 metre Southern Resident Killer Whale approach prohibition zone - 🔔 You're in the Haro Strait ECHO Program voluntary slowdown zone  Overall the boat looks in good shape, but I'd flag the battery discharge and those whale zone alerts as things to be mindful of overnight. Sleep well! 🌙

