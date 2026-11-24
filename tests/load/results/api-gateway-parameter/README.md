Load Test with API Gateway and Parameter Service:
Replica: 1
CPU-Limit: 1
Memory-Limit: 1Gi

4750: FAIL: Get \"http://192.168.178.240:30080/api/spectrum/bf47cfe9-27f0-4d5e-837e-a1cb352c7cd6\": dial tcp 192.168.178.240:30080: connect: connection refused"

2000: FAIL: connect: connection refused - CPU at limit

NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-7d98bc6db4-d5bz8         997m         584Mi
mongo-parameter-0                    45m          125Mi
parameter-service-5f6cdc8674-x47sl   112m         238Mi
postgres-gateway-0                   89m          113Mi
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1325m        8%       4165Mi          13%

1000: FAIL

500: FAIL

NAME                                 CPU(cores)   MEMORY(bytes)
api-gateway-9f8df7984-kvf84          999m         487Mi
mongo-parameter-0                    30m          117Mi
parameter-service-66d8799964-6zkck   115m         238Mi
postgres-gateway-0                   36m          96Mi
redis-gateway-0                      2m           36Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1331m        8%       3924Mi          12%