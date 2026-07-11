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
ignore the header, which is why the API and every integration test pass — but a **browser obeys it**,
and a browser is exactly what a judge will use.

This is the same restriction that broke the PDF route (`ExternalRedirectForbidden` on a cross-domain
302, see `api/app.py::quote_pdf`). The default domain is deliberately crippled for browser use, in
two different ways, and we have now been bitten by both.

**Why not OSS static hosting?** Tried. This account has **Block Public Access at the account level**:

```
$ oss2 put_bucket_acl(public-read)
AccessDenied: Put public bucket acl is not allowed
```

That is the correct setting and it should stay — the artifacts bucket holds customer quote PDFs. It
also means no bucket on this account can serve a public page, so there is exactly one fix.

---

## The fix: bind a custom domain (≈15 minutes)

**Singapore (`ap-southeast-1`) does not require an ICP filing.** This only works in a non-mainland
region, which is where we are.

### 1. Create the custom domain in Function Compute

Console → **Function Compute** → **Custom Domains** (Tên miền tuỳ chỉnh) → **Create**.

| Field | Value |
|---|---|
| Domain name | `quotemind.cyberskill.world` |
| Protocol | **HTTP & HTTPS** (pick HTTPS-only after step 3) |
| Route — Path | `/*` |
| Route — Service/Function | `quotemind` → `quotemind-api` |
| Route — Version | `LATEST` |

Save. The console shows you a **CNAME target** that looks like:

```
<account-id>.ap-southeast-1.fc.aliyuncs.com
```

Copy it.

### 2. Point DNS at it

Wherever `cyberskill.world` is managed, add:

| Type | Name | Value | TTL |
|---|---|---|---|
| CNAME | `quotemind` | `<account-id>.ap-southeast-1.fc.aliyuncs.com` | 600 |

Wait for it to resolve:

```bash
dig +short quotemind.cyberskill.world
```

### 3. HTTPS

Back in the custom-domain screen, enable **HTTPS** and either:

- upload a certificate for `quotemind.cyberskill.world`, or
- issue a free one via Alibaba Cloud SSL Certificates (Digital Certificate Service → free DV cert),
  then select it here.

### 4. Verify

```bash
# the header must be GONE
curl -sI https://quotemind.cyberskill.world/ | grep -i content-disposition   # expect: nothing

# and the page must render, not download
open https://quotemind.cyberskill.world/
```

### 5. Two things to change in the repo once it works

1. **`README.md` and `docs/submission-description.md`** — swap the live URL. The `fcapp.run` URL
   still works for the API; it is only unusable as a *page*.
2. **`api/app.py::quote_pdf`** — restore the FR-091 302. The comment there says "restore the 302 the
   day a custom domain is bound." That day is this one.

---

## What we do in the meantime

The submission's live URL is the primary artifact and it currently downloads. Until the domain is
bound, the honest options are:

- **Ship the demo video** (`.demo/quotemind-demo.mp4`), which shows the real UI against live cloud
  data, and say plainly in the submission that the dashboard is at the custom domain.
- **Judges can still verify the deployment** without a browser page: `/health` returns JSON with the
  deployed commit and the model probe, and every API route works with `curl`. That is worth one line
  in the README.

Neither is a substitute for a URL that opens. **Bind the domain.**
