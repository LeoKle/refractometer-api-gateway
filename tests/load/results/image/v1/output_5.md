█ THRESHOLDS 

    http_req_duration
    ✗ 'p(95)<500' p(95)=18.97s
    ✗ 'p(99)<1000' p(99)=1m4s

    http_req_failed
    ✗ 'rate<0.01' rate=43.05%


  █ TOTAL RESULTS 

    checks_total.......: 72     0.17245/s
    checks_succeeded...: 56.94% 41 out of 72
    checks_failed......: 43.05% 31 out of 72

    ✗ status 201
      ↳  56% — ✓ 41 / ✗ 31

    HTTP
    http_req_duration..............: avg=9.21s  med=8.52s  p(95)=18.97s p(99)=1m4s   max=1m4s  
      { expected_response:true }...: avg=13.05s med=13.93s p(95)=18.87s p(99)=19.74s max=20.17s
    http_req_failed................: 43.05% 31 out of 72
    http_reqs......................: 72     0.17245/s

    EXECUTION
    iteration_duration.............: avg=24.76s med=21.28s p(95)=1m6s   p(99)=1m12s  max=1m13s 
    iterations.....................: 70     0.16766/s
    vus............................: 1      min=1        max=5
    vus_max........................: 5      min=5        max=5

    NETWORK
    data_received..................: 9.5 kB 23 B/s
    data_sent......................: 2.1 GB 5.0 MB/s




running (6m57.5s), 0/5 VUs, 70 complete and 2 interrupted iterations
users ✓ [======================================] 0/5 VUs  6m30s
ERRO[0394] thresholds on metrics 'http_req_duration, http_req_failed' have been crossed 

Last State:     Terminated
      Reason:       OOMKilled
      Exit Code:    137
      Started:      Thu, 29 Oct 2026 18:25:04 +0100
      Finished:     Thu, 29 Oct 2026 18:33:57 +0100
    Ready:          True