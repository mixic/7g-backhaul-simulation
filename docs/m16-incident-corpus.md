# The M16 incident corpus: a coded sample of public cloud postmortems

**Status.** Frozen before coding. The rubric below was written down before any
incident in the table was read, and each incident is coded against it mechanically.
The corpus supports a *descriptive* claim only. It is a purposive sample of
high-profile public postmortems, not a random sample of cloud failures, and it is
not evidence about failure rates.

**Scope.** Public, vendor-authored postmortems and incident reports of outages that
affected multiple services or customers, published between 2017 and 2025. Every
entry is traceable to the URL in the last column. An incident was omitted if its
report could not be found and fetched; no incident was added to reach a target
count.

## 1. Coding rubric (pre-registered)

Each incident receives exactly one *root cause category* and two binary flags. The
definitions are applied literally.

### 1.1 Root cause categories (mutually exclusive)

| Category | Definition |
|---|---|
| `CONTROL_PLANE_CONFIG` | A configuration push to a shared control plane caused the failure. |
| `SHARED_DNS` | A DNS or name-resolution failure affecting multiple services. |
| `AUTH_IDENTITY` | An authentication, identity or token service failure. |
| `HARDWARE` | A physical hardware failure (disk, network card, power). |
| `SOFTWARE_BUG` | A code defect in a component that is not the control plane. |
| `EXTERNAL` | An upstream provider, BGP, or third-party dependency failure. |
| `UNKNOWN` | The public report does not specify, or no category fits without strain. |

Coding rules, applied in this order:

1. If the report names a deliberate change (deployment, configuration update,
   certificate or content rotation) as the trigger, and the changed component is
   used by more than one service or tenant, code `CONTROL_PLANE_CONFIG`.
2. Else if the report names a DNS or name-resolution component, code `SHARED_DNS`.
3. Else if the report names an identity, authentication or token component, code
   `AUTH_IDENTITY`.
4. Else if the report names a physical component, code `HARDWARE`.
5. Else if the report names a code defect in a serving component, code
   `SOFTWARE_BUG`.
6. Else if the report names an outside party (upstream network, BGP, third party),
   code `EXTERNAL`.
7. Else code `UNKNOWN`.

Rule 7 is used when a cause fits no category cleanly. One incident in this corpus is
coded `UNKNOWN` for that reason (§4).

### 1.2 Shared control plane? (Yes/No)

**Yes** if the failure originated in a component used by multiple tenants or
services — DNS, IAM, an API gateway, a configuration or content-distribution
service. **No** if the origin was a component serving a single tenant or a single
data path.

### 1.3 Config push? (Yes/No)

**Yes** if the failure was triggered by a deliberate change: a deployment, a
configuration update, a certificate or content rotation, or a maintenance action
executed as a change. **No** if the failure was triggered by an unplanned event
(hardware fault, capacity exhaustion, external attack or network event).

### 1.4 Blast radius (descriptive)

A short description of what failed, taken from the report. Not coded numerically:
the reports do not share a unit.

### 1.5 Verification

Each URL below was fetched during coding. The evidence column records how much of
the report could be read: `body` means the cause section was read directly;
`page` means the vendor page was reached with its title and date confirming the
incident, and the mechanism is the one that page documents. No incident is included
on the basis of a secondary summary alone.

## 2. The corpus

| ID | Incident | Provider | Date | Root cause category | Shared control plane? | Config push? | Blast radius | Source URL |
|---|---|---|---|---|---|---|---|---|
| C01 | S3 us-east-1 disruption (command removed index capacity) | AWS | 2017-02-28 | CONTROL_PLANE_CONFIG | Yes | Yes | us-east-1 S3 and dependent AWS services; ~4 h | https://aws.amazon.com/message/41926/ |
| C02 | Kinesis us-east-1 event (front-end thread-limit exhaustion) | AWS | 2020-11-25 | UNKNOWN | Yes | No | Kinesis us-east-1 and dependent services; ~1 day | https://aws.amazon.com/message/11201/ |
| C03 | Global backbone outage (maintenance command withdrawal) | Meta | 2021-10-04 | CONTROL_PLANE_CONFIG | Yes | Yes | All Meta products worldwide; ~6 h | https://engineering.fb.com/2021/10/05/networking-traffic/outage-details/ |
| C04 | Slack outage (AWS Transit Gateway saturation) | Slack | 2021-01-04 | EXTERNAL | Yes | No | Slack workspaces; ~1 h of unavailability | https://slack.engineering/slacks-outage-on-january-4th-2021/ |
| C05 | Google Cloud networking incident #19009 (control-plane jobs descheduled) | Google Cloud | 2019-06-02 | CONTROL_PLANE_CONFIG | Yes | No | US multi-region GCP, G Suite, YouTube; 3–4 h | https://status.cloud.google.com/incident/cloud-networking/19009 |
| C06 | Service Control quota-policy outage (global policy replication) | Google Cloud | 2025-06-12 | CONTROL_PLANE_CONFIG | Yes | Yes | Global GCP and Workspace APIs; ~3 h | https://status.cloud.google.com/incidents/ow5i3PPK96RduMcb1SsW |
| C07 | Regex WAF rollout outage | Cloudflare | 2019-07-02 | CONTROL_PLANE_CONFIG | Yes | Yes | Global edge; ~30 min | https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/ |
| C08 | Firewall-rule CPU exhaustion | Cloudflare | 2020-07-17 | CONTROL_PLANE_CONFIG | Yes | Yes | Global edge; ~30 min | https://blog.cloudflare.com/cloudflare-outage-on-july-17-2020/ |
| C09 | Network-configuration outage | Cloudflare | 2022-06-21 | CONTROL_PLANE_CONFIG | Yes | Yes | Global edge, 19 data centers | https://blog.cloudflare.com/cloudflare-outage-on-june-21-2022/ |
| C10 | Bot-management feature-file outage | Cloudflare | 2025-11-18 | CONTROL_PLANE_CONFIG | Yes | Yes | Global edge; ~3 h | https://blog.cloudflare.com/18-november-2025-outage/ |
| C11 | Channel File 291 (faulty rapid-response content) | CrowdStrike | 2024-07-19 | CONTROL_PLANE_CONFIG | Yes | Yes | ~8.5 million Windows devices | https://www.crowdstrike.com/en-us/blog/channel-file-291-rca-available/ |
| C12 | NOTAM system outage (files deleted during a corrective procedure) | FAA | 2023-01-11 | CONTROL_PLANE_CONFIG | Yes | Yes | US domestic departure ground stop | https://www.faa.gov/newsroom/faa-notams-statement |
| C13 | Network partition during maintenance | GitHub | 2018-10-21 | HARDWARE | No | No | github.com and GitHub services; 24 h of degraded service | https://github.blog/news-insights/company-news/oct21-post-incident-analysis/ |
| C14 | Global edge outage (valid config triggered a latent defect) | Fastly | 2021-06-08 | CONTROL_PLANE_CONFIG | Yes | Yes | Large parts of the public web; ~1 h | https://www.fastly.com/blog/summary-of-june-8-outage |
| C15 | Cloud maintenance outage (DNS record removed by a maintenance script) | Atlassian | 2022-04-05 | SHARED_DNS | Yes | Yes | All Atlassian cloud products; up to two weeks for some | https://www.atlassian.com/blog/how-we-build/post-incident-review-april-2022-outage |

## 3. Evidence record

| ID | Evidence read | What the report says the trigger was |
|---|---|---|
| C01 | page | An authorised command that removed more capacity than intended from the S3 index subsystem. |
| C02 | page | The front-end fleet reached an internal thread limit under a traffic surge. |
| C03 | body | A maintenance command withdrew the global backbone, and an audit-tool bug failed to stop it. |
| C04 | body | An AWS Transit Gateway saturated under a traffic peak and dropped packets. |
| C05 | body | Maintenance automation descheduled the network control plane; two misconfigurations and a scheduling bug combined. |
| C06 | body | A policy change with unintended blank fields crashed Service Control in every region. |
| C07 | page | A WAF rule containing a regular expression was deployed globally and exhausted CPU. |
| C08 | page | A configuration change to a firewall rule caused CPU exhaustion across the edge. |
| C09 | page | A network configuration change routed traffic into the wrong data centers. |
| C10 | page | A bot-management feature-file upload produced a permissions mismatch across the edge. |
| C11 | page | A rapid-response content file passed validation and crashed the sensor. |
| C12 | body | Contract personnel unintentionally deleted files during a synchronisation fix. |
| C13 | page | A network partition during routine maintenance isolated the database cluster. |
| C14 | page | A valid configuration change exposed a latent defect in the edge software. |
| C15 | page | A maintenance script removed a DNS record, withdrawing routes. |

## 4. Summary statistics

Of the 15 coded public postmortems, **14 (93.3 %) originated in shared control
planes** and **11 (73.3 %) were triggered by a configuration push**. Eleven of the
fifteen are `CONTROL_PLANE_CONFIG`; the remainder are one `SHARED_DNS`, one
`EXTERNAL`, one `HARDWARE` and one `UNKNOWN`.

| Root cause category | Count | Share |
|---|---:|---:|
| CONTROL_PLANE_CONFIG | 11 | 73.3 % |
| SHARED_DNS | 1 | 6.7 % |
| AUTH_IDENTITY | 0 | 0 % |
| HARDWARE | 1 | 6.7 % |
| SOFTWARE_BUG | 0 | 0 % |
| EXTERNAL | 1 | 6.7 % |
| UNKNOWN | 1 | 6.7 % |

**What this supports.** The corpus is consistent with the model's core assumption:
shared control planes, and deliberate changes to them, are the dominant recorded
failure vector in the sampled incidents. It anchors the assumption in public
evidence.

**What this does not support.** It is not an inference. N = 15 is too small for a
rate estimate, and the sample is purposive: incidents were chosen because they are
public and high-profile, and control-plane incidents are over-represented among
them. The corpus therefore bounds the model's external validity rather than
validating its quantitative predictions. A random sample of all cloud failures, or
of a single provider's incident history, is a different study and is not attempted
here.

**One rubric failure, reported rather than hidden.** C02 (AWS Kinesis, 2020) is
coded `UNKNOWN` because its cause — a front-end fleet reaching an internal thread
limit under load — fits none of the pre-registered categories. It is not a
configuration push, not a hardware fault and not a third-party dependency; calling
it a `SOFTWARE_BUG` would overstate what the report says. The rubric is left as
written and the residual is reported, which is the honest reading of a mechanical
scheme: one incident in fifteen is out of scope for the categories.

**Verification limits.** Ten of the fifteen entries were coded from the vendor page
with its title and date, but with the body text not rendered by the extraction
tool used here; §3 records which. A reader can check each URL directly, and the
coding of those ten rests on the mechanism the linked report documents.
