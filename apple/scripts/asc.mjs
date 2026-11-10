#!/usr/bin/env node
// App Store Connect API helper for the Fantasy Edge visionOS app, modelled on hinge-pop's scripts/asc.mjs.
// No dependencies: Node's crypto signs the ES256 JWT. Reads apple/.env.testflight
// (TEAM_ID, ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH). Never prints the key or the token.
//
//   node apple/scripts/asc.mjs whoami          check the key works and list the apps it can see
//   node apple/scripts/asc.mjs bundle          find (or register) com.mutaaf.fantasyedge
//   node apple/scripts/asc.mjs signing         create/install an Apple Distribution cert + the App Store profile
//                                              (App Manager keys cannot use Xcode cloud signing)
//   node apple/scripts/asc.mjs notes [version] print the TestFlight "What to Test" text built from WhatsNew.json
//   node apple/scripts/asc.mjs ship <build>    wait for processing, set What to Test, put the build in the internal group
//   node apple/scripts/asc.mjs crew            make sure every team member is in the internal group
//   node apple/scripts/asc.mjs status [build]  processing state of a build (or the latest five)
//   node apple/scripts/asc.mjs call GET <path> debug passthrough (prints JSON)
//
// INTERNAL ONLY. There is deliberately no external group, no Beta App Review and no App Review
// submission here: those put the app in front of people outside the team and need the user's say-so.
import { createSign, createPrivateKey } from "node:crypto";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), ".."); // apple/
const BUNDLE = "com.mutaaf.fantasyedge";
const APP_ID = "6833213130"; // "Fantasy Edge: Game Day" (the plain name was taken; the in-app name stays Fantasy Edge)
const PROFILE = "Fantasy Edge App Store";
const INTERNAL = "Fantasy Edge Crew";
const API = "https://api.appstoreconnect.apple.com";

function env() {
  const f = join(ROOT, ".env.testflight");
  const out = { ...process.env };
  if (existsSync(f)) for (const line of readFileSync(f, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z_]+)=(.*)$/);
    if (m) out[m[1]] = m[2].trim().replace(/^["']|["']$/g, "").replace(/^\$HOME|^~/, process.env.HOME);
  }
  for (const k of ["ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH"]) if (!out[k]) throw new Error(`Missing ${k} in apple/.env.testflight (see AGENTS.md, TestFlight)`);
  return out;
}

const b64u = (b) => Buffer.from(b).toString("base64url");
let cached;
function token() {
  const now = Math.floor(Date.now() / 1000);
  if (cached && cached.exp - 60 > now) return cached.jwt;
  const e = env();
  const head = b64u(JSON.stringify({ alg: "ES256", kid: e.ASC_KEY_ID, typ: "JWT" }));
  const body = b64u(JSON.stringify({ iss: e.ASC_ISSUER_ID, iat: now, exp: now + 1200, aud: "appstoreconnect-v1" }));
  const sig = createSign("SHA256").update(`${head}.${body}`).sign({ key: createPrivateKey(readFileSync(e.ASC_KEY_PATH)), dsaEncoding: "ieee-p1363" });
  cached = { jwt: `${head}.${body}.${b64u(sig)}`, exp: now + 1200 };
  return cached.jwt;
}

async function api(method, path, body) {
  const r = await fetch(API + path, {
    method, headers: { authorization: `Bearer ${token()}`, "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  const json = text ? JSON.parse(text) : {};
  if (!r.ok) {
    const why = (json.errors ?? []).map((x) => {
      const inner = Object.values(x.meta?.associatedErrors ?? {}).flat().map((e) => e.detail ?? e.title).join(" | ");
      return `${x.title}: ${x.detail}${inner ? ` [${inner}]` : ""}`;
    }).join("; ") || text;
    const err = new Error(`${method} ${path} → ${r.status} ${why}`);
    err.status = r.status; err.body = json;
    throw err;
  }
  return json;
}

async function app() {
  const r = await api("GET", `/v1/apps/${APP_ID}`);
  if (r.data.attributes.bundleId !== BUNDLE) throw new Error(`App ${APP_ID} is ${r.data.attributes.bundleId}, expected ${BUNDLE}`);
  return r.data;
}

/** VERSION in generate_project.py: the marketing version and the WhatsNew.json key. */
export function version() {
  return readFileSync(join(ROOT, "generate_project.py"), "utf8").match(/^VERSION\s*=\s*"([^"]+)"/m)[1];
}

/** WhatsNew.json's entry for the version → TestFlight "What to Test": headline, subhead, the full notes. ≤ 4000 chars. */
export function notesFor(v = version()) {
  const doc = JSON.parse(readFileSync(join(ROOT, "FantasyEdge", "WhatsNew.json"), "utf8"));
  const rel = (doc.releases ?? []).find((r) => r.version === v);
  if (!rel) throw new Error(`apple/FantasyEdge/WhatsNew.json has no entry for ${v}. Add it before shipping (AGENTS.md, What's new).`);
  if (!rel.notes?.length) throw new Error(`WhatsNew.json ${v} has no notes`);
  const text = [`${rel.headline}`, rel.subhead, "", ...rel.notes.map((n) => `• ${n}`)].filter((l) => l != null).join("\n");
  // TestFlight rejects emoji in whatsNew ("invalid characters").
  const plain = text.replace(/[\p{Extended_Pictographic}\u{FE0F}\u{200D}\u{1F3FB}-\u{1F3FF}]/gu, "").replace(/[ \t]+$/gm, "").trim();
  if (plain.length > 4000) throw new Error(`What to Test for ${v} is ${plain.length} characters; TestFlight allows 4000.`);
  return plain;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** The internal group, created if missing. Access to all builds, so every later build reaches it on its own. */
async function group(appId) {
  const r = await api("GET", `/v1/betaGroups?filter[app]=${appId}&filter[name]=${encodeURIComponent(INTERNAL)}`);
  if (r.data.length) return r.data[0];
  const c = await api("POST", "/v1/betaGroups", { data: { type: "betaGroups",
    attributes: { name: INTERNAL, isInternalGroup: true, hasAccessToAllBuilds: true },
    relationships: { app: { data: { type: "apps", id: appId } } } } });
  console.log(`✓ created internal group “${INTERNAL}”`);
  return c.data;
}

async function findBuild(appId, buildNumber) {
  const r = await api("GET", `/v1/builds?filter[app]=${appId}&filter[version]=${buildNumber}&limit=1`);
  return r.data[0];
}

async function ship(buildNumber) {
  if (!buildNumber) throw new Error("usage: asc.mjs ship <build number>");
  const notes = notesFor();
  const a = await app();
  let b;
  for (let i = 0; i < 90; i++) { // up to ~45 minutes: an upload takes a while to appear, then to process
    b = await findBuild(a.id, buildNumber);
    const state = b?.attributes.processingState;
    if (state === "VALID") break;
    if (state === "FAILED" || state === "INVALID") throw new Error(`Build ${buildNumber} processing ${state}`);
    process.stdout.write(i ? "." : `… waiting for build ${buildNumber} to finish processing `);
    await sleep(30000);
  }
  if (b?.attributes.processingState !== "VALID") throw new Error(`Build ${buildNumber} still processing; rerun: node apple/scripts/asc.mjs ship ${buildNumber}`);
  console.log(`\n✓ build ${buildNumber} processed`);

  // The Info.plist says ITSAppUsesNonExemptEncryption = NO; this only matters for a build made before that key existed.
  if (b.attributes.usesNonExemptEncryption == null) {
    await api("PATCH", `/v1/builds/${b.id}`, { data: { type: "builds", id: b.id, attributes: { usesNonExemptEncryption: false } } });
    console.log("✓ export compliance: no non-exempt encryption");
  }

  const locs = await api("GET", `/v1/builds/${b.id}/betaBuildLocalizations`);
  const en = locs.data.find((l) => l.attributes.locale === "en-US");
  if (en) await api("PATCH", `/v1/betaBuildLocalizations/${en.id}`, { data: { type: "betaBuildLocalizations", id: en.id, attributes: { whatsNew: notes } } });
  else await api("POST", "/v1/betaBuildLocalizations", { data: { type: "betaBuildLocalizations", attributes: { locale: "en-US", whatsNew: notes }, relationships: { build: { data: { type: "builds", id: b.id } } } } });
  console.log("✓ What to Test set from WhatsNew.json");

  const g = await group(a.id);
  // hasAccessToAllBuilds covers it, but adding explicitly is harmless and survives someone unticking that box.
  try { await api("POST", `/v1/betaGroups/${g.id}/relationships/builds`, { data: [{ type: "builds", id: b.id }] }); }
  catch (e) { if (e.status !== 409 && e.status !== 422) throw e; }
  console.log(`✓ build ${buildNumber} in “${INTERNAL}”`);
  await crew();
}

/** Every App Store Connect team member into the internal group (internal testers must be team users). */
async function crew() {
  const a = await app();
  const g = await group(a.id);
  const users = (await api("GET", "/v1/users?limit=100")).data;
  const have = new Set((await api("GET", `/v1/betaGroups/${g.id}/betaTesters?limit=200`)).data.map((t) => (t.attributes.email || "").toLowerCase()));
  let added = 0;
  for (const u of users) {
    const email = (u.attributes.username || "").toLowerCase();
    if (!email || have.has(email)) continue;
    try {
      await api("POST", "/v1/betaTesters", { data: { type: "betaTesters", attributes: { email, firstName: u.attributes.firstName, lastName: u.attributes.lastName },
        relationships: { betaGroups: { data: [{ type: "betaGroups", id: g.id }] } } } });
      added++;
    } catch (e) { if (e.status !== 409) throw e; }
  }
  console.log(`✓ “${INTERNAL}”: ${have.size + added} tester(s) (${added} added); each gets a TestFlight invite email`);
}

async function status(buildNumber) {
  const a = await app();
  const r = buildNumber
    ? { data: [await findBuild(a.id, buildNumber)].filter(Boolean) }
    : await api("GET", `/v1/builds?filter[app]=${a.id}&sort=-uploadedDate&limit=5`);
  if (!r.data.length) return console.log(buildNumber ? `No build ${buildNumber} yet (uploads take a few minutes to appear)` : "No builds yet");
  for (const b of r.data) console.log(`${b.attributes.version}  ${b.attributes.processingState}  uploaded ${b.attributes.uploadedDate}  expired=${b.attributes.expired}`);
}

async function bundleId() {
  const r = await api("GET", `/v1/bundleIds?filter[identifier]=${BUNDLE}`);
  const hit = r.data.find((x) => x.attributes.identifier === BUNDLE);
  if (hit) { console.log(`✓ bundle id ${BUNDLE} registered (${hit.attributes.platform})`); return hit; }
  const c = (await api("POST", "/v1/bundleIds", { data: { type: "bundleIds", attributes: { identifier: BUNDLE, name: "Fantasy Edge", platform: "UNIVERSAL" } } })).data;
  console.log(`✓ registered bundle id ${BUNDLE}`);
  return c;
}

async function whoami() {
  const r = await api("GET", "/v1/apps?limit=50&fields[apps]=name,bundleId");
  console.log(`✓ key works: ${r.data.length} app(s) visible`);
  for (const x of r.data) console.log(`  ${x.attributes.bundleId}  ${x.attributes.name}`);
}

/** Distribution signing without cloud signing: the shared Apple Distribution certificate from our own CSR
 *  (~/.appstoreconnect/signing, the same one hinge-pop and the other apps use), plus a freshly made App Store
 *  profile for the bundle id, both installed locally. */
async function signing() {
  const { execFileSync } = await import("node:child_process");
  const { writeFileSync, mkdirSync, readdirSync, unlinkSync } = await import("node:fs");
  const dir = join(process.env.HOME, ".appstoreconnect", "signing");
  if (!existsSync(join(dir, "dist.key")) || !existsSync(join(dir, "dist.csr")))
    throw new Error(`No signing key/CSR in ${dir}. Make one: openssl req -new -newkey rsa:2048 -nodes -keyout dist.key -out dist.csr -subj "/CN=Apple Distribution"`);
  const certs = await api("GET", "/v1/certificates?filter[certificateType]=DISTRIBUTION,IOS_DISTRIBUTION&limit=50");
  const known = existsSync(join(dir, "dist.cer.id")) ? readFileSync(join(dir, "dist.cer.id"), "utf8").trim() : "";
  let cert = known && certs.data.find((c) => c.id === known);
  if (!cert) {
    cert = (await api("POST", "/v1/certificates", { data: { type: "certificates", attributes: { certificateType: "DISTRIBUTION", csrContent: readFileSync(join(dir, "dist.csr"), "utf8") } } })).data;
    writeFileSync(join(dir, "dist.cer.id"), cert.id);
    console.log("✓ created Apple Distribution certificate");
  }
  writeFileSync(join(dir, "dist.cer"), Buffer.from(cert.attributes.certificateContent, "base64"));
  const p = randomPass();
  execFileSync("sh", ["-c", `openssl x509 -inform der -in "${dir}/dist.cer" -out "${dir}/dist.pem" && { openssl pkcs12 -export -legacy -inkey "${dir}/dist.key" -in "${dir}/dist.pem" -out "${dir}/fe.p12" -passout env:P12 2>/dev/null || openssl pkcs12 -export -inkey "${dir}/dist.key" -in "${dir}/dist.pem" -out "${dir}/fe.p12" -passout env:P12; } && { security import "${dir}/fe.p12" -k ~/Library/Keychains/login.keychain-db -P "$P12" -T /usr/bin/codesign >/dev/null 2>&1 || true; }; rm -f "${dir}/fe.p12"`],
    { env: { ...process.env, P12: p } });
  console.log("✓ Apple Distribution identity in the login keychain");

  const bid = await bundleId();
  const pdir = join(process.env.HOME, "Library", "Developer", "Xcode", "UserData", "Provisioning Profiles");
  mkdirSync(pdir, { recursive: true });
  const profs = await api("GET", `/v1/profiles?filter[name]=${encodeURIComponent(PROFILE)}&limit=10`);
  for (const x of profs.data) await api("DELETE", `/v1/profiles/${x.id}`); // re-create so it always holds the current cert
  for (const f of readdirSync(pdir).filter((f) => f.endsWith(".mobileprovision"))) {
    try {
      const xml = execFileSync("security", ["cms", "-D", "-i", join(pdir, f)], { stdio: ["ignore", "pipe", "ignore"] }).toString();
      if (xml.match(/<key>Name<\/key>\s*<string>([^<]*)<\/string>/)?.[1] === PROFILE) unlinkSync(join(pdir, f));
    } catch {}
  }
  // visionOS has no profile type of its own: an App Store profile on a UNIVERSAL bundle id is IOS_APP_STORE.
  const prof = (await api("POST", "/v1/profiles", { data: { type: "profiles", attributes: { name: PROFILE, profileType: "IOS_APP_STORE" }, relationships: {
    bundleId: { data: { type: "bundleIds", id: bid.id } }, certificates: { data: [{ type: "certificates", id: cert.id }] } } } })).data;
  writeFileSync(join(pdir, `${prof.attributes.uuid}.mobileprovision`), Buffer.from(prof.attributes.profileContent, "base64"));
  console.log(`✓ installed profile “${PROFILE}” (${prof.attributes.uuid})`);
}

function randomPass() { return Buffer.from(globalThis.crypto.getRandomValues(new Uint8Array(18))).toString("base64url"); }

async function call(method, path, body) { console.log(JSON.stringify(await api(method, path, body ? JSON.parse(body) : undefined), null, 2)); }

const [cmd, arg] = process.argv.slice(2);
const run = { whoami, bundle: bundleId, signing, crew, status: () => status(arg), ship: () => ship(arg),
  notes: () => console.log(notesFor(arg)), call: () => call(arg, process.argv[4], process.argv[5]) }[cmd];
if (!run) { console.log("usage: asc.mjs whoami | bundle | signing | notes [version] | ship <build> | crew | status [build] | call <METHOD> <path> [json]"); process.exit(2); }
Promise.resolve().then(run).catch((e) => { console.error("✗ " + e.message); process.exit(1); });
