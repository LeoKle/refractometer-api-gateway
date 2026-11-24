// Self-issued access tokens for load testing through the API gateway.
//
// Mirrors src/auth/tokens.py (JsonWebToken): the gateway requires
// iss, sub, aud, iat, exp, jti, fid and token_type="access", verifies the
// signature with JWT_PUBLIC_KEY and then looks `sub` up in its user database
// (the user must exist and have access=True).
//
// Supported algorithms match the gateway settings: EdDSA (Ed25519, prod) and
// HS256 (dev/test only). k6's WebCrypto has no Ed25519, so EdDSA signing uses
// @noble/ed25519 (run `npm install` in tests/load first) with k6's SHA-512.
//
// Must be imported from a script's init context (it reads env/files there).

import encoding from 'k6/encoding';
import k6crypto from 'k6/crypto';
import { SharedArray } from 'k6/data';
import * as ed from '../node_modules/@noble/ed25519/index.js';

ed.hashes.sha512 = (msg: Uint8Array) =>
    new Uint8Array(k6crypto.sha512(msg.slice().buffer, 'binary') as ArrayBuffer);

type Algorithm = 'EdDSA' | 'HS256';

const ALGORITHM = (__ENV.JWT_ALGORITHM || 'EdDSA') as Algorithm;
if (ALGORITHM !== 'EdDSA' && ALGORITHM !== 'HS256') {
    throw new Error(`JWT_ALGORITHM must be EdDSA or HS256, got "${ALGORITHM}"`);
}

const ISSUER = required('JWT_ISSUER');
const AUDIENCE = required('JWT_AUDIENCE');
// Lifetime of each self-issued token. Longer than the gateway's default
// 10 min so a normal run needs no re-issue; tokens are re-issued per VU
// shortly before they expire either way.
const TTL_SECONDS = Number(__ENV.JWT_TTL || 900);
const RENEW_BEFORE_SECONDS = 30;

export const ACCESS_COOKIE = __ENV.COOKIE_NAME_ACCESS || 'refractometer_access';

// k6 resolves open() relative to the calling module (this file), so map
// relative paths onto tests/load, where the tests are run from.
const fromLoadDir = (path: string) => (/^([a-zA-Z]:)?[\\/]/.test(path) ? path : `../${path}`);

// Private key: JWT_PRIVATE_KEY (inline PEM, literal "\n" allowed, or the
// shared secret for HS256) or JWT_PRIVATE_KEY_FILE (path to the PEM).
const RAW_KEY = __ENV.JWT_PRIVATE_KEY_FILE ? open(fromLoadDir(__ENV.JWT_PRIVATE_KEY_FILE)) : __ENV.JWT_PRIVATE_KEY;
if (!RAW_KEY) throw new Error('set JWT_PRIVATE_KEY or JWT_PRIVATE_KEY_FILE');

const ED25519_SEED = ALGORITHM === 'EdDSA' ? ed25519SeedFromPem(RAW_KEY) : null;
const HS256_SECRET = ALGORITHM === 'HS256' ? RAW_KEY : null;

// Users the tokens are issued for (`sub`): SUB gives a single user id;
// otherwise USERS (default users.json) is a JSON array of user ids or of user
// objects ({ id, access, ... }). Users with `access: false` are skipped, the
// gateway would answer 403 for them.
// Relative paths (USERS, JWT_PRIVATE_KEY_FILE) are resolved from tests/load.
type UserEntry = string | { id: string; access?: boolean };

const USER_IDS = new SharedArray('jwt-users', () => {
    if (__ENV.SUB) return [__ENV.SUB];

    const file = __ENV.USERS || 'users.json';
    const users = JSON.parse(open(fromLoadDir(file))) as UserEntry[];
    const ids = users
        .filter((u) => typeof u === 'string' || u.access !== false)
        .map((u) => (typeof u === 'string' ? u : u.id));
    if (ids.length === 0 || ids.some((id) => !id)) throw new Error(`users file ${file} has no usable user ids`);
    return ids;
});

/** User id for this VU: VUs are spread round-robin over the user list. */
export const userIdForVu = (vu: number = __VU): string => USER_IDS[(Math.max(vu, 1) - 1) % USER_IDS.length];

function required(name: string): string {
    const value = __ENV[name];
    if (!value) throw new Error(`set ${name} (must match the gateway's ${name})`);
    return value;
}

function ed25519SeedFromPem(raw: string): Uint8Array {
    // Accept the key as stored in a .env too: surrounding quotes, literal "\n".
    const pem = raw.trim().replace(/^(['"])([\s\S]*)\1$/, '$2').replace(/\\n/g, '\n');
    const labels = pem.match(/-----BEGIN ([A-Z0-9 ]+)-----/g) || [];
    const label = labels.length ? labels[0].slice(11, -5) : null;
    const fail = (why: string) => {
        throw new Error(`JWT private key: ${why}. Expected an Ed25519 key in PKCS#8 PEM ("-----BEGIN PRIVATE KEY-----"), the format the gateway's JWT_PRIVATE_KEY uses.`);
    };

    if (!label) fail('no "-----BEGIN ...-----" line found');
    if (labels.length > 1) fail(`found ${labels.length} PEM blocks (${labels.join(', ')}), keep only the private key`);
    if (label === 'OPENSSH PRIVATE KEY') fail('this is an OpenSSH key (ssh-keygen), not a PKCS#8 PEM');
    if (label === 'ENCRYPTED PRIVATE KEY') fail('the key is password protected, decrypt it with `openssl pkey -in <file> -out <new file>`');
    if (label === 'PUBLIC KEY') fail('this is the public key, the test needs the private key');
    if (label !== 'PRIVATE KEY') fail(`found a "${label}" PEM (wrong key type or format)`);

    const b64 = pem.replace(/-----(BEGIN|END) [A-Z0-9 ]+-----/g, '').replace(/\s+/g, '');
    let der: Uint8Array;
    try {
        der = new Uint8Array(encoding.b64decode(b64));
    } catch (_) {
        return fail('the PEM body is not valid base64');
    }

    // PKCS#8 for Ed25519 (RFC 8410): ... OID 1.3.101.112, then the private key
    // as OCTET STRING { OCTET STRING (32-byte seed) }. Covers v1 and v2 (with
    // the public key appended).
    const oid = [0x06, 0x03, 0x2b, 0x65, 0x70];
    const key = [0x04, 0x22, 0x04, 0x20];
    for (let i = 0; i + oid.length + key.length + 32 <= der.length; i++) {
        if (oid.every((b, j) => der[i + j] === b)) {
            const k = i + oid.length;
            if (!key.every((b, j) => der[k + j] === b)) break;
            return der.slice(k + key.length, k + key.length + 32);
        }
    }
    return fail(`the PKCS#8 key (${der.length} bytes) is not an Ed25519 key, e.g. RSA or EC`);
}

function ascii(s: string): Uint8Array {
    const bytes = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) bytes[i] = s.charCodeAt(i);
    return bytes;
}

function uuid4(): string {
    const b = new Uint8Array(k6crypto.randomBytes(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const hex = Array.from(b, (x) => (x < 16 ? '0' : '') + x.toString(16)).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function sign(signingInput: string): string {
    if (ED25519_SEED) {
        const signature = ed.sign(ascii(signingInput), ED25519_SEED);
        return encoding.b64encode(signature.slice().buffer, 'rawurl');
    }
    return k6crypto.hmac('sha256', HS256_SECRET as string, signingInput, 'base64rawurl') as string;
}

export interface AccessToken {
    token: string;
    exp: number;
}

/** Sign an access token with the same claims the gateway issues on login. */
export function issueAccessToken(sub: string, fid: string = uuid4()): AccessToken {
    const iat = Math.floor(Date.now() / 1000);
    const exp = iat + TTL_SECONDS;
    const header = { alg: ALGORITHM, typ: 'JWT' };
    const claims = { iss: ISSUER, sub, aud: AUDIENCE, iat, exp, jti: uuid4(), fid, token_type: 'access' };
    const input = `${encoding.b64encode(JSON.stringify(header), 'rawurl')}.${encoding.b64encode(JSON.stringify(claims), 'rawurl')}`;
    return { token: `${input}.${sign(input)}`, exp };
}

// One session per VU: a token for the VU's user, re-issued within the same
// session family (fid) shortly before it expires, like a browser refreshing.
let current: AccessToken | null = null;
let familyId: string | null = null;

export function vuAccessToken(): string {
    const now = Math.floor(Date.now() / 1000);
    if (!current || current.exp - now <= RENEW_BEFORE_SECONDS) {
        familyId = familyId || uuid4();
        current = issueAccessToken(userIdForVu(), familyId);
    }
    return current.token;
}

/** Request headers that authenticate as `token` (the gateway reads a cookie). */
export const authHeaders = (token: string): Record<string, string> => ({
    Cookie: `${ACCESS_COOKIE}=${token}`,
});