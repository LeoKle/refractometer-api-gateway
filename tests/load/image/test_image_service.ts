
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

export const between = (lo: number, hi: number) => lo + Math.random() * (hi - lo);

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const VUS = Number(__ENV.VUS || 100);

// const PAYLOAD_FILE = __ENV.PAYLOAD_FILE || './payload.json';
// const body = new SharedArray('image-payload', () => [
//   open(PAYLOAD_FILE),
// ])[0];

const PAYLOAD_FILE = __ENV.PAYLOAD_FILE || './payload.bin';
const SHAPE = __ENV.SHAPE || '2556,2440';
const DTYPE = __ENV.DTYPE || 'float32';
const body = open(PAYLOAD_FILE, 'b');

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
};

export default function () {
  if (__ITER === 0) sleep(between(0, 5)); // spread out VUs that start in the same tick

  // const response = http.post(
  //     `${BASE_URL}/api/image`,
  //     body,
  //     {
  //       headers: { 'Content-Type': 'application/json' },
  //       tags: { endpoint: 'POST /api/image' },
  //     },
  //   );

  const response = http.post(`${BASE_URL}/api/v2/image`, body, {
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Image-Shape': SHAPE,
      'X-Image-Dtype': DTYPE,
    },
    tags: { endpoint: 'POST /api/v2/image' },
  });


  check(response, {"status 201": (r) => r.status == 201})

  sleep(between(5, 15));
}