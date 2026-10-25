import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const VUS = Number(__ENV.VUS || 100);
const users = new SharedArray('users', () => JSON.parse(open(__ENV.USERS || 'users.json')));

export const options = {
  scenarios: {
    users: {
      executor: 'ramping-vus',
      stages: [
        { duration: __ENV.RAMP_UP || '60s', target: VUS },
        { duration: __ENV.DURATION || '5m', target: VUS },
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


const between = (lo: number, hi: number) => lo + Math.random() * (hi - lo);

export default function () {
  const user = users[(__VU - 1) % users.length];
  if (__ITER === 0) sleep(between(0, 5)); // spread out VUs that start in the same tick

  http.get(`${BASE_URL}/health`);

  sleep(between(5, 15));
}