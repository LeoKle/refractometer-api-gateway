█ THRESHOLDS 

    http_req_duration
    ✓ 'p(95)<500' p(95)=3.96ms
    ✓ 'p(99)<1000' p(99)=7.26ms

    http_req_failed
    ✓ 'rate<0.01' rate=0.58%


  █ TOTAL RESULTS 

    checks_total.......: 123136 307.837964/s
    checks_succeeded...: 99.41% 122415 out of 123136
    checks_failed......: 0.58%  721 out of 123136

    ✗ POST status 200
      ↳  99% — ✓ 122415 / ✗ 721

    HTTP
    http_req_duration..............: avg=2.93ms med=2.71ms p(95)=3.96ms p(99)=7.26ms max=108.04ms
      { expected_response:true }...: avg=2.95ms med=2.72ms p(95)=3.97ms p(99)=7.28ms max=108.04ms
    http_req_failed................: 0.58%  721 out of 123136
    http_reqs......................: 123136 307.837964/s

    EXECUTION
    iteration_duration.............: avg=10.29s med=10.09s p(95)=14.67s p(99)=18.93s max=44.99s  
    iterations.....................: 122638 306.592972/s
    vus............................: 4      min=4             max=3625
    vus_max........................: 3625   min=3625          max=3625

    NETWORK
    data_received..................: 16 MB  39 kB/s
    data_sent......................: 33 MB  82 kB/s




running (6m40.0s), 0000/3625 VUs, 122638 complete and 540 interrupted iterations
users ✓ [======================================] 0000/3625 VUs  6m30s