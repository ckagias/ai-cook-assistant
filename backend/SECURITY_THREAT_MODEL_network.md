# Threat model: network access and trust boundary

## The two deployment shapes this app actually has today

1. **`adb reverse` / same-origin-on-localhost.** `adb reverse tcp:8000
   tcp:8000` makes a tethered Android tablet's browser see the backend as
   `localhost` over USB. Traffic never leaves the USB link - there is no
   network path for anyone else to reach it. This is the default bring-up
   path (`DESIGN.md` #10).
2. **Self-signed HTTPS on a LAN.** A fallback for iOS (no USB debugging
   equivalent) or a tablet not physically tethered. The backend is reachable
   by anything else on the same network - a home LAN today, but "same
   network" is a much weaker boundary than "same USB cable": a guest on the
   Wi-Fi, a compromised IoT device, or a misconfigured router with UPnP all
   count as "on the network."

`adb reverse` has no exposure to worry about. Self-signed HTTPS on a LAN is
the shape this plan is actually defending.

## What each unauthenticated route costs

- **`/analyze`**: real API spend per call (a live vision-provider request),
  and a captured recipe context could be used to probe the safety-override
  behavior (`_apply_protein_safety`/`_apply_safety_flag` in `main.py`).
  Costs the operator money and, at volume, could be used to explore how the
  safety rules respond.
- **`/barcode/{code}`**: a free, open, unauthenticated proxy to Open Food
  Facts' API. Abuse of this doesn't just cost the operator - hammering a
  third party through this app's IP could get the whole app rate-limited or
  blocked by Open Food Facts, a problem for every user of the app, not just
  the attacker.
- **`/recipes`, `/recipes/{id}`, `/reference/{id}/{step}`**: low
  sensitivity. No cost, no secrets - just recipe text and images that are
  already meant to be shown to whoever is using the app.
- **`/health`**: no cost, no data. Meant to be checkable without a secret.
- **The static file mount**: inert HTML/JS/CSS. Serving it to an
  unauthenticated request costs nothing and reveals nothing sensitive.

## Explicitly not in scope

This plan does not attempt full multi-tenant user accounts, OAuth, or
anything sized for a public SaaS. This is a **single-household
device-pairing model**: one backend, one or a few tablets on the same
network, matching how the rest of the app is designed. The goal is making
"who can call this" an explicit, opt-in decision instead of an accident of
network topology, not building an identity system.
