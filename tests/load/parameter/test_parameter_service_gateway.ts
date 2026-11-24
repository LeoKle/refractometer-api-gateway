import http from 'k6/http';
import { check, fail, group, sleep } from 'k6';
import { authHeaders, issueAccessToken, userIdForVu, vuAccessToken } from '../auth/jwt.ts';

// Copy of test_parameter_service.ts that goes through the API gateway, which
// requires a signed access token on every request. Tokens are self-issued
// (see ../auth/jwt.ts for the JWT_* / USERS / SUB variables). Differences to
// the direct test: auth cookie on every request, and POST /api/sample
// returns 201 from the gateway (the parameter service returns 200).

export const between = (lo: number, hi: number) => lo + Math.random() * (hi - lo);
const pick = <T>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const VUS = Number(__ENV.VUS || 100);
// Likelihood (0..1) that a session creates a sample or spectrum instead of just viewing.
const CREATE_RATE = Number(__ENV.CREATE_RATE || 0.2);
const SLEEP_MIN = Number(__ENV.SLEEP_MIN || 5);
const SLEEP_MAX = Number(__ENV.SLEEP_MAX || 15);
// Points per created spectrum (380..780 nm in 1 nm steps by default).
const SPECTRUM_POINTS = Number(__ENV.SPECTRUM_POINTS || 401);
// Samples and spectrums created in setup() for the viewers to open.
const SEED = Number(__ENV.SEED || 20);

export const options = {
  scenarios: {
    users: {
      executor: 'ramping-vus',
      stages: [
        { duration: __ENV.RAMP_UP || '60s', target: VUS },
        { duration: __ENV.DURATION || '5m', target: VUS },
        // { duration: __ENV.DURATION || '5s', target: VUS },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
  },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  setupTimeout: '120s',
};

interface SellmeierCoefficientsDTO {
  B: number[]; // max 3
  C: number[]; // max 3
}

export interface SampleDTO {
  name: string;
  id?: string; // not set on post
  sellmeier_coefficients: SellmeierCoefficientsDTO;
}

export interface SpectrumDTO {
  name: string;
  id?: string;
  wavelengths: number[];
  intensities: number[];
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

// `token` defaults to this VU's token; setup() passes its own.
const tag = (name: string, token: string = vuAccessToken()) => ({
  headers: { ...JSON_HEADERS, ...authHeaders(token) },
  tags: { name },
});

const think = () => sleep(between(SLEEP_MIN, SLEEP_MAX));

function newSample(name: string): SampleDTO {
  return {
    name,
    sellmeier_coefficients: {
      B: [0.6961663, 0.4079426, 0.8974794],
      C: [0.00467914826, 0.0135120631, 97.9340025],
    },
  };
}

function newSpectrum(name: string): SpectrumDTO {
  const wavelengths: number[] = [];
  const intensities: number[] = [];
  for (let i = 0; i < SPECTRUM_POINTS; i++) {
    wavelengths.push(380 + i);
    intensities.push(Math.random());
  }
  return { name, wavelengths, intensities };
}


type SetupData = { sampleIds: string[]; spectrumIds: string[] };

// Runs once before the test: create SEED samples and spectrums for the viewers.
export function setup(): SetupData {
  const sampleIds: string[] = [];
  const spectrumIds: string[] = [];
  const { token } = issueAccessToken(userIdForVu(1));
  for (let i = 0; i < SEED; i++) {
    const sample = http.post(`${BASE_URL}/api/sample`, JSON.stringify(newSample(`k6-seed-sample-${i}`)), tag('setup', token));
    if (sample.status !== 201) fail(`seeding sample failed: ${sample.status} ${sample.body}`);
    sampleIds.push(sample.json('id') as string);

    const spectrum = http.post(`${BASE_URL}/api/spectrum`, JSON.stringify(newSpectrum(`k6-seed-spectrum-${i}`)), tag('setup', token));
    if (spectrum.status !== 201) fail(`seeding spectrum failed: ${spectrum.status} ${spectrum.body}`);
    spectrumIds.push(spectrum.json('id') as string);
  }
  return { sampleIds, spectrumIds };
}

function viewSample(data: SetupData) {
  think();
  const res = http.get(`${BASE_URL}/api/sample/${pick(data.sampleIds)}`, tag('GET /api/sample/{id}'));
  check(res, { 'get sample 200': (r) => r.status === 200 });
}

function viewSpectrum(data: SetupData) {
  think();
  const res = http.get(`${BASE_URL}/api/spectrum/${pick(data.spectrumIds)}`, tag('GET /api/spectrum/{id}'));
  check(res, { 'get spectrum 200': (r) => r.status === 200 });
}

function createSample() {
  think();
  const sample = newSample(`k6-sample-${__VU}-${__ITER}`);
  const created = http.post(`${BASE_URL}/api/sample`, JSON.stringify(sample), tag('POST /api/sample'));
  if (!check(created, { 'create sample 201': (r) => r.status === 201 })) return;
  const id = created.json('id') as string;

  think();
  const res = http.get(`${BASE_URL}/api/sample/${id}`, tag('GET /api/sample/{id}'));
  check(res, {
    'created sample exists': (r) => r.status === 200 && r.json('name') === sample.name,
  });
}

function createSpectrum() {
  think();
  const spectrum = newSpectrum(`k6-spectrum-${__VU}-${__ITER}`);
  const created = http.post(`${BASE_URL}/api/spectrum`, JSON.stringify(spectrum), tag('POST /api/spectrum'));
  if (!check(created, { 'create spectrum 201': (r) => r.status === 201 })) return;
  const id = created.json('id') as string;

  think();
  const res = http.get(`${BASE_URL}/api/spectrum/${id}`, tag('GET /api/spectrum/{id}'));
  check(res, {
    'created spectrum exists': (r) => r.status === 200 && r.json('name') === spectrum.name,
  });
}

export default function (data: SetupData) {
  if (__ITER === 0) sleep(between(0, 5)); // spread out VUs that start in the same tick

  if (Math.random() < CREATE_RATE) {
    if (Math.random() < 0.5) group('create sample', createSample);
    else group('create spectrum', createSpectrum);
  } else {
    group('view', () => {
      viewSample(data);
      viewSpectrum(data);
    });
  }
}