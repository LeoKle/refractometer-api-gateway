█ THRESHOLDS 

    http_req_duration
    ✓ 'p(95)<500' p(95)=3.39ms
    ✓ 'p(99)<1000' p(99)=4.17ms

    http_req_failed
    ✓ 'rate<0.01' rate=0.00%


  █ TOTAL RESULTS 

    checks_total.......: 69547   173.977645/s
    checks_succeeded...: 100.00% 69547 out of 69547
    checks_failed......: 0.00%   0 out of 69547

    ✓ POST status 200

    HTTP
    http_req_duration..............: avg=2.75ms med=2.68ms p(95)=3.39ms p(99)=4.17ms max=80.45ms
      { expected_response:true }...: avg=2.75ms med=2.68ms p(95)=3.39ms p(99)=4.17ms max=80.45ms
    http_req_failed................: 0.00%  0 out of 69547
    http_reqs......................: 69547  173.977645/s

    EXECUTION
    iteration_duration.............: avg=10.06s med=10.03s p(95)=14.57s p(99)=14.96s max=22.05s 
    iterations.....................: 69313  173.392274/s
    vus............................: 8      min=8          max=2000
    vus_max........................: 2000   min=2000       max=2000

    NETWORK
    data_received..................: 8.9 MB 22 kB/s
    data_sent......................: 19 MB  47 kB/s




running (6m39.7s), 0000/2000 VUs, 69313 complete and 234 interrupted iterations
users ✓ [======================================] 0000/2000 VUs  6m30s