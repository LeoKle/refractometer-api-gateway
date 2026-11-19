 █ THRESHOLDS 

    http_req_duration
    ✓ 'p(95)<500' p(95)=6.97ms
    ✓ 'p(99)<1000' p(99)=56.06ms

    http_req_failed
    ✗ 'rate<0.01' rate=1.55%


  █ TOTAL RESULTS 

    checks_total.......: 131857 329.686809/s
    checks_succeeded...: 98.44% 129811 out of 131857
    checks_failed......: 1.55%  2046 out of 131857

    ✗ POST status 200
      ↳  98% — ✓ 129811 / ✗ 2046

    HTTP
    http_req_duration..............: avg=4.38ms med=2.74ms p(95)=6.97ms p(99)=56.06ms max=236.32ms
      { expected_response:true }...: avg=4.45ms med=2.75ms p(95)=7.17ms p(99)=56.56ms max=236.32ms
    http_req_failed................: 1.55%  2046 out of 131857
    http_reqs......................: 131857 329.686809/s

    EXECUTION
    iteration_duration.............: avg=10.6s  med=10.17s p(95)=14.77s p(99)=38.34s  max=45s     
    iterations.....................: 131281 328.246616/s
    vus............................: 1      min=1              max=4000
    vus_max........................: 4000   min=4000           max=4000

    NETWORK
    data_received..................: 17 MB  42 kB/s
    data_sent......................: 35 MB  87 kB/s




running (6m39.9s), 0000/4000 VUs, 131281 complete and 648 interrupted iterations
users ✓ [======================================] 0000/4000 VUs  6m30s
ERRO[0400] thresholds on metrics 'http_req_failed' have been crossed 