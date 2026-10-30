█ THRESHOLDS 

    http_req_duration
    ✗ 'p(95)<500' p(95)=14.38s
    ✗ 'p(99)<1000' p(99)=16.89s

    http_req_failed
    ✓ 'rate<0.01' rate=0.00%


  █ TOTAL RESULTS 

    checks_total.......: 185     0.432139/s
    checks_succeeded...: 100.00% 185 out of 185
    checks_failed......: 0.00%   0 out of 185

    ✓ status 201

    HTTP
    http_req_duration..............: avg=9.54s  med=9.62s  p(95)=14.38s p(99)=16.89s max=17.24s
      { expected_response:true }...: avg=9.54s  med=9.62s  p(95)=14.38s p(99)=16.89s max=17.24s
    http_req_failed................: 0.00%  0 out of 185
    http_reqs......................: 185    0.432139/s

    EXECUTION
    iteration_duration.............: avg=19.24s med=19.25s p(95)=25.55s p(99)=27.26s max=28.25s
    iterations.....................: 181    0.422795/s
    vus............................: 1      min=1        max=10
    vus_max........................: 10     min=10       max=10

    NETWORK
    data_received..................: 43 kB  100 B/s
    data_sent......................: 4.6 GB 11 MB/s




running (7m08.1s), 00/10 VUs, 181 complete and 4 interrupted iterations
users ✓ [======================================] 01/10 VUs  6m30s
ERRO[0400] thresholds on metrics 'http_req_duration' have been crossed 