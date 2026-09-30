# #1378 — Realtime voice mode (research / spike)

**Verdict: adapt the shipped REQ-77 custom path for LAN LiteLLM batch STT/TTS. Do not ship a full realtime voice product.**

This brief is the spike deliverable for
[issue #1378](https://github.com/matthewhand/open-swarm-private/issues/1378).
It is **not** a product ship. No live audio, paid provider, LAN host, or secret
is required to read or merge it.

> **Source note.** This runner's GitHub Issues API returned 403 for the private
> issue body. Success criteria used here are the operator brief that launched
> the spike: options matrix, map onto existing Swarm speech surfaces, recommend
> a v1 path for LAN LiteLLM STT/TTS, and include the composer
> waveform↔submit UX sketch. Claims about in-tree code are verified against
> this checkout. External LiteLLM / OpenAI / Speaches claims are cited.
> Anything not verified from a primary source is marked **unverified**.

---

## 1. Scope

### In scope

- Compare voice-transport options that a later implement issue could pick.
- Map each option onto **already-shipped** Swarm speech surfaces.
- Recommend a **v1** that uses an operator-owned LAN LiteLLM as the
  OpenAI-compatible audio gateway (`/v1/audio/transcriptions`,
  `/v1/audio/speech`).
- Sketch the composer **waveform ↔ submit** control so a later UI issue does
  not fight #1070 / #1096 / #1148 / REQ-77.

### Out of scope (explicit)

- Implementing a duplex realtime voice agent (barge-in, WebRTC, phone trunk).
- Auto-filling Settings → Speech from `LITELLM_BASE_URL` or any other profile
  URL (REQ-77: empty custom URL never guesses a host).
- Wakeword / shared-mic ownership with chatty-commander (`ROADMAP.md` § wakeword).
- Persisting tokens, LAN IPs, or personal dumps. Config examples use env
  **names** and the already-documented loopback placeholder from
  `USERGUIDE.md` (`http://127.0.0.1:8000/v1`).
- Changing seat kinds, the composer provider picker, or `blueprint_id`.

---

## 2. Existing Swarm speech surfaces

REQ-77 / #422 already shipped a complete **push-to-talk + read-aloud** stack.
#116 added a per-agent voice bind. A v1 LAN path should **reuse** these, not
add a parallel Kind or a second audio client.

| Surface | Location | What it does today |
|---|---|---|
| Settings → Speech | `webui/frontend/src/components/SpeechSettings.tsx` | Per-direction `source` (`system` \| `custom`), base URL, model id, **api-key env name only**. System stays selected even if a custom URL is stored. |
| Speech persist / probe | `src/swarm/core/speech.py` | Reads `swarm_config.json` `speech.*` then `SPEECH_STT_*` / `SPEECH_TTS_*` env. Empty URL → no host. Refuses `:8001` and `open-litellm` / `fly.dev` hosts. Persist writes `${ENV}` only. |
| REST | `src/swarm/views/speech_api.py` | `GET/PATCH /v1/speech/`, `POST /v1/speech/transcribe/` (multipart file → custom `/v1/audio/transcriptions`), `POST /v1/speech/speak/` (JSON text → custom `/v1/audio/speech`). Responses never include live tokens. |
| Browser runtime | `webui/frontend/src/lib/speechRuntime.ts` | `system` = `SpeechRecognition` / `speechSynthesis`. `custom` = `MediaRecorder` blob → `transcribeSpeechAudio`, or `speakSpeechText` → `<audio>`. |
| Path resolver | `resolveSttPath` / `resolveTtsPath` | `source: custom` plus a non-empty URL uses custom. `source: custom` with an empty URL is unavailable — it does **not** fall back to the browser. `source: system` uses the browser when `SpeechRecognition` / `speechSynthesis` exists. A stored custom URL is used only when that browser API is missing (`speechRuntime.test.ts`). |
| Composer mic | `useComposerControls.handleMic` + `ChatBottomDock` | Mic starts listen. Second click stops. **Transcript is appended into the composer and does not auto-send.** Custom path toasts “click the mic again to stop.” |
| Mic-as-stop | `#1148` in `ChatBottomDock` + `.os-composer__icon--recording` | While listening the mic **is** the stop control (same footprint, square glyph). |
| Submit slot | `#632` / `#1070` / `#1096` | Send lives **outside** the pill, 2.25rem circle. Idle send is mounted and disabled (no reflow). Generation stop lives on the agent row, not the composer. |
| Per-agent bind | `#116` `agentVoiceBind.ts`, `speech.bind_for_agent` | `inherit` / `voice` / `endpoint`. Endpoint overlays STT/TTS base URL + model + env name. A non-empty overlay URL forces that direction's `source` to `custom`. `bind_for_agent` leaves a forbidden host (`:8001`, `open-litellm`, `fly.dev`) unchanged; persisting one is already refused in `agent_settings`. The browser helper does not repeat that host check. `auto_speak_replies` speaks the first not-yet-spoken complete assistant message after the thread has hydrated; history already on screen is marked spoken and skipped. |
| Agent editor | Agent editor Advanced → Voice | Operator binds voice / instruction / optional per-robot endpoints. |
| Config example | `swarm_config.example.json` `speech` | Default `source: system`, empty URLs, `${STT_API_KEY}` / `${TTS_API_KEY}` placeholders. |
| Docs | `CONFIGURATION.md` § Speech, `FEATURE_STATUS.md` REQ-77 row | Documents the same contract. Tests stub system APIs and HTTP — no live mic / LAN / paid calls. CI: `.github/workflows/req77-speech.yml`. |

### What is **not** a speech surface

| Nearby thing | Why it is not the voice stack |
|---|---|
| Composer routing picker (`NavbarRoutingPicker` / `composerPicker.ts`) | Adjusts `params.provider` / `params.model` only. Must never switch the seat or overwrite `blueprint_id`. Voice must not hitch a ride here. |
| LLM profiles / `LITELLM_BASE_URL` | Chat completions gateway. Same host *may* also expose `/v1/audio/*`, but speech settings stay a separate opt-in. |
| Chat websocket (`DjangoChatConsumer`) | Text turns. No audio frames today. |
| Bubble theme `speech` | Visual tails (`REQ-844`), not STT/TTS. |
| 3D robot `listen` clip (`REQ-194`) | Avatar pose only. Can later *react* to `sttListening`; it is not a transport. |
| ROADMAP wakeword / chatty-commander | Always-on detector + shared mic. Separate product. |

### Invariants a later implement issue must keep

1. **No guessed host.** Empty custom URL does not become OpenAI, LiteLLM, LAN, or `:8001`.
2. **Env name only.** PATCH that includes `api_key` is 400.
3. **Stored default stays `system`** until the operator sets `source` to `custom`. Custom with an empty URL is off (no browser fallback). The other direction is real: `source: system` with no browser recognizer will use a stored custom URL. Do not describe that as “empty custom falls back to system.”
4. **Transcript does not auto-send** (REQ-77). Waveform↔submit (below) commits a *take*, then the existing ↑ sends the turn.
5. **One composer action** (#1096): submit lives in the send slot. Mic is listen / cancel, not send.
6. **Generation stop stays on the agent row** (#1096). Voice listen-stop is the mic (#1148). Do not re-merge those.
7. **Bootstrap / demo LiteLLM is not a speech default.** `speech.py` already refuses `open-litellm` / `:8001`.

---

## 3. Options matrix

Legend: **Fit** = how well it matches shipped Swarm surfaces. **LAN** = can
stay on an operator-owned LiteLLM + local audio backend. **Latency** = typical
time-to-transcript / time-to-first-audio. **Ship cost** is relative to “reuse
REQ-77.”

| # | Option | Transport | LAN LiteLLM? | Fit on REQ-77 | Latency | Ship cost | Verdict |
|---|---|---|---|---|---|---|---|
| A | **Batch HTTP via existing `/v1/speech/*`** → LiteLLM `/v1/audio/transcriptions` + `/v1/audio/speech` | Composer `MediaRecorder` blob; Django proxies multipart / JSON | Yes — operator types the LiteLLM `/v1` base URL | Direct | One-shot after release (latency **unverified**; not measured in this spike) | Low (config + UX polish) | **v1** |
| B | Browser / OS `SpeechRecognition` + `speechSynthesis` | Web Speech API | No (vendor cloud or OS) | Already the stored default when `source` is `system` and the browser API exists | Fast interim on Chromium; quality / language vary | None | Keep as stored default |
| C | LiteLLM `/v1/realtime` WebSocket | Server-to-server WS, OpenAI-style events | Only if a *local* realtime model is behind the proxy (**unverified** for common LAN stacks) | New consumer + new Django/ASGI path; bypasses `/v1/speech/*` | Duplex (**unverified** latency) | High | Defer (full product) |
| D | LiteLLM WebRTC (`/v1/realtime/client_secrets` + `/v1/realtime/calls`) | Browser peer; LiteLLM mints token; **audio skips the proxy** | No — audio goes to OpenAI/Azure | New browser peer-connection; secrets handling | Lowest cloud duplex | High + policy conflict (audio leaves LAN) | Reject for LAN v1 |
| E | Chunked batch STT (sliced `MediaRecorder` → same `/v1/speech/transcribe/`) | HTTP every N00ms | Yes | Additive on A | Interim captions | Medium | v1.1 if operators want live text |
| F | Streaming TTS (`stream_format=sse` / chunked `audio/*` through LiteLLM) | HTTP stream on `/v1/audio/speech` | Yes, if the backend streams | Additive on `synthesize_speech` (today it `read()`s the whole body) | Faster time-to-first-audio | Medium | v1.1 for auto-speak |
| G | Direct provider Realtime (OpenAI / Azure / xAI), skip LiteLLM | WS / WebRTC to vendor | No | Parallel client | Low | High | Reject (breaks the LiteLLM gateway story) |
| H | Local OpenAI-compat audio **without** LiteLLM (Speaches / Voicebox pointed at Settings → Speech) | Same as A, different base URL | Yes, but two operator URLs | Direct | Same as A | Low | Supported already; LiteLLM is preferred when the operator already has a LAN gateway |
| I | vLLM `/v1/realtime` transcription | WS PCM16 chunks | Possible as a *backend*; LiteLLM proxy support for this path is **unverified** | New WS client | Streaming STT | High | Watch |
| J | Wakeword + shared capture (chatty-commander / openWakeWord) | Always-on mic service | N/A | ROADMAP-only; fights the composer mic for the device | Event-driven | High | Out of scope |

### Option notes (cited)

- **A / F — LiteLLM batch audio.** Proxy documents OpenAI-compatible
  [`/v1/audio/transcriptions`](https://docs.litellm.ai/docs/audio_transcription)
  (`mode: audio_transcription`) and
  [`/v1/audio/speech`](https://docs.litellm.ai/docs/text_to_speech)
  (`mode: audio_speech`). Swarm already calls exactly those suffixes via
  `transcriptions_url` / `speech_url`. LiteLLM
  [PR #33976](https://github.com/BerriAI/litellm/pull/33976) streams TTS bytes
  (and optional `stream_format=sse`); Swarm's `synthesize_speech` currently
  buffers the whole response — fine for v1, leftover for v1.1.
- **C / D — LiteLLM realtime.** Documented at
  [`/realtime`](https://docs.litellm.ai/docs/realtime) (WS) and
  [WebRTC](https://docs.litellm.ai/docs/proxy/realtime_webrtc). The WebSocket
  page lists cloud providers: OpenAI, Azure, xAI, Gemini, Vertex, Bedrock, and
  Meta Muse (transcription). WebRTC is documented for **OpenAI and Azure
  only**, and **does not send audio through the proxy** — it relays SDP and
  lets the browser talk to the vendor. That is the opposite of “LAN LiteLLM
  STT/TTS.”
- **H — Speaches / Voicebox.** Community OpenAI-audio servers
  ([Speaches](https://speaches.ai/),
  [Voicebox](https://github.com/agjs/voicebox)) expose the same
  `/v1/audio/transcriptions` + `/v1/audio/speech` pair (faster-whisper +
  Piper/Kokoro). Operators already wire them through LiteLLM as
  `model: openai/<backend-model>` + `api_base` + `model_info.mode`
  ([LiteLLM #12407](https://github.com/BerriAI/litellm/issues/12407),
  [LiteLLM #14897](https://github.com/BerriAI/litellm/issues/14897)). Swarm
  Settings → Speech can also point **straight** at that server; LiteLLM is
  the better v1 when chat and audio should share one gateway + one env key
  name.
- **I — vLLM realtime STT.** vLLM documents a
  [Realtime WebSocket transcription example](https://docs.vllm.ai/en/stable/examples/speech_to_text/realtime/)
  (`input_audio_buffer.append`, `transcription.delta`). Whether LiteLLM's
  `/v1/realtime` will proxy a self-hosted vLLM of that shape is
  **unverified**.

---

## 4. Recommended v1 — LAN LiteLLM STT/TTS on the shipped path

**Reuse option A. Do not open a realtime socket.**

```
mic → MediaRecorder (webm/opus)
    → POST /v1/speech/transcribe/     (Django, session auth, env key)
    → POST {LITELLM}/v1/audio/transcriptions
    → text appended to composer       (no auto-send)
    → operator hits existing ↑        (normal chat turn)

assistant text
    → POST /v1/speech/speak/          (optional Read aloud / auto_speak)
    → POST {LITELLM}/v1/audio/speech
    → <audio> playback
```

### Why this is the v1

- The HTTP shapes already exist on both sides. Swarm's custom path is
  literally “OpenAI-compatible audio.” LiteLLM's proxy is the same pair.
- LAN stays LAN: Django holds the env-resolved bearer; the browser never
  sees a live key.
- Operators who already run LiteLLM for `orchestration` / `auxiliary` /
  `delegation` add two `model_list` rows. No new seat kind.
- Failure mode is already honest: probe `DOWN`, empty URL = off, forbidden
  demo hosts refused.
- A later realtime product (C/D/I) can still be designed; v1 does not paint
  it into a corner and does not spend a websocket + barge-in + interruption
  state machine before anyone has LAN Whisper working.

### Operator config (placeholders only)

Chat completions already document
`LITELLM_BASE_URL=http://127.0.0.1:8000/v1` in `USERGUIDE.md` (stock LiteLLM
docs often use `:4000`; Swarm's example is `:8000`). Speech **must not**
copy that URL implicitly.

LiteLLM `config.yaml` sketch (operator-owned file, not committed here):

```yaml
model_list:
  # existing chat slugs omitted
  # LiteLLM proxy config reads os.environ/NAME (not Swarm's ${NAME} form).
  # #12407's working TTS comment sets api_base to http://<audio-host>:8100/v1.
  # The STT snippet in that same issue omitted /v1 and still transcribed.
  # LAN_AUDIO_BASE_URL should be whichever form that audio server expects.
  - model_name: whisper
    litellm_params:
      model: openai/Systran/faster-whisper-small   # cited, LiteLLM #12407
      api_base: os.environ/LAN_AUDIO_BASE_URL
      api_key: os.environ/LAN_AUDIO_API_KEY        # placeholder ok if keyless
    model_info:
      mode: audio_transcription
  - model_name: tts
    litellm_params:
      model: openai/speaches-ai/piper-fr_FR-siwis-medium  # cited working id, #12407
      api_base: os.environ/LAN_AUDIO_BASE_URL
      api_key: os.environ/LAN_AUDIO_API_KEY
    model_info:
      mode: audio_speech
```

Settings → Speech (explicit opt-in):

| Field | STT | TTS |
|---|---|---|
| source | `custom` | `custom` |
| base URL | The LiteLLM base the operator types (same host as `LITELLM_BASE_URL` in `USERGUIDE.md`). Include `/v1` or not — `speech._join_audio_url` accepts both. Speech does **not** expand a literal `${LITELLM_BASE_URL}` in this field. | same or a different audio-only host |
| model id | LiteLLM `model_name` (e.g. `whisper`) | LiteLLM `model_name` (e.g. `tts`) |
| api-key env | `LITELLM_API_KEY` (or a dedicated `STT_API_KEY`) | `LITELLM_API_KEY` (or `TTS_API_KEY`) |

Per-robot overlay: Agent editor → Speech mode `voice` (same host, this
robot's `tts_voice` / instruction) or `endpoint` (this robot's own audio
server). `auto_speak_replies` stays off unless the operator asks for it.

### What v1 does **not** change

- Default `source` remains `system`.
- Composer still inserts text; it does not start a turn by itself.
- Provider picker, rail seat, and `blueprint_id` stay untouched.
- No new REST resource. No new websocket opcode. No new Kind.

### Optional later affordance (still not a guessed host)

A Settings button **“Copy URL from LLM profile…”** that pastes the selected
profile's `base_url` into the STT/TTS fields and leaves Save in the
operator's hands is acceptable. Silent copy-on-load is not.

---

## 5. Composer waveform ↔ submit — UX sketch

Success asks for this sketch now so a later UI issue does not collide with
the composer doctrines already tested (`ChatBottomDock`,
`RailComposerBatch1146_1149`, REQ-77 voice-input tests).

### Shipped states (do not regress)

```
idle (no draft)
[ + ] [ Message…                    ][picker][ mic ]  (↑ disabled)

listening  (#1148 — mic IS stop)
[ + ] [ Message…                    ][picker][  ■  ]  (↑ disabled)

draft ready  (typed or STT inserted — REQ-77 does not auto-send)
[ + ] [ hello from mic          Esc ][picker][ mic ]  (↑ send)
```

Send is a 2.25rem circle **outside** the pill (#632). Idle send stays mounted
and inert (#1070). Generation stop is on the agent row (#1096).

### Proposed voice-take states (implement in a follow-up, not this spike)

```
listening (v1 voice take)
[ + ] [ listening…                  ][picker][  ■  ]  [ ~~~~ waveform ~~~~ ]
                                                      ^ send slot, click = COMMIT TAKE

commit in flight (custom STT)
[ + ] [ transcribing…               ][picker][ mic ]  (↑ disabled)

take landed (same as today's draft-ready)
[ + ] [ hello from mic          Esc ][picker][ mic ]  (↑ send)
```

| Control | While listening | Meaning |
|---|---|---|
| **Send slot (waveform)** | Enabled, `aria-label="Commit voice take"` | Stop capture → transcribe (custom) or finalize (system) → `appendTranscript` → leave text in the composer. **Does not** call `submitUserText`. |
| **Mic (■)** | `#1148` stop glyph | **Cancel** the take: abort `MediaRecorder` / recognition, discard buffer, no insert. |
| **Esc** | First press | Same as mic cancel (add to the existing Esc ladder *above* “clear draft”). |
| **↑ after take** | Existing send | Starts the chat turn. Unchanged. |

That is the waveform↔submit contract: **the submit slot becomes the waveform;
activating it submits the *take*, not the *turn*.** Auto-sending the turn
would violate REQ-77 and surprise anyone who uses mic as dictation.

### Geometry vs #1070

A useful waveform does not fit in 2.25rem. Two implement-time choices:

1. **Capsule (preferred).** While `sttListening`, the send slot grows to a
   fixed capsule (about 7.5rem × 2.25rem) with a canvas / CSS bars. Reserve
   that width on `.os-composer-row` (invisible spacer when idle) so the pill
   does not jump. Click target is the whole capsule.
2. **Mini meter (fallback).** Keep the 2.25rem circle; draw 3–5 level bars
   inside it. Zero reflow, weaker “waveform” read.

Do **not** put the waveform inside the textarea (fights ChatMessageInput,
slash menu, paste, routing picker). Do **not** replace the mic with the
waveform (mic is cancel; submit is commit).

### Motion and a11y

- `prefers-reduced-motion: reduce` → static bars or a “Listening” label, no
  oscillation.
- Theme tokens only (`var(--color-base-content)`, `var(--color-error)` for
  cancel). No raw hex in new rules where tokens exist.
- Announce via the existing `aria-pressed` mic plus
  `aria-label="Commit voice take"` on the waveform. Keep `data-testid`s:
  `composer-mic`, add `composer-voice-commit`.
- System STT can still commit on `onend` (today it already inserts). Waveform
  click should be equivalent to that finalization, not a second recognizer.

### Explicitly rejected UX

| Idea | Why not |
|---|---|
| Waveform click = stop + transcribe + `submitUserText` | Voice-to-turn. Breaks REQ-77 “does not auto-send.” Offer later as an opt-in (`speech.stt.commit_sends_turn`, default off). |
| Hold-to-talk on the send circle | Conflicts with #1070 disabled idle send and with pointer-up outside the circle. |
| Hide send while listening | Reflows the row; #1070 forbids it. |
| Morph send into generation-stop during STT | #1096 moved generation-stop to the agent row. STT cancel is the mic. |

### Follow-up implement issue (suggested title)

`feat: composer voice-take waveform in the send slot (no auto-send)` —
UI-only on top of the existing `handleMic` stop path; tests for commit vs
cancel vs typed send; no new backend.

---

## 6. Mapping options → Swarm (quick view)

| Option | Settings → Speech | `/v1/speech/*` | Composer mic | Read aloud / auto-speak | New code? |
|---|---|---|---|---|---|
| A v1 LAN LiteLLM | custom + operator URL | as-is | as-is (+ waveform later) | as-is | Docs + UX follow-up |
| B system | source=system | unused | `listenSystemStt` | `speakSystem` | none |
| E chunked STT | same as A | same POST, more often | slice blobs | — | `speechRuntime` only |
| F stream TTS | same as A | stream `speak` | — | progressive `<audio>` | `synthesize_speech` + client |
| C/D/I realtime | new “realtime” source **or** a different pane | unused or parallel | WS/WebRTC session | model audio track | large |
| H direct Speaches | custom URL to the audio box | as-is | as-is | as-is | none |
| J wakeword | n/a | maybe reuse transcribe | not the composer | maybe | ROADMAP |

---

## 7. Suggested issue split (after this spike)

1. **This spike (#1378)** — research only. **Fixes #1378.**
2. **Operator how-to** (optional doc PR) — Settings recipe pointing at LAN
   LiteLLM. Still no guessed default.
3. **Composer waveform commit** — §5. No backend.
4. **v1.1 streaming TTS** — if auto-speak feels slow on long replies.
5. **v1.1 chunked STT** — if operators want live captions in the composer.
6. **Realtime product** — only with a new Issue, a Kind/session story, and a
   decision that cloud WebRTC (option D) is acceptable. Not LAN v1.

---

## 8. Open questions

- Which LAN audio **backend** the operator will put behind LiteLLM
  (Speaches, Voicebox, cloud Whisper/TTS through the same proxy, something
  else). v1 does not care as long as the OpenAI audio paths answer.
- Whether Settings should offer “copy from LLM profile” (explicit paste) in
  the same implement issue as the waveform, or later.
- System STT on Firefox / Safari: Web Speech coverage is uneven; custom LAN
  path is the portable one. Keep system as default where it works.
- `instruction` on `/v1/audio/speech` is OpenAI `gpt-4o-mini-tts` shaped.
  Piper/Kokoro will ignore it. Agent-editor “voice instruction” stays
  best-effort.
- LiteLLM proxying of **local** `/v1/realtime` (vLLM) is **unverified**. Do
  not block v1 on it.

---

## 9. Sources

### In-tree (verified this checkout)

- `src/swarm/core/speech.py`, `src/swarm/views/speech_api.py`
- `webui/frontend/src/lib/speechRuntime.ts`, `speechSettings.ts`, `agentVoiceBind.ts`
- `webui/frontend/src/features/chat/useComposerControls.ts`, `ChatBottomDock.tsx`
- `webui/frontend/src/components/SpeechSettings.tsx`
- `CONFIGURATION.md` § Speech, `USERGUIDE.md` LAN LiteLLM example,
  `FEATURE_STATUS.md` REQ-77 row, `swarm_config.example.json` `speech`
- `tests/core/test_speech.py`, `tests/views/test_speech_api.py`
- `ROADMAP.md` wakeword / chatty-commander (out of scope)

### External (fetched)

- <https://docs.litellm.ai/docs/audio_transcription>
- <https://docs.litellm.ai/docs/text_to_speech>
- <https://docs.litellm.ai/docs/realtime>
- <https://docs.litellm.ai/docs/proxy/realtime_webrtc>
- <https://github.com/BerriAI/litellm/pull/33976> (streaming TTS)
- <https://github.com/BerriAI/litellm/issues/12407> / [#14897](https://github.com/BerriAI/litellm/issues/14897) (Speaches via `openai/` + `mode`)
- <https://docs.vllm.ai/en/stable/examples/speech_to_text/realtime/>
- <https://github.com/agjs/voicebox> (OpenAI-audio faster-whisper + Piper/Kokoro)
