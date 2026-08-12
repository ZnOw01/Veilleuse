import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import {
  IDENTITY_TEMPERATURE,
  RANGES,
  clamp,
  clampBrightness,
  clampTemperature,
  clampGamma,
  parseStatus,
  copyModel,
  period,
  createQueue,
  pushLatest,
  completeQueue
} from '../Model.js'

describe('Model.js ranges and clamping', () => {
  it('defines the brightness range 1..100', () => {
    assert.equal(RANGES.brightness.min, 1)
    assert.equal(RANGES.brightness.max, 100)
  })

  it('defines the temperature range 2500..6500', () => {
    assert.equal(RANGES.temperature.min, 2500)
    assert.equal(RANGES.temperature.max, 6500)
  })

  it('defines the gamma range 0..100', () => {
    assert.equal(RANGES.gamma.min, 0)
    assert.equal(RANGES.gamma.max, 100)
  })

  it('defines the identity temperature point at 6000 K', () => {
    assert.equal(IDENTITY_TEMPERATURE, 6000)
  })

  it('clamps generic values into a range', () => {
    assert.equal(clamp(5, 1, 100), 5)
    assert.equal(clamp(0, 1, 100), 1)
    assert.equal(clamp(150, 1, 100), 100)
  })

  it('clamps brightness to 1..100', () => {
    assert.equal(clampBrightness(42), 42)
    assert.equal(clampBrightness(0), 1)
    assert.equal(clampBrightness(200), 100)
    assert.equal(clampBrightness('75'), 75)
  })

  it('clamps temperature to 2500..6500', () => {
    assert.equal(clampTemperature(3500), 3500)
    assert.equal(clampTemperature(1000), 2500)
    assert.equal(clampTemperature(9999), 6500)
  })

  it('clamps gamma to 0..100', () => {
    assert.equal(clampGamma(70), 70)
    assert.equal(clampGamma(-5), 0)
    assert.equal(clampGamma(250), 100)
  })
})

describe('Model.js parseStatus', () => {
  it('parses a full combined status payload', () => {
    const raw = {
      brightness: { available: true, percent: '42', monitor: 'eDP-1', error: null },
      nightlight: {
        available: true,
        enabled: true,
        temperature: '3500',
        identity: false,
        gamma: '100',
        error: null
      },
      schedule: {
        day_time: '06:00',
        day_temp: 6000,
        night_time: '15:30',
        night_temp: 3500,
        day_identity: true,
        period: 'night'
      }
    }
    const model = parseStatus(raw)
    assert.equal(model.brightness.percent, 42)
    assert.equal(model.brightness.available, true)
    assert.equal(model.nightlight.temperature, 3500)
    assert.equal(model.nightlight.gamma, 100)
    assert.equal(model.nightlight.enabled, true)
    assert.equal(model.schedule.night_time, '15:30')
    assert.equal(model.schedule.day_time, '06:00')
  })

  it('coerces string numerics and clamps out-of-range values', () => {
    const model = parseStatus({
      brightness: { available: true, percent: '200', monitor: 'DP-1', error: null },
      nightlight: { available: true, temperature: '500', identity: false, gamma: '300', error: null },
      schedule: {}
    })
    assert.equal(model.brightness.percent, 100)
    assert.equal(model.nightlight.temperature, 2500)
    assert.equal(model.nightlight.gamma, 100)
  })

  it('keeps the nightlight enabled flag at false when unavailable', () => {
    const model = parseStatus({ nightlight: { available: false } })
    assert.equal(model.nightlight.enabled, false)
    assert.equal(model.nightlight.temperature, null)
  })

  it('treats identity as authoritative over a stale temperature', () => {
    const model = parseStatus({
      nightlight: { available: true, temperature: '3500', identity: true, gamma: '100', error: null }
    })
    assert.equal(model.nightlight.enabled, false)
    assert.equal(model.nightlight.identity, true)
  })

  it('computes the schedule period when the payload omits it', () => {
    const model = parseStatus({
      schedule: { day_time: '06:00', day_temp: 6000, night_time: '18:00', night_temp: 3500 },
      nightlight: { available: false }
    })
    // 15:00 is between 06:00 and 18:00 → day
    const at = new Date(2026, 0, 1, 15, 0, 0)
    assert.equal(period(model.schedule, at), 'day')
  })

  it('handles empty and malformed payloads without throwing', () => {
    const model = parseStatus(null)
    assert.equal(model.brightness.percent, null)
    assert.equal(model.nightlight.temperature, null)
    assert.equal(model.schedule.day_time, null)
    const fallback = parseStatus('not json')
    assert.equal(fallback.brightness.available, false)
  })
})

describe('Model.js copyModel', () => {
  it('copies nested objects without sharing references', () => {
    const model = parseStatus({
      brightness: { available: true, percent: 42, monitor: 'eDP-1', error: null },
      nightlight: { available: true, temperature: 3500, identity: false, gamma: 100, error: null },
      schedule: { day_time: '06:00', day_temp: 6000, night_time: '15:30', night_temp: 3500 }
    })
    const copy = copyModel(model)
    assert.deepEqual(copy, model)
    assert.notEqual(copy, model)
    assert.notEqual(copy.brightness, model.brightness)
    assert.notEqual(copy.nightlight, model.nightlight)
    copy.brightness.percent = 1
    assert.equal(model.brightness.percent, 42)
  })
})

describe('Model.js period', () => {
  it('returns night while current time sits in the night window', () => {
    const schedule = { day_time: '06:00', night_time: '18:00' }
    assert.equal(period(schedule, new Date(2026, 0, 1, 22, 0, 0)), 'night')
    assert.equal(period(schedule, new Date(2026, 0, 1, 3, 0, 0)), 'night')
  })

  it('returns day during the day window', () => {
    const schedule = { day_time: '06:00', night_time: '18:00' }
    assert.equal(period(schedule, new Date(2026, 0, 1, 9, 0, 0)), 'day')
    assert.equal(period(schedule, new Date(2026, 0, 1, 12, 0, 0)), 'day')
  })

  it('handles a night window that crosses midnight', () => {
    // night_time 22:00 → day_time 06:00 spans midnight
    const schedule = { day_time: '06:00', night_time: '22:00' }
    assert.equal(period(schedule, new Date(2026, 0, 1, 23, 0, 0)), 'night')
    assert.equal(period(schedule, new Date(2026, 0, 1, 4, 0, 0)), 'night')
    assert.equal(period(schedule, new Date(2026, 0, 1, 12, 0, 0)), 'day')
  })

  it('treats an unparseable schedule defensively', () => {
    assert.equal(period(null, new Date(2026, 0, 1, 12, 0, 0)), 'night')
    assert.equal(period({}, new Date(2026, 0, 1, 12, 0, 0)), 'night')
  })
})

describe('Model.js latest-wins queue (pure)', () => {
  it('starts empty with no active or pending value', () => {
    const queue = createQueue()
    assert.equal(queue.active, null)
    assert.equal(queue.pending, null)
  })

  it('pushes the first value into the active slot', () => {
    const queue = pushLatest(createQueue(), 20)
    assert.equal(queue.active, 20)
    assert.equal(queue.pending, null)
  })

  it('retains only the newest value while one is active', () => {
    let queue = createQueue()
    queue = pushLatest(queue, 20)
    queue = pushLatest(queue, 40)
    queue = pushLatest(queue, 60)
    assert.equal(queue.active, 20)
    assert.equal(queue.pending, 60)
  })

  it('promotes the pending value on completion, latest wins', () => {
    let queue = createQueue()
    queue = pushLatest(queue, 20)
    queue = pushLatest(queue, 40)
    queue = pushLatest(queue, 60)
    queue = completeQueue(queue)
    assert.equal(queue.active, 60)
    assert.equal(queue.pending, null)
  })

  it('does not mutate the previous queue state (pure)', () => {
    const initial = createQueue()
    const afterFirst = pushLatest(initial, 20)
    const afterSecond = pushLatest(afterFirst, 40)
    assert.equal(initial.active, null)
    assert.equal(initial.pending, null)
    assert.equal(afterFirst.active, 20)
    assert.equal(afterSecond.pending, 40)
    assert.equal(afterFirst.pending, null)
  })

  it('pushing after completion starts a fresh value', () => {
    let queue = createQueue()
    queue = pushLatest(queue, 20)
    queue = completeQueue(queue)
    queue = pushLatest(queue, 80)
    assert.equal(queue.active, 80)
    assert.equal(queue.pending, null)
  })
})
