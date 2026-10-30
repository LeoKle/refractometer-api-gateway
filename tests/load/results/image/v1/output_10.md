█ THRESHOLDS 

    http_req_duration
    ✗ 'p(95)<500' p(95)=19.09s
    ✗ 'p(99)<1000' p(99)=1m3s

    http_req_failed
    ✗ 'rate<0.01' rate=66.15%


  █ TOTAL RESULTS 

    checks_total.......: 65     0.152858/s
    checks_succeeded...: 33.84% 22 out of 65
    checks_failed......: 66.15% 43 out of 65

    ✗ status 201
      ↳  33% — ✓ 22 / ✗ 43

    HTTP
    http_req_duration..............: avg=6.79s  med=0s     p(95)=19.09s p(99)=1m3s   max=1m3s  
      { expected_response:true }...: avg=11.05s med=10.11s p(95)=17.79s p(99)=18.93s max=19.21s
    http_req_failed................: 66.15% 43 out of 65
    http_reqs......................: 65     0.152858/s

    EXECUTION
    iteration_duration.............: avg=27.89s med=19.67s p(95)=1m10s  p(99)=1m13s  max=1m14s 
    iterations.....................: 62     0.145803/s
    vus............................: 1      min=1        max=5
    vus_max........................: 5      min=5        max=5

    NETWORK
    data_received..................: 5.1 kB 12 B/s
    data_sent......................: 1.4 GB 3.3 MB/s




running (7m05.2s), 0/5 VUs, 62 complete and 3 interrupted iterations
users ✓ [======================================] 0/5 VUs  6m30s
ERRO[0400] thresholds on metrics 'http_req_duration, http_req_failed' have been crossed

Last State:     Terminated
      Reason:       OOMKilled
      Exit Code:    137
      Started:      Thu, 29 Oct 2026 18:15:20 +0100
      Finished:     Thu, 29 Oct 2026 18:20:05 +0100
    Ready:          True