# P1 Plan — Verified Core (policy regression, pipeline tests, alerting, fail-soft)

Status: proposal, 2026-09-19. Baseline verified on branch
`arena/01a0b967-opstranslate` @ `8a9237a` with
`.venv/bin/python -m pytest -q` → **49 passed in 2.20s**
(`test_cache_lang` 9, `test_groupgate` 15, `test_policy` 16,
`test_ratelimit` 4, `test_repair` 2, `test_toggle` 3).

Every claim below was checked against this working tree; file:line
references are included so each one can be re-checked.

## Progress

| Package | State | Evidence |
|---|---|---|
| P1.0 group-gate `chat_member` wiring + status enum | **done** | 27 group-gate tests; real `ChatMemberMember` now allowed |
| P1.1 40-case regression set + publish gate | **done** | `pytest` 119 passed, 1 skipped (live-provider, opt-in) |
| P1.2 pipeline/handler integration tests | **done** | `pytest` 166 passed, 1 skipped |
| P1.2a script check in the sanity gate (finding A) | **done** | wrong-script answer withheld, 3 tests |
| P1.3 alerting completion | pending | |
| P1.4 fail-soft cache | pending | |
| P1.5 budget / logging / docs | pending | |

Test baseline moved 49 → 119 → **166 passed, 1 skipped**.

## Live-environment verification (2026-09-19)

The owner supplied real credentials for a local run. This sandbox cannot use
them: the egress firewall allows TCP but resets TLS to everything outside an
allowlist — `pypi.org` and `github.com` return 200, while
`api.telegram.org` and the provider host return `HTTP 000` (`SSL_ERROR_SYSCALL`).
So the live provider and the live bot were **not** exercised here.

What was verified instead, with the owner's real values:

1. **Config** — `validate_live()` clean, `provider_defs()` parses their
   `PROVIDERS_JSON` into exactly one named provider, the request URL
   resolves to `<PROVIDER_BASE_URL>/chat/completions`, the group gate reads
   the configured `GROUP_CHAT_ID`, `TEST_ALLOW_ALL=false`, timeout 30 s.
   (Host names, chat ids and keys are deliberately not repeated here -
   nothing environment-specific belongs in the repository.)
2. **The real entry point, end to end** — the actual FastAPI app under
   uvicorn in webhook mode, with only the two *external* services mocked
   (mock Telegram Bot API on :8898, mock OpenAI-compatible provider on
   :8897; aiogram pointed at the mock via `TelegramAPIServer`). 16/16 checks
   passed: Gate 1 rejects missing/wrong secret headers (403), the Phase 0
   gate silently drops a non-member (`getChatMember` → `left`, zero provider
   calls), Gate 2 processes a replayed `update_id` once, Gate 5 replies
   `251 / 250` with no provider call, Gate 6 rejects Chinese, Gate 8 returns
   the countdown on the third message in 30 s, the placeholder is sent with
   the reply anchor, the masked text (`⟦T:user_id⟧ မှားနေတယ်`) is what the
   provider receives, `User ID` is rendered on the way back, English input
   auto-toggles to a genuinely Burmese answer, and `/whoami` answers a
   non-member.
3. **`scripts/live_check.py`** (new, secret-free) — the same checks as a
   runnable script for a machine with real egress: config, `getMe`, a
   `getChatMember` check that the bot is a **group admin**, three probe
   translations through the real pipeline, and `--regression` for the 40-case
   set (spec 4.6). Its config step passes here; step 2 fails with a clear
   `TelegramNetworkError` and exit code 1, as expected without egress.

Findings from the supplied `.env`:

- **`PROVIDERS_JSON` as pasted is not valid JSON** (the chat transport turned
  the URLs into Markdown links). `config.provider_defs()` swallows the parse
  error and silently falls back to the single `PROVIDER_*` set — verified:
  the provider comes back named `primary`, not the configured name. The intended
  one-liner is in `.env.example`'s comment; `scripts/live_check.py` now fails
  loudly on this instead of letting it pass silently.
- **`HANDLER_BUDGET_S` is 60 s, not the 12 s the comment assumes**
  (`app/services/pipeline.py:64`). The note "30 s keeps the 12 s handler
  budget as the binding limit" is therefore wrong today, and more importantly
  the spec's 12 s budget (P1.5) is **incompatible** with a provider whose
  first reasoning-heavy request takes ~11 s: applying it verbatim would turn
  most translations into `ERROR_GENERIC`. Decision needed — keep 60 s and
  document the deviation, or derive the budget from `PROVIDER_TIMEOUT_S`.
- `AUTO_TOGGLE` is absent from the `.env` (defaults to `true`); it belongs in
  `.env.example` — already listed under P1.5.

---

## 1. Where P0 actually stands

P0 = the Phase 0 group gate (`GROUP_CHAT_ID` membership gate for private
DMs). Implemented in `app/bot/groupgate.py` and wired into every entry
point in `app/bot/handlers.py`:

| Entry point | Gated | Location |
|---|---|---|
| `/start` (fresh lookup, skips cache) | yes | `handlers.py:98` |
| `/help` | yes | `handlers.py:108` |
| `/whoami` | exempt by spec v3.1(2), private-only | `handlers.py:115` |
| `/status` | gate + admin role | `handlers.py:126` |
| `/tr` (reply / inline text) | yes | `handlers.py:152` |
| `callback_query lang:*` | yes | `handlers.py:199` |
| plain text / caption | yes, before the type check | `handlers.py:227` |

Decision table, asymmetric TTLs, fail-closed on error, allowlist
override: all present and covered by 15 tests.

### 1.1 Two P0 defects found (both fixed — see 3.1)

**(a) The status enum made the gate deny everyone.** `groupgate.py` read the
Telegram status with `str(member.status).lower()`. aiogram's
`ChatMemberStatus` is a str-mixed Enum whose `str()` is
`'ChatMemberStatus.MEMBER'`, not `'member'`, so the value matched none of
`_MEMBER_STATUSES` and every lookup fell through to the deny branch. Verified
with real aiogram objects before the fix:

```
member         -> allowed=False reason=non_member:chatmemberstatus.member
administrator  -> allowed=False reason=non_member:chatmemberstatus.administrator
owner          -> allowed=False reason=non_member:chatmemberstatus.creator
left           -> allowed=False reason=non_member:chatmemberstatus.left
```

The 15 original tests could not see this: `FakeMember.status` is a plain
string. In production only the static allowlist and `TEST_ALLOW_ALL` would
have got through. After the fix:

```
member         -> allowed=True  reason=member:member
administrator  -> allowed=True  reason=member:administrator
owner          -> allowed=True  reason=member:creator
left           -> allowed=False reason=non_member:left
```

**(b) The membership watcher was on the wrong update type.**
`app/bot/handlers.py:276` registered it on `my_chat_member`:

```python
@router.my_chat_member()          # <- the BOT's own membership changes
async def on_membership_change(event: ChatMemberUpdated, services): ...
```

`my_chat_member` is delivered when **the bot's** status changes in a chat.
Updates about **other users** joining/leaving the group arrive as
`chat_member` updates, which additionally require `"chat_member"` in
`allowed_updates` — and `app/main.py:113` and `app/main.py:124` list only
`["message", "callback_query", "my_chat_member"]`.

Verified in this tree (before the fix):

```
$ python -c "from app.bot import handlers; r = handlers.router; \
  print(len(r.my_chat_member.handlers), len(r.chat_member.handlers))"
1 0
```

The handler body was wrong too: it invalidated `event.from_user.id`, but on a
`chat_member` update `from_user` is the **admin who made the change** — the
subject is `event.new_chat_member.user`. It also compared
`str(new_chat_member.status).lower()` against `("left", "kicked")`, which is
the same enum bug as (a).

**Consequence:** a member who is kicked from the GP keeps a cached
`allow` verdict and keeps translating until the 6 h allow TTL expires
(`groupgate._ttl_for` → `GROUP_CACHE_TTL_S`). The code comment in
`handlers.py:284` ("a kick must lock the door immediately") describes
behaviour the wiring does not deliver. The 5-minute deny TTL only helps
joins, not kicks.

**Fix (≈30 min):** add `"chat_member"` to both `allowed_updates` lists,
add a `@router.chat_member()` handler that calls
`drop_cached_verdict()` on `left`/`kicked`, keep the existing
`my_chat_member` handler for the bot's own removal (log + P2 alert,
because `getChatMember` then fails for everyone and the gate fails
closed). Requires the bot to be admin in the GP — already documented in
the README quick start.

---

## 2. What is already built (so P1 does not re-do it)

Checked against the spec's Build Checklist (§13) and the v3.2 change
list:

| Spec item | State |
|---|---|
| MUST 1 allowlist gate | done (superseded by the P0 group gate + allowlist override) |
| MUST 2 policy engine mask/render/deny-scan + repair + withhold | done, 16 tests |
| MUST 3 policy versioning + **40-case regression set** | **versioning only — 10 stale seed cases, no gate** (see 3.2) |
| MUST 4 provider router, failover, circuit breaker | done (`provider.py`); DB-side live switching not done (P2) |
| MUST 5 cache keyed on policy version | done (`cache.cache_key`) |
| MUST 6 gate order 1–10 | done (`pipeline.run_translation`) |
| MUST 7 250-char cap with visible count | done; cap string hardcoded (3.6) |
| MUST 8 idempotency + duplicate handling | done |
| MUST 9 language gate (v3.2: confident CJK rejected) | done, `langdetect.detect` |
| MUST 10 reply-anchored delivery, anchor on first send | done (`_send_placeholder`) |
| MUST 11 two-path alerting, fingerprint, cooldown, **resolution** | **partial — `resolve()` has no callers, most triggers missing** (3.4) |
| MUST 12 no message text stored | done (`models.UsageLog` has `text_hash`/`char_len` only) |
| SHOULD 14 per-language deny lists + ratio check | done |
| SHOULD 15 entity protection | done, tested |
| SHOULD 16 8 s provider timeout / **12 s handler budget** | **`HANDLER_BUDGET_S = 60.0`** (3.6) |
| SHOULD 17 spend cap + P2 alert | done (`pipeline.py:476`) |
| SHOULD 18 char_len + rejection logging | partial — two branches never log (3.6) |
| v3.2 auto EN↔MM toggle | done (`resolve_toggle_dst`, 3 tests) |
| v3.2 Chinese out of scope | done (`detect` → `UNSUPPORTED_LANG`) |
| v3.2 member concept, `Amount`/`ပမာဏ`, `Platform` | done (`policy_data.py`, tested) |
| v3.2 style guidance + EN→MY few-shot | done (`build_system_prompt`) |
| v3.2 proxy session, `no_proxy` sanitizer, script-aware ratios | done (`config.telegram_session`, `provider._sanitize_no_proxy`, `ratio_ok`) |

---

## 3. P1 scope — "Verified core"

Goal: make the business rules **provable** and the failure paths
**loud**, without adding product surface. Six work packages, ordered.

### 3.1 P1.0 — close the P0 holes (§1.1) — DONE

Changed: `app/bot/groupgate.py` (new `_status_of()` normaliser, used by the
verdict logic), `app/bot/handlers.py` (`on_group_membership_change` on
`@router.chat_member()` reading `new_chat_member.user`;
`on_bot_membership_change` on `@router.my_chat_member()`),
`app/main.py` (`ALLOWED_UPDATES` constant, now including `"chat_member"`,
used by both polling and `set_webhook`), `tests/test_groupgate.py`
(+12 tests, now running against real aiogram `ChatMember*` objects).

Acceptance — all met:
- real `ChatMemberMember` / `Administrator` / `Owner` are allowed, `Left` /
  `Banned` denied, `Restricted` decided by `is_member`;
- a `ChatMemberUpdated` for another user deletes **that user's** cached
  verdict and leaves the actor's alone;
- a kick re-verifies on the next message (fake-bot call count 1 → 2), a join
  clears a cached deny;
- bot removed from the GP raises P2 `GROUP_GATE_UNAVAILABLE`, returning
  resolves it;
- `"chat_member"` is in `main.ALLOWED_UPDATES`, asserted by a test.

### 3.2 P1.1 — the 40-case regression set as executable test data — DONE

Spec MUST 3 and §4.5 ("a version cannot be published unless all 40
pass"; "the artefact that keeps the bot correct over time").

Current state, verified by running the seeded cases through the live
`compile_policy(1)` + `mask` + `render`:

```
5/10 seed regression cases pass against policy v1
FAIL my->en 'ပွိုင့်တွေ ဘယ်လိုလွှဲမလဲ'   rendered='Amountတွေ ...' expected 'Balance'
FAIL en->my 'check my game points'          rendered='check my ပမာဏ' expected 'လက်ကျန်'
FAIL zh->en '游戏里的积分怎么转'             rendered='Platform里的Amount...' expected 'balance'
FAIL en->en 'transfer my points to ...'     rendered='transfer my Amount to ⟦E:id:1⟧' expected 'Balance'
FAIL en->en 'GAMER points balance'          rendered='GAMER Amount balance' expected 'Balance'
```

The owner's 2026-09-19 term changes (`Balance → Amount`,
`လက်ကျန် → ပမာဏ`) were never propagated to `app/store/seed.py:43`.

Work:
1. Single source of truth: `app/policy/regression_set.py` — 40 cases as
   data (`src`, `dst`, `input`, `must_contain`, `must_not_contain`,
   `note`). `seed.py` populates `policy_tests` from it; pytest consumes
   the same list (no duplicated expectations).
2. Coverage: each of the 5 concepts in each direction, both `အိုင်ဒီ` /
   `အိုက်ဒီ` transliterations, longest-match traps (`ဂိမ်းပွိုင့်` vs
   `ဂိမ်း`; `game points` vs `points` vs `gamer` vs `checkpoint`),
   mixed-language Burmese+English (the normal case), entity round-trip
   (URL / @mention / number / `/command`), separator evasion
   (`g-a-m-e`, `赌-场`), ratio bands, meta-response rejection, and
   negative cases that must **not** be masked.
3. Deterministic runner (no provider): mask → render → deny_scan →
   restore, asserting `must_contain` / `must_not_contain` and an empty
   deny-scan. Parametrised, so the failure names the case.
4. Optional live runner behind `PYTEST_LIVE_PROVIDER=1` that pushes the
   same 40 cases through `ProviderRouter` — §4.6 requires the set to be
   run against every provider before it goes live.
5. Publish gate: `app/policy/governance.py::assert_publishable(version)`
   raises unless all cases pass; called by the seed/publish path.

Delivered:
- `app/policy/regression_set.py` — 40 `RegressionCase` rows (+9 `DenyCase`
  rows for Layer 3), `evaluate()` / `check()` / `run_all()` for the
  deterministic runner, `run_live()` for the opt-in provider run;
- `app/policy/governance.py` — `regression_report()` /
  `assert_publishable()` / `PolicyNotPublishable`;
- `app/store/seed.py` — the stale 10-case `REGRESSION_SEED` is gone; the seed
  writes the same 40 rows to `policy_tests` and publishes the version only
  when the report is clean, otherwise `status="draft"`;
- `tests/test_regression_set.py` — 40 parametrised cases, coverage matrix,
  unique ids, stale-term guard, 9 deny cases, publish-gate pass/block tests,
  and the `PYTEST_LIVE_PROVIDER=1` hook.

Verified: `regression_report(1)` → `published - 40/40 regression cases
pass`; the seed builds 40 `policy_tests` rows with no blank expectations;
`pytest -q` → 119 passed, 1 skipped.

### 3.3 P1.2 — pipeline integration tests, Gates 3–10 — DONE

Verified gap (before this package): no test in `tests/` referenced
`run_translation`, `handlers`, `healthz` or `webhook` (grep returned
nothing); the only `ProviderRouter`/`AlertManager` use was two subclasses in
`test_repair.py`. The whole delivery path was unverified.

Delivered: `tests/fakes.py` (recording `FakeBot` — captures
`reply_parameters`, edits, deletes and chat actions; `StubRouter` with
scripted outputs, failure, hang and delay modes; `RecordingAlerts`;
`StubUserStore`; `make_services()`; `seed_cache()` for aged cache entries;
`FakeMessage`), `tests/test_pipeline.py` (22 tests) and
`tests/test_handlers.py` (21 tests):

- §03 input-resolution table, all six rows, at handler level;
- `TOO_LONG` shows the real count and consumes **no** rate slot
  (Gate 5 precedes Gate 8);
- confident CJK/Thai → `UNSUPPORTED_LANG`, no provider call;
- reply to the bot → `ALREADY_TRANSLATED`, no provider call;
- duplicate inside 30 s → cached resend, no rate slot;
- rate limit → countdown text matches `ratelimit.check`;
- cache hit → no provider call, `cache_hit=True` logged;
- spend cap → `SPEND_CAP_REACHED` + P2 `SPEND_CAP`;
- daily soft cap → `DAILY_CAP_REACHED`;
- policy refusal → placeholder **deleted** (withhold), P2 `POLICY_LEAK`,
  usage `status=policy_refusal`;
- provider outage → `ERROR_GENERIC` + P1 `PROVIDER_OUTAGE`;
- reply anchor is set on the placeholder send (Locked Rule 5), and every
  edit targets that same message id (one send, then edits);
- the provider only ever receives the masked text (asserted on
  `router.masked`), never the raw source;
- typing indicator, spend counter, stats and cache-hit accounting;
- `/start`, `/help`, `/whoami` (gate-exempt, private-only), `/status`
  (admin-only), the `lang:` callback, group-chat silence and non-member
  silence.

Findings this package produced:

**(A) No script check — a wrong-language answer was shipped. FIXED.** With
the auto toggle resolving the target to Myanmar, a provider that replied in
English passed every existing guard: `ratio_ok` saw latin→latin (band
0.3–3.0) and `deny_scan` only holds the *target* language's list. Verified
before the fix — input `"check my game points"` with the stub answering
`"send chips now"` was delivered as `🌐 EN → MY\nsend chips now`, with
`router.calls == 1`, no retry and no alert.

Fix: `policy.script_ok(output, dst)` — a Layer 2b sanity check applied in
`translate_policied`'s `_problem()` gate alongside the ratio and meta checks,
so a wrong-script answer is retried once and then withheld like any other
unstable output (`AllProvidersDown("unstable output (wrong script for my)")`
→ `ERROR_GENERIC` + P1). Deliberately narrow, to avoid withholding real
translations:

- fails only when the target script is **entirely absent** — `"Facebook ပါ"`
  and `"⟦T:user_id⟧ ကို စစ်ပေးပါ"` still ship;
- placeholders are stripped before counting (their own names are Latin, and
  they render into the target language afterwards), so a placeholder-only
  answer is not a false failure;
- fewer than 3 script-bearing characters is too little to judge, so a
  translation of a bare ID passes;
- unknown/`auto` targets assert nothing.

Verified after the fix: English answer → 2 calls, withheld, P1 alert;
corrected on retry → shipped; Burmese answer → 1 call, shipped.

The new guard also caught two of these tests relying on the old behaviour
(`test_entities_survive_the_round_trip` and
`test_third_message_in_30s_gets_a_countdown` both fed English answers to a
Myanmar target); both now state their direction explicitly.

**(B) The gate ignores the injected user store.** `groupgate.py:99/104` build
a fresh `UserStore()` per call instead of using `services.user_store`, so the
hot path queries Postgres on every message and `/status` can consult a
different source than the gate. Already tracked as P1.4.

**(C) Minor, expected:** no typing indicator is sent when the provider
answers instantly — `ChatActionSender`'s worker never gets scheduled. The
test asserts the indicator for a provider with a 20 ms delay.

`/healthz` and the webhook endpoint are still untested (they need a FastAPI
TestClient run against the app); carried into P1.3, which touches both.

`script_ok` is an extension beyond the spec (section 08-03 specifies only the
ratio check). It belongs in the README's spec-deviations list — carried into
P1.5 with the other documentation drift.

### 3.4 P1.3 — alerting completion (MUST 11) — ~0.5 day

Verified: `AlertManager.resolve` (`app/services/alerts.py:113`) has
**zero callers**; only three alert sites exist
(`pipeline.py:163` POLICY_LEAK, `:476` SPEND_CAP, `:527`
PROVIDER_OUTAGE). Spec §07 triggers not implemented: DB unreachable,
Redis unreachable, policy engine raising on >20%, circuit-opened,
error rate >5 %/5 min, p95 > 4 s, P3 daily digest, P3 unknown
`/whoami`, and every resolution message.

Work:
1. Resolution: `PROVIDER_OUTAGE` resolves when a breaker closes again;
   cache/DB alerts resolve when the ping recovers.
2. P2 `PROVIDER_CIRCUIT_OPEN` from `provider.py` where
   `circuit_opened` is already logged.
3. A 60 s watchdog task over `Stats` for error rate > 5 %/5 min and
   p95 > 4 s (P2), and the P1 "policy engine raising on >20 %" check.
4. P1 when `/healthz` observes `db` or `cache` false.
5. P3 daily digest at 09:00 Asia/Yangon (volume, cache hit rate, spend,
   rejections, policy hits, provider states) — SHOULD 21; P3 on
   `/whoami` from a user the gate denied.
6. Privacy test: assert nothing that reaches `_deliver` can contain
   source or translated text (concept/provider/version/counts only).

Existing cooldown (15 min), hourly cap (20) and fingerprinting stay as
they are; they just need tests.

### 3.5 P1.4 — fail-soft cache, and Postgres out of the hot path — ~0.5 day

Verified with a stub Redis client that raises:

```
check_idempotent   -> RAISED ConnectionError  [no degrade]
mark_inflight      -> RAISED ConnectionError  [no degrade]
get                -> RAISED ConnectionError  [no degrade]
put                -> RAISED ConnectionError  [no degrade]
get_str / set_str  -> ok                      [degrades]
ping               -> False
```

`cache.py:105,113,131,150` let Redis errors escape. `mark_inflight` is
called before the placeholder is sent (`pipeline.py:412`), and
`check_idempotent` runs in the outer middleware (`main.py:84`), so a
Redis blip makes the bot stop answering entirely — with no alert,
because no alert trigger exists for cache failure.

Work:
1. Degrade to the existing `_mem` store on Redis errors for the four
   methods above; count consecutive failures; raise P1
   `CACHE_UNREACHABLE` once, resolve on recovery. Document the
   correctness trade (in-memory idempotency is per-process, best-effort).
2. Remove the three Postgres round trips per message that exist when
   `DATABASE_URL` is set — `groupgate.py:99/104` `is_allowed`,
   `handlers.py:167/180/255` `get_target`, `pipeline.py:445`
   `daily_soft_cap`. Spec optimisation §08-02: nothing in the hot path
   should touch Postgres. Add a 60 s in-process memo for
   role/target/soft-cap with explicit invalidation on admin changes;
   Neon cold start stops sitting in front of every message.

Acceptance: with a dead Redis the full pipeline still returns a
translation (or a clean generic error) and exactly one P1 fires; with
`DATABASE_URL` set a steady-state message issues 0 queries after the
first minute.

### 3.6 P1.5 — budget, logging, doc drift — ~0.25 day

- `pipeline.py:63` `HANDLER_BUDGET_S = 60.0` vs the spec's 12 s handler
  budget (SHOULD 16: "the user must always receive something"). Set 12 s
  or record the deviation in the README with a reason.
- `pipeline.py:540-544` (handler-budget timeout) and `pipeline.py:445-453`
  (daily soft cap) return without `log_usage` → those rejections are
  invisible in `usage_log`, which is exactly the evidence MUST 18 /
  risk E depend on.
- `app/bot/strings.py:36` hardcodes "/ 250 characters" while
  `MAX_INPUT_CHARS` is configurable — format the configured cap.
- README drift: line 7 still claims `EN / MY / ZH` in scope (v3.2 cut
  Chinese), line 89 cites the v3.1 spec filename, line 118 says backup
  providers are "not yet config-driven" although
  `config.provider_defs()` already parses `PROVIDERS_JSON`.
- `.env.example` has no `AUTO_TOGGLE` entry (`config.py:60`, default on).
- `pipeline.py:99` `lang_buttons()` is dead code (v3.2 removed the
  buttons); delete it or keep it with an explicit note.

---

## 4. Explicitly out of P1 (P2 candidates)

DB-driven policy / prompts / provider list with a 60 s version poll and
one-click rollback (SHOULD 13); admin dashboard Mini App with initData +
TOTP (SHOULD 19); nightly `pg_dump` backup with a performed restore
(SHOULD 20); encrypted provider keys and one-command rotation (§08-16);
written staff notice (SHOULD 22); bad-translation reporter (§12);
Zawgyi patch (Appendix A); inline / group / voice modes (LATER).

---

## 5. Sequencing and effort

| Order | Package | Effort |
|---|---|---|
| 1 | ~~P1.0 group-gate `chat_member` wiring + status enum~~ **done** | 0.5 h |
| 2 | ~~P1.1 40-case regression set + publish gate~~ **done** | 1 day |
| 3 | ~~P1.2 pipeline/handler integration tests~~ **done** | 1 day |
| 4 | P1.3 alerting completion + resolutions | 0.5 day |
| 5 | P1.4 fail-soft cache + hot-path DB removal | 0.5 day |
| 6 | P1.5 budget, logging, doc drift | 0.25 day |

P1.1 before P1.2: the regression set fixes the policy expectations that
the pipeline tests will assert against. P1.3/P1.4 last among the
behaviour changes so the new tests can cover them.

Total ≈ 3 working days.

Verification for every package: `.venv/bin/python -m pytest -q` green,
plus the package-specific acceptance list above.
