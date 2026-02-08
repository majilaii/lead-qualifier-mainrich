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
  {
    text: "> BOSTON DYNAMICS · ROBOTICS · MARC RAIBERT · CEO · 9/10",
    tier: "hot",
  },
  {
    text: "> FIGURE AI · HUMANOID ROBOTS · BRETT ADCOCK · CEO · 10/10",
    tier: "hot",
  },
  {
    text: "> AGILITY ROBOTICS · HUMANOIDS · DAMION SHELTON · CEO · 10/10",
    tier: "hot",
  },
  {
    text: "> UNITREE ROBOTICS · QUADRUPEDS · WANG XINGXING · CEO · 9/10",
    tier: "hot",
  },
  {
    text: "> MAXON GROUP · PRECISION MOTORS · EUGEN ELMIGER · CEO · 8/10",
    tier: "hot",
  },
  {
    text: "> TESLA INC · EV AND ENERGY · DREW BAGLINO · SVP ENG · 8/10",
    tier: "hot",
  },
  {
    text: "> ABB ROBOTICS · INDUSTRIAL AUTO · SAMI ATIYA · PRES · 8/10",
    tier: "hot",
  },
  {
    text: "> HARMONIC DRIVE · ACTUATORS · S YAMAZAKI · CTO · 9/10",
    tier: "hot",
  },
  { text: "> MOOG INC · MOTION CONTROL · PAT ROCHE · CEO · 9/10", tier: "hot" },
  {
    text: "> KOLLMORGEN · SERVO SYSTEMS · DAN ST-PIERRE · DIR · 8/10",
    tier: "hot",
  },
  {
    text: "> SAMSUNG SDI · BATTERY TECH · YOONHO CHOI · VP ENG · 8/10",
    tier: "hot",
  },
  {
    text: "> 1X TECHNOLOGIES · HUMANOIDS · BERNT BORNICH · CEO · 10/10",
    tier: "hot",
  },
  { text: "- NIDEC CORP · MOTOR MFG · JUN SEKI · COO · 7/10", tier: "review" },
  {
    text: "- SIEMENS AG · INDUSTRIAL · CEDRIK NEIKE · BOARD · 6/10",
    tier: "review",
  },
  {
    text: "- BOSCH GROUP · AUTOMOTIVE · STEFAN HARTUNG · CEO · 6/10",
    tier: "review",
  },
  {
    text: "- FANUC CORP · CNC ROBOTICS · KENJI YAMAGUCHI · CEO · 7/10",
    tier: "review",
  },
  {
    text: "- DENSO CORP · AUTO PARTS · KOJI ARIMA · CEO · 6/10",
    tier: "review",
  },
  {
    text: "- FESTO SE · PNEUMATICS · DR FRANK MELZER · CTO · 5/10",
    tier: "review",
  },
  {
    text: "- YASKAWA ELEC · SERVO MOTORS · H OGASAWARA · CEO · 7/10",
    tier: "review",
  },
  {
    text: "- RETHINK ROBOTICS · COBOTS · CONTACT TBD · TBD · 5/10",
    tier: "review",
  },
  {
    text: "- KUKA AG · INDUSTRIAL ROBOTS · PETER MOHNEN · CEO · 6/10",
    tier: "review",
  },
  {
    text: "- DELTA ELECTRONICS · POWER SYS · PING CHENG · CEO · 5/10",
    tier: "review",
  },
  {
    text: "- SCHAEFFLER AG · BEARINGS · KLAUS ROSENFELD · CEO · 6/10",
    tier: "review",
  },
  {
    text: "- NSK LTD · BEARINGS · TOSHIHIRO UCHIYAMA · CEO · 5/10",
    tier: "review",
  },
  {
    text: "- SMC CORP · PNEUMATICS · YOSHIKI TAKADA · PRES · 5/10",
    tier: "review",
  },
  {
    text: "- OMRON CORP · AUTOMATION · JUNTA TSUJINAGA · CEO · 6/10",
    tier: "review",
  },
  {
    text: "- ROCKWELL AUTO · PLC SYSTEMS · BLAKE MORET · CEO · 4/10",
    tier: "review",
  },
  {
    text: "- COGNEX CORP · VISION SYS · ROBERT WILLETT · CEO · 4/10",
    tier: "review",
  },
  {
    text: "- KEYENCE CORP · SENSORS · T TAKIZAKI · CHAIR · 5/10",
    tier: "review",
  },
  {
    text: "- THK CO LTD · LINEAR MOTION · A TERAMACHI · CEO · 7/10",
    tier: "review",
  },
  {
    text: "x HUBSPOT INC · SAAS · YAMINI RANGAN · CEO · 2/10",
    tier: "rejected",
  },
  {
    text: "x SLACK TECH · MESSAGING · DENISE DRESSER · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x CANVA PTY · DESIGN TOOL · MELANIE PERKINS · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x STRIPE INC · PAYMENTS · PATRICK COLLISON · CEO · 2/10",
    tier: "rejected",
  },
  {
    text: "x NOTION LABS · PRODUCTIVITY · IVAN ZHAO · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x MAILCHIMP · EMAIL MKTG · BEN CHESTNUT · CEO · 2/10",
    tier: "rejected",
  },
  {
    text: "x ZENDESK INC · SUPPORT SAAS · TOM EGGEMEIER · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x INTERCOM · CHAT TOOLS · EOGHAN MCCABE · CEO · 2/10",
    tier: "rejected",
  },
  {
    text: "x AIRTABLE INC · DATABASE · HOWIE LIU · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x FIGMA INC · DESIGN TOOL · DYLAN FIELD · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x LOOM INC · VIDEO TOOL · JOE THOMAS · CEO · 2/10",
    tier: "rejected",
  },
  {
    text: "x CALENDLY · SCHEDULING · TOPE AWOTONA · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x ASANA INC · PROJECT MGT · D MOSKOVITZ · CEO · 2/10",
    tier: "rejected",
  },
  {
    text: "x TYPEFORM SL · FORMS SAAS · JOAQUIM LECHA · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x FRESHWORKS · CRM SAAS · G MATHRUBOOTHAM · CEO · 2/10",
    tier: "rejected",
  },
  {
    text: "x SURVEYMONKEY · SURVEYS · ZANDER LURIE · CEO · 1/10",
    tier: "rejected",
  },
  {
    text: "x DOCUSIGN INC · E-SIGN · ALLAN THYGESEN · CEO · 2/10",
    tier: "rejected",
  },
];

const TOTAL = DATA_POOL.length;

/* ─── Characters ───────────────────────────────────────── */

const NOISE_CH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,;:_-+[](){}·>";
const SCRAM_CH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-:>";
const rn = () => NOISE_CH[Math.floor(Math.random() * NOISE_CH.length)];
const rs = () => SCRAM_CH[Math.floor(Math.random() * SCRAM_CH.length)];

/* ─── Spatial hash ─────────────────────────────────────── */

function hash2(a: number, b: number): number {
  let h = (a * 374761393 + b * 668265263) | 0;
  h = ((h ^ (h >> 13)) * 1274126177) | 0;
  return ((h ^ (h >> 16)) >>> 0) / 4294967296;
}

/* ─── Easing ───────────────────────────────────────────── */

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/* ─── Phase Thresholds ─────────────────────────────────── */
/*
 * Scroll phases (0→1 over 1100vh):
 *
 *   0.00–0.17   Pure noise wall (builds tension)
 *   0.17–0.55   Exponential lead decode: first 1–2 contacts appear with a
 *               long visible scramble, then the pace accelerates over ~2.2
 *               viewports — power 4.0 curve + 140× variable decode duration.
 *   ~0.55       SNAP flash — wall of contacts fully locked in
 *   0.55–0.64   Wall holds, all contacts visible
 *   0.64–0.84   MORPH — text cells brighten to form "FROM CHAOS / TO CLARITY",
 *               non-text cells scramble back to dim chaos
 *   0.84–1.00   Final state holds — ASCII art tagline readable, chaos in bg
 */

const SNAP = 0.55;
const DECODE_DUR = 0.045;
const SEP = "  ";

const MORPH_START = 0.575;
const MORPH_END = 0.84;

/* ─── Cell info ────────────────────────────────────────── */

interface CellInfo {
  dataCh: string;
  tier: Tier | null;
  revealAt: number;
  leadColStart: number;
  leadLen: number;
  decodeDur: number; // pre-computed per-cell decode duration
  alphaVal: number; // pre-computed tier alpha (0 for separators)
}

function tierAlpha(t: Tier): number {
  return t === "hot" ? 0.92 : t === "review" ? 0.38 : 0.18;
}

/* ─── Build the data wall ──────────────────────────────── */

function buildDataGrid(rows: number, cols: number): CellInfo[][] {
  const grid: CellInfo[][] = [];

  for (let r = 0; r < rows; r++) {
    const cells: CellInfo[] = new Array(cols);
    const dataStartIdx = Math.floor(hash2(r, 9999) * TOTAL);
    const hShift = Math.floor(hash2(r, 7777) * 55);
    const needed = hShift + cols + 80;

    const sCh: string[] = [];
    const sTier: (Tier | null)[] = [];
    const sInstKey: number[] = [];
    const sLocalIdx: number[] = [];
    const sLeadLen: number[] = [];

    let dataIdx = dataStartIdx;
    let instCounter = r * 1000;

    while (sCh.length < needed) {
      const d = DATA_POOL[dataIdx % TOTAL];
      for (let i = 0; i < d.text.length; i++) {
        sCh.push(d.text[i]);
        sTier.push(d.tier);
        sInstKey.push(instCounter);
        sLocalIdx.push(i);
        sLeadLen.push(d.text.length);
      }
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

    for (let c = 0; c < cols; c++) {
      const si = hShift + c;
      const tier = sTier[si];

      let revealAt: number;
      if (tier === null) {
        revealAt = 0.6;
      } else {
        const raw = hash2(r * 137 + 7, sInstKey[si] * 53 + 13);
        if (tier === "hot") {
          revealAt = 0.005 + raw * 0.4; // 0.005–0.405 (massive spread)
        } else if (tier === "review") {
          revealAt = 0.08 + raw * 0.38; // 0.08–0.46
        } else {
          revealAt = 0.15 + raw * 0.38; // 0.15–0.53
        }
      }

      cells[c] = {
        dataCh: sCh[si],
        tier,
        revealAt,
        leadColStart: c - sLocalIdx[si],
        leadLen: sLeadLen[si],
        decodeDur:
          tier !== null
            ? DECODE_DUR * (0.05 + 8.0 * Math.pow(1 - revealAt / SNAP, 3))
            : 0,
        alphaVal: tier ? tierAlpha(tier) : 0,
      };
    }

    grid.push(cells);
  }

  return grid;
}

/* ─── Build text bitmap from offscreen canvas ──────────── */
/*
 * Renders "FROM CHAOS / TO CLARITY" in large bold text on a
 * hidden canvas, then reads the pixel data to create a boolean
 * grid: true = this cell is part of the tagline shape.
 */

function buildTextBitmap(
  w: number,
  h: number,
  cw: number,
  lh: number,
  cols: number,
  rows: number,
): boolean[][] {
  // Render at 2× for better stroke detection
  const scale = 2;
  const off = document.createElement("canvas");
  off.width = w * scale;
  off.height = h * scale;
  const oc = off.getContext("2d");
  if (!oc) return [];

  oc.scale(scale, scale);

  // Larger, heavier font → thicker strokes → more cells hit
  const fontSize = Math.floor(Math.min(w * 0.11, 180));
  oc.font = `900 ${fontSize}px "Roboto Mono", "Fira Code", monospace`;
  oc.textAlign = "center";
  oc.textBaseline = "middle";
  oc.fillStyle = "#fff";

  // Two lines, vertically centered with gap
  const halfGap = fontSize * 0.65;
  oc.fillText("FROM CHAOS", w / 2, h / 2 - halfGap);
  oc.fillText("TO CLARITY", w / 2, h / 2 + halfGap);

  // Read at full 2× resolution for accurate sampling
  const imageData = oc.getImageData(0, 0, w * scale, h * scale);
  const pixels = imageData.data;
  const imgW = w * scale;

  // Multi-sample 3×3 grid per cell — catches thin horizontal/vertical
  // strokes that single-center sampling misses (F top bar, R details)
  const bitmap: boolean[][] = [];
  for (let r = 0; r < rows; r++) {
    const row: boolean[] = [];
    for (let c = 0; c < cols; c++) {
      let hit = false;
      for (let sy = 0; sy < 3 && !hit; sy++) {
        for (let sx = 0; sx < 3 && !hit; sx++) {
          const px = Math.floor((c * cw + (cw * (sx + 0.5)) / 3) * scale);
          const py = Math.floor((r * lh + (lh * (sy + 0.5)) / 3) * scale);
          if (px >= 0 && px < imgW && py >= 0 && py < h * scale) {
            const idx = (py * imgW + px) * 4;
            // Very low threshold catches all anti-aliased edges
            if (pixels[idx + 3] > 25) hit = true;
          }
        }
      }
      row.push(hit);
    }
    bitmap.push(row);
  }

  return bitmap;
}

/* ─── Component ────────────────────────────────────────── */

export default function InfiniteRolodex() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const progressRef = useRef(0);
  const rafId = useRef(0);
  const dataGridRef = useRef<CellInfo[][]>([]);
  const textBitmapRef = useRef<boolean[][]>([]);
  const [sp, setSp] = useState(0);
  const lastSpRef = useRef(0);

  /* ── Canvas effect ────────────────────────────────────── */
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
      textBitmapRef.current = buildTextBitmap(
        cvs.width,
        cvs.height,
        CW,
        LH,
        cols,
        rows,
      );
    };

    const resize = () => {
      cvs.width = window.innerWidth;
      cvs.height = window.innerHeight;
      build();
      // Set font/baseline here — canvas state resets on dimension change
      ctx.font = `${FS}px "Roboto Mono","Fira Code",monospace`;
      ctx.textBaseline = "top";
    };
    resize();
    window.addEventListener("resize", resize);

    let f = 0;
    let lastScroll = -1;
    let idleFrames = 0;

    const draw = () => {
      f++;
      const scroll = progressRef.current;

      // When scroll is static, drop to ~30fps (skip every other frame)
      if (scroll === lastScroll) {
        idleFrames++;
        if (idleFrames > 5 && (f & 1) === 0) {
          rafId.current = requestAnimationFrame(draw);
          return;
        }
      } else {
        idleFrames = 0;
        lastScroll = scroll;
      }

      const W = cvs.width;
      const H = cvs.height;
      ctx.clearRect(0, 0, W, H);

      const dg = dataGridRef.current;
      const bitmap = textBitmapRef.current;

      if (scroll < MORPH_START) {
        /* ═══════════════════════════════════════════════════
         *  WALL MODE — noise → decode → snap → hold
         *
         *  Power 4.0 over SNAP=0.55 → decode phase spans 605vh.
         *  First contact trickles in around scroll ~0.17, then
         *  the pace visibly accelerates over ~2.2 viewports.
         *  Combined with 140× variable decode duration (first
         *  contacts scramble for ages, last ones snap instantly),
         *  the ramp is unmistakable.
         * ═══════════════════════════════════════════════════ */
        const t = Math.min(1, scroll / SNAP);
        const decodeScroll = Math.pow(t, 1.7) * SNAP;

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

            // Per-cell decode progress (uses exponential decodeScroll).
            // decodeDur is pre-computed in buildDataGrid — 66× variation.
            let progress = 0;
            if (cell.tier !== null) {
              if (decodeScroll >= cell.revealAt) {
                progress = Math.min(
                  1,
                  (decodeScroll - cell.revealAt) / cell.decodeDur,
                );
              }
            } else {
              // Separator: clean up noise after snap (uses real scroll)
              if (scroll >= SNAP) {
                progress = Math.min(1, (scroll - SNAP) / 0.06);
              }
            }

            if (cell.tier === null) {
              // Separator — fading noise
              if (progress >= 1) continue;
              const fade = 1 - progress;
              const base = (0.055 + hash2(r * 311 + c, f >> 2) * 0.035) * fade;
              if (base < 0.004) continue;
              ctx.fillStyle = `rgba(160,160,160,${base})`;
              ctx.fillText(ng.ch, x, y);
            } else if (progress <= 0) {
              // Pure noise (not yet decoding)
              const base = 0.055 + hash2(r * 311 + c, f >> 2) * 0.035;
              ctx.fillStyle = `rgba(160,160,160,${base})`;
              ctx.fillText(ng.ch, x, y);
            } else if (progress >= 1) {
              // Fully revealed lead character
              const ch = cell.dataCh;
              if (ch === " ") continue;
              ctx.fillStyle = `rgba(250,250,250,${cell.alphaVal})`;
              ctx.fillText(ch, x, y);
            } else {
              // Decoding — left-to-right sweep within the lead
              const lockCount = Math.floor(progress * cell.leadLen);
              const charIdx = c - cell.leadColStart;
              const ch = cell.dataCh;
              const alpha = cell.alphaVal;
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
      } else {
        /* ═══════════════════════════════════════════════════
         *  MORPH MODE — wall characters reshape into tagline,
         *  remaining characters dissolve back to chaos
         * ═══════════════════════════════════════════════════ */
        const rawP = Math.min(
          1,
          (scroll - MORPH_START) / (MORPH_END - MORPH_START),
        );
        const mp = easeInOutCubic(rawP);

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
            const isText = bitmap[r]?.[c] ?? false;

            if (isText) {
              /* ── Text cell: brighten to form the tagline shape ── */

              // Alpha lerps from wall brightness to full white
              const startA = cell.alphaVal;
              const alpha = startA + (0.94 - startA) * mp;

              // Scramble: ramps up briefly then settles to real chars
              // Creates a "hologram locking in" feel
              const scrambleUp = Math.min(1, mp * 3.5);
              const scrambleDown = Math.min(1, Math.max(0, (mp - 0.28) / 0.35));
              const scrambleAmount = scrambleUp * (1 - scrambleDown);
              const isScrambled = hash2(r * 137 + c, f >> 2) < scrambleAmount;

              // Stable character for this cell (deterministic)
              const stableCh =
                cell.tier !== null && cell.dataCh !== " "
                  ? cell.dataCh
                  : SCRAM_CH[
                      Math.floor(hash2(r * 997 + c, 42) * SCRAM_CH.length)
                    ];

              const ch = isScrambled ? rs() : stableCh;
              ctx.fillStyle = `rgba(250,250,250,${alpha})`;
              ctx.fillText(ch, x, y);
            } else {
              /* ── Non-text cell: fade back to dim chaos ── */

              const startA = cell.alphaVal;
              const endA = 0.03 + hash2(r, c) * 0.022;
              const alpha = startA + (endA - startA) * mp;

              if (alpha < 0.005) continue;

              // Character morphs from wall data → noise
              const noiseP = Math.min(1, mp * 1.8);
              const useNoise = hash2(r * 311 + c, f >> 1) < noiseP;
              const ch = useNoise
                ? ng.ch
                : cell.dataCh === " "
                  ? ng.ch
                  : cell.dataCh;

              ctx.fillStyle = `rgba(160,160,160,${alpha})`;
              ctx.fillText(ch || ng.ch, x, y);
            }
          }
        }
      }

      /* ── Snap flash ───────────────────────────────────── */
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
        end: "+=1100%",
        pin: true,
        scrub: true,
        onUpdate(self) {
          progressRef.current = self.progress;
          // Throttle React re-renders — HUD only needs ~20fps updates
          if (Math.abs(self.progress - lastSpRef.current) > 0.002) {
            lastSpRef.current = self.progress;
            setSp(self.progress);
          }
        },
      });
    });
    return () => gCtx.revert();
  }, []);

  /* ── Derived values ──────────────────────────────────── */
  const hintOp = sp < 0.004 ? 0.35 : Math.max(0, 0.35 - sp * 12);
  const postSnap = sp >= SNAP + 0.04;
  const morphP = Math.min(
    1,
    Math.max(0, (sp - MORPH_START) / (MORPH_END - MORPH_START)),
  );
  const hudOp = morphP > 0.2 ? Math.max(0, 1 - morphP * 1.5) : 1;

  // Vignette returns during morph to darken edges around the text
  const vignetteOp = morphP > 0 ? 0.1 + morphP * 0.5 : postSnap ? 0.1 : 1;

  // Subtitle fades in after morph completes
  const subtitleOp =
    sp < MORPH_END + 0.03 ? 0 : Math.min(1, (sp - MORPH_END - 0.03) / 0.06);

  return (
    <section
      ref={sectionRef}
      className="relative w-full h-screen overflow-hidden bg-void"
    >
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full z-0" />

      {/* Vignette — darkens edges, lifts after snap, returns for text readability */}
      <div
        className="pointer-events-none absolute inset-0 z-10"
        style={{
          background:
            "radial-gradient(ellipse at center,transparent 30%,rgba(9,9,11,.55) 95%)",
          opacity: vignetteOp,
          transition: "opacity 0.5s",
        }}
      />

      {/* Subtitle — small product label after the ASCII art tagline forms */}
      <div
        className="absolute z-30 left-0 right-0 pointer-events-none"
        style={{ bottom: "14%", opacity: subtitleOp }}
      >
        <div className="w-12 h-px bg-zinc-700 mx-auto mb-4" />
        <p className="font-sans text-xs md:text-sm text-zinc-500 text-center tracking-wide">
          AI-Powered B2B Lead Qualification
        </p>
      </div>

      {/* HUD — bottom-left status */}
      <div
        className="absolute bottom-5 left-5 z-20 font-mono text-[10px] tracking-[.2em] uppercase transition-all duration-300"
        style={{ opacity: hudOp }}
      >
        {postSnap ? (
          <span className="text-zinc-400">{TOTAL} LEADS QUALIFIED</span>
        ) : sp > 0.03 ? (
          <span className="text-zinc-600">QUALIFYING...</span>
        ) : (
          <span className="text-zinc-700">SCANNING · 7.2B RECORDS</span>
        )}
      </div>

      {/* HUD — bottom-right brand */}
      <div
        className="absolute bottom-5 right-5 z-20 font-mono text-[10px] tracking-[.2em] uppercase text-zinc-800"
        style={{ opacity: hudOp }}
      >
        THE MAGNET HUNTER
      </div>

      {/* Scroll hint (visible only at very start) */}
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
