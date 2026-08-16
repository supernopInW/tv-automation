const fs = require('fs');
const assert = require('assert');

// The app no longer handles T&V credentials: the officer logs into T&V
// manually in the Playwright browser and /api/run receives no username or
// password. This suite verifies the one remaining cleanup duty (purging
// legacy Web Storage keys from older versions) and guards the new
// no-credential invariants in static/app.js.
const source = fs.readFileSync('static/app.js', 'utf8');

const sourceStart = source.indexOf('function clearLegacyTvCredentialStorage()');
if (sourceStart < 0) {
  throw new Error('legacy credential storage cleanup function not found');
}
const sourceEnd = source.indexOf('\n}', sourceStart) + 2;
if (sourceEnd <= sourceStart) {
  throw new Error('legacy credential storage cleanup function is malformed');
}

// Evaluate only the pure cleanup function from the production bundle.
const cleanupSource = source.slice(sourceStart, sourceEnd);
const realConsole = console;
global.console = { warn: () => {}, log: realConsole.log.bind(realConsole) };
eval(cleanupSource);

// Legacy keys left behind by older app versions must all be removed.
{
  const local = new Map([['tv_username', 'user']]);
  const session = new Map([
    ['tv_username', 'session-user'],
    ['tv_password', 'password-value'],
  ]);
  global.localStorage = { removeItem: (key) => local.delete(key) };
  global.sessionStorage = { removeItem: (key) => session.delete(key) };

  clearLegacyTvCredentialStorage();

  assert.strictEqual(local.has('tv_username'), false, 'legacy local username must be removed');
  assert.strictEqual(session.has('tv_username'), false, 'legacy session username must be removed');
  assert.strictEqual(session.has('tv_password'), false, 'legacy session password must be removed');
}

// No-credential invariants: the frontend must never read T&V credential
// inputs, persist credentials, or send them to /api/run.
{
  assert.ok(
    !source.includes("getElementById('username')"),
    'frontend must not read a T&V username input',
  );
  assert.ok(
    !source.includes("getElementById('password')"),
    'frontend must not read a T&V password input',
  );
  assert.ok(
    !source.includes("localStorage.setItem('tv_username'"),
    'frontend must not persist a T&V username',
  );
  assert.ok(
    !source.includes("sessionStorage.setItem('tv_password'"),
    'frontend must not persist a T&V password',
  );

  const runCallStart = source.indexOf("fetch('/api/run'");
  assert.ok(runCallStart >= 0, '/api/run call must exist');
  const payloadStart = source.lastIndexOf('const payload = {', runCallStart);
  assert.ok(payloadStart >= 0, '/api/run payload literal must exist');
  const payloadEnd = source.indexOf('};', payloadStart);
  const payloadSource = source.slice(payloadStart, payloadEnd);
  assert.ok(!/\busername\s*:/.test(payloadSource), '/api/run payload must not contain a username field');
  assert.ok(!/\bpassword\s*:/.test(payloadSource), '/api/run payload must not contain a password field');
}

// The user-driven T&V login session flow must be wired in.
{
  assert.ok(source.includes('/api/tv-browser/status'), 'frontend must poll T&V login status');
  assert.ok(source.includes('/api/tv-browser/start'), 'frontend must open the T&V login browser');
  assert.match(
    source,
    /startBtn\.disabled = !tvSessionState\.loggedIn/,
    'Start button must stay disabled until T&V is logged in',
  );
}

console.log('PASS credential cleanup unit tests: legacy purge, no-credential payload, login gating');
