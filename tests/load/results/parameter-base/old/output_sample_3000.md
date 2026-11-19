█ THRESHOLDS 

    http_req_duration
    ✓ 'p(95)<500' p(95)=3.68ms
    ✓ 'p(99)<1000' p(99)=5.1ms

    http_req_failed
    ✓ 'rate<0.01' rate=0.59%


  █ TOTAL RESULTS 

    checks_total.......: 101009 252.546158/s
    checks_succeeded...: 99.40% 100413 out of 101009
    checks_failed......: 0.59%  596 out of 101009

    ✗ POST status 200
      ↳  99% — ✓ 100413 / ✗ 596

    HTTP
    http_req_duration..............: avg=2.8ms  med=2.69ms p(95)=3.68ms p(99)=5.1ms  max=95.26ms
      { expected_response:true }...: avg=2.82ms med=2.69ms p(95)=3.69ms p(99)=5.11ms max=95.26ms
    http_req_failed................: 0.59%  596 out of 101009
    http_reqs......................: 101009 252.546158/s

    EXECUTION
    iteration_duration.............: avg=10.38s med=10.18s p(95)=14.74s p(99)=23.57s max=44.98s 
    iterations.....................: 100605 251.536064/s
    vus............................: 3      min=3             max=3000
    vus_max........................: 3000   min=3000          max=3000

    NETWORK
    data_received..................: 13 MB  32 kB/s
    data_sent......................: 27 MB  67 kB/s




running (6m40.0s), 0000/3000 VUs, 100605 complete and 427 interrupted iterations
users ✓ [======================================] 0000/3000 VUs  6m30s