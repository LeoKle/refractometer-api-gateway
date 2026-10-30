█ THRESHOLDS 

    http_req_duration
    ✗ 'p(95)<500' p(95)=10.18s
    ✗ 'p(99)<1000' p(99)=11.41s

    http_req_failed
    ✓ 'rate<0.01' rate=0.00%


  █ TOTAL RESULTS 

    checks_total.......: 44      0.103409/s
    checks_succeeded...: 100.00% 44 out of 44
    checks_failed......: 0.00%   0 out of 44

    ✓ status 201

    HTTP
    http_req_duration..............: avg=6.95s  med=6.05s  p(95)=10.18s p(99)=11.41s max=12.17s
      { expected_response:true }...: avg=6.95s  med=6.05s  p(95)=10.18s p(99)=11.41s max=12.17s
    http_req_failed................: 0.00%  0 out of 44
    http_reqs......................: 44     0.103409/s

    EXECUTION
    iteration_duration.............: avg=16.49s med=16.71s p(95)=20.89s p(99)=24.45s max=25.12s
    iterations.....................: 43     0.101059/s
    vus............................: 1      min=1       max=2
    vus_max........................: 2      min=2       max=2

    NETWORK
    data_received..................: 10 kB  24 B/s
    data_sent......................: 2.1 GB 5.0 MB/s




running (7m05.5s), 0/2 VUs, 43 complete and 1 interrupted iterations
users ✓ [======================================] 0/2 VUs  6m30s
ERRO[0400] thresholds on metrics 'http_req_duration' have been crossed 