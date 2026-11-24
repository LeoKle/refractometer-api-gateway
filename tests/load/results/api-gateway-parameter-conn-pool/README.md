Load Test with API Gateway and Parameter Service:
Replica: 1
CPU-Limit: 1
Memory-Limit: 1Gi

with a httpx2 connection pool

---

500: PASS

```
NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-59f5cb454-k5q94          257m         94Mi
mongo-parameter-0                    33m          112Mi
parameter-service-58d8b74d98-fcb7r   113m         231Mi
postgres-gateway-0                   32m          71Mi
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   561m         3%       3545Mi          11%
```
---

1000: PASS
```
NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-696f67b65d-wvkfr         520m         396Mi
mongo-parameter-0                    55m          113Mi
parameter-service-8476cfb5d6-v7fxl   222m         237Mi
postgres-gateway-0                   53m          85Mi
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   943m         5%       3856Mi          12%
```
---
2000: FAIL: thresholds on metrics 'http_req_duration' have been crossed 

```
NAME                                CPU(cores)   MEMORY(bytes)
api-gateway-696f67b65d-wvkfr        998m         466Mi 
mongo-parameter-0                   75m          114Mi
parameter-service-dc797cc7d-wsmzt   357m         239Mi
postgres-gateway-0                  156m         103Mi
redis-gateway-0                     2m           36Mi 

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1741m        10%      3935Mi          12%
```
---

1500: PASS

```
NAME                               CPU(cores)   MEMORY(bytes)
api-gateway-7db697bddd-r42w6       816m         409Mi  
mongo-parameter-0                  87m          127Mi
parameter-service-cfb58bc5-c99z7   328m         238Mi
postgres-gateway-0                 73m          96Mi  
redis-gateway-0                    2m           36Mi  

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1384m        8%       3911Mi          12%
```

---

1750: FAIL: thresholds on metrics 'http_req_duration' have been crossed 

```
NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-5f6b65b78c-skc9n         1000m        449Mi
mongo-parameter-0                    85m          125Mi
parameter-service-57566ccdfb-b5xq4   366m         239Mi
postgres-gateway-0                   132m         101Mi
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1681m        10%      3933Mi          12%
```