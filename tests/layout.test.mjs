import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const qml = fs.readFileSync(new URL('../Panel.qml', import.meta.url), 'utf8');
const schedule = qml.slice(qml.indexOf('id: scheduleColumn'));

test('schedule editor uses native vertically centered fields', () => {
  assert.equal((schedule.match(/\bTextField\s*\{/g) || []).length, 2);
  assert.equal((schedule.match(/\bNumberField\s*\{/g) || []).length, 1);
  assert.equal((schedule.match(/\bTextInput\s*\{/g) || []).length, 0);
});

test('schedule controls share full width and the save label is centered', () => {
  assert.match(schedule, /id:\s*startEditor[\s\S]*?width:\s*parent\.width/);
  assert.match(schedule, /id:\s*endEditor[\s\S]*?width:\s*parent\.width/);
  assert.match(schedule, /id:\s*scheduleTemperatureEditor[\s\S]*?fieldWidth:\s*parent\.width/);
  assert.match(schedule, /text:\s*Model\.copy\.save[\s\S]*?width:\s*parent\.width[\s\S]*?leftAlign:\s*false/);
});
