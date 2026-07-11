# Creating the OSS trigger for `quotemind-ingest`

`s deploy` cannot create this trigger on every network, and the failure is not one you can retry
your way out of. Serverless Devs hard-codes a **3-second** timeout on the RAM call that resolves
`AliyunOSSEventNotificationRole`; from Vietnam that endpoint answers in **3-20 seconds**. The deploy
aborts *before* it creates the function, so you end up with neither a trigger nor a function:

```
ReadTimeout(3000). POST https://ram.aliyuncs.com/?RoleName=AliyunOSSEventNotificationRole failed.
```

The trigger is therefore declared in `deploy/s.yaml` - because that is the truth about the system -
and created once by hand. `s.yaml` is the specification; this document is how to satisfy it.

## Deploy the function without the trigger

```bash
# 1. comment out the `triggers:` block under quotemind-ingest in deploy/s.yaml
# 2. deploy the function on its own
cd deploy && s quotemind-ingest deploy -y
# 3. restore the block
```

## Create the trigger

Function Compute console -> `ap-southeast-1` -> Functions -> **quotemind-ingest** -> Triggers ->
**Create Trigger**. It must match `s.yaml` exactly:

| Field | Value |
|---|---|
| Trigger Type | OSS |
| Name | `oss-rfq-drop` |
| Version or Alias | `LATEST` |
| Bucket Name | `quotemind-inbox` |
| Object Prefix | `rfq/` |
| Trigger Event | `oss:ObjectCreated:PutObject`, `oss:ObjectCreated:PostObject`, `oss:ObjectCreated:CompleteMultipartUpload` |
| Role Name | `AliyunOSSEventNotificationRole` |

The console pre-selects `oss:ObjectCreated:PutSymlink` as a fourth event. **Remove it.** A symlink is
not an uploaded RFQ, and firing the pipeline on one would quote a file that does not exist.

## Verify

```bash
aliyun oss cp eval/dataset/vi_xlsx_001.xlsx oss://quotemind-inbox/rfq/  # or the console uploader
```

Within ~30 s a new quote appears at `pending_approval` on the dashboard. If it does not, read the
function's logs - which is why `logConfig` is declared for this function too. An event-driven
function has no caller to return an error to; without logs, a failed ingest is just a file that
silently never becomes a quote.
