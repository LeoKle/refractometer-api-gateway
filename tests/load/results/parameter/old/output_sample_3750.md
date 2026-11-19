█ THRESHOLDS 

    http_req_duration
    ✓ 'p(95)<500' p(95)=4.07ms
    ✓ 'p(99)<1000' p(99)=10.84ms

    http_req_failed
    ✗ 'rate<0.01' rate=1.00%


  █ TOTAL RESULTS 

    checks_total.......: 125599 313.994848/s
    checks_succeeded...: 98.99% 124335 out of 125599
    checks_failed......: 1.00%  1264 out of 125599

    ✗ POST status 200
      ↳  98% — ✓ 124335 / ✗ 1264

    HTTP
    http_req_duration..............: avg=3.05ms med=2.71ms p(95)=4.07ms p(99)=10.84ms max=139.28ms
      { expected_response:true }...: avg=3.08ms med=2.72ms p(95)=4.08ms p(99)=11.01ms max=139.28ms
    http_req_failed................: 1.00%  1264 out of 125599
    http_reqs......................: 125599 313.994848/s

    EXECUTION
    iteration_duration.............: avg=10.43s med=10.14s p(95)=14.72s p(99)=29.77s  max=44.99s  
    iterations.....................: 125067 312.66486/s
    vus............................: 4      min=4              max=3750
    vus_max........................: 3750   min=3750           max=3750

    NETWORK
    data_received..................: 16 MB  40 kB/s
    data_sent......................: 33 MB  83 kB/s




running (6m40.0s), 0000/3750 VUs, 125067 complete and 589 interrupted iterations
users ✓ [======================================] 0000/3750 VUs  6m30s
ERRO[0400] thresholds on metrics 'http_req_failed' have been crossed 