#!/usr/bin/env node
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')
const tmpDir = '/tmp/gd-verify'

function compileEngine() {
  fs.rmSync(tmpDir, { recursive: true, force: true })
  fs.mkdirSync(tmpDir, { recursive: true })

  const files = [
    'src/LevelLoader.ts',
    'src/GameLevel.ts',
    'src/GamePhysics.ts',
    'src/utils/FileStream.ts',
    'src/cpp.ts',
    'src/MathF16.ts',
    'src/Micro.ts',
    'src/TimerOrMotoPartOrMenuElem.ts',
    'src/class_10.ts',
  ]

  execSync(
    `npx tsc --outDir ${tmpDir} --module NodeNext --moduleResolution NodeNext --target ES2022 --rewriteRelativeImportExtensions --types vite/client --skipLibCheck --strict ${files.join(' ')}`,
    { cwd: repoRoot, stdio: 'pipe' }
  )

  fs.writeFileSync(path.join(tmpDir, 'package.json'), JSON.stringify({ type: 'module' }))
  fs.writeFileSync(
    path.join(tmpDir, 'GameCanvas.js'),
    `export class GameCanvas {
  static advanceFlagAnimation() {}
}
`
  )
}

function getGroundYAndSlope(gameLevel, worldX) {
  const pts = gameLevel.pointPositions
  const n = gameLevel.pointsCount
  const target = worldX * 8192
  if (n < 2) return { y: 0, slope: 0, idx: 0 }
  if (target <= pts[0][0]) {
    const dx = (pts[1][0] - pts[0][0]) / 8192
    const dy = (pts[1][1] - pts[0][1]) / 8192
    return { y: pts[0][1] / 8192, slope: dy / Math.max(1e-6, dx), idx: 0 }
  }
  for (let i = 0; i < n - 1; i++) {
    if (target <= pts[i + 1][0]) {
      const x0 = pts[i][0] / 8192
      const y0 = pts[i][1] / 8192
      const x1 = pts[i + 1][0] / 8192
      const y1 = pts[i + 1][1] / 8192
      const t = (worldX - x0) / Math.max(1e-6, x1 - x0)
      return {
        y: y0 + t * (y1 - y0),
        slope: (y1 - y0) / Math.max(1e-6, x1 - x0),
        idx: i,
      }
    }
  }
  const dx = (pts[n - 1][0] - pts[n - 2][0]) / 8192
  const dy = (pts[n - 1][1] - pts[n - 2][1]) / 8192
  return { y: pts[n - 1][1] / 8192, slope: dy / Math.max(1e-6, x1MinusX0(pts, n)), idx: n - 2 }
}

function x1MinusX0(pts, n) {
  return Math.max(1e-6, (pts[n - 1][0] - pts[n - 2][0]) / 8192)
}

function inspectAhead(gameLevel, frontX, rearX) {
  const pts = gameLevel.pointPositions
  const n = gameLevel.pointsCount
  const frontInfo = getGroundYAndSlope(gameLevel, frontX)
  const rearInfo = getGroundYAndSlope(gameLevel, rearX)

  let maxStepRise = 0
  let distToStep = 999
  let hasGap = false
  let gapDrop = 0
  let distToGap = 999
  let lookSlopeSum = 0
  let lookSamples = 0

  for (let d = 5; d <= 55; d += 5) {
    const g = getGroundYAndSlope(gameLevel, frontX + d)
    lookSlopeSum += Math.atan(g.slope)
    lookSamples++
  }

  for (let i = Math.max(0, frontInfo.idx - 1); i < n - 1; i++) {
    const x0 = pts[i][0] / 8192
    const y0 = pts[i][1] / 8192
    const x1 = pts[i + 1][0] / 8192
    const y1 = pts[i + 1][1] / 8192
    if (x0 > frontX + 65) break
    const dx = Math.max(1, x1 - x0)
    const dy = y1 - y0
    const slope = dy / dx
    if (slope > 0.7 && dy > 10 && x1 > frontX - 2) {
      const dist = Math.max(0, x0 - frontX)
      if (dy > maxStepRise) {
        maxStepRise = dy
        distToStep = dist
      }
    }
    if (slope < -1.0 && dy < -20 && x1 > frontX - 5) {
      hasGap = true
      gapDrop = Math.min(gapDrop, dy)
      distToGap = Math.min(distToGap, Math.max(0, x0 - frontX))
    }
  }

  // Ground chord angle between rearX and frontX
  const chordSlope = (frontInfo.y - rearInfo.y) / Math.max(1, frontX - rearX)

  return {
    frontGroundY: frontInfo.y,
    rearGroundY: rearInfo.y,
    frontSlope: frontInfo.slope,
    rearSlope: rearInfo.slope,
    chordAngle: Math.atan(chordSlope),
    avgAheadAngle: lookSamples > 0 ? lookSlopeSum / lookSamples : 0,
    maxStepRise,
    distToStep,
    hasGap,
    gapDrop,
    distToGap,
  }
}

const BOT_PROFILES = [
  { name: 'flow', baseRelPitch: 0.02, airBias: 0.05, wheelieBoost: 0.34, maxPitch: 1.18, minPitch: -0.95, speedCap: 48, airThrottle: 0 },
  { name: 'attack', baseRelPitch: -0.04, airBias: 0.08, wheelieBoost: 0.42, maxPitch: 1.25, minPitch: -1.05, speedCap: 75, airThrottle: 1 },
  { name: 'trials', baseRelPitch: 0.08, airBias: 0.02, wheelieBoost: 0.48, maxPitch: 1.12, minPitch: -0.85, speedCap: 34, airThrottle: 0 },
  { name: 'steady', baseRelPitch: -0.08, airBias: 0.0, wheelieBoost: 0.24, maxPitch: 1.05, minPitch: -0.85, speedCap: 28, airThrottle: 0 },
  { name: 'send_it', baseRelPitch: 0.0, airBias: 0.14, wheelieBoost: 0.52, maxPitch: 1.28, minPitch: -1.1, speedCap: 95, airThrottle: 1 },
  { name: 'tech_low', baseRelPitch: -0.12, airBias: -0.04, wheelieBoost: 0.38, maxPitch: 1.15, minPitch: -0.9, speedCap: 22, airThrottle: 0 },
]

function runBotAttempt(GamePhysics, levelLoader, levelIdx, trackIdx, leagueIdx, profile, maxSteps = 14000) {
  levelLoader.loadLevel(levelIdx, trackIdx)
  const physics = new GamePhysics(levelLoader)
  physics.setMode(1)
  physics.setMotoLeague(leagueIdx)

  const gameLevel = levelLoader.gameLevel
  const finishWorldX = levelLoader.getFinishX() / 16384
  const startWorldX = levelLoader.getStartPosX() / 16384

  let maxProgressX = startWorldX
  let prevPitch = 0
  let stuckTicks = 0
  let lastProgressCheckX = startWorldX

  for (let step = 0; step < maxSteps; step++) {
    const front = physics.bikeParts[1].motoComponents[physics.index01]
    const rear = physics.bikeParts[2].motoComponents[physics.index01]
    const chassis = physics.bikeParts[0].motoComponents[physics.index01]

    const fx = front.xF16 / 16384
    const fy = front.yF16 / 16384
    const rx = rear.xF16 / 16384
    const ry = rear.yF16 / 16384
    const vx = chassis.velocityXF16 / 65536
    const vy = chassis.velocityYF16 / 65536

    const pitch = Math.atan2(fy - ry, fx - rx)
    const pitchVel = pitch - prevPitch
    prevPitch = pitch

    if (fx > maxProgressX) maxProgressX = fx

    if (step % 260 === 0 && step > 0) {
      if (maxProgressX - lastProgressCheckX < 4) {
        stuckTicks++
      } else {
        stuckTicks = 0
        lastProgressCheckX = maxProgressX
      }
      if (stuckTicks >= 5) {
        return { finished: false, reason: `stuck at x=${fx.toFixed(1)}`, maxX: maxProgressX, finishX: finishWorldX, steps: step }
      }
    }

    if (step < 30) {
      physics.setInputDirection(0, 0)
    } else {
      const ahead = inspectAhead(gameLevel, fx, rx)
      const frontClear = fy - ahead.frontGroundY - 7
      const rearClear = ry - ahead.rearGroundY - 7
      const inAir = frontClear > 5.0 && rearClear > 5.0

      const groundAngle = ahead.chordAngle
      let targetPitch = groundAngle + profile.baseRelPitch

      if (inAir) {
        targetPitch = ahead.avgAheadAngle * 0.75 + profile.airBias
      } else if (ahead.maxStepRise > 11 && ahead.distToStep < 22 && ahead.distToStep > 2) {
        targetPitch = groundAngle + profile.wheelieBoost
      } else if (ahead.hasGap && ahead.distToGap < 18) {
        targetPitch = Math.max(groundAngle + 0.1, 0.12)
      }

      targetPitch = Math.max(profile.minPitch, Math.min(profile.maxPitch, targetPitch))

      const predictedPitch = pitch + pitchVel * 7.5
      const pitchErr = targetPitch - predictedPitch
      let lean = 0
      if (pitchErr > 0.04) lean = -1
      else if (pitchErr < -0.04) lean = 1

      let throttle = 1
      if (inAir) {
        throttle = profile.airThrottle
      } else {
        // Prevent backflip relative to vertical or excessive wheelie relative to ground
        if (pitch > 1.22 && pitchVel > 0) {
          throttle = 0
          lean = 1
        }
        if (pitch - groundAngle > 0.68 && pitchVel > 0.005) {
          throttle = 0
          lean = 1
        }
        if (pitch > 1.38) {
          throttle = -1
          lean = 1
        }
        // Speed control when not jumping a gap
        if (!ahead.hasGap && vx > profile.speedCap) {
          throttle = 0
        }
        // Brake briefly if rushing blindly into a steep drop without a launch ramp
        if (ahead.hasGap && ahead.distToGap < 12 && ahead.frontSlope < -0.2 && vx > 18) {
          throttle = -1
        }
      }

      if (stuckTicks >= 1 && step % 90 < 35) {
        throttle = 1
        lean = step % 90 < 18 ? -1 : 1
      }

      physics.setInputDirection(throttle, lean)
    }

    const res = physics.updatePhysics()
    if (step < 30 && (res === 3 || res === 5)) {
      return { finished: false, reason: `spawn_crash(step=${step}, res=${res})`, maxX: maxProgressX, finishX: finishWorldX, steps: step }
    }
    if (res === 1 || res === 2) {
      return { finished: true, reason: 'finished', maxX: finishWorldX, finishX: finishWorldX, steps: step, profile: profile.name }
    }
    if (res === 3 || res === 5) {
      return { finished: false, reason: `crash(res=${res}) at x=${fx.toFixed(1)}`, maxX: maxProgressX, finishX: finishWorldX, steps: step }
    }
  }

  return { finished: false, reason: `timeout at x=${maxProgressX.toFixed(1)}`, maxX: maxProgressX, finishX: finishWorldX, steps: maxSteps }
}

async function main() {
  const mrgArg = process.argv[2] || 'src/assets/alt-career.mrg'
  const mrgPath = path.isAbsolute(mrgArg) ? mrgArg : path.resolve(repoRoot, mrgArg)
  const filterArg = process.argv[3] || null

  console.log(`Compiling TypeScript engine to ${tmpDir}...`)
  compileEngine()

  const { FileStream } = await import(pathToFileURL(path.join(tmpDir, 'utils/FileStream.js')).href)
  const { LevelLoader } = await import(pathToFileURL(path.join(tmpDir, 'LevelLoader.js')).href)
  const { GamePhysics } = await import(pathToFileURL(path.join(tmpDir, 'GamePhysics.js')).href)

  const buf = fs.readFileSync(mrgPath)
  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength)
  const stream = new FileStream(ab)
  const loader = new LevelLoader(stream)

  console.log(`Loaded ${mrgPath}`)
  for (let l = 0; l < 3; l++) {
    console.log(`  Level ${l}: ${loader.levelNames[l].length} tracks -> [${loader.levelNames[l].join(', ')}]`)
  }

  let totalTracks = 0
  let passedSpawn = 0
  let passedAll = 0
  const failures = []

  const leaguesToTest = process.env.LEAGUES
    ? process.env.LEAGUES.split(',').map((s) => Number(s.trim()))
    : [2, 3] // 220cc and 325cc

  for (let lvl = 0; lvl < 3; lvl++) {
    for (let trk = 0; trk < loader.levelNames[lvl].length; trk++) {
      const name = loader.levelNames[lvl][trk]
      if (filterArg && !`${lvl}:${trk}`.includes(filterArg) && !name.toLowerCase().includes(filterArg.toLowerCase())) {
        continue
      }
      totalTracks++

      loader.loadLevel(lvl, trk)
      const gl = loader.gameLevel
      let strictX = true
      for (let i = 1; i < gl.pointsCount; i++) {
        if (gl.pointPositions[i][0] <= gl.pointPositions[i - 1][0]) {
          strictX = false
          break
        }
      }

      const leagueResults = {}
      let trackSpawnOk = true
      let trackAllOk = true

      for (const league of leaguesToTest) {
        let bestRes = null
        for (const profile of BOT_PROFILES) {
          const res = runBotAttempt(GamePhysics, loader, lvl, trk, league, profile)
          if (!bestRes || (res.finished && !bestRes.finished) || (!bestRes.finished && res.maxX > bestRes.maxX)) {
            bestRes = res
          }
          if (res.reason.startsWith('spawn_crash')) {
            trackSpawnOk = false
          }
          if (res.finished) break
        }
        leagueResults[league] = bestRes
        if (!bestRes.finished) trackAllOk = false
      }

      if (trackSpawnOk && strictX) passedSpawn++
      if (trackAllOk && strictX && trackSpawnOk) passedAll++
      else failures.push({ lvl, trk, name, strictX, trackSpawnOk, leagueResults })

      const parts = leaguesToTest.map((l) => {
        const r = leagueResults[l]
        const label = ['100cc', '175cc', '220cc', '325cc'][l] || `L${l}`
        const val = r.finished ? `PASS(${r.steps}st,${r.profile})` : `FAIL(${r.reason}/${r.finishX.toFixed(0)})`
        return `${label}=${val.padEnd(24)}`
      })
      console.log(`[L${lvl}:${trk}] ${name.padEnd(18)} pts=${String(gl.pointsCount).padStart(3)} monoX=${strictX ? 'OK' : 'BAD'} | ${parts.join(' | ')}`)
    }
  }

  const leagueDesc = leaguesToTest.map((l) => ['100cc', '175cc', '220cc', '325cc'][l] || `L${l}`).join(' and ')
  console.log(`\nSummary: ${passedAll}/${totalTracks} tracks completed on ALL of ${leagueDesc} (spawn+monoX OK: ${passedSpawn}/${totalTracks}).`)
  if (failures.length > 0) {
    console.log(`Failures (${failures.length}):`)
    for (const f of failures) {
      const fDesc = leaguesToTest.map((l) => `${['100cc', '175cc', '220cc', '325cc'][l]}=${f.leagueResults[l].reason}`).join(', ')
      console.log(`  - [L${f.lvl}:${f.trk}] ${f.name}: ${fDesc}`)
    }
    process.exitCode = 1
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
