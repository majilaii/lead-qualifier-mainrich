"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

/* ─── Data ─────────────────────────────────────────────── */

type Tier = "hot" | "review" | "rejected";
type DataRow = { text: string; tier: Tier };

const DATA_POOL: DataRow[] = [
  { text: "> BOSTON DYNAMICS · ROBOTICS · MARC RAIBERT · CEO · 9/10", tier: "hot" },
  { text: "> FIGURE AI · HUMANOID ROBOTS · BRETT ADCOCK · CEO · 10/10", tier: "hot" },
  { text: "> AGILITY ROBOTICS · HUMANOIDS · DAMION SHELTON · CEO · 10/10", tier: "hot" },
  { text: "> UNITREE ROBOTICS · QUADRUPEDS · WANG XINGXING · CEO · 9/10", tier: "hot" },
  { text: "> MAXON GROUP · PRECISION MOTORS · EUGEN ELMIGER · CEO · 8/10", tier: "hot" },
  { text: "> TESLA INC · EV AND ENERGY · DREW BAGLINO · SVP ENG · 8/10", tier: "hot" },
  { text: "> ABB ROBOTICS · INDUSTRIAL AUTO · SAMI ATIYA · PRES · 8/10", tier: "hot" },
  { text: "> HARMONIC DRIVE · ACTUATORS · S YAMAZAKI · CTO · 9/10", tier: "hot" },
  { text: "> MOOG INC · MOTION CONTROL · PAT ROCHE · CEO · 9/10", tier: "hot" },
  { text: "> KOLLMORGEN · SERVO SYSTEMS · DAN ST-PIERRE · DIR · 8/10", tier: "hot" },
  { text: "> SAMSUNG SDI · BATTERY TECH · YOONHO CHOI · VP ENG · 8/10", tier: "hot" },
  { text: "> 1X TECHNOLOGIES · HUMANOIDS · BERNT BORNICH · CEO · 10/10", tier: "hot" },
  { text: "- NIDEC CORP · MOTOR MFG · JUN SEKI · COO · 7/10", tier: "review" },
  { text: "- SIEMENS AG · INDUSTRIAL · CEDRIK NEIKE · BOARD · 6/10", tier: "review" },
  { text: "- BOSCH GROUP · AUTOMOTIVE · STEFAN HARTUNG · CEO · 6/10", tier: "review" },
  { text: "- FANUC CORP · CNC ROBOTICS · KENJI YAMAGUCHI · CEO · 7/10", tier: "review" },
  { text: "- DENSO CORP · AUTO PARTS · KOJI ARIMA · CEO · 6/10", tier: "review" },
  { text: "- FESTO SE · PNEUMATICS · DR FRANK MELZER · CTO · 5/10", tier: "review" },
  { text: "- YASKAWA ELEC · SERVO MOTORS · H OGASAWARA · CEO · 7/10", tier: "review" },
  { text: "- RETHINK ROBOTICS · COBOTS · CONTACT TBD · TBD · 5/10", tier: "review" },
  { text: "- KUKA AG · INDUSTRIAL ROBOTS · PETER MOHNEN · CEO · 6/10", tier: "review" },
  { text: "- DELTA ELECTRONICS · POWER SYS · PING CHENG · CEO · 5/10", tier: "review" },
  { text: "- SCHAEFFLER AG · BEARINGS · KLAUS ROSENFELD · CEO · 6/10", tier: "review" },
  { text: "- NSK LTD · BEARINGS · TOSHIHIRO UCHIYAMA · CEO · 5/10", tier: "review" },
  { text: "- SMC CORP · PNEUMATICS · YOSHIKI TAKADA · PRES · 5/10", tier: "review" },
  { text: "- OMRON CORP · AUTOMATION · JUNTA TSUJINAGA · CEO · 6/10", tier: "review" },
  { text: "- ROCKWELL AUTO · PLC SYSTEMS · BLAKE MORET · CEO · 4/10", tier: "review" },
  { text: "- COGNEX CORP · VISION SYS · ROBERT WILLETT · CEO · 4/10", tier: "review" },
  { text: "- KEYENCE CORP · SENSORS · T TAKIZAKI · CHAIR · 5/10", tier: "review" },
  { text: "- THK CO LTD · LINEAR MOTION · A TERAMACHI · CEO · 7/10", tier: "review" },
  { text: "x HUBSPOT INC · SAAS · YAMINI RANGAN · CEO · 2/10", tier: "rejected" },
  { text: "x SLACK TECH · MESSAGING · DENISE DRESSER · CEO · 1/10", tier: "rejected" },
  { text: "x CANVA PTY · DESIGN TOOL · MELANIE PERKINS · CEO · 1/10", tier: "rejected" },
  { text: "x STRIPE INC · PAYMENTS · PATRICK COLLISON · CEO · 2/10", tier: "rejected" },
  { text: "x NOTION LABS · PRODUCTIVITY · IVAN ZHAO · CEO · 1/10", tier: "rejected" },
  { text: "x MAILCHIMP · EMAIL MKTG · BEN CHESTNUT · CEO · 2/10", tier: "rejected" },
  { text: "x ZENDESK INC · SUPPORT SAAS · TOM EGGEMEIER · CEO · 1/10", tier: "rejected" },
  { text: "x INTERCOM · CHAT TOOLS · EOGHAN MCCABE · CEO · 2/10", tier: "rejected" },
  { text: "x AIRTABLE INC · DATABASE · HOWIE LIU · CEO · 1/10", tier: "rejected" },
  { text: "x FIGMA INC · DESIGN TOOL · DYLAN FIELD · CEO · 1/10", tier: "rejected" },
  { text: "x LOOM INC · VIDEO TOOL · JOE THOMAS · CEO · 2/10", tier: "rejected" },
  { text: "x CALENDLY · SCHEDULING · TOPE AWOTONA · CEO · 1/10", tier: "rejected" },
  { text: "x ASANA INC · PROJECT MGT · D MOSKOVITZ · CEO · 2/10", tier: "rejected" },
  { text: "x TYPEFORM SL · FORMS SAAS · JOAQUIM LECHA · CEO · 1/10", tier: "rejected" },
  { text: "x FRESHWORKS · CRM SAAS · G MATHRUBOOTHAM · CEO · 2/10", tier: "rejected" },
  { text: "x SURVEYMONKEY · SURVEYS · ZANDER LURIE · CEO · 1/10", tier: "rejected" },
  { text: "x DOCUSIGN INC · E-SIGN · ALLAN THYGESEN · CEO · 2/10", tier: "rejected" },
];

const TOTAL = DATA_POOL.length;

/* ─── Characters ───────────────────────────────────────── */

const NOISE_CH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,;:_-+[](){}·>";
const SCRAM_CH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-:>";
const rn = () => NOISE_CH[Math.floor(Math.random() * NOISE_CH.length)];
const rs = () => SCRAM_CH[Math.floor(Math.random() * SCRAM_CH.length)];

/* ─── Integer hash for spatial scatter ─────────────────── */

function hash2(a: number, b: number): number {
  let h = (a * 374761393 + b * 668265263) | 0;
  h = ((h ^ (h >> 13)) * 1274126177) | 0;
  return ((h ^ (h >> 16)) >>> 0) / 4294967296; // [0, 1)
}

/* ─── Constants ────────────────────────────────────────── */

const SNAP = 0.84;
const DECODE_DUR = 0.045;
const SNAP_DUR = 0.03;
const SEP = "  ";

/* ─── Cell info precomputed per resize ─────────────────── */

interface CellInfo {
  dataCh: string;
  tier: Tier | null;
  revealAt: number;
  leadColStart: number;
  leadLen: number;
}

function tierAlpha(t: Tier): number {
  return t === "hot" ? 0.92 : t === "review" ? 0.38 : 0.18;
}

/* ─── Build the data wall ──────────────────────────────── */

function buildDataGrid(rows: number, cols: number): CellInfo[][] {
  const grid: CellInfo[][] = [];

  for (let r = 0; r < rows; r++) {
    const cells: CellInfo[] = new Array(cols);

    // Per-row: pick a random start index into DATA_POOL and a horizontal shift
    const dataStartIdx = Math.floor(hash2(r, 9999) * TOTAL);
    const hShift = Math.floor(hash2(r, 7777) * 55);

    // Build a stream of characters for this row: lead text + separator, repeating
    // We need hShift + cols + extra to be safe
    const needed = hShift + cols + 80;

    // Stream entry: each character knows its parent lead
    const sCh: string[] = [];
    const sTier: (Tier | null)[] = [];
    const sInstKey: number[] = [];
    const sLocalIdx: number[] = [];
    const sLeadLen: number[] = [];

    let dataIdx = dataStartIdx;
    let instCounter = r * 1000;

    while (sCh.length < needed) {
      const d = DATA_POOL[dataIdx % TOTAL];

      // Push each character of the lead
      for (let i = 0; i < d.text.length; i++) {
        sCh.push(d.text[i]);
        sTier.push(d.tier);
        sInstKey.push(instCounter);
        sLocalIdx.push(i);
        sLeadLen.push(d.text.length);
      }

      // Push separator
      for (let i = 0; i < SEP.length; i++) {
        sCh.push(" ");
        sTier.push(null);
        sInstKey.push(instCounter);
        sLocalIdx.push(0);
        sLeadLen.push(0);
      }

      instCounter++;
      dataIdx = (dataIdx + 1) % TOTAL;
    }

    // Extract the visible window [hShift .. hShift + cols)
    for (let c = 0; c < cols; c++) {
      const si = hShift + c;
      const tier = sTier[si];

      // Reveal timing — scattered by spatial hash of (row, instanceKey)
      let revealAt: number;
      if (tier === null) {
        revealAt = 0.88;
      } else {
        const raw = hash2(r * 137 + 7, sInstKey[si] * 53 + 13);
        if (tier === "hot") {
          revealAt = 0.04 + raw * 0.38;
        } else if (tier === "review") {
          revealAt = 0.18 + raw * 0.40;
        } else {
          revealAt = 0.35 + raw * 0.43;
        }
      }

      // leadColStart: the visible column where this lead begins
      const leadColStart = c - sLocalIdx[si];

      cells[c] = {
        dataCh: sCh[si],
        tier,
        revealAt,
        leadColStart,
        leadLen: sLeadLen[si],
      };
    }

    grid.push(cells);
  }

  return grid;
}

/* ─── Component ────────────────────────────────────────── */

export default function InfiniteRolodex() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const progressRef = useRef(0);
  const rafId = useRef(0);
  const dataGridRef = useRef<CellInfo[][]>([]);
  const [sp, setSp] = useState(0);

  /* ── Canvas ───────────────────────────────────────────── */
  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext("2d");
    if (!ctx) return;

    const FS = 13;
    const CW = FS * 0.62;
    const LH = FS * 1.35;

    type G = { ch: string; tick: number };
    let noiseGrid: G[][] = [];
    let cols = 0;
    let rows = 0;

    const build = () => {
      cols = Math.ceil(cvs.width / CW) + 1;
      rows = Math.ceil(cvs.height / LH) + 1;

      noiseGrid = [];
      for (let r = 0; r < rows; r++) {
        const row: G[] = [];
        for (let c = 0; c < cols; c++)
          row.push({ ch: rn(), tick: 4 + Math.floor(Math.random() * 18) });
        noiseGrid.push(row);
      }

      dataGridRef.current = buildDataGrid(rows, cols);
    };

    const resize = () => {
      cvs.width = window.innerWidth;
      cvs.height = window.innerHeight;
      build();
    };
    resize();
    window.addEventListener("resize", resize);

    let f = 0;

    const draw = () => {
      f++;
      const W = cvs.width;
      const H = cvs.height;
      ctx.clearRect(0, 0, W, H);

      const scroll = progressRef.current;
      const dg = dataGridRef.current;

      ctx.font = `${FS}px "Roboto Mono","Fira Code",monospace`;
      ctx.textBaseline = "top";

      for (let r = 0; r < rows && r < dg.length; r++) {
        const y = r * LH;
        if (y > H + LH) break;
        const dgRow = dg[r];

        for (let c = 0; c < cols && c < dgRow.length; c++) {
          const cell = dgRow[c];
          const ng = noiseGrid[r]?.[c];
          if (!ng) continue;

          if (f % ng.tick === 0) ng.ch = rn();

          const x = c * CW;

          // Progress for this cell
          let progress = 0;
          if (cell.tier !== null) {
            if (scroll >= SNAP && scroll < cell.revealAt) {
              progress = Math.min(1, (scroll - SNAP) / SNAP_DUR);
            } else if (scroll >= cell.revealAt) {
              progress = Math.min(1, (scroll - cell.revealAt) / DECODE_DUR);
            }
          } else {
            // Separator: fade noise out after snap
            if (scroll >= SNAP) {
              progress = Math.min(1, (scroll - SNAP) / 0.06);
            }
          }

          if (cell.tier === null) {
            // Separator — show noise, fading after snap
            if (progress >= 1) continue;
            const fade = 1 - progress;
            const base = (0.055 + Math.random() * 0.035) * fade;
            if (base < 0.004) continue;
            ctx.fillStyle = `rgba(160,160,160,${base})`;
            ctx.fillText(ng.ch, x, y);
          } else if (progress <= 0) {
            // Pure noise
            const base = 0.055 + Math.random() * 0.035;
            ctx.fillStyle = `rgba(160,160,160,${base})`;
            ctx.fillText(ng.ch, x, y);
          } else if (progress >= 1) {
            // Fully revealed
            const ch = cell.dataCh;
            if (ch === " ") continue;
            ctx.fillStyle = `rgba(250,250,250,${tierAlpha(cell.tier)})`;
            ctx.fillText(ch, x, y);
          } else {
            // Decoding — left-to-right sweep within the lead
            const lockCount = Math.floor(progress * cell.leadLen);
            const charIdx = c - cell.leadColStart;
            const ch = cell.dataCh;
            const alpha = tierAlpha(cell.tier);
            const isSep = ch === " " || ch === "·" || ch === "/";

            if (isSep) {
              const a = progress > 0.25 ? alpha * progress * 0.6 : 0.04;
              ctx.fillStyle = `rgba(250,250,250,${a})`;
              ctx.fillText(ch, x, y);
            } else if (charIdx < lockCount) {
              ctx.fillStyle = `rgba(255,255,255,${alpha * (0.7 + progress * 0.3)})`;
              ctx.fillText(ch, x, y);
            } else {
              ctx.fillStyle = `rgba(180,180,180,${0.06 + progress * 0.09})`;
              ctx.fillText(rs(), x, y);
            }
          }
        }
      }

      // Snap flash
      const snapDist = Math.abs(scroll - SNAP);
      if (snapDist < 0.015) {
        const flashA = Math.max(0, 1 - snapDist * 66) * 0.08;
        ctx.fillStyle = `rgba(255,255,255,${flashA})`;
        ctx.fillRect(0, 0, W, H);
      }

      rafId.current = requestAnimationFrame(draw);
    };

    rafId.current = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(rafId.current);
      window.removeEventListener("resize", resize);
    };
  }, []);

  /* ── GSAP ScrollTrigger ───────────────────────────────── */
  useEffect(() => {
    const gCtx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: sectionRef.current,
        start: "top top",
        end: "+=550%",
        pin: true,
        scrub: true,
        onUpdate(self) {
          progressRef.current = self.progress;
          setSp(self.progress);
        },
      });
    });
    return () => gCtx.revert();
  }, []);

  /* ── Derived ──────────────────────────────────────────── */
  const taglineOp = sp < 0.006 ? 0.85 : Math.max(0, 0.85 - sp * 40);
  const hintOp = sp < 0.004 ? 0.3 : 0;
  const postSnap = sp >= SNAP + 0.04;

  return (
    <section
      ref={sectionRef}
      className="relative w-full h-screen overflow-hidden bg-void"
    >
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full z-0" />

      {/* Vignette */}
      <div
        className="pointer-events-none absolute inset-0 z-10 transition-opacity duration-700"
        style={{
          background:
            "radial-gradient(ellipse at center,transparent 30%,rgba(9,9,11,.45) 95%)",
          opacity: postSnap ? 0.1 : 1,
        }}
      />

      {/* Tagline */}
      <div
        className="absolute top-[13%] left-0 right-0 z-20 text-center px-6 pointer-events-none"
        style={{ opacity: taglineOp }}
      >
        <h1 className="font-mono text-lg sm:text-2xl md:text-3xl lg:text-4xl font-bold text-white tracking-tight mb-3">
          From Chaos to Clarity
        </h1>
        <p className="font-sans text-xs md:text-sm text-zinc-500 max-w-md mx-auto leading-relaxed">
          Scroll through the noise. Watch the leads appear.
        </p>
      </div>

      {/* HUD */}
      <div className="absolute bottom-5 left-5 z-20 font-mono text-[10px] tracking-[.2em] uppercase transition-all duration-300">
        {postSnap ? (
          <span className="text-zinc-400">{TOTAL} LEADS QUALIFIED</span>
        ) : sp > 0.05 ? (
          <span className="text-zinc-600">QUALIFYING...</span>
        ) : (
          <span className="text-zinc-700">SCANNING · 7.2B RECORDS</span>
        )}
      </div>

      <div className="absolute bottom-5 right-5 z-20 font-mono text-[10px] tracking-[.2em] uppercase text-zinc-800">
        THE MAGNET HUNTER
      </div>

      {/* Scroll hint */}
      <div
        className="absolute bottom-14 left-1/2 -translate-x-1/2 z-20 flex flex-col items-center gap-2 pointer-events-none"
        style={{ opacity: hintOp }}
      >
        <span className="font-mono text-[9px] tracking-[.3em] uppercase text-zinc-600">
          Scroll
        </span>
        <svg width="14" height="20" fill="none" className="animate-bounce">
          <path
            d="M7 3v10m0 0l-3-3m3 3l3-3"
            stroke="rgba(250,250,250,.2)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </section>
  );
}
