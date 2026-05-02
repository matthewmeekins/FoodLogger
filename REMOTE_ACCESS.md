# Remote Access Options

Guide for accessing your local Food Log database from anywhere (WAN access).

## Goal

Access the FastAPI server running on your Mac from your iPhone when you're not on the same WiFi network.

---

## Option 1: Tailscale (Recommended)

**What it is:** Zero-config VPN that creates a private network between your devices.

**Pros:**
- Free for personal use (up to 100 devices)
- Automatic encryption
- No router configuration needed
- Works behind any firewall/NAT
- Direct peer-to-peer connections when possible
- Easy setup (5 minutes)
- Persistent private IP addresses for your devices

**Cons:**
- Requires installing Tailscale on both Mac and iPhone
- Another service to trust (though well-regarded)

**Setup:**
1. Install Tailscale on Mac: `brew install tailscale`
2. Install Tailscale iOS app
3. Sign in on both devices
4. Your Mac gets a persistent IP (e.g., `100.x.x.x`)
5. Access API at `http://100.x.x.x:8000` from iPhone

**Security:** Strong - encrypted VPN, only your devices can connect

**Best for:** Ongoing personal use, multiple devices, no router access

---

## Option 2: Cloudflare Tunnel (Free Tier)

**What it is:** Secure tunnel that exposes your local server through Cloudflare's network.

**Pros:**
- Completely free for personal use
- No router configuration needed
- HTTPS automatically included
- Works behind any firewall
- Can use custom domain or provided subdomain
- Very reliable infrastructure

**Cons:**
- Requires cloudflared daemon running on Mac
- Public URL (though obscure subdomain if you don't add domain)
- Subject to Cloudflare Terms of Service

**Setup:**
1. Install: `brew install cloudflare/cloudflare/cloudflared`
2. Authenticate: `cloudflared tunnel login`
3. Create tunnel: `cloudflared tunnel create food-log`
4. Run: `cloudflared tunnel --url http://localhost:8000`
5. Access at provided URL (e.g., `https://random-name.trycloudflare.com`)

**Security:** Good - HTTPS encrypted, though URL could be found if leaked

**Best for:** Quick setup, no router access, want HTTPS

---

## Option 3: ngrok (Free Tier)

**What it is:** Instant tunnel service with public HTTPS URL.

**Pros:**
- Fastest setup (1 command)
- HTTPS included
- Good for testing/temporary use
- Web inspector UI to see requests
- No router configuration

**Cons:**
- Free tier: Random URL that changes on restart
- Free tier: Connection limits and timeouts
- Public URL (anyone with link can access)
- Need to keep terminal window open

**Setup:**
1. Install: `brew install ngrok`
2. Sign up and add auth token: `ngrok config add-authtoken YOUR_TOKEN`
3. Run: `ngrok http 8000`
4. Use the HTTPS URL shown (e.g., `https://abc123.ngrok.io`)

**Security:** Moderate - HTTPS encrypted, but URL is public

**Best for:** Testing, temporary access, demos

---

## Option 4: Router Port Forwarding + Dynamic DNS

**What it is:** Traditional NAT port forwarding to expose your Mac to the internet.

**Pros:**
- No third-party services required
- Direct connection (low latency)
- Full control

**Cons:**
- Requires router admin access
- Need static Mac IP or DHCP reservation
- Security responsibility is on you
- Home IP address visible
- May violate ISP terms of service
- Need Dynamic DNS if IP changes (common for residential)
- No HTTPS without additional setup (Let's Encrypt + domain)

**Setup:**
1. Give Mac static local IP or DHCP reservation
2. Forward external port (e.g., 8000) to Mac's IP:8000 in router
3. Sign up for Dynamic DNS (DuckDNS, No-IP, Dynu - free)
4. Install DDNS client to update your IP
5. Access at `http://yourname.duckdns.org:8000`

**Security:** Low - **Not recommended without authentication**

**Best for:** Learning, must avoid third parties, already have setup

---

## Option 5: VPN to Home Network

**What it is:** Set up VPN server on router or Mac, connect from iPhone.

**Pros:**
- Access all home services, not just this app
- Encrypted
- No third parties (except maybe router vendor)

**Cons:**
- Complex setup
- Requires VPN-capable router or running VPN server on Mac
- Port forwarding still needed for VPN port
- May require router firmware update (e.g., DD-WRT)

**Setup varies by router model**

**Security:** Good if configured correctly

**Best for:** Already have home VPN, want access to multiple services

---

## Comparison Table

| Option | Setup Time | Cost | Security | Reliability | Router Config |
|--------|-----------|------|----------|-------------|---------------|
| **Tailscale** | 5 min | Free | ★★★★★ | ★★★★★ | None |
| **Cloudflare Tunnel** | 10 min | Free | ★★★★☆ | ★★★★★ | None |
| **ngrok** | 2 min | Free tier | ★★★☆☆ | ★★★★☆ | None |
| **Port Forward + DDNS** | 30-60 min | Free | ★★☆☆☆ | ★★★☆☆ | Required |
| **Home VPN** | 1-2 hours | Free | ★★★★☆ | ★★★☆☆ | Required |

---

## Recommendations

**For your use case (iPhone Shortcuts + personal use):**

### Primary Recommendation: Tailscale
- Simple, secure, reliable
- Works everywhere
- No exposed public endpoints
- Free forever for personal use
- Takes 5 minutes to set up

### Alternative: Cloudflare Tunnel
- If you want a public URL for some reason
- Good if you might share access later
- Also very reliable

### Avoid for Production:
- ngrok free tier (URL changes, timeouts)
- Port forwarding without authentication (security risk)

---

## Security Additions (Recommended)

Regardless of access method, consider adding:

1. **API Key Authentication**
   - Add simple bearer token to requests
   - Reject requests without valid key

2. **Rate Limiting** (already implemented)
   - Current: 40 requests/minute
   - Review line in main.py

3. **HTTPS**
   - Tailscale: Not required (encrypted VPN)
   - Cloudflare/ngrok: Included automatically
   - Port forwarding: Need Let's Encrypt + domain

---

## Next Steps

1. Choose access method (recommend Tailscale)
2. Decide if you want to add API authentication
3. Test with curl from iPhone before creating Shortcut
4. Update Apple Shortcut with final URL

Would you like help implementing any of these options?
