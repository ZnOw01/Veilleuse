// Veilleuse plugin model — pure, side-effect-free state helpers.
//
// This module never talks to the system.  It normalizes and clamps the status
// JSON produced by scripts/veilleuse-control, computes the active schedule
// period on a circular 24-hour clock, and implements the latest-wins value
// queue used by the display controls.  It is shared verbatim between the
// Quickshell UI and the Node test suite (module.exports guard below lets
// Quickshell import it with `import "Model.js" as Model`).

// Keep in sync with the temperature threshold used by Omarchy's nightlight
// plugins and bin/omarchy-toggle-nightlight: values strictly below this count
// as night light, while identity stays authoritative.
var IDENTITY_TEMPERATURE = 6000

var RANGES = {
  brightness: { min: 1, max: 100 },
  temperature: { min: 2500, max: 6500 },
  gamma: { min: 0, max: 100 }
}

function clamp(value, min, max) {
  var number = Number(value)
  if (value === null || value === undefined || isNaN(number)) return null
  return Math.max(min, Math.min(max, number))
}

function clampBrightness(value) {
  return clamp(value, RANGES.brightness.min, RANGES.brightness.max)
}

function clampTemperature(value) {
  return clamp(value, RANGES.temperature.min, RANGES.temperature.max)
}

function clampGamma(value) {
  return clamp(value, RANGES.gamma.min, RANGES.gamma.max)
}

function toInt(value) {
  if (value === null || value === undefined || value === "") return null
  var number = Number(value)
  return isNaN(number) ? null : number
}

function parseSchedule(raw) {
  var schedule = raw && typeof raw === "object" ? raw : {}
  return {
    day_time: schedule.day_time ? String(schedule.day_time) : null,
    day_temp: clampTemperature(toInt(schedule.day_temp)) === null
      ? null
      : clampTemperature(toInt(schedule.day_temp)),
    night_time: schedule.night_time ? String(schedule.night_time) : null,
    night_temp: clampTemperature(toInt(schedule.night_temp)) === null
      ? null
      : clampTemperature(toInt(schedule.night_temp)),
    day_identity: schedule.day_identity === true
  }
}

// identity is authoritative: a stale temperature reading must never win over
// an active natural-color mode.
function parseNightlight(raw) {
  var nightlight = raw && typeof raw === "object" ? raw : {}
  var available = nightlight.available === true
  var identity = nightlight.identity === true
  var temperature = available ? clampTemperature(toInt(nightlight.temperature)) : null
  var enabled = available && !identity && temperature !== null
    ? temperature < IDENTITY_TEMPERATURE
    : false
  return {
    available: available,
    enabled: enabled,
    temperature: temperature,
    identity: identity,
    gamma: available ? clampGamma(toInt(nightlight.gamma)) : null,
    error: nightlight.error ? String(nightlight.error) : null
  }
}

function parseBrightness(raw) {
  var brightness = raw && typeof raw === "object" ? raw : {}
  var available = brightness.available === true
  var percent = available ? clampBrightness(toInt(brightness.percent)) : null
  return {
    available: available,
    percent: percent,
    monitor: brightness.monitor ? String(brightness.monitor) : null,
    error: brightness.error ? String(brightness.error) : null
  }
}

function minutesOfDay(value) {
  if (typeof value !== "string") return NaN
  var match = /^\s*([0-9]{1,2}):([0-9]{2})\s*$/.exec(value)
  if (!match) return NaN
  var hour = Number(match[1])
  var minute = Number(match[2])
  if (hour > 23 || minute > 59) return NaN
  return hour * 60 + minute
}

// Python-style modulo: the result always carries the sign of the divisor, so
// elapsed distances on the 24-hour clock stay comparable across midnight.
function mod(a, n) {
  return ((a % n) + n) % n
}

// Circular 24-hour clock, mirroring schedule_utils.schedule_period():
// night wins when the distance since night_time is shorter than the distance
// since day_time.
function period(schedule, now) {
  var night = schedule && minutesOfDay(schedule.night_time)
  var day = schedule && minutesOfDay(schedule.day_time)
  if (night === null || day === null || isNaN(night) || isNaN(day)) return "night"
  var current = minutesOfDay(nowTime(now))
  if (isNaN(current)) current = minutesOfDay(nowFallback())
  if (isNaN(current)) return "night"
  return mod(current - night, 1440) < mod(current - day, 1440) ? "night" : "day"
}

function nowTime(now) {
  if (now instanceof Date) {
    return twoDigits(now.getHours()) + ":" + twoDigits(now.getMinutes())
  }
  if (typeof now === "string") return now
  return ""
}

function nowFallback() {
  var date = new Date()
  return twoDigits(date.getHours()) + ":" + twoDigits(date.getMinutes())
}

function twoDigits(value) {
  return String(value).padStart(2, "0")
}

function parseStatus(raw) {
  var input = null
  if (typeof raw === "string") {
    try {
      input = JSON.parse(raw)
    } catch (e) {
      input = null
    }
  } else if (raw && typeof raw === "object") {
    input = raw
  }
  var status = input && typeof input === "object" ? input : {}

  var brightness = parseBrightness(status.brightness)
  var nightlight = parseNightlight(status.nightlight)
  var schedule = parseSchedule(status.schedule)
  if (!schedule.period || typeof schedule.period !== "string") {
    schedule.period = period(schedule)
  }
  var plugin = status.plugin && typeof status.plugin === "object" ? status.plugin : {}
  return {
    plugin: {
      id: plugin.id ? String(plugin.id) : null,
      root: plugin.root ? String(plugin.root) : null
    },
    brightness: brightness,
    nightlight: nightlight,
    schedule: schedule
  }
}

function copyValue(value) {
  if (value === null || typeof value !== "object") return value
  if (Array.isArray(value)) return value.map(copyValue)
  var copy = {}
  for (var key in value) {
    if (Object.prototype.hasOwnProperty.call(value, key)) copy[key] = copyValue(value[key])
  }
  return copy
}

function copyModel(model) {
  return copyValue(model)
}

// Pure latest-wins queue: the first value becomes active immediately; any
// value pushed while one is active replaces the single pending slot, so only
// the newest requested value is applied after the active operation completes.
function createQueue() {
  return { active: null, pending: null }
}

function pushLatest(queue, value) {
  var next = copyQueue(queue)
  if (next.active === null) {
    next.active = value
  } else {
    next.pending = value
  }
  return next
}

function completeQueue(queue) {
  var next = copyQueue(queue)
  if (next.pending !== null) {
    next.active = next.pending
    next.pending = null
  } else {
    next.active = null
  }
  return next
}

function copyQueue(queue) {
  return {
    active: queue && queue.active !== undefined ? queue.active : null,
    pending: queue && queue.pending !== undefined ? queue.pending : null
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    IDENTITY_TEMPERATURE: IDENTITY_TEMPERATURE,
    RANGES: RANGES,
    clamp: clamp,
    clampBrightness: clampBrightness,
    clampTemperature: clampTemperature,
    clampGamma: clampGamma,
    parseStatus: parseStatus,
    copyModel: copyModel,
    period: period,
    createQueue: createQueue,
    pushLatest: pushLatest,
    completeQueue: completeQueue
  }
}
