# The live URL downloads instead of rendering (P0)

**Symptom.** Open `https://quotemind-api-yccvwlooxw.ap-southeast-1.fcapp.run/` in any browser and
you get a *file download* — `download.html` — instead of the dashboard. Same for `/eval`.

**Cause.** Function Compute injects this header on **every** response served from its default
`*.fcapp.run` domain:

```
Content-Disposition: attachment
```

We do not set it. It is not configurable. It is Alibaba Cloud's anti-abuse measure: the default
domain is a debugging endpoint, and they do not want it used to host web pages. `curl` and `fetch`
ignore the header, which is why the API and every live check in `BUILD_LOG.md` pass — but a
**browser obeys it**, and a browser is exactly what a judge will use.

It is the same restriction that broke the PDF route (`ExternalRedirectForbidden` on a cross-domain
302, see `api/app.py::quote_pdf`). The default domain is deliberately crippled for browser use in
two different ways, and we have now been bitten by both.

**Why not OSS static hosting?** Tried. Block Public Access is set at the **account** level:

```
AccessDenied: Put public bucket acl is not allowed
```

That is the correct setting and it should stay — the artifacts bucket holds customer quote PDFs
served by short-lived presigned URLs. It also means no bucket on this account can serve a public
page. So there is exactly one fix.

---

# The fix

**Everything on the Alibaba side is scripted.** The only thing that needs a human is one DNS record,
because Function Compute *refuses* to create a custom domain until the CNAME already points at it:

```
DomainNameNotResolved: domain name 'quotemind.cyberskill.world' has not been resolved to your
FC endpoint, the expected endpoint is '5492870817983957.ap-southeast-1.fc.aliyuncs.com.'
```

So DNS is genuinely step one. It is one row.

## Step 1 — add one CNAME (this is the only manual step)

`cyberskill.world` is on **Tenten.vn** (`ns-a1/a2/a3.tenten.vn`). Log in there, open the DNS records
for `cyberskill.world`, and add:

| Type | Name / Host | Value / Target | TTL |
|---|---|---|---|
| **CNAME** | `quotemind` | `5492870817983957.ap-southeast-1.fc.aliyuncs.com` | 600 |

> That value is not a guess — it is the endpoint Function Compute itself named in the error above,
> and `deploy/custom_domain.py` prints it from the live account ID.

Wait for it to propagate (usually a few minutes):

```bash
dig +short quotemind.cyberskill.world
# should return an alibaba fc endpoint
```

## Step 2 — bind it (scripted)

```bash
source .venv/bin/activate
set -a && source .env && set +a
python deploy/custom_domain.py --domain quotemind.cyberskill.world
```

That creates the FC custom domain, routes `/*` to `quotemind-api:LATEST`, and then verifies that the
attachment header is gone. Re-run it any time; it updates rather than duplicating.

## Step 3 — HTTPS

Console → **Function Compute → Custom Domains → quotemind.cyberskill.world → HTTPS**. Either upload a
certificate, or issue a free DV one (Digital Certificate Service) and select it.

`--protocol` is created as `HTTP,HTTPS` so the CNAME can be verified before a certificate exists.
Once the cert is on, switch it to HTTPS-only.

## Step 4 — verify

```bash
python deploy/custom_domain.py --domain quotemind.cyberskill.world --check
```

Expected:

```
  DNS      quotemind.cyberskill.world resolves
  HTTP     200 - and NO attachment header
  HTTPS    200 - and NO attachment header
```

And then the thing that actually matters: **open it in a browser.** It should render, not download.

## Step 5 — two things to change in the repo once it works

1. **`README.md`** and **`docs/submission-description.md`** — swap the live URL. The `fcapp.run` URL
   still works as an *API*; it is only unusable as a *page*.
2. **`api/app.py::quote_pdf`** — restore the FR-091 302. The comment there already says: *"restore
   the 302 the day a custom domain is bound."* That day is this one.

---

## Until then

The submission's primary artifact is a URL that downloads. Nothing about that is fine, and the honest
stopgaps are:

- The **demo clip** (`.demo/quotemind-demo.mp4`) shows the real UI against live cloud data.
- A judge can still verify the deployment without a page: `GET /health` returns the deployed commit
  and the model probe, and every API route works with `curl`. Worth one line in the README.

Neither is a substitute for a link that opens. **Add the CNAME.**
