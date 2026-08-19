const fs = require('fs');
const assert = require('assert');

const source = fs.readFileSync('static/app.js', 'utf8');

assert.ok(
  source.includes('function persistTvCredentialsToSession()'),
  'session persist helper must exist',
);
assert.ok(
  source.includes('function loadTvCredentialsFromSession()'),
  'session load helper must exist',
);
assert.ok(
  source.includes("sessionStorage.setItem('tv_username'"),
  'T&V username may live in tab sessionStorage',
);
assert.ok(
  source.includes("sessionStorage.setItem('tv_password'"),
  'T&V password may live in tab sessionStorage',
);
assert.ok(
  !source.includes("localStorage.setItem('tv_username'"),
  'T&V username must not be written to localStorage',
);
assert.ok(
  !source.includes("localStorage.setItem('tv_password'"),
  'T&V password must not be written to localStorage',
);

const runCallStart = source.indexOf("fetch('/api/run'");
assert.ok(runCallStart >= 0, '/api/run call must exist');
const payloadStart = source.lastIndexOf('const payload = {', runCallStart);
assert.ok(payloadStart >= 0, '/api/run payload literal must exist');
const payloadEnd = source.indexOf('};', payloadStart);
const payloadSource = source.slice(payloadStart, payloadEnd);
assert.ok(/\busername\s*:/.test(payloadSource), '/api/run payload must send T&V username from the tab session');
assert.ok(/\bpassword\s*:/.test(payloadSource), '/api/run payload must send T&V password from the tab session');

assert.match(
  source,
  /startBtn\.disabled = !ready/,
  'Start button must stay disabled until T&V credentials are in this tab session',
);

console.log('PASS credential session tests: tab sessionStorage only, payload includes T&V creds, start gating');
