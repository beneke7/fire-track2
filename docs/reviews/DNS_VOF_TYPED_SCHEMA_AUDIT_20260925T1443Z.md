# DNS/VOF typed-record extraction for H3

Read-only CPU audit, 2026-09-25 14:43 UTC. This memo extracts the candidate5
dns.in and vof.in records for a successor source-release interface. It does
not accept the parser, contract, candidate, or any source gate. No code,
shared contract, status, or plan file was changed.

## Frozen inputs and source identity

The v0.1 contract admits five exact candidate5 fixture triplets:
dns.in, source-boundary.in, and vof.in under
containers/flutas/candidate5/cases/source_boundary/. The following full
SHA-256 values are from the v0.1 table and were independently checked against
the fixture inventory. The three quiet/dry DNS files are byte-identical; both
crossflow DNS files are byte-identical; all five VOF files are byte-identical.

| Case | DNS SHA-256 | Source-boundary SHA-256 | VOF SHA-256 |
| --- | --- | --- | --- |
| dry_four | 929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0 | f14d5e44d14928e5c3db0b4158e9ff7122aec64ac591fc8ea2fea9ce5df154e0 | 2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54 |
| quiescent_one | 929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0 | 761dfef4cf386ae122344fc3b9b8e0fa3fb6e468ba79a7235224389c779b9b13 | 2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54 |
| quiescent_four | 929011ead3bf96a094b0082520de0aa333ac69b1a4fc5209847e9ca9dfda10e0 | f4d904ae10986f6fa6ff872f76435bb6e4cdb0b8a9c7707ff5307f911410f5b7 | 2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54 |
| dry_crossflow | 574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7 | 7bbb8cdd01a06ae6bcbfe47fb448d9cf5a61f3bb2ae82b7a83c6b688be1024db | 2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54 |
| crossflow_four | 574bcfe3afa0c17284677f78a28b5bdad70e97c80a32ee0dc8af1651227da7b7 | 55f485ce507b8d19fa05c4324308028696ef50ddfe3faec2bab6b1a242e201ec | 2b18cca4d60c9d64eb52804db2573afdab59be782b96d58f23fcf91eaabefa54 |

The fixture inventory SHA-256 is
a04cbac29baf540bce1c969ad0df2c081b0dc2a3a7a31177606c34602d7978f1; its
sha256sum -c check passed for all 15 input files. Each DNS/VOF file is ASCII,
LF-only, ends in one LF, has no BOM, no CR, and no blank record. There are
exactly 29 DNS records and 8 VOF records. After removing each inline !
comment, token counts are:

- DNS: 3,3,1,2,1,2,2,3,2,1,3,3,4,6,6,6,6,6,6,6,6,6,3,3,3,3,6,2,1.
- VOF: 4,1,1,4,6,6,1,2.

The pinned FluTAS commit is 598210616bebd51f7d51f61455f196e6f3479916,
named identically in candidate5 and candidate6 source-pin.txt files. Each
source-pin.txt hash is e07ae0f21196fac176f88c5ec553b33e64c7595aa947839903d38f1c853beefb.
Reader and parameter declarations below are from that commit's
src/apps/two_phase_inc_isot/param.f90 and src/types.f90. Their commit-object
byte hashes are 153519b5efb1be6b454a57a7bb6a96d7803511effe5d376e4b993df8cd8e4507
and b356113a254a9d0e18c6ee4490004580ef8049a6b37469caf4fb820144aeb142.

Candidate5's source patch SHA-256 is
aabff8059c9f50834166bdbbd7b92a2891a2821177719cb21beb9acbb52973a7.
Candidate6's patch SHA-256 is
3302908d5542d7fee022293f060584f762f7afc01e2a76aea3982b0c4ce79dee.
Candidate6 is the H4 dzf lower-bound successor; its handoff says candidate5
files were left unchanged. It retains the same DNS/VOF reader and fixtures;
it adds no independent DNS/VOF typed parser or alternate input-hash binding.

Current input binding is weaker than the v0.1 fixture map. Candidate5's
write_run_manifest.py (SHA-256
79219cfb371f94b9949c19617ca454487d630870ff40d4484ee816261ffc6304) requires
the regular input-name set {dns.in, source-boundary.in, vof.in}, rejects
symlinks, and records the actual SHA-256 for each file
(lines 40,115-131,314-342). It does not compare those hashes to the five
allowlisted triplets. Its planned-interval reader strips ! and # comments and
checks only that the eleventh nonempty DNS row begins with integer 14
(lines 134-148); it does not parse all DNS records or VOF records by their
declared types. The manifest case_id is the directory name (line 340), so
that field alone is not a fixture identity. Candidate5's Dockerfile copies
the cases into its image to run source-boundary validator tests
(Dockerfile:6-20), but this is not a DNS/VOF runtime parser or five-hash
eligibility check. Candidate6's checksum list contains its source patch,
source pin, H4 tests/drivers, handoff, and evidence manifests; none of its
entries is a DNS/VOF fixture. The candidate6 handoff remains scoped to H4.
Its input binding therefore inherits candidate5 behavior without closing the
allowlist or typed-parser gap.

## Reader declarations and row mapping

The source declarations are param.f90:21-62. The read sequence is
param.f90:122-189: DNS is 29 sequential list-directed reads at lines 126-154;
VOF is eight records at lines 168-180, with record 4 selected through the
nbub=1 array branch. In the tables, I means default integer, R means
real(rp), L means default logical, and Cn means character(len=n). Repetition
notation applies to each listed field; indices and value order match the read
statement. Q means dry_four, quiescent_one, and quiescent_four. X means
dry_crossflow and crossflow_four.

rp is conditional in src/types.f90:6-11: it is kind(1.0) when
_SINGLE_PRECISION is defined and kind(0.0D0) otherwise. Recorded candidate
build flags select no _SINGLE_PRECISION, so the current build uses the latter
real kind. The source declaration remains real(rp); do not hard-code a kind
independent of the candidate build.

### DNS records

| Record | Fields in read order | Types | Tokens | Q values | X values |
| ---: | --- | --- | ---: | --- | --- |
| 1 | itot, jtot, ktot | I × 3 | 3 | 160 84 40 | 160 84 40 |
| 2 | lx, ly, lz | R × 3 | 3 | 4.0 2.1 1.0 | 4.0 2.1 1.0 |
| 3 | gr | R | 1 | 0.0 | 0.0 |
| 4 | cfl, dt_input | R × 2 | 2 | 0.2 1.0e-4 | 0.2 1.0e-4 |
| 5 | constant_dt | L | 1 | T | T |
| 6 | time_scheme, space_scheme_mom | C3 × 2 | 2 | ab2 cen | ab2 cen |
| 7 | rho_sp, mu_sp | R × 2 | 2 | 1000.0 1.0e-3 | 1000.0 1.0e-3 |
| 8 | inivel, is_noise_vel, noise_vel | C100, L, R | 3 | zer F 0.0 | zer F 0.0 |
| 9 | is_wallturb, wallturb_type | L, C3 | 2 | F hkv | F hkv |
| 10 | bulk_ftype | C3 | 1 | cfr | cfr |
| 11 | nstep, time_max, tw_max | I, R, R | 3 | 14 0.0014 1.0 | 14 0.0014 1.0 |
| 12 | stop_type(1), stop_type(2), stop_type(3) | L × 3 | 3 | T F F | T F F |
| 13 | restart, num_max_chkpt, input_chkpt, latest | L, I, I, L | 4 | F 1 1 T | F 1 1 T |
| 14 | icheck, iout0d, iout1d, iout2d, iout3d, isave | I × 6 | 6 | 1 1 1000000 1000000 1000000 1000000 | same as Q |
| 15 | cbcvel(0,1,1),cbcvel(1,1,1),cbcvel(0,2,1),cbcvel(1,2,1),cbcvel(0,3,1),cbcvel(1,3,1) | C1 × 6 | 6 | P P P P D D | same as Q |
| 16 | cbcvel(0,1,2),cbcvel(1,1,2),cbcvel(0,2,2),cbcvel(1,2,2),cbcvel(0,3,2),cbcvel(1,3,2) | C1 × 6 | 6 | P P P P D D | same as Q |
| 17 | cbcvel(0,1,3),cbcvel(1,1,3),cbcvel(0,2,3),cbcvel(1,2,3),cbcvel(0,3,3),cbcvel(1,3,3) | C1 × 6 | 6 | P P P P D D | same as Q |
| 18 | cbcpre(0,1),cbcpre(1,1),cbcpre(0,2),cbcpre(1,2),cbcpre(0,3),cbcpre(1,3) | C1 × 6 | 6 | P P P P N N | same as Q |
| 19 | bcvel(0,1,1),bcvel(1,1,1),bcvel(0,2,1),bcvel(1,2,1),bcvel(0,3,1),bcvel(1,3,1) | R × 6 | 6 | 0 0 0 0 0 0 | 0 0 0 0 -50 -50 |
| 20 | bcvel(0,1,2),bcvel(1,1,2),bcvel(0,2,2),bcvel(1,2,2),bcvel(0,3,2),bcvel(1,3,2) | R × 6 | 6 | 0 0 0 0 0 0 | same as Q |
| 21 | bcvel(0,1,3),bcvel(1,1,3),bcvel(0,2,3),bcvel(1,2,3),bcvel(0,3,3),bcvel(1,3,3) | R × 6 | 6 | 0 0 0 0 0 0 | same as Q |
| 22 | bcpre(0,1),bcpre(1,1),bcpre(0,2),bcpre(1,2),bcpre(0,3),bcpre(1,3) | R × 6 | 6 | 0 0 0 0 0 0 | same as Q |
| 23 | is_forced(1), is_forced(2), is_forced(3) | L × 3 | 3 | F F F | same as Q |
| 24 | gacc_x, gacc_y, gacc_z | R × 3 | 3 | 0 0 0 | 0 0 -9.81 |
| 25 | bvel_x, bvel_y, bvel_z | R × 3 | 3 | 0 0 0 | same as Q |
| 26 | dpdl_x, dpdl_y, dpdl_z | R × 3 | 3 | 0 0 0 | same as Q |
| 27 | is_outflow(0,1),is_outflow(1,1),is_outflow(0,2),is_outflow(1,2),is_outflow(0,3),is_outflow(1,3) | L × 6 | 6 | F F F F F F | same as Q |
| 28 | dims_in(1), dims_in(2) | I × 2 | 2 | 1 1 | same as Q |
| 29 | nthreadsmax | I | 1 | 1 | 1 |

### VOF records

| Record | Fields in read order | Types | Tokens | Exact value in all five cases |
| ---: | --- | --- | ---: | --- |
| 1 | rho1, rho2, mu1, mu2 | R × 4 | 4 | 1000.0 1.0 1.0e-3 1.8e-5 |
| 2 | inivof | C3 | 1 | zer |
| 3 | nbub | I | 1 | 1 |
| 4 | xc(1), yc(1), zc(1), r(1) | R × 4 | 4 | 0.0 0.0 0.5 0.0 |
| 5 | cbcvof(0,1),cbcvof(1,1),cbcvof(0,2),cbcvof(1,2),cbcvof(0,3),cbcvof(1,3) | C1 × 6 | 6 | P P P P N N |
| 6 | bcvof(0,1),bcvof(1,1),bcvof(0,2),bcvof(1,2),bcvof(0,3),bcvof(1,3) | R × 6 | 6 | 0 0 0 0 0 0 |
| 7 | sigma | R | 1 | 0.0 |
| 8 | late_init, i_late_init | L, I | 2 | F 0 |

Record 4 is consumed even though the fixture comment calls it a dummy bubble:
the reader allocates arrays using nbub, then with nbub=1 reads xc,yc,zc,r
at param.f90:170-176. In the pinned VOF initializer, case zer assigns zero
VOF to every cell (src/vof.f90:1974-2069); the bubble tuple remains part of
the input record contract even though that case does not use it.

## Lexical, comment, line-ending, and numeric policy

The v0.2 draft says the two files use separate fixture grammars: decode ASCII,
remove only an inline ! comment, preserve record order, require exact
physical-record count and token count, parse by declared type, and reject
blank records, CRLF, BOM, continuations, comma/slash/null/repetition syntax,
and added records. These are draft constraints, not parser acceptance.
Each table record index is also its physical line number in the corresponding
allowlisted DNS or VOF fixture.

The fixture vocabulary actually present is fully enumerable:

- Logical tokens are uppercase T and F.
- DNS identifiers are lowercase ab2, cen, zer, hkv, and cfr. VOF's
  initialization identifier is lowercase zer.
- Character boundary tokens are uppercase one-character P, D, and N.
- Integer tokens in these bytes are exactly 0, 1, 14, 40, 84, 160, and
  1000000. Real-valued fields also use integer-looking 0 tokens. The other
  real lexemes in the tables are 0.0, 0.2, 0.0014, 0.5, 1.0, 2.1, 4.0,
  1000.0, -50, -9.81, 1.0e-4, 1.0e-3, and 1.8e-5. No explicit plus,
  uppercase exponent, D exponent, nonfinite spelling, or comma/slash token
  syntax occurs.

This is an observed exact-fixture vocabulary, not proof of a general Fortran
lexical grammar. v0.2 does not fully freeze DNS/VOF whitespace rules, numeric
regular expressions/conversion and underflow behavior, case normalization,
or generalized logical/identifier alternatives. Because v0.1 restricts
eligibility to the five exact fixture hashes, the safe contract can admit
only these bytes and these token values until a reviewed amendment broadens
it. Do not infer that list-directed Fortran's wider token syntax is accepted
by an independent parser.

All 29 DNS and 8 VOF records in the five fixture pairs contain finite values.
The pinned upstream reader declares types but does not itself apply an
ieee_is_finite check to DNS/VOF values or enforce these physical-line token
counts. General ranges should therefore be fixed by the typed schema or exact
fixture hashes; they cannot be recovered from declarations alone. For the
accepted byte set, observed integer values are the exact table values above.
This audit does not claim that values outside the allowlisted bytes are
physically or numerically valid.

Units explicitly supported by fixture comments are: lx,ly,lz in m; dt_input
and time_max in s; tw_max in h; rho_sp in kg/m3; mu_sp in Pa s; and
gacc_x/y/z in m/s2. The source patch independently labels its frozen grid
spacing and source normal speed as 0.025 m and -4.8 m/s. Parameter
declarations do not attach units to the remaining values; a schema may map
bcvel and VOF material fields to units only by citing their source usage or
the existing v1.2 unit-bearing observables, whose names include rho1_kg_m3,
mu1_pa_s, and sigma_n_m (observability schema v1.2, lines 280-295, SHA-256
4ecd3c194dcf185184617e5e1cc3980ce624e5e22c6e60ae7d3eec287488f492). The VOF
initializer constructs cell-center positions from dl and subtracts r from a
Euclidean distance (src/vof.f90:1982-2008), supporting m for xc,yc,zc,r.
cfl is dimensionless by convention; gr has no unit annotation in the reader
or fixture comment. Flags and identifiers are control inputs. Do not infer a
unit for every real solely from its declared type.

## Defaults, duplicates, and cross-file checks

The only explicit default initializer among DNS/VOF file fields is nbub=0
in the declaration (param.f90:62); the file's record 3 overwrites it with
1. The xc,yc,zc,r arrays are allocatable, then sized from that read value.
The source-boundary module's corresponding fields have implementation
initializers (src/vof.f90 in the candidate overlay, lines 49-74), but the
explicit source-boundary file values are still read and checked.

The following relations are supported by the v0.1 contract, exact fixture
bytes, and candidate5 validator. “Exact fixture relation” records the
semantic equality for the allowlisted bytes. It does not imply that the
current Fortran producer compares reals bit-for-bit.

| Relation | Exact fixture values / interpretation | Current implementation evidence and qualification |
| --- | --- | --- |
| DNS grid to source grid | itot,jtot,ktot = source grid = 160,84,40 in every case. | Candidate5 validator checks ng == restas_grid (source-boundary.patch:320-321) and freezes the grid at 160×84×40 (:321-322). |
| DNS physical grid to derived spacing | lx,ly,lz = 4.0,2.1,1.0 m; with grid counts, each spacing is 0.025 m. | Candidate5 validator checks spacing and extents (source-boundary.patch:323-328). These lengths are not repeated in source-boundary.in. |
| Fixed time step | constant_dt=T, dt_input=source dt_s=1.0e-4 s; fixed_step_factor=0.2 is an additional source-boundary input, not a duplicated DNS field. | Candidate5 validator uses absolute tolerance restas_input_tol=1e-12_rp for the DNS/source dt comparison and also freezes 1e-4 s (source-boundary.patch:329-332). |
| Planned schedule | DNS has nstep=14, time_max=0.0014 s, and stop_type=T F F. Source schedule is [2,12) for one/four-slot cases and disabled [0,0) for dry cases. This gives 15 states and 14 intervals, with source interval ending before DNS stop. | Candidate5 reader validates dry/positive interval shapes (source-boundary.patch:239-246) and case values (:334-338). DNS records are list-directed reads upstream. |
| Start/restart and VOF late initialization | restart=F and late_init=F; no-restart fixture start time is derived as 0 s. latest=T, checkpoint integers 1,1, and i_late_init=0 remain literal fields but do not change those flags. | Candidate5 validator rejects restart or late_init (source-boundary.patch:346-347). No start-time record exists in DNS or VOF. |
| Gravity | DNS gacc_x/y/z equals source gravity_x/y/z: quiet cases (0,0,0); crossflow cases (0,0,-9.81) m/s2. | Candidate5 compares with absolute tolerance 1e-12_rp (source-boundary.patch:348-349) and limits permitted vectors (:357-364). |
| Background and source velocity | Quiet: source (0,0,-4.8) and background (0,0,0). Crossflow: source (-50,0,-4.8) and background (-50,0,0). Source U/V equal background U/V; source W is -4.8 m/s and background W is zero. | Candidate5 checks background cases and source tangential equality with tolerance (source-boundary.patch:350-356). Initial-flow assignment and velocity boundaries are in the same patch. |
| DNS velocity boundary values | All cbcvel rows are P P P P D D; U z-face values are 0 in quiet cases and 0 0 0 0 -50 -50 in crossflow; V and W values are all zero. U/V z-face values correspond to source background U/V; W normal base values are zero before source override. | Candidate5 checks BC types, z-face tangential values, and zero W z values (source-boundary.patch:432-439). It does not explicitly compare every x/y numeric boundary token; exact fixture hashes cover them. |
| Pressure and VOF BCs | DNS pressure codes and VOF codes are P P P P N N, each with six zero values. is_outflow and is_forced are false; bvel and dpdl are zero; bulk_ftype=cfr. | Candidate5 checks these source-case constraints (source-boundary.patch:364-367,425-434). The typed schema should retain complete values as well as the checked subset. |
| Empty initial VOF | inivof=zer, nbub=1, tuple (0,0,0.5,0) (commented as dummy), and late_init=F. | The upstream reader consumes the tuple. Candidate5 rejects late init. The tuple is not optional when inivof=zer. |
| Fluid inputs | VOF values are rho1=1000, rho2=1 kg/m3, mu1=1e-3, mu2=1.8e-5 Pa s. DNS rho_sp=1000, mu_sp=1e-3 are not equal to VOF gas values rho2/mu2 and must not be treated as duplicates. | Upstream param.f90:264-268 replaces rho_sp/mu_sp with rho2/mu2 when VOF is enabled. The v0.1 phrase “fluid ... values must agree” needs field-specific wording; equality between those original DNS placeholders and both VOF phase values would be false. |

The exact candidate5 source comparisons above use restas_input_tol, which is
1e-12_rp, rather than exact floating-point equality. A new analyzer can
validate the current allowlist by exact token values and hashes. If the
successor parser is intended to admit amended inputs, the primary must freeze
whether each real comparison is lexical, exact converted-value equality, or
tolerance-based; neither v0.1 nor v0.2 settles that policy for DNS/VOF.

## H3 gaps and disposition

The v0.1 contract lists hashes and says DNS/VOF are independently parsed, but
does not publish these 29/8 record definitions. v0.2 specifies physical
record handling and field-type parsing, but still lacks an explicit
hash-pinned DNS/VOF record schema and full per-field conversion/range policy.
This extraction supplies the reader-side record names, values, types, and
source anchors for the primary's successor annex. It does not settle
unjustified physical ranges or convert assumptions into producer validation.

Current FluTAS read_input uses ordinary list-directed read statements for
both files; it does not enforce exact token counts on physical lines or check
EOF after the final record (param.f90:124-180). Candidate5's separate
source-boundary.in reader is also list-directed (source-boundary.patch:205-238).
The stricter independent interpretation in the contract is additional
interface work, not behavior established by successful candidate builds.
Candidate6 changes the H4 source helper and does not close this parser gap.
No parser acceptance, source run, or scientific gate is implied by this audit.

## Source paths and reproduction

Exact source anchors:

- Pinned FluTAS commit 598210616bebd51f7d51f61455f196e6f3479916,
  src/apps/two_phase_inc_isot/param.f90:21-62,122-189,264-268.
- Same commit, src/types.f90:4-12; selected precision macro absent from the
  recorded candidate5/candidate6 NVFORTRAN command flags.
- Same commit, src/vof.f90:1974-2069, where case zer sets every VOF cell to
  zero.
- Candidate5/candidate6 build evidence showing no _SINGLE_PRECISION macro:
  containers/flutas/candidate5/evidence/runs/20260925T132844Z-2122673/docker-build.log:101-106
  and containers/flutas/candidate6/evidence/native-build-20260925T141014Z/build.log:19-24.
- Candidate5 fixture map and hash allowlist:
  experiments/FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT.md:23-85.
- Draft DNS/VOF grammar constraints:
  experiments/FLUTAS_CANDIDATE5_SOURCE_RELEASE_CONTRACT_v0.2.md:124-143.
- Candidate5 added source read and cross-file validation:
  containers/flutas/candidate5/source-boundary.patch:205-238,303-446.
- Candidate5 pinned fixture inventory:
  containers/flutas/candidate5/cases/source_boundary/SHA256SUMS.
- Current candidate5 manifest input binding:
  containers/flutas/candidate5/tools/write_run_manifest.py:40,115-148,314-342;
  SHA-256 79219cfb371f94b9949c19617ca454487d630870ff40d4484ee816261ffc6304.
- Candidate5 build fixture-copy/test wiring:
  containers/flutas/candidate5/Dockerfile:6-20.
- Candidate6 scope:
  containers/flutas/candidate6/HANDOFF.md:3-8,49-54 and
  containers/flutas/candidate6/SHA256SUMS (SHA-256
  907f76c837f0679713f86d3286771693aa2618e4b9d71c30d8c2b53a1b376f25).

Read-only reproduction commands, run from the repository root:

    cd containers/flutas/candidate5/cases/source_boundary
    sha256sum -c SHA256SUMS
    cd ../../../../..
    git -C /tmp/candidate5-upstream rev-parse HEAD
    git -C /tmp/candidate5-upstream show 598210616bebd51f7d51f61455f196e6f3479916:src/apps/two_phase_inc_isot/param.f90 | nl -ba | sed -n '19,63p;122,189p;250,268p'
    git -C /tmp/candidate5-upstream show 598210616bebd51f7d51f61455f196e6f3479916:src/types.f90 | nl -ba | sed -n '4,12p'
    nl -ba containers/flutas/candidate5/tools/write_run_manifest.py | sed -n '40p;115,148p;314,342p'
    cat containers/flutas/candidate6/SHA256SUMS
    python3 - <<'PY'
    from pathlib import Path
    from hashlib import sha256
    root = Path("containers/flutas/candidate5/cases/source_boundary")
    for case in ("dry_four", "quiescent_one", "quiescent_four", "dry_crossflow", "crossflow_four"):
        for name in ("dns.in", "vof.in"):
            data = (root / case / name).read_bytes()
            lines = data.splitlines(keepends=True)
            counts = [len(line.split(b"!", 1)[0].split()) for line in lines]
            print(case, name, sha256(data).hexdigest(), len(lines), counts,
                  all(byte < 128 for byte in data), b"\r" in data,
                  data.startswith(bytes.fromhex("efbbbf")), data.endswith(b"\n"))
    PY

The checksum command passed for all 15 files. The pinned checkout resolved to
the recorded commit. No build, parser test, source case, solver, or GPU action
was run for this read-only audit.
