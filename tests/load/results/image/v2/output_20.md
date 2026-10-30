█ THRESHOLDS 

    http_req_duration
    ✗ 'p(95)<500' p(95)=33.46s
    ✗ 'p(99)<1000' p(99)=35.27s

    http_req_failed
    ✓ 'rate<0.01' rate=0.00%


  █ TOTAL RESULTS 

    checks_total.......: 190     0.442958/s
    checks_succeeded...: 100.00% 190 out of 190
    checks_failed......: 0.00%   0 out of 190

    ✓ status 201

    HTTP
    http_req_duration..............: avg=27.65s med=30.31s p(95)=33.46s p(99)=35.27s max=35.42s
      { expected_response:true }...: avg=27.65s med=30.31s p(95)=33.46s p(99)=35.27s max=35.42s
    http_req_failed................: 0.00%  0 out of 190
    http_reqs......................: 190    0.442958/s

    EXECUTION
    iteration_duration.............: avg=36.75s med=38.35s p(95)=44.53s p(99)=46.42s max=46.77s
    iterations.....................: 181    0.421975/s
    vus............................: 1      min=1        max=20
    vus_max........................: 20     min=20       max=20

    NETWORK
    data_received..................: 44 kB  102 B/s
    data_sent......................: 4.9 GB 11 MB/s




running (7m08.9s), 00/20 VUs, 181 complete and 19 interrupted iterations
users ✓ [======================================] 00/20 VUs  6m30s
ERRO[0398] thresholds on metrics 'http_req_duration' have been crossed