# Contributing

## The loop

```bash
make test      # before you change anything
# ... change something ...
make test      # and after
```

56 tests, no network, under two seconds. If they are green, the thing works;
if they are red, nothing else matters. There is no CI to hide behind and no
staging environment — the suite is the contract.

## Ground rules

**Standard library only.** Python 3.11+, zero third-party dependencies. This is
a deliberate constraint, not an oversight: it means `git clone` and run, with
no virtualenv, no lockfile, and no supply chain. If a change seems to need
`requests`, `pandas`, or a web framework, it does not — read how `providers/base.py`
does HTTP with retry in about forty lines.

**No credentials in the tree, ever.** See [AGENTS.md](AGENTS.md). `data/*.db`
and `*.env` are gitignored; keep it that way.

**Fixtures come from the script.** `python3 tests/fixtures/make_fixtures.py` is
deterministic. Editing a fixture by hand once cost 74% of the roster rows to a
silent primary-key collision, and the tests still passed.

## Adding a provider

One subclass of `Provider` plus `@register`. Nothing else changes — analytics
reads normalized tables and never imports a provider, which is exactly why the
same nine analyses work across ESPN, Yahoo, Sleeper and pasted text.

1. Subclass `Provider` in `fantasyedge/providers/<name>.py`
2. Emit the records in `models.py` — that is the whole interface
3. Register it, import it in `cli.py`
4. Add a fixture and a test that normalizes a season from it

The test should use a stub `Http`, which is the entire reason `Http` is
injected rather than imported at call sites.

## Adding an analysis

1. A pure function in `analytics.py`: `(store, provider, league) -> Result`
2. **A non-empty `caveat`.** A test asserts this. An analysis that will not
   admit its own limits does not ship.
3. Register it in `ANALYSES`
4. Return `empty: true` rather than raising when its data is not loaded

## Adding an API route

1. The endpoint method on `Api`
2. A branch in `dispatch` that returns `(payload, POLICY)` — pick the policy
   from what the data *is*, not from convenience
3. An entry in `ROUTES`; a test asserts every advertised route dispatches
4. A 404 must carry a `fix` telling the caller what to do next

## Touching the leverage model

`leverage.py` is ported by hand into JavaScript inside
`templates/mosaic.html`, and will be ported again into Swift. **Change both.**
The properties in `TestLeverage` are the specification — if a change breaks
"the last player running absorbs the leverage", the change is wrong.

Keep it free of I/O. The moment it imports a store it stops being portable.

## Style

- Explain **why** in docstrings and comments. The code says what.
- Match the density of the file you are editing.
- Prefer a named intermediate over a clever one-liner in analytics; these are
  read far more often than written.
- Do not add a formatting pass, a changelog, or a coverage report unless it was
  asked for.

## Front end

`templates/mosaic.html` is one file on purpose: it is served by `api.py` with
its data injected, published as an Artifact, and built into `docs/` for Pages
from the same source. `__DATA__` and `__IMAGES__` are the two injection points.

Node is only used to syntax-check the script block:

```bash
python3 - <<'EOF' > /tmp/check.js
d=open('fantasyedge/templates/mosaic.html').read()
js=d[d.index('<script>')+8:d.rindex('</script>')]
print(js.replace('__DATA__','{"leagues":[]}').replace('__IMAGES__','{}'))
EOF
node --check /tmp/check.js
```

## Releasing the demo

```bash
make docs      # writes docs/index.html, anonymised
```

`--anon` is the default for a reason: NFL players are public facts, the people
in your league are not.
