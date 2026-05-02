# Apple Shortcut Setup Guide

Complete guide to create a "Log Food" Siri shortcut for voice-based food logging.

---

## Prerequisites

✅ Tailscale installed on Mac (running)  
✅ Tailscale installed on iPhone (connected)  
✅ Food Log API running on Mac  
✅ Your Machine DNS: **`matthews-mbp.deer-regulus.ts.net`**

---

## DNS Configuration

**Why machine-specific DNS?**
- `matthews-mbp.deer-regulus.ts.net` explicitly targets your Mac
- More reliable than tailnet-level DNS
- Future-proof if you add more machines to your tailnet
- Guarantees requests always go to the correct machine

---

**What it does:**
1. Activates when you say "Hey Siri, Log Food"
2. Prompts you to dictate your food entry
3. Sends the text to your Food Log API for OpenAI estimation
4. Logs immediately with nutrition breakdown
5. Shows "Food Logged! ✅" confirmation

---

## Part 1: Create the Basic Shortcut

### Step 1: Open Shortcuts App
- Open the **Shortcuts** app on your iPhone
- Tap the **"+"** button (top right) to create a new shortcut

### Step 2: Add Dictate Text Action
1. Tap **"Add Action"**
2. Search for **"Dictate Text"**
3. Tap to add it
4. Configure:
   - **Language:** English (or your preference)
   - **Stop Listening:** After Pause *(default)*

### Step 3: Add Get Contents of URL Action
1. Tap the **"+"** button below Dictate Text
2. Search for **"Get Contents of URL"**
3. Tap to add it
4. Configure the URL action:

**URL:** `http://matthews-mbp.deer-regulus.ts.net:8000/log`

**Method:** `POST`

**Headers:**
- Tap "Add new field" → Select "Header"
- Key: `Content-Type`
- Value: `text/plain`

**Request Body:** `Dictated Text`
- Tap on the text field
- Tap the variable button (looks like a pill/token)
- Select **"Dictated Text"** from the previous step

### Step 4: Add Response Handling
1. Tap the **"+"** button
2. Search for **"Show Notification"**
3. Tap to add it
4. Configure:
   - Title: `Food Logged! ✅`
   - Body: Tap variable → Select `Contents of URL`

### Step 5: Name Your Shortcut
1. Tap the name at the top (probably "New Shortcut")
2. Change it to: **"Log Food"**
3. Tap **"Done"** (top right)

---

## Part 2: Enable Siri Integration

### Step 1: Add to Siri
1. Find your "Log Food" shortcut in the list
2. Tap the **(···)** menu button on the shortcut card
3. Tap the **Details** button (top right)
4. Tap **"Add to Siri"**
5. Record the phrase: **"Log Food"**
6. Tap **"Done"**

### Step 2: Optional - Add to Home Screen
While in the shortcut details:
1. Tap **"Add to Home Screen"**
2. Choose an icon (optional)
3. Tap **"Add"**

---

## Testing Your Shortcut

### Test 1: Manual Test
1. Open the Shortcuts app
2. Tap your "Log Food" shortcut
3. When prompted, say: **"I had a banana and coffee for breakfast"**
4. Wait for response
5. You should see a "Food Logged! ✅" notification

### Test 2: Siri Test
1. Say: **"Hey Siri, Log Food"**
2. Siri will prompt: *"What would you like to say?"*
3. Say: **"Two eggs and toast"**
4. Wait for confirmation

### Test 3: Check the Database
1. Open Safari on iPhone
2. Go to: `http://matthews-mbp.deer-regulus.ts.net:8000`
3. Tap **"Today"** tab
4. Verify your entries appear

---

## Alternative: Simplified Display

If you want to skip the notification and just see the raw response:

1. **Dictate Text** (as configured above)
2. **Get Contents of URL** (as configured above)
3. **Show Result**

This shows the API JSON response directly. Less polished, but works fine if you prefer minimal UI.

---

## Troubleshooting

### "Cannot Connect to Server"
- **Check:** Is Tailscale running on iPhone? (green indicator)
- **Check:** Is Tailscale running on Mac? Run: `tailscale status`
- **Check:** Is your Food Log server running? Test: `http://matthews-mbp.deer-regulus.ts.net:8000/health`

### "Request Failed" or Timeout
- **Check:** Your Mac isn't asleep (must be awake to serve requests)
- **Check:** Your machine DNS is correct: `matthews-mbp.deer-regulus.ts.net`
- **Try:** Restart Tailscale on iPhone (toggle off/on)

### Siri Not Recognizing Command
- **Check:** Did you add the shortcut to Siri?
- **Try:** Re-record the Siri phrase
- **Try:** Say "Hey Siri, shortcuts" to see available shortcuts

### Dictation Stops Too Early
- In dictate action, change "Stop Listening" to "After 30 seconds" or "On Tap"

### Response Shows Raw JSON
- This is normal if you're using the simple version
- Upgrade to the version with notification formatting

---

## Quick Reference Card

```
┌─────────────────────────────────────┐
│  Say: "Hey Siri, Log Food"         │
│                                     │
│  Examples:                          │
│  • "I had a banana and coffee"      │
│  • "Two eggs with toast"            │
│  • "Large burger from Five Guys"    │
│  • "Chicken breast, broccoli, rice" │
│                                     │
│  Wait for: "Food Logged! ✅"        │
└─────────────────────────────────────┘
```

---

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/log` | POST | Log food entry immediately (used by shortcut) |
| `/log/today` | GET | View today's entries (in browser) |
| `/health` | GET | Test connection |
| `/clarify` | POST | **DEPRECATED** (410 Gone) - All entries now log immediately |

---

## What Happens Behind the Scenes

1. **You speak** → Siri/Dictate converts to text
2. **Shortcut sends** → Plain text POST to your Mac
3. **Mac processes** → OpenAI directly estimates calories and macros
4. **Immediate logging** → Stored with reasoning and full OpenAI response
5. **Response returned** → Shortcut shows "Food Logged! ✅" notification

---

## Privacy & Security Notes

✅ **All data stays local** - SQLite on your Mac  
✅ **Encrypted in transit** - Tailscale VPN  
✅ **Private network** - Only your devices can connect  
✅ **No cloud storage** - Except OpenAI API for parsing  
⚠️ **OpenAI sees** - Your food text (for parsing only)  

---

## Battery & Network Considerations

- **Mac must be awake** to respond (use Energy Saver settings)
- **Tailscale uses minimal battery** on iPhone
- **Works over cellular** - as long as both devices have internet
- **No data limits** - Tailscale free tier is unlimited

---

## Next Steps

After you've created and tested the shortcut:

1. ✅ Use it for a few days to get comfortable
2. ✅ Check your logs in the web UI regularly
3. ✅ Review entries for accuracy (edit via UI if needed)
4. ✅ Consider adding authentication if sharing your Mac

---

## Support Commands

**On Mac - Check Tailscale:**
```bash
tailscale status
tailscale ip -4
```

**On Mac - Check API:**
```bash
curl http://matthews-mbp.deer-regulus.ts.net:8000/health
curl http://localhost:8000/log/today
```

**On Mac - View Logs:**
```bash
# If running with uvicorn, check terminal output
# Or use the /metrics endpoint
curl http://localhost:8000/metrics
```

---

## Example Usage Scenarios

**Breakfast at home:**
- "Hey Siri, Log Food"
- "Two eggs, toast with butter, and coffee"

**Lunch on the go:**
- "Hey Siri, Log Food"  
- "Chipotle burrito bowl with chicken"

**Snack:**
- "Hey Siri, Log Food"
- "Apple and peanut butter"

**Restaurant meal:**
- "Hey Siri, Log Food"
- "Burger and fries from Five Guys"

---

Ready to create your shortcut? Follow the steps above and test it out!
