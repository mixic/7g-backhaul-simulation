# Attack-aware dual-role control: authenticated name-class admission

**Status:** pre-registered claim, written before running the attack-aware
experiment. The exploratory DDoS result in
[`dual-role-results.md`](dual-role-results.md) showed that the unclassified
pressure controller *serves the attack*: a flood at `E2` raised `α` at the
attacked and interior nodes, starving forwarding to an unattacked target
(`E3`: 92.08 % versus 98.79 % for the separated baseline).

The next step is a controller that can distinguish attack-shaped load from
demand. The layered-protocol testbed's finding is the design input: a field is
safe to act on only when it is **visible and outside the attacker's control** —
i.e. authenticated. Apply the same rule at the service layer: a request is
eligible for serving only if its **name class** is authenticated (self-certifying
or signed). Unauthenticated flood traffic may be forwarded best-effort but
never consumes serving capacity. This is name-class filtering informed by the
integrity-scope result, not a cryptographic claim.

## 1. Falsifiable claim

> Under the `ddos` scenario, a dual-role controller that admits only
> authenticated demand keeps legitimate delivery to **every** target at
> **≥ 95 %** and improves unattacked-target (`E3`) legitimate delivery by
> **≥ 5 percentage points** over the unclassified fluid controller, for a
> stipulated classifier with false-positive rate **≤ 2 %** and false-negative
> rate **≤ 50 %** of the flood.

The claim is **refuted** if, at false-negative rate 0.5:

1. any target's legitimate delivery is below 95 %, or
2. `E3` legitimate delivery does not exceed the unclassified fluid arm by at
   least 5 pp.

It is **inconclusive** if the classifier cannot be parameterised as stipulated
(model limitation).

The experiment also reports the largest false-negative rate (on the tested
grid) at which the 95 % bar still holds. That number is the result, not a
tuning target: it is measured once and reported whether it is high or low.

## 2. Classifier model (stipulated)

- Legitimate demand is authenticated and admitted with probability
  `1 − false_positive`.
- Flood demand is unauthenticated; it is admitted with probability
  `false_negative` and dropped otherwise.
- False positives are indistinguishable from attacks and therefore lose
  legitimate service: this is the cost of the defence.
- Admission is modelled as a per-tick volume split, not per-request
  classification. The real difficulty of name verification is not modelled;
  the classifier error rates are **stipulated**, not measured.

After admission, admitted legitimate and admitted attack traffic share the
flow allocator. The model does **not** give verified traffic priority within a
tick; the defence is dropping unverified volume before it competes for
capacity. That limitation is deliberate and reported.

## 3. Legitimate-delivery attribution (stipulated)

The allocator does not tag individual bytes after admission. Delivered volume
per target is attributed to the legitimate class in proportion to admitted
volume:

```text
legit_share(t) = admitted_legit(t) / (admitted_legit(t) + admitted_attack(t))
```

For `E1` and `E3` there is no attack demand, so this is exact. For `E2` it is
a stipulated proportional-attribution assumption and is reported as such.

## 4. Arms

| Arm | Admission | Role control |
|---|---|---|
| separated, open | none | fixed roles |
| fluid, open | none | continuous α |
| fluid, authenticated | name-class filter (`fp = 0.02`) | continuous α |
| fluid, authenticated, sweep | `fn ∈ {0, 0.1, …, 0.9}` | continuous α |

Twelve paired seeds, `ddos` scenario, 120 ticks, otherwise identical to the
frozen dual-role comparison.

## 5. What this does and does not show

- It tests whether **filtering** attack-shaped load fixes the collateral
  damage of the unclassified controller. It does not test real attack
  classification, signatures, or name-resolution security.
- A confirmed result would identify a *condition* under which fluid
  reallocation is safe: the role controller must not see unauthenticated
  demand. It would not demonstrate the paradigm in deployment.
- A refuted result (e.g. the 95 % bar fails at `fn = 0.5`, or `E3` does not
  improve by 5 pp) is equally informative: it would bound how accurate a
  classifier must be before role fluidity is viable under attack.
