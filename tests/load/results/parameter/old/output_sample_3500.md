█ THRESHOLDS 

    http_req_duration
    ✓ 'p(95)<500' p(95)=3.91ms
    ✓ 'p(99)<1000' p(99)=6.45ms

    http_req_failed
    ✓ 'rate<0.01' rate=0.45%


  █ TOTAL RESULTS 

    checks_total.......: 119174 297.971229/s
    checks_succeeded...: 99.54% 118635 out of 119174
    checks_failed......: 0.45%  539 out of 119174

    ✗ POST status 200
      ↳  99% — ✓ 118635 / ✗ 539

    HTTP
    http_req_duration..............: avg=2.91ms med=2.71ms p(95)=3.91ms p(99)=6.45ms max=93.2ms
      { expected_response:true }...: avg=2.92ms med=2.71ms p(95)=3.92ms p(99)=6.47ms max=93.2ms
    http_req_failed................: 0.45%  539 out of 119174
    http_reqs......................: 119174 297.971229/s

    EXECUTION
    iteration_duration.............: avg=10.27s med=10.13s p(95)=14.66s p(99)=17.92s max=44.99s
    iterations.....................: 118740 296.886097/s
    vus............................: 4      min=4             max=3500
    vus_max........................: 3500   min=3500          max=3500

    NETWORK
    data_received..................: 15 MB  38 kB/s
    data_sent......................: 32 MB  80 kB/s




running (6m40.0s), 0000/3500 VUs, 118740 complete and 440 interrupted iterations
users ✓ [======================================] 0000/3500 VUs  6m30s