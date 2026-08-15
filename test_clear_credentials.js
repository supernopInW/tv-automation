const fs = require('fs');
const assert = require('assert');

const source = fs.readFileSync('static/app.js', 'utf8');
const sourceStart = source.indexOf('function clearTandVCredentials()');
const sourceEnd = source.indexOf('\n}\n\ndocument.addEventListener("DOMContentLoaded"', sourceStart) + 2;
if (sourceStart < 0 || sourceEnd <= sourceStart) {
  throw new Error('credential cleanup functions not found');
}

// Evaluate only the two pure cleanup functions from the production bundle.
const cleanupSource = source.slice(sourceStart, sourceEnd);
const realConsole = console;
global.console = { warn: () => {}, log: realConsole.log.bind(realConsole) };
eval(cleanupSource);

function makeBrowserState() {
  const local = new Map([['tv_username', 'user']]);
  const session = new Map([
    ['tv_username', 'session-user'],
    ['tv_password', 'password-value'],
  ]);
  const fields = {
    username: { value: 'user' },
    password: { value: 'password-value' },
  };
  let localRemovals = 0;
  let sessionRemovals = 0;

  global.localStorage = {
    removeItem: (key) => {
      localRemovals += 1;
      local.delete(key);
    },
  };
  global.sessionStorage = {
    removeItem: (key) => {
      sessionRemovals += 1;
      session.delete(key);
    },
  };
  global.document = {
    getElementById: (id) => fields[id],
  };

  return {
    local,
    session,
    fields,
    removalCounts: () => ({ local: localRemovals, session: sessionRemovals }),
  };
}

function assertCredentialsCleared(state, message) {
  assert.strictEqual(state.local.has('tv_username'), false, `${message}: local username`);
  assert.strictEqual(state.session.has('tv_username'), false, `${message}: session username`);
  assert.strictEqual(state.session.has('tv_password'), false, `${message}: session password`);
  assert.strictEqual(state.fields.username.value, '', `${message}: username input`);
  assert.strictEqual(state.fields.password.value, '', `${message}: password input`);
}

// Direct helper test: both browser storage locations and visible fields clear.
{
  const state = makeBrowserState();
  const clear = createRunCredentialCleanup();
  clear();
  clear(); // idempotency: the second signal must not repeat cleanup.
  assertCredentialsCleared(state, 'direct cleanup');
  assert.deepStrictEqual(state.removalCounts(), { local: 1, session: 2 });
}

// Simulate Playwright SSE success: reader returns done=true.
{
  const state = makeBrowserState();
  const clearRunCredentials = createRunCredentialCleanup();
  const readerResult = { done: true, value: undefined };
  if (readerResult.done) clearRunCredentials();
  assertCredentialsCleared(state, 'Playwright success completion');
}

// Simulate Playwright SSE failure: reader rejects while processing the run.
{
  const state = makeBrowserState();
  const clearRunCredentials = createRunCredentialCleanup();
  Promise.reject(new Error('simulated stream failure')).catch(() => clearRunCredentials());
  returnPromiseDrain().then(() => {
    assertCredentialsCleared(state, 'Playwright error completion');
    assertLifecycleWiring();
    console.log('PASS credential cleanup unit tests: direct, success, error, idempotency');
  });
}

function returnPromiseDrain() {
  return new Promise((resolve) => setImmediate(resolve));
}

function assertLifecycleWiring() {
  assert.match(
    source,
    /if \(done\) \{[\s\S]*?clearRunCredentials\(\);/,
    'success path must clear credentials when the SSE reader is done',
  );
  assert.match(
    source,
    /reader\.read\(\)\.then\([\s\S]*?\.catch\(err => \{[\s\S]*?clearRunCredentials\(\);/,
    'stream error path must clear credentials',
  );
  assert.match(
    source,
    /fetch\('\/api\/run'[\s\S]*?\.catch\(err => \{[\s\S]*?clearRunCredentials\(\);/,
    'request error path must clear credentials',
  );
}
