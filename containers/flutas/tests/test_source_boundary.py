#!/usr/bin/env python3
"""Static and analytic checks for the synthetic FluTAS boundary patch.

This suite never invokes the FluTAS executable, OpenACC kernels, MPI run, or GPU.
"""
from __future__ import annotations

import math
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases" / "source_boundary"
SOURCE_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/FluTAS")
if len(sys.argv) > 1:
    sys.argv = sys.argv[:1]


def tokens(path: Path) -> list[list[str]]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.split("!", 1)[0].strip()
        if line:
            rows.append(line.split())
    return rows


def case_values(name: str):
    case = CASES / name
    dns = tokens(case / "dns.in")
    vof = tokens(case / "vof.in")
    source = tokens(case / "source-boundary.in")
    nslot = int(source[0][0])
    grid = tuple(map(int, source[1]))
    on, off = map(int, source[2])
    dt = float(source[3][0])
    inlet = tuple(map(float, source[4]))
    background = tuple(map(float, source[5]))
    gravity = tuple(map(float, source[6]))
    geometry = tuple(map(float, source[7]))
    masks = [tuple(map(int, row)) for row in source[8:]]
    return case, dns, vof, nslot, grid, on, off, dt, inlet, background, gravity, geometry, masks


class FrozenInputTests(unittest.TestCase):
    def test_fixture_files_match_frozen_hashes(self):
        hashes_file = CASES / "SHA256SUMS"
        self.assertTrue(hashes_file.is_file())
        for line in hashes_file.read_text().splitlines():
            if not line.strip():
                continue
            expected, relative = line.split(maxsplit=1)
            path = CASES / relative.strip()
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, path.name)

    def test_dry_fixture_has_no_source_or_return_across_the_full_window(self):
        (_, dns, _, nslot, _, on, off, _, inlet, _, _, _, masks) = case_values("dry_four")
        self.assertEqual((nslot, on, off, masks), (0, 0, 0, []))
        self.assertEqual(tuple(map(float, dns[10][:2])), (14.0, 0.0014))
        active_intervals = [step for step in range(14) if on <= step < off]
        self.assertEqual(active_intervals, [])
        self.assertEqual(nslot * 0.15 * abs(inlet[2]), 0.0)

    def test_all_declared_cases_are_grid_aligned_and_under_one_million_cells(self):
        expected_names = {"quiescent_one", "quiescent_four", "crossflow_four", "dry_four"}
        self.assertEqual({p.name for p in CASES.iterdir() if p.is_dir()}, expected_names)
        frozen_masks = [
            (74, 79, 2, 41),
            (82, 87, 2, 41),
            (74, 79, 44, 83),
            (82, 87, 44, 83),
        ]
        expected_slot_counts = {"quiescent_one": 1, "quiescent_four": 4, "crossflow_four": 4, "dry_four": 0}
        for name in sorted(expected_names):
            with self.subTest(case=name):
                (case, dns, vof, nslot, grid, on, off, dt, inlet, background,
                 gravity, geometry, masks) = case_values(name)
                self.assertEqual(grid, (160, 84, 40))
                self.assertEqual(math.prod(grid), 537_600)
                self.assertLess(math.prod(grid), 1_000_000)
                self.assertEqual(tuple(map(float, dns[1])), (4.0, 2.1, 1.0))
                self.assertEqual(tuple(map(float, dns[3])), (0.2, 1.0e-4))
                self.assertEqual(dt, 1.0e-4)
                self.assertEqual((on, off), (0, 0) if name == "dry_four" else (2, 12))
                self.assertEqual(tuple(map(float, dns[10][:2])), (14.0, 0.0014))
                self.assertEqual(tuple(map(float, dns[2])), (0.0,))
                self.assertEqual(tuple(map(float, dns[23])), gravity)
                self.assertEqual(tuple(map(float, dns[24])), (0.0, 0.0, 0.0))
                self.assertEqual(tuple(map(float, dns[25])), (0.0, 0.0, 0.0))
                self.assertEqual(dns[9], ["cfr"])
                self.assertEqual(dns[22], ["F", "F", "F"])
                self.assertEqual(dns[26], ["F"] * 6)
                self.assertEqual(dns[27], ["1", "1"])
                self.assertEqual(dns[28], ["1"])
                self.assertEqual(dns[4], ["T"])
                self.assertEqual(dns[11], ["T", "F", "F"])
                self.assertEqual(dns[12][0], "F")
                self.assertEqual(dns[14:17], [["P", "P", "P", "P", "D", "D"]] * 3)
                self.assertEqual(dns[17], ["P", "P", "P", "P", "N", "N"])
                self.assertEqual(dns[18], ["0", "0", "0", "0", f"{background[0]:.12g}", f"{background[0]:.12g}"])
                self.assertEqual(dns[19], ["0", "0", "0", "0", f"{background[1]:.12g}", f"{background[1]:.12g}"])
                self.assertEqual(dns[20], ["0"] * 6)
                self.assertEqual(dns[21], ["0"] * 6)
                self.assertEqual(vof[1], ["zer"])
                self.assertEqual(vof[4], ["P", "P", "P", "P", "N", "N"])
                self.assertEqual(tuple(map(float, vof[5])), (0.0,) * 6)
                self.assertEqual(vof[7][0], "F")
                self.assertEqual(nslot, expected_slot_counts[name])
                self.assertEqual(len(masks), nslot)
                self.assertEqual(masks, frozen_masks[:nslot])
                self.assertEqual(geometry, (0.15, 1.0, 0.05, 0.05))
                # Convert solver cell-edge coordinates to the centered declaration;
                # each mask is 0.15 m in short-axis x and 1.0 m in long-axis y.
                for i0, i1, j0, j1 in masks:
                    x_edges = ((i0 - 1) * 0.025 - 2.0, i1 * 0.025 - 2.0)
                    y_edges = ((j0 - 1) * 0.025 - 1.05, j1 * 0.025 - 1.05)
                    self.assertAlmostEqual(x_edges[1] - x_edges[0], 0.15)
                    self.assertAlmostEqual(y_edges[1] - y_edges[0], 1.0)
                if len(masks) == 4:
                    self.assertAlmostEqual((masks[1][0] - 1 - masks[0][1]) * 0.025, 0.05)
                    self.assertAlmostEqual((masks[2][2] - 1 - masks[0][3]) * 0.025, 0.05)
                self.assertEqual(inlet, (background[0], background[1], -4.8))
                self.assertEqual(background[2], 0.0)
                if name == "crossflow_four":
                    self.assertEqual(background, (-50.0, 0.0, 0.0))
                    self.assertEqual(gravity, (0.0, 0.0, -9.81))
                else:
                    self.assertEqual(background, (0.0, 0.0, 0.0))
                    self.assertEqual(gravity, (0.0, 0.0, 0.0))

    def test_mask_geometry_and_expected_source_totals(self):
        dx = dy = dz = 0.025
        area = 0.15 * 1.0
        self.assertAlmostEqual((6 * 40) * dx * dy, area)
        for name, nslot in (("quiescent_one", 1), ("quiescent_four", 4), ("crossflow_four", 4), ("dry_four", 0)):
            with self.subTest(case=name):
                *_, dt, inlet, background, gravity, geometry, masks = case_values(name)
                per_slot_rate = area * abs(inlet[2])
                per_slot_mass = 1000.0 * per_slot_rate * (12 - 2) * dt
                total_rate = nslot * per_slot_rate
                return_w = -total_rate / (4.0 * 2.1)
                if nslot:
                    self.assertAlmostEqual(per_slot_mass, 0.72, places=12)
                self.assertAlmostEqual(total_rate, 0.72 * nslot, places=12)
                self.assertAlmostEqual(return_w, -0.08571428571428572 * nslot, places=12)
                self.assertAlmostEqual(per_slot_rate * (12 - 2) * dt, 0.00072, places=12)
                # n=2..11 are active; intervals 12 and 13 verify post-pulse shutoff.
                active = [n for n in range(14) if 2 <= n < 12] if nslot else []
                self.assertEqual(len(active), 10 if nslot else 0)
                self.assertAlmostEqual(2 * dt, 0.0002)
                self.assertAlmostEqual(12 * dt, 0.0012)
                self.assertAlmostEqual(14 * dt, 0.0014)
                self.assertEqual(inlet[:2], background[:2])
                self.assertEqual(gravity[2], -9.81 if background[0] == -50.0 else 0.0)
        self.assertAlmostEqual(0.72 * 4, 2.88)
        self.assertAlmostEqual(0.00072 * 4, 0.00288)
        self.assertAlmostEqual(-2.88 + 2.88, 0.0)


class SourceCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vof = (SOURCE_ROOT / "src" / "vof.f90").read_text().lower()
        cls.main = (SOURCE_ROOT / "src" / "apps" / "two_phase_inc_isot" / "main__two_phase_inc_isot.f90").read_text().lower()
        cls.helper = (SOURCE_ROOT / "src" / "restas_source.inc").read_text().lower()
        cls.chkdt = (SOURCE_ROOT / "src" / "chkdt.f90").read_text().lower()

    def test_interval_and_vof_boundary_state_order(self):
        self.assertIn("restas_source_active_at=(step_index.ge.restas_step_on.and.step_index.lt.restas_step_off)", self.helper)
        self.assertIn("source_interval=istep-1", self.main)
        adv = self.vof.split("subroutine advvof(", 1)[1].split("end subroutine advvof", 1)[0]
        x = adv.index("call cmpt_vof_flux", adv.index("! flux in x"))
        self.assertLess(adv.rfind("restas_source_prepare_boundary", 0, x), x)
        self.assertLess(x, adv.index("restas_source_accumulate_boundary_flux(n,dl,dzf,1,flux)", x))
        b1 = adv.index("call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,dvof1)")
        p1 = adv.index("restas_source_prepare_boundary(n,nh_u,source_step,dvof1,wg)", b1)
        u1 = adv.index("call update_vof", p1)
        self.assertLess(b1, p1)
        self.assertLess(p1, u1)
        y = adv.index("call cmpt_vof_flux", adv.index("! flux in y"))
        self.assertLess(adv.rfind("restas_source_prepare_boundary", p1, y), y)
        self.assertLess(y, adv.index("restas_source_accumulate_boundary_flux(n,dl,dzf,2,flux)", y))
        b2 = adv.index("call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,dvof2)")
        p2 = adv.index("restas_source_prepare_boundary(n,nh_u,source_step,dvof2,wg)", b2)
        self.assertLess(b2, p2)
        z = adv.index("call cmpt_vof_flux", adv.index("! flux in z"))
        match = adv.index("call restas_source_check_volume_pair", z)
        self.assertLess(z, match)
        self.assertLess(match, adv.index("restas_source_accumulate_boundary_flux(n,dl,dzf,3,flux)", match))
        self.assertLess(adv.index("restas_source_record_flux", match), adv.index("vof(i,j,k) =", match))
        final_bound = adv.rindex("call boundp(cbcvof,n,bcvof,nh_d,+1,halo,dl,dzc,dzf,vof)")
        final_source = adv.index("restas_source_prepare_boundary(n,nh_u,source_step,vof,wg)", final_bound)
        self.assertLess(final_bound, final_source)
        self.assertLess(final_source, adv.rindex("call update_vof"))

    def test_inflow_only_alpha_and_property_ghosts(self):
        prepare = self.helper.split("subroutine restas_source_prepare_boundary", 1)[1].split("end subroutine restas_source_prepare_boundary", 1)[0]
        top = prepare.index("if(w(i,j,n(3)).lt.0._rp) then")
        top_end = prepare.index("! z- reverse inflow", top)
        top_block = prepare[top:top_end]
        self.assertIn("vof(i,j,n(3)+1)=alpha_in", top_block)
        self.assertIn("if(active.and.in_slot) alpha_in=1._rp", top_block)
        self.assertIn("rho(i,j,n(3)+1)=alpha_in*rho1+(1._rp-alpha_in)*rho2", top_block)
        self.assertIn("mu(i,j,n(3)+1)=alpha_in*mu1+(1._rp-alpha_in)*mu2", top_block)
        self.assertNotIn("else", top_block)
        bottom = prepare[prepare.index("if(w(i,j,0).gt.0._rp) then"):]
        self.assertIn("vof(i,j,0)=0._rp", bottom)
        self.assertIn("rho(i,j,0)=rho2", bottom)
        self.assertIn("mu(i,j,0)=mu2", bottom)
        # Post-advvof generic property fills are immediately followed by source-aware fills.
        rho_fill = self.main.index("call boundp(cbcvof,n,bcvof,nh_d,nh_v,halo_v,dl,dzc,dzf,rho)", self.main.index("call advvof"))
        mu_fill = self.main.index("call boundp(cbcvof,n,bcvof,nh_d,nh_v,halo_v,dl,dzc,dzf,mu )", rho_fill)
        source_fill = self.main.index("call restas_source_prepare_boundary(n,nh_u,source_interval,psi,w,rho,mu)", mu_fill)
        self.assertLess(rho_fill, mu_fill)
        self.assertLess(mu_fill, source_fill)

    def test_velocity_override_order_and_return_from_actual_geometric_flux(self):
        bound_calls = [line for line in self.main.splitlines() if "call bounduvw(" in line]
        self.assertEqual(len(bound_calls), 3)
        for line in bound_calls:
            pos = self.main.index(line)
            self.assertIn("call restas_source_apply_velocity", self.main[pos:pos + 350])
        match = self.helper.split("subroutine restas_source_check_volume_pair", 1)[1].split("end subroutine restas_source_check_volume_pair", 1)[0]
        self.assertIn("top_volume=top_volume+max(0._rp,-flux(i,j,n(3))*area)", match)
        self.assertIn("qtop=top_volume/dt", match)
        self.assertIn("qbottom=qbottom-w(i,j,0)*area", match)
        self.assertIn("if(abs(qtop-qexpected).gt.tol)", match)
        self.assertIn("if(abs(qbottom-qexpected).gt.tol)", match)
        self.assertNotIn("w(i,j,0)=", match)
        apply = self.helper.split("subroutine restas_source_apply_velocity", 1)[1].split("end subroutine restas_source_apply_velocity", 1)[0]
        self.assertIn("qbottom=qtop", apply)
        initial = self.helper.split("subroutine restas_source_set_initial_flow", 1)[1].split(
            "end subroutine restas_source_set_initial_flow", 1
        )[0]
        self.assertIn("u(i,j,k)=restas_background_velocity(1)", initial)
        self.assertIn("v(i,j,k)=restas_background_velocity(2)", initial)
        self.assertIn("w(i,j,k)=restas_background_velocity(3)", initial)
        self.assertIn("call restas_source_set_initial_flow(n,nh_u,u,v,w)", self.main)

    def test_pulse_endpoint_reaches_postprojection_velocity_state(self):
        # State U_k is checked before interval-k VOF. Projection in the next step
        # creates U_(k+1), with the next interval's boundary profile.
        case = case_values("quiescent_four")
        nstep = int(case[1][10][0])
        on, off = case[5], case[6]
        intervals = [istep - 1 for istep in range(1, nstep + 1)]
        self.assertEqual(intervals, list(range(14)))
        self.assertEqual([k for k in intervals if on <= k < off], list(range(2, 12)))
        self.assertEqual([k for k in intervals if not on <= k < off][-2:], [12, 13])
        projected_state_profile = {0: on <= 0 < off}
        for istep, interval in enumerate(intervals, start=1):
            self.assertEqual(projected_state_profile[interval], on <= interval < off)
            projected_state_profile[istep] = on <= istep < off
        self.assertFalse(projected_state_profile[12])
        self.assertFalse(projected_state_profile[13])
        dry = case_values("dry_four")
        self.assertFalse(any(dry[5] <= k < dry[6] for k in range(14)))

        # Confirm interval-k VOF does not mutate U_k, the next interval is installed
        # in both projection boundary hooks, and geometric phase flux is only audited.
        active = self.helper.split("logical function restas_source_active_at", 1)[1].split(
            "end function restas_source_active_at", 1
        )[0]
        self.assertIn("step_index.ge.restas_step_on.and.step_index.lt.restas_step_off", active)
        apply = self.helper.split("subroutine restas_source_apply_velocity", 1)[1].split(
            "end subroutine restas_source_apply_velocity", 1
        )[0]
        self.assertIn("active=restas_source_active_at(step_index)", apply)
        self.assertIn("w(i,j,n(3))=0._rp", apply)
        self.assertIn("if(active) w(i,j,n(3))=restas_source_velocity(3)", apply)
        prepare = self.helper.split("subroutine restas_source_prepare_boundary", 1)[1].split(
            "end subroutine restas_source_prepare_boundary", 1
        )[0]
        self.assertIn("if(active.and.in_slot) alpha_in=1._rp", prepare)
        assert_state = self.helper.split("subroutine restas_source_assert_velocity", 1)[1].split(
            "end subroutine restas_source_assert_velocity", 1
        )[0]
        self.assertIn("current top velocity does not match projected source interval", assert_state)
        self.assertIn("current bottom return does not match projected source interval", assert_state)
        check_flux = self.helper.split("subroutine restas_source_check_volume_pair", 1)[1].split(
            "end subroutine restas_source_check_volume_pair", 1
        )[0]
        self.assertIn("qtop=top_volume/dt", check_flux)
        self.assertIn("if(abs(qtop-qexpected).gt.tol)", check_flux)
        self.assertIn("if(abs(qbottom-qexpected).gt.tol)", check_flux)
        self.assertNotIn("w(i,j,0)=", check_flux)

        # k=12 has zero imposed top W; the geometric sweep is zero, so the return
        # and corrected source-face profile are exactly zero at the final states.
        self.assertFalse(on <= 12 < off)
        top_face_w = 0.0
        geometric_inward_volume = max(0.0, -top_face_w) * 0.025 * 0.025 * 0.0001
        qtop = geometric_inward_volume / 0.0001
        qbottom = qtop
        return_velocity = -qbottom / (160 * 84 * 0.025 * 0.025) if qbottom > 0 else 0.0
        self.assertEqual((geometric_inward_volume, qtop, qbottom, return_velocity), (0.0, 0.0, 0.0, 0.0))

        correction = self.main.index("call correc(")
        bound_after_correction = self.main.index("call bounduvw(", correction)
        override_after_correction = self.main.index("call restas_source_apply_velocity", bound_after_correction)
        self.assertLess(correction, bound_after_correction)
        self.assertLess(bound_after_correction, override_after_correction)
        self.assertIn("istep,dl,u,v,w,source_qtop,source_qbottom", self.main[override_after_correction:override_after_correction + 160])
        self.assertIn("source_interval=istep-1", self.main)
        self.assertIn("call advvof(n,dli,dt,halo_v,nh_d,nh_u,dzc,dzf,u,v,w,psi,nor,cur_t,kappa,d_thinc,source_interval)", self.main)
        advvof = self.main.index("call advvof(n,dli,dt,halo_v,nh_d,nh_u,dzc,dzf,u,v,w,psi,nor,cur_t,kappa,d_thinc,source_interval)")
        state_assert = self.main.index("call restas_source_assert_velocity(n,source_interval,dl,w)", advvof - 200)
        self.assertLess(state_assert, advvof)
        self.assertNotIn("call restas_source_apply_velocity", self.main[state_assert:advvof])
        preproject = self.main.index("call bounduvw(cbcvel,n,bcvel,nh_d,nh_u,halo_u,no_outflow")
        next_state_apply = self.main.index("call restas_source_apply_velocity", preproject)
        self.assertIn("istep,dl,u,v,w,source_qtop,source_qbottom", self.main[next_state_apply:next_state_apply + 160])
        self.assertLess(preproject, next_state_apply)

    def test_physical_flux_units_mass_momentum_ledgers_and_divergence(self):
        adv = self.vof.split("subroutine advvof(", 1)[1].split("end subroutine advvof", 1)[0]
        self.assertIn("dl(:) = dli(:)**(-1)", adv)
        self.assertIn("restas_source_accumulate_boundary_flux(n,dl,dzf,1,flux)", adv)
        self.assertIn("restas_source_accumulate_boundary_flux(n,dl,dzf,2,flux)", adv)
        self.assertIn("restas_source_accumulate_boundary_flux(n,dl,dzf,3,flux)", adv)
        flux = self.helper.split("subroutine restas_source_accumulate_boundary_flux", 1)[1].split("end subroutine restas_source_accumulate_boundary_flux", 1)[0]
        for expected in ("-flux(0,j,k)*area", "flux(n(1),j,k)*area", "-flux(i,0,k)*area", "flux(i,n(2),k)*area", "-flux(i,j,0)*area", "flux(i,j,n(3))*area"):
            self.assertIn(expected, flux)
        record = self.helper.split("subroutine restas_source_record_flux", 1)[1].split("end subroutine restas_source_record_flux", 1)[0]
        self.assertIn("area=dl(1)*dl(2)", record)
        self.assertIn("dm=rho1*max(0._rp,-flux(i,j,n(3))*area)", record)
        self.assertIn("requested_momentum=requested_mass*restas_source_velocity", record)
        self.assertIn("uf=0.5_rp*(u(i,j,n(3))+u(i,j,n(3)+1))", record)
        self.assertIn("vf=0.5_rp*(v(i,j,n(3))+v(i,j,n(3)+1))", record)
        self.assertIn("wf=w(i,j,n(3))", record)
        self.assertIn("do islot=1,restas_slot_count", record)
        self.assertIn("do j=restas_slot_j0(islot),restas_slot_j1(islot)", record)
        self.assertIn("do i=restas_slot_i0(islot),restas_slot_i1(islot)", record)
        audit = self.helper.split("subroutine restas_source_record_velocity_audit", 1)[1].split("end subroutine restas_source_record_velocity_audit", 1)[0]
        self.assertIn("div=(u(i,j,k)-u(i-1,j,k))/dl(1)+", audit)
        self.assertIn("(v(i,j,k)-v(i,j-1,k))/dl(2)+", audit)
        self.assertIn("(w(i,j,k)-w(i,j,k-1))/dzf(k)", audit)
        self.assertIn("closure=div_integral-net_boundary", audit)
        self.assertIn("div_max=max(div_max,abs(div))", audit)
        self.assertIn("div_l1=div_l1+abs(div)*cell_volume", audit)
        # Exact finite-volume telescoping check for an arbitrary staggered field.
        nx, ny, nz = 4, 3, 2
        dx, dy, dz = 0.25, 0.4, 0.5
        u = [[[float(i * i + j + k) for k in range(nz)] for j in range(ny)] for i in range(nx + 1)]
        v = [[[float(i - 2 * j + k) for k in range(nz)] for j in range(ny + 1)] for i in range(nx)]
        w = [[[float(i + j + k * k) for k in range(nz + 1)] for j in range(ny)] for i in range(nx)]
        integrated = 0.0
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    divergence = (u[i + 1][j][k] - u[i][j][k]) / dx
                    divergence += (v[i][j + 1][k] - v[i][j][k]) / dy
                    divergence += (w[i][j][k + 1] - w[i][j][k]) / dz
                    integrated += divergence * dx * dy * dz
        boundary = 0.0
        boundary += sum((-u[0][j][k] + u[nx][j][k]) * dy * dz for j in range(ny) for k in range(nz))
        boundary += sum((-v[i][0][k] + v[i][ny][k]) * dx * dz for i in range(nx) for k in range(nz))
        boundary += sum((-w[i][j][0] + w[i][j][nz]) * dx * dy for i in range(nx) for j in range(ny))
        self.assertAlmostEqual(integrated, boundary, places=12)
        inventory = self.helper.split("subroutine restas_source_record_inventory", 1)[1].split(
            "end subroutine restas_source_record_inventory", 1
        )[0]
        self.assertIn(
            "residual=restas_cumulative_in_mass-restas_cumulative_out_mass-", inventory
        )
        self.assertIn("net_volume=sum(restas_step_in_volume)-sum(restas_step_out_volume)", inventory)

    def test_upstream_co_formula_and_fixed_fixture_values_are_static_only(self):
        self.assertIn("ux = abs(u(i,j,k))", self.chkdt)
        self.assertIn("vx = 0.25_rp*abs( v(i,j,k)+v(i,j-1,k)+v(i+1,j,k)+v(i+1,j-1,k) )", self.chkdt)
        self.assertIn("dtix = ux*dxi+vx*dyi+wx*dzfi(k)", self.chkdt)
        self.assertIn("dtiy = uy*dxi+vy*dyi+wy*dzfi(k)", self.chkdt)
        self.assertIn("dtiz = uz*dxi+vz*dyi+wz*dzci(k)", self.chkdt)
        self.assertIn("dtmax  = cfl_c*2._rp*(dtic+dtiv+sqrt((dtic+dtiv)**2+4._rp*(dtig**2+dtik**2)))**(-1)", self.chkdt)
        self.assertIn("dtmax  = min(dtmax,1._rp/dtik)", self.chkdt)
        self.assertAlmostEqual(4.8 * 1.0e-4 / 0.025, 0.0192)
        self.assertAlmostEqual(50.0 * 1.0e-4 / 0.025, 0.2)
        self.assertAlmostEqual((50.0 + 4.8) * 1.0e-4 / 0.025, 0.2192)
        self.assertIn("constant_dt", self.main)
        self.assertIn("if(.not.constant_dt)", self.main)


if __name__ == "__main__":
    unittest.main(verbosity=2)
