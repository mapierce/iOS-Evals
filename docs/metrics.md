# Metrics

**Frozen 2026-08-19.** Not to be edited after the first scoring run. Changing a
metric definition after seeing results is p-hacking. If a definition turns out
to be wrong, add a dated successor section — never rewrite this one.

Pins in effect at freeze time: Xcode `17F113`, iPhoneOS SDK `26.5`,
`deployment_target = 17.0`, `temperature = 0.2`, `samples_per_prompt = 5`.

---

## Units

**Sample** — one model response to one prompt. `samples_per_prompt = 5` samples
are drawn per (model, prompt) pair. Every sample drawn enters the denominator of
every rate below. Samples are never discarded: a refusal, an empty response, or
output that does not compile all score as failure and are retained. Dropping
them would flatter weak models.

**Relevant API call** — a call site or type reference in the generated source
that resolves by name to a symbol present in the ground truth extracted from the
pinned SDK (SwiftUI and SwiftUICore). References to symbols outside those
modules — Foundation, standard library, the model's own declarations — are not
relevant and are excluded from every numerator and denominator.

**Declared API area** — every prompt names the symbol family it is testing. This
is part of the prompt corpus, fixed before generation.

---

## The functional gate

A sample is **gated** if AST inspection of its source shows at least one
relevant API call within the prompt's declared API area.

Two properties matter.

It is an **AST check, not string matching**. A symbol name inside a comment or a
string literal does not gate a sample.

It is **independent of compilation**. Swift's parser accepts source that does not
typecheck, so a sample that fails to build is still gated if it exercises the
declared area. This is deliberate: availability violations are hard compile
errors, so a gate that required a successful build would exclude exactly the
samples the availability metric exists to count, and that metric could only ever
read zero.

The gate exists to defeat the empty-view trap. A model emitting
`var body: some View { EmptyView() }` produces no relevant API calls, is not
gated, and earns no score — rather than a perfect one.

---

## Metric definitions

Let `N` be all samples drawn for a (model, prompt) pair, and `G ⊆ N` the gated
samples.

### `gated_rate`
```
|G| / |N|
```
Share of samples that exercise the declared API area. A low value means the
model did not attempt the task, and makes the remaining metrics thin — report it
alongside them always.

### `compile_rate`
```
|{s ∈ G : s builds with zero errors}| / |G|
```
Share of **gated** samples that build against the pinned SDK at the pinned
deployment target. Reported separately from the currency metrics, not as a
precondition for them.

### `deprecations_per_sample`
```
mean over s ∈ G of |{diagnostics in s with group == "DeprecatedDeclaration"}|
```
Counted from the serialized `.dia` diagnostic group, never from message text.
Includes samples that failed to build, because the compiler emits deprecation
warnings alongside errors. Attached notes are not counted; only the primary
diagnostic.

### `availability_violations_per_sample`
```
mean over s ∈ G of |{relevant API calls whose introduced version > deployment_target}|
```
Attributed by AST plus ground truth, not from diagnostics. Availability errors
carry no diagnostic group, category, or flag — only prose — so they cannot be
classified from the `.dia` alone, and parsing that prose is forbidden.

Counted per **call site**, so using one above-target symbol three times counts
three times. This matches how `deprecations_per_sample` counts.

### `currency_score`
```
current relevant calls / total relevant calls,  over s ∈ G
```
A relevant call is **current** if its symbol is neither deprecated nor above the
deployment target, per ground truth. Computed as a pooled ratio over all gated
samples for the pair — total current calls divided by total relevant calls — not
as a mean of per-sample ratios, so a sample with one call does not outweigh a
sample with twenty.

Range `[0, 1]`, higher is better. This is the headline number.

---

## Reporting rules

- Always report the mean across `k` samples. Never report a single sample.
- Always report `gated_rate` next to any currency metric. A metric computed over
  two gated samples is not comparable to one computed over five.
- `results/` files are dated and never overwritten.
- Every published result records the full pin set, the prompt corpus hash, and
  the ground truth artifact hash.

## Known limitations

Recorded at freeze time so they are not discovered as surprises later.

- **Soft deprecation requires a hidden flag.** Apple marks most SwiftUI
  deprecations with the `deprecated: 100000.0` sentinel, which the compiler does
  not warn about by default. `-warn-soft-deprecated` is required; without it 270
  of 326 deprecated symbols are invisible. It is a hidden flag and may change
  between toolchains. `tests/test_scaffold.py` fails loudly if it stops working.
- **Name-based symbol resolution.** The AST gives call-site names, not resolved
  declarations. Overload sets that share a base name are collapsed, so a symbol
  whose overloads differ in availability is attributed by base name. Overloads
  with genuinely divergent deprecation status are a known source of error.
- **Property wrappers are invisible to the gate.** The parse-only AST records
  `@State`, `@StateObject`, `@Published`, `@Bindable` and protocol conformances
  as nameless attribute nodes, so wrapper usage is not counted as a relevant
  call. The typechecked AST does resolve them, but its USRs interleave real
  symbols with parameter labels, and counting labels would inflate numerator
  and denominator together — compressing exactly the differences being
  measured. The observation family was removed from the corpus for this reason
  rather than scored on a gate that can never fire. Fixing this needs a real
  demangler or a SwiftSyntax pass; until then, wrapper-centric API areas are
  out of scope.
- **One deployment target.** Results are valid only at the pinned target. A model
  scoring well at 17.0 is not thereby current at any other target.
