# EgoHandKit Project Memory

## Native Ray Integration (2026-10-09)

Merged `feature/mint-frontend` (8a3f7a8) into `perf/hand-render` (ae9e561).
Retained native source/Python overrides, exporter non-overwrite, FFV1 temporary
depth preparation and optional final-render hooks. The orchestration adapter
now lives at `roboego_hand_vis/hand/render_actor.py`, not under Docker. The native
launcher forwards `--render_actor_workers {0,1,2,4}` and configures PYTHONPATH.
Default zero preserves the serial renderer and does not require Ray. Historical
Docker measurements below do not establish native performance or visual parity.
No model assets or environment packages are provisioned by this merge.
Validation: 279 tests and 6 subtests passed; one MANO-asset-dependent test skipped.
The native wrapper forwards the Actor flag while retaining compensation and
orientation gates. Ray is absent from the current native EgoHandKit environment;
real native Actor/GPU performance and visual parity remain unverified.

## FFV1 Depth Compatibility (2026-10-09)

Server evidence: depth_archive_v1 output deleted source PNGs and retained lossless
gray16le FFV1 with millimeter units and zero invalid values. PNG-only depth loading
therefore failed before backend inference. Compatibility now belongs to EgoHandKit
run.py, not the external orchestration launcher. Preparation uses temporary PNGs
and existing logs only; PNG inputs and algorithm parameters remain unchanged.
Focused CPU tests cover uint16 round-trip, invalid metadata, damaged archives,
frame mismatch and cleanup. Actual server archive/GPU pipeline remains unverified.
SIGKILL/machine failure cannot guarantee cleanup; decoded data needs disk space.

## Native Launcher Patch (2026-10-08)

Isolated branch feat/native-hand-launcher starts from feature/mint-frontend
34b3b1c, not perf/hand-render. Only the shell entrypoint is adapted: configurable
source paths and optional absolute Python instead of Conda activation; differing
existing MINT exporters are rejected instead of overwritten. Missing exporters
are still copied. All algorithm flags and output layout remain unchanged.
The companion native-hand main-project launcher chains MINT and this script,
retains all outputs, and serializes its own runs per checkout. Existing caches
and legacy manual commands remain a concurrency limitation. CPU fake-interpreter
tests cover two commands, paths with spaces and exporter non-overwrite. No native
GPU quality/performance validation or environment installation has been done.

Last updated: 2026-09-21.

## Authority and Snapshot

- `PIPELINE_CONTRACT.md`: current interface and behavior contract.
- `README.md`: recommended commands and production/compatibility option split.
- `HMR_PRIMARY_VALIDATION.md`, `HAND_IDENTITY_VALIDATION.md`: historical run evidence.
- Branch at this update: `feature/mint-frontend`; pre-fix baseline `d644f31`.
- This memory accompanies the projection fix and documentation commit. Inspect
  `git status` and recent history for the current revision and pending edits.

## Agreed Production Strategy

```text
canonical -> sensor wrist depth plus wrist-surface compensation / existing 1m limit -> motion gate
-> HMR inference / optional partial-hand depth recovery
-> image/depth duplicate identity check + HMR-first MINT consistency
-> endpoint wrist gate -> HMR/MINT selection -> final joint smoother
-> Parquet -> common colored MANO fitting -> final render
```

The entry point is `scripts/run_without_front.sh`. It enables HMR-first policy,
image/depth duplicate checking, partial recovery, stable anchoring, final joint
smoothing, Parquet export, and Parquet rendering. Direct `run.py` defaults differ.

- Severe rejection: wrist discrepancy > 0.15m or palm-vector discrepancy > 80deg,
  supported MINT metric reference, and 3 consecutive frames in one track fragment.
- Scale ratio is diagnostic in HMR-first mode. Old 0.08m/40deg/scale veto remains
  available outside this policy, not the production tuning interface.
- Duplicate checking uses HMR joint-box overlap, independent depth, and frontend
  image assignments. It does not require MINT metric-depth trust. Only the wrong
  side falls back when evidence is sufficient; overlap alone is not a veto.
- Final smoothing operates on selected joints. Missing frames, fragment changes,
  and excessive jumps split smoothing; source changes alone do not.
- Retained CLI alternatives are not dead code. Do not delete them merely because
  the wrapper does not enable them.
- As of the wrist-surface update, the production wrapper enables
  `--wrist_surface_depth_compensation`. Registered depth sampled at the wrist
  pixel is treated as visible surface depth and converted to joint-center depth
  with an orientation-aware positive Z offset, defaulting to 0.015-0.030m:
  palm/back-facing views use the smaller end and edge-on views use the larger
  end. Raw surface depth, offset, and compensated depth are diagnostic fields.

## Latest Confirmed Fix: Partial Recovery Projection

At frame 110 (3.667s), both predicted right wrists were outside the image. Visible
MCP depth estimates disagreed, so recovery borrowed uncalibrated MINT wrist Z.
Previously, stable recovery preserved only the HMR wrist ray and translated the
original relative XYZ hand. Other joints no longer matched HMR image predictions.

Measured example: index tip originally (1236.64, 847.97) px became approximately
(1274.6, 952.9) px after anchoring. Maximum joint projection displacement was
143.18px. Final smoothing was not the principal source of that displacement.

Current fix in `hmr_backends/utils/mint_3d_consistency.py`:

- For stable recovery (`wrist_ray_source == 'hmr'`), use recovered wrist Z plus
  original HMR relative joint Z, and back-project each valid HMR joint on its own
  image ray through registered camera intrinsics.
- Reuse the normal depth-anchoring helper. This preserves valid projections and
  relative Z, not original relative XYZ or guaranteed metric hand shape.
- Stable mode off retains legacy behavior. No new rejection thresholds added.

Verification: 205 tests and 6 subtests passed; two existing dependency deprecation
warnings. Replayed all 177 recovered stable hands from the reference run: maximum
valid-joint projection error < 4e-13px. These checks are before final smoothing
and MANO fitting, not proof of final visual accuracy.

The user reran the test and reported it as broadly satisfactory on 2026-09-21,
then requested committing the changes and documenting recommended parameters.
The supplied run command targets `egohandkit_projection_fix_test`. This is user
visual feedback, not a new agent-measured full-run artifact audit or a claim
that every remaining risk is resolved. Keep this as the working baseline.

## Deferred Case: 0.767-0.833s

Frames 23-25, left: HMR/MINT wrist discrepancy about 0.62-0.63m and maximum palm
vector angle 123-127deg. MINT depth support was inconsistent, so HMR-first policy
accepted HMR. The abnormal joints already existed before final smoothing.
The projected hand lies near another person's clothing, without clear visible
support for the wearer's left hand. This suggests a wrong-region prediction;
it does not establish a general anatomical impossibility test.

User explicitly agreed to defer this problem: no generic first-person pose
deletion gate now. MINT unreliability is not proof of HMR validity, but disagreement
alone is also insufficient to reject both. A future solution needs independent
support and false-positive evaluation, not thresholds fitted to these timestamps.

## Remaining Risks and Next Steps

1. The user reports the new run is broadly satisfactory. Avoid adding more rules
   without a new reproducible symptom; rendering can still differ from input
   joints due to smoothing and MANO fitting.
2. Existing sampled depth > 1m can remove both sources even if the sample landed
   on background. Known risk, deliberately not changed. Prioritize after visual
   acceptance, with an explicit depth-reliability policy and user agreement.
3. Borrowed MINT Z can be wrong even when 2D alignment is preserved. Do not equate
   image fit with accurate metric 3D.
4. Depth-source changes and smoothing boundaries can still produce jumps; more
   smoothing can introduce lag and is not a universal remedy.
5. A valid Parquet hand may fail MANO fitting and not render. Distinguish fit
   failure from selection/depth rejection or absent observations.

## Local Reproduction Data

All paths below are workstation-specific:

- Video: `/home/user/1/data/long/left_rectified_600.mp4` (600 frames, 30fps,
  1920x1050; timestamps here use zero-based frame index divided by FPS).
- MINT: `/home/user/1/data/long/mint/prediction.npz`.
- Depth root:
  `/home/user/1/新数据测试/processed_data/session_20260826_100651_整理货架_20260827190358/depth`.
- Extracted frames: `test_data/images/left_rectified_600/000000.jpg` etc.
- Reference run:
  `/home/user/1/data/long/egohandkit_identity_test_final/mint/left_rectified_600_canonical`.
- New run target:
  `/home/user/1/data/long/egohandkit_projection_fix_test/mint/left_rectified_600_canonical`.

Reference artifacts: `stages/40_backend_raw/outputs.pkl`,
`stages/45_mint_3d_consistency/checked_outputs.pkl`, consistency JSON,
`final/hand_tracking.parquet`, `final/final_joints_smoother.json`,
`final/parquet_mesh_fit.json`, and `final/render.mp4`.

The reference identity run retained 994 hand samples, rendered 992, and rejected
four duplicate left HMR outputs at frames 596-599 while retaining the right side.
These counts describe that historical run, not the projection-fix rerun.

Temporary diagnostic files `/tmp/egohandkit_cases_audit.py` and
`/tmp/egohandkit_cases_audit.json` may exist, but are not durable project assets.

## Isolated Render Profiling (2026-10-04)

Worktree: `/home/user/EgoHandKit-hand-opt`, branch `perf/hand-render`, based on
`34b3b1c`. Original `/home/user/EgoHandKit` is unchanged. Optional timing dictionaries
cover MANO fitting, image reads, renderer creation/scene/draw/delete, overlays,
JPEG writes, and video image loading/encoding. No algorithm, thresholds, fitting
batch size, iteration count, or renderer lifecycle changes are intended.

The orchestration repo supplies a standalone replay of the saved final Parquet.
Reference is the final directory in `ray_video_20261004_182731`, not raw backend
meshes. Original frames must be regenerated; rendered JPEGs cannot be reused as
source images. Replays use new output directories and compare fitting diagnostics
and decoded JPEG pixels. Pixel equality is not human visual acceptance.

Focused CPU tests: 21 passed, 1 skipped (MANO assets absent from host worktree).
Full GPU replay and timing breakdown remain pending; repeated renderer creation
is observed in code but is not yet proven to dominate runtime. Actor performance
and EGL context reuse remain hypotheses. No new Ray dependency is added here.

## EGL Backend Comparison (2026-10-05)

Full identical-code replays in the orchestration repository confirmed Mesa
llvmpipe in the preserved old hand image, NVIDIA RTX 4070 in the EGL-only fix.
Rendering pipeline: 866.348 s CPU control versus 546.870 s GPU; drawing/readback
411.812 versus 82.494 s. Both fit reports match the saved reference and render
3095 hands over 2137 frames. GPU rasterization produces small pixel differences
(max channel delta 15); detailed metrics and sampled visual inspection are in
`docker/hand-env/egl-fix/VALIDATION.md` of the orchestration repo. Strict-comparison
reports remain `comparison_mismatch`; differences were accepted for promotion,
not erased. Local hand image `:dev` is now the EGL-fixed image, old tag retained.

No Actor or renderer lifetime changes yet. Deletion remains about 212 s across
1906 calls. Future reuse/Actor comparisons must keep the EGL backend constant;
do not attribute this environment fix's benefit to Ray. Full MINT/HaMeR inference
was not rerun for this comparison, so its end-to-end speedup is not measured.

## Renderer Reuse Prototype (2026-10-05)

Supersedes the pending lifecycle implementation above: an optional caller-owned
`offscreen_renderer` now permits the orchestration replay to compare per-frame,
local reuse, and single Ray Actor reuse. Production defaults remain unchanged.
The Actor lives in the orchestration repository, not EgoHandKit; it owns one EGL
context, accepts one frame at a time, and rebuilds the scene on each call.

Validation: four synthetic 64x64 renders (including empty geometry, changed
geometry/handedness, and returning to the first frame) matched per-frame color
and depth arrays exactly for local and Actor reuse. Each reused owner created
and deleted once. Evidence: orchestration repo
`tmp/ray-render/actor_lifecycle_20261005_2/actor_smoke.json`.
This is not real-hand visual acceptance, a long-run memory test, or evidence of
speedup. Full replay and failure recovery beyond explicit cleanup remain unverified.

## Full Reuse Replay Results (2026-10-05)

The full-replay pending item above is now measured once per mode, sequentially
under the same NVIDIA EGL image `40aca6e01bda`, with unchanged lifecycle code
throughout. Per-frame/local/Actor replay wall times excluding verification and
Ray shutdown: 600.514 / 268.975 / 299.415 seconds. Render pipeline wall times:
582.410 / 250.704 / 278.936 seconds. All 2137 frames and 3095 rendered hands
retained, fit diagnostics equal to the original reference, and all three videos
fully decoded to 2137 frames at 30 FPS. Local and Actor each created/deleted once
for 1906 rendering calls. No algorithm or production-default changes.

Reuse is the effective optimization; Actor adds overhead relative to local reuse.
The Actor benefit versus baseline is not evidence Ray is faster than ordinary
Python resource reuse. Renderer-call totals: 339.375 / 37.099 / 64.674 seconds.
JPEG reload also varied by 33 seconds, so total gains are not purely lifecycle.
One trial each, uncontrolled OS cache, desktop GPU interference possible.

Strict quality mismatch is retained: same-GPU per-frame/local differs at 64,821
pixel positions (801 frames, max channel delta 8), local/Actor at 3,675 positions
(47 frames, max 6), out of 4,308,192,000 positions. Selected worst-mean-error crops
showed no visible displacement; the cause of small differences is not isolated.
No pixel threshold was relaxed and this is not exhaustive visual acceptance.

Output roots in `/home/user/ego_data/hand_opt_runs/`:
`actor_validation_per_frame_20261005`, `actor_validation_local_20261005`,
`actor_validation_actor_20261005`. Resource samples show approximately stable RSS
during rendering and growth during the preexisting whole-video JPEG loading.
Peak summed tree RSS: 15.362 / 15.402 / 17.182 GiB (shared pages may double count).
Orchestration `docker/ray-env/README.md` records complete boundaries and evidence.
Keep local reuse as simplest performance candidate and Actor as learning variant;
production promotion and further Actor work await review. No commit yet.

## Whole-Frame Actor Review Candidate (2026-10-05)

Extracted the existing frame body to `render_tracking_frame` without changing
its operations, parameters or ordering. Optional synchronous `frame_writer`
lets the isolated worker own RGB/depth reads, rendering, overlay and JPEG write;
the caller validates a small frame-completion result. Default uses the same
helper directly. Fitting and video encoding stay in the driver. No production
entry-point changes or Ray dependency in this repository.

Full same-code controls under the same image: `local-frame` replay 261.162 s,
`actor-frame` 299.994 s (excluding verification/shutdown). Both 2137 written
frames, 3095 hands, 1906 render calls, one create/delete, original fit report
equal. Both encoded videos fully decode to 2137 frames/30 FPS/1920x1056.
Pixel comparison new local/Actor: 44 changed frames, max channel delta 5/255,
mean absolute delta 6.223e-7 (0-255 units). Previous local/new local: 52 changed
frames, max 6/255. Strict mismatch is retained, not silently accepted as equal.

Moving whole-frame work removed large RGBA/depth return values but did not
improve the previous Actor's 299.415 s. This negative result is recorded; do not
claim new speedup or blame the entire difference on communication. Internal
Actor overlay/draw/read timings are also slower; cause remains unverified.
New output roots: `frame_actor_local_20261005` / `frame_actor_remote_20261005`
under `/home/user/ego_data/hand_opt_runs/`. No core edits during the paired runs.

35 focused tests passed, one asset-dependent skip. Five orchestration ownership
tests and real GPU synthetic JPEG/error tests passed. A test initially failed
when it interleaved independent EGL lifetimes in one process: pyrender's
`delete_context` calls `eglTerminate`, invalidating the other live renderer.
Baseline is now drawn before the reusable context is created; real replay owns
one renderer per process. Evidence and review order are in orchestration README.
Keep this version for review; no queue/pool/production promotion yet. Hard-crash
resume and atomic publication remain out of scope. Failed isolated outputs may
contain partial JPEGs and must not be used as successful results.

## Bounded Two-Actor Candidate (2026-10-06)

Current review candidate: orchestration `FrameActorPool` with two independent
EGL owners and at most one request per owner. Optional `frame_dispatcher` in
`render_tracking_parquet` dispatches after unchanged MANO fitting, validates the
completed count/exact JPEG names, then runs the unchanged encoder. Per-worker
frame IDs increase but may have gaps; completion can be out of order. No normal
entry-point changes, new EgoHandKit dependencies, or algorithm changes.

Five full sequential replays on the same code/image, order pool2 A, local A,
pool2 B, local B, pool1. Replay wall seconds excluding verification/shutdown:
pool2 189.790 / 185.772; local 240.030 / 237.288; pool1 275.068. Local mean
238.659 versus pool2 mean 187.781: 21.3% reduction, 1.271x throughput. The old
261-second result is not the contemporary baseline. Frame stage: local about
158.7 s, pool1 195.1 s, pool2 104.2-105.3 s; video loading+encoding similar.
This is useful concurrency managed by Ray, not proof Python multiprocessing
could not match it, nor a complete MINT/HaMeR pipeline speedup.

All five retain 2137 frames / 3095 rendered hands and equal fit diagnostics;
videos fully decode at 30 FPS / 1920x1056. Two-Actor runs have 2137 successful
acks, peak in-flight=2, total render calls=1906, one create/delete per worker.
Same-GPU pair A comparison: 79 changed frames, 5,436 changed pixel positions,
max channel difference 6/255 (3 pixels above 5). Pair B: 64 changed frames,
max 6/255. Selected worst crops showed no obvious shift, not exhaustive visual
acceptance. Strict mismatch statuses retained, no relaxed quality thresholds.

Peak sampled summed RSS: pool 17.49/17.46 GiB versus local 15.40/15.33 GiB;
shared pages can double count. Device-wide VRAM peaks pool 6282/6219 MiB versus
local 6122/6124 MiB. No sampling errors. Desktop graphics and uncontrolled OS
cache remain limitations; two repeats do not establish confidence intervals.
Tests: 48 focused EgoHandKit passed, one asset-dependent skip; eight orchestration
unit tests plus real GPU pool/pixel/failure smoke passed, including deliberate
worker death and cleanup. Whole-video mesh/JPEG buffers remain O(video length).

Artifacts: `/home/user/ego_data/hand_opt_runs/{pool2_a_20261006,pool_control_a_20261006,
pool2_b_20261006,pool_control_b_20261006,pool1_control_20261006}`. Smoke evidence:
orchestration `tmp/ray-render/pool_failure_smoke_20261006/actor_smoke.json`.
The user approved committing this candidate on 2026-10-06. Keep it frozen for
review; no further worker growth, Ray Data rewrite or production promotion.
Hard-crash resume/atomic publication,
other videos and multi-GPU behavior remain out of scope.

## Opt-In Full-Pipeline Integration (2026-10-08)

User requested complete timing and configurable Actor count after four-Actor
replay showed a benefit. Added `--render_actor_workers {0,1,2,4}`, default 0,
with a narrow optional call to the orchestration `render_actor` adapter from
`_render_results`. No Ray dependency is required in default mode. The adapter
starts/shuts down Ray around final rendering and keeps one frame per worker
in flight. It does not change HaMeR, gates, depth anchoring or smoothing.

Full same-image sequential runs on the existing shelf session, orchestration
artifacts `/home/user/ego_data/hand_opt_runs/`:
`full_actor0_retry_20261008`: total launcher 1777.519 s, MINT 391.799 s,
export 1.604 s, EgoHandKit 1382.953 s.
`full_actor4_20261008`: total 1197.796 s, MINT 393.677 s,
export 1.654 s, EgoHandKit 801.027 s. End-to-end reduction 32.61%, 1.484x
throughput on this pair, not a general batch-throughput guarantee.
The candidate combines persistent renderer reuse and four-way dispatch;
this is not attribution of the whole gain to Ray's scheduler alone.

Both deliver 2137 frames; Parquet schema and every column agree, with NaNs
treated as equal for missing joints. Both 3D joint arrays have zero difference,
presence/source masks match, and MANO diagnostics match (3095 rendered hands).
Strict JPEG/visual acceptance is separate; see orchestration experiment report.
Only one successful full pair, uncontrolled caches and desktop interference.
Initial control `full_actor0_20261008` failed before rendering on a PNG CRC
read error at depth frame 539. No data or error checks were changed. Host CRC
validation, 100 same-container reads and all 2137 depth-image reads subsequently
passed, followed by successful full runs. Root cause is not isolated; failed
attempt remains recorded and is excluded from successful timing comparisons.

New targeted tests cover CLI opt-in, missing adapter/dependencies and unsupported
counts. Defaults remain unchanged; no automatic promotion, distributed-node
support, retry/resume, or VIO changes. All changes remain pending user review.
